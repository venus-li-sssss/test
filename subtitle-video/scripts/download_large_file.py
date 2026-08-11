#!/usr/bin/env python3
"""
飞书云盘大文件分块下载器

问题：lark-cli drive +download 对 >100MB 的文件会失败（响应体大小限制）。
方案：通过 MITM 代理截获 lark-cli 的认证 headers，然后用 HTTP Range 请求分块下载。

流程：
  1. 启动本地 MITM 代理（自签 CA + 动态证书）
  2. 让 lark-cli 走代理发一个简单 API 请求，截获 auth headers
  3. 用截获的 headers 向 aily 网关发 HTTP Range 请求，10MB 一块下载
  4. 支持断点续传（检查已有文件大小，从断点继续）
  5. 下载完成后用 ffprobe 校验文件完整性

用法：
  python3 download_large_file.py <file_token> <output_path> [--as user|bot]
  python3 download_large_file.py PBc1b7zksoNJvDxnWF9crC0An7g ./video.mp4
  python3 download_large_file.py PBc1b7zksoNJvDxnWF9crC0An7g ./video.mp4 --as user

  # 也可直接用飞书文件 URL：
  python3 download_large_file.py "https://quectel.feishu.cn/file/PBc1b7zksoNJvDxnWF9crC0An7g" ./video.mp4
"""
import argparse
import http.client
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

# === MITM 代理基础设施 ===

CA_KEY_PATH = "/tmp/feishu_dl_ca_key.pem"
CA_CERT_PATH = "/tmp/feishu_dl_ca_cert.pem"
CERT_BUNDLE_PATH = "/tmp/feishu_dl_cert_bundle.pem"
HEADERS_OUTPUT = "/tmp/feishu_dl_headers.json"
PROXY_PORT = 19876
GATEWAY_HOST = "aily.feishu.cn"

_cert_cache = {}


def _generate_ca():
    """生成自签 CA 证书（每次运行重新生成，不持久化）"""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Feishu DL CA")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow() - timedelta(days=1))
        .not_valid_after(datetime.utcnow() + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    with open(CA_KEY_PATH, "wb") as f:
        f.write(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ))
    with open(CA_CERT_PATH, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    # 合并系统 CA + 我们的 CA，让 lark-cli 信任我们的代理证书
    system_certs = subprocess.check_output(["cat", "/etc/ssl/certs/ca-certificates.crt"]).decode()
    with open(CERT_BUNDLE_PATH, "w") as f:
        f.write(system_certs)
        f.write(open(CA_CERT_PATH).read())


def _get_cert_for_host(hostname):
    """为指定 hostname 生成由我们的 CA 签发的证书"""
    if hostname in _cert_cache:
        return _cert_cache[hostname]

    ca_key = serialization.load_pem_private_key(open(CA_KEY_PATH, "rb").read(), password=None)
    ca_cert = x509.load_pem_x509_certificate(open(CA_CERT_PATH, "rb").read())

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)]))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow() - timedelta(days=1))
        .not_valid_after(datetime.utcnow() + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )

    cert_path = f"/tmp/feishu_dl_{hostname}_cert.pem"
    key_path = f"/tmp/feishu_dl_{hostname}_key.pem"
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(key_path, "wb") as f:
        f.write(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ))
    _cert_cache[hostname] = (cert_path, key_path)
    return cert_path, key_path


class MITMHandler(BaseHTTPRequestHandler):
    """MITM 代理处理器：截获发往 aily.feishu.cn 的请求头"""

    def do_CONNECT(self):
        host, port = self.path.split(":")
        port = int(port)

        if host != GATEWAY_HOST:
            # 非目标 host，直接隧道转发
            self._tunnel(host, port)
            return

        self.send_response(200, "Connection Established")
        self.end_headers()

        cert_path, key_path = _get_cert_for_host(host)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_path, key_path)

        try:
            ssl_socket = context.wrap_socket(self.connection, server_side=True)
        except Exception:
            return

        try:
            # 读取完整 HTTP 请求头
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = ssl_socket.recv(4096)
                if not chunk:
                    return
                data += chunk

            header_part, body_start = data.split(b"\r\n\r\n", 1)
            request_text = header_part.decode("utf-8", errors="replace")
            lines = request_text.split("\r\n")
            request_line = lines[0]
            method, path, _ = request_line.split(" ", 2)

            # 解析 headers
            headers = {}
            for line in lines[1:]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    headers[k.strip()] = v.strip()

            # 保存截获的 headers（只需要第一次请求的）
            if not os.path.exists(HEADERS_OUTPUT):
                with open(HEADERS_OUTPUT, "w") as f:
                    json.dump({"method": method, "path": path, "headers": headers}, f, indent=2)

            # 读取请求 body（如果有）
            body = body_start
            if "Content-Length" in headers:
                cl = int(headers["Content-Length"])
                while len(body) < cl:
                    chunk = ssl_socket.recv(4096)
                    if not chunk:
                        break
                    body += chunk

            # 转发到真实服务器
            real_conn = http.client.HTTPSConnection(host, port, timeout=60)
            real_conn.request(method, path, body=body if body else None, headers=headers)
            real_resp = real_conn.getresponse()
            resp_body = real_resp.read()

            response = f"HTTP/1.1 {real_resp.status} {real_resp.reason}\r\n"
            for k, v in real_resp.getheaders():
                response += f"{k}: {v}\r\n"
            response += "\r\n"
            ssl_socket.sendall(response.encode("utf-8") + resp_body)
            real_conn.close()

        except Exception as e:
            print(f"  [MITM] 错误: {e}", file=sys.stderr)
        finally:
            try:
                ssl_socket.close()
            except Exception:
                pass

    def _tunnel(self, host, port):
        try:
            remote = socket.create_connection((host, port), timeout=30)
            self.send_response(200, "Connection Established")
            self.end_headers()

            def fwd(src, dst):
                try:
                    while True:
                        d = src.recv(4096)
                        if not d:
                            break
                        dst.sendall(d)
                except Exception:
                    pass
                finally:
                    try:
                        src.close()
                    except Exception:
                        pass

            t1 = threading.Thread(target=fwd, args=(self.connection, remote))
            t2 = threading.Thread(target=fwd, args=(remote, self.connection))
            t1.start()
            t2.start()
            t1.join()
            t2.join()
        except Exception:
            pass

    def log_message(self, format, *args):
        pass


def capture_auth_headers(as_user="user"):
    """启动 MITM 代理，让 lark-cli 走代理发一个轻量请求来截获 auth headers"""
    _generate_ca()

    # 清理旧的 headers 文件
    if os.path.exists(HEADERS_OUTPUT):
        os.remove(HEADERS_OUTPUT)

    server = HTTPServer(("127.0.0.1", PROXY_PORT), MITMHandler)
    proxy_thread = threading.Thread(target=server.serve_forever, daemon=True)
    proxy_thread.start()
    time.sleep(0.5)

    # 让 lark-cli 走代理发一个轻量 API 请求
    env = os.environ.copy()
    env["SSL_CERT_FILE"] = CERT_BUNDLE_PATH
    env["HTTPS_PROXY"] = f"http://127.0.0.1:{PROXY_PORT}"
    env["HTTP_PROXY"] = f"http://127.0.0.1:{PROXY_PORT}"
    env["NO_PROXY"] = "localhost,127.0.0.1"
    env["no_proxy"] = "localhost,127.0.0.1"

    result = subprocess.run(
        ["lark-cli", "api", "GET", "/open-apis/authen/v1/user_info", "--as", as_user],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    server.shutdown()

    if not os.path.exists(HEADERS_OUTPUT):
        print(f"  [错误] 未能截获 auth headers", file=sys.stderr)
        if result.stderr:
            print(f"  lark-cli stderr: {result.stderr[:300]}", file=sys.stderr)
        return None

    with open(HEADERS_OUTPUT) as f:
        captured = json.load(f)

    print(f"  已截获 auth headers（{len(captured['headers'])} 个字段）")
    return captured["headers"]


def download_with_range(file_token, output_path, headers, chunk_size=10 * 1024 * 1024):
    """用 HTTP Range 请求分块下载文件，支持断点续传"""
    download_path = f"/play/api/v2/cli/lark_openapi_proxy/open-apis/drive/v1/files/{file_token}/download"

    dl_headers = headers.copy()
    dl_headers.pop("Content-Type", None)
    dl_headers.pop("Content-Length", None)
    dl_headers["Accept-Encoding"] = "identity"

    # Step 1: HEAD 请求检查 Range 支持并获取文件大小
    conn = http.client.HTTPSConnection(GATEWAY_HOST, 443, timeout=30)
    conn.request("HEAD", download_path, headers=dl_headers)
    resp = conn.getresponse()
    head_status = resp.status
    head_headers = dict(resp.getheaders())
    resp.read()
    conn.close()

    # 从 HEAD 或首次 Range 请求获取文件总大小
    total_size = None
    if head_status == 200:
        cl = head_headers.get("Content-Length") or head_headers.get("content-length")
        if cl:
            total_size = int(cl)

    if total_size is None:
        # 用 Range 请求试一块来获取 Content-Range
        range_headers = dl_headers.copy()
        range_headers["Range"] = "bytes=0-1048575"
        conn = http.client.HTTPSConnection(GATEWAY_HOST, 443, timeout=30)
        conn.request("GET", download_path, headers=range_headers)
        resp = conn.getresponse()
        content_range = resp.getheader("Content-Range")
        resp.read()
        conn.close()

        if content_range:
            total_size = int(content_range.split("/")[-1])
        elif resp.status == 200:
            # 服务器不支持 Range，需要一次性下载
            print(f"  服务器不支持 Range 请求，尝试一次性下载...")
            return _download_full(download_path, output_path, dl_headers)

    if total_size is None:
        print(f"  [错误] 无法获取文件大小", file=sys.stderr)
        return False

    print(f"  文件大小: {total_size / 1024 / 1024:.1f} MB")

    # Step 2: 检查断点续传
    existing_size = 0
    if os.path.exists(output_path):
        existing_size = os.path.getsize(output_path)
        if existing_size >= total_size:
            print(f"  文件已存在且大小匹配，跳过下载")
            return True
        print(f"  断点续传: 从 {existing_size / 1024 / 1024:.1f} MB 继续")

    # Step 3: 分块下载
    downloaded = existing_size
    mode = "ab" if existing_size > 0 else "wb"

    with open(output_path, mode) as f:
        while downloaded < total_size:
            end = min(downloaded + chunk_size - 1, total_size - 1)
            range_headers = dl_headers.copy()
            range_headers["Range"] = f"bytes={downloaded}-{end}"

            retry_count = 0
            while retry_count < 3:
                try:
                    conn = http.client.HTTPSConnection(GATEWAY_HOST, 443, timeout=120)
                    conn.request("GET", download_path, headers=range_headers)
                    resp = conn.getresponse()

                    if resp.status not in (206, 200):
                        body = resp.read()
                        print(f"\n  [错误] 下载失败 at byte {downloaded}: {resp.status} - {body[:200]}", file=sys.stderr)
                        conn.close()
                        return False

                    chunk = resp.read()
                    f.write(chunk)
                    downloaded += len(chunk)
                    conn.close()
                    break
                except Exception as e:
                    retry_count += 1
                    if retry_count >= 3:
                        print(f"\n  [错误] 下载失败 at byte {downloaded}: {e}", file=sys.stderr)
                        return False
                    print(f"\n  重试 {retry_count}/3...", file=sys.stderr)
                    time.sleep(2)
                    # 重新截获 headers（token 可能过期）
                    if retry_count == 2:
                        new_headers = capture_auth_headers()
                        if new_headers:
                            dl_headers = new_headers.copy()
                            dl_headers.pop("Content-Type", None)
                            dl_headers.pop("Content-Length", None)
                            dl_headers["Accept-Encoding"] = "identity"

            pct = downloaded / total_size * 100
            print(f"\r  下载: {downloaded / 1024 / 1024:.1f} / {total_size / 1024 / 1024:.1f} MB ({pct:.0f}%)", end="", flush=True)

    print(f"\n  下载完成: {downloaded} bytes")
    return downloaded == total_size


def _download_full(download_path, output_path, headers):
    """不支持 Range 时的一次性流式下载"""
    conn = http.client.HTTPSConnection(GATEWAY_HOST, 443, timeout=300)
    conn.request("GET", download_path, headers=headers)
    resp = conn.getresponse()

    if resp.status != 200:
        body = resp.read()
        print(f"  [错误] 下载失败: {resp.status} - {body[:200]}", file=sys.stderr)
        conn.close()
        return False

    total = 0
    with open(output_path, "wb") as f:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            total += len(chunk)
            print(f"\r  下载: {total / 1024 / 1024:.1f} MB", end="", flush=True)

    conn.close()
    print(f"\n  下载完成: {total} bytes")
    return True


def verify_file(file_path):
    """用 ffprobe 校验文件完整性"""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_format", file_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return False


def extract_token(input_arg):
    """从 file_token 或飞书 URL 中提取 token"""
    # URL 格式: https://xxx.feishu.cn/file/TOKEN 或 https://xxx.feishu.cn/drive/folder/TOKEN
    m = re.search(r"/file/([A-Za-z0-9]+)", input_arg)
    if m:
        return m.group(1)
    # 纯 token
    if re.match(r"^[A-Za-z0-9]+$", input_arg):
        return input_arg
    print(f"  [错误] 无法从输入中提取 file_token: {input_arg}", file=sys.stderr)
    return None


def main():
    parser = argparse.ArgumentParser(
        description="飞书云盘大文件分块下载器（解决 lark-cli >100MB 限制）"
    )
    parser.add_argument("file_token_or_url", help="飞书文件 file_token 或文件 URL")
    parser.add_argument("output_path", help="输出文件路径（相对路径）")
    parser.add_argument("--as", dest="as_user", default="user", choices=["user", "bot"],
                        help="lark-cli 身份 (默认: user)")
    parser.add_argument("--chunk-size", type=int, default=10,
                        help="分块大小 MB (默认: 10)")
    parser.add_argument("--no-verify", action="store_true",
                        help="跳过 ffprobe 完整性校验")
    args = parser.parse_args()

    file_token = extract_token(args.file_token_or_url)
    if not file_token:
        sys.exit(1)

    print(f"=== 飞书云盘大文件下载 ===")
    print(f"  file_token: {file_token}")
    print(f"  输出路径: {args.output_path}")

    # 磁盘空间检查
    if os.path.exists(args.output_path):
        existing_size = os.path.getsize(args.output_path)
    else:
        existing_size = 0

    # Step 1: 截获 auth headers
    print(f"\n[Step 1] 截获认证 headers...")
    headers = capture_auth_headers(args.as_user)
    if not headers:
        print("  [错误] 无法截获认证 headers", file=sys.stderr)
        sys.exit(1)

    # Step 2: 分块下载
    print(f"\n[Step 2] 分块下载（{args.chunk_size}MB/块）...")
    chunk_bytes = args.chunk_size * 1024 * 1024
    success = download_with_range(file_token, args.output_path, headers, chunk_bytes)

    if not success:
        print(f"\n下载失败！", file=sys.stderr)
        sys.exit(1)

    # Step 3: 校验
    if not args.no_verify:
        print(f"\n[Step 3] 校验文件完整性...")
        if verify_file(args.output_path):
            print(f"  ✓ 文件校验通过")
        else:
            print(f"  ⚠️ ffprobe 校验未通过（文件可能不是音视频，或文件损坏）", file=sys.stderr)
            print(f"  文件大小: {os.path.getsize(args.output_path) / 1024 / 1024:.1f} MB")

    print(f"\n完成！文件已保存到: {args.output_path}")
    print(f"大小: {os.path.getsize(args.output_path) / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
