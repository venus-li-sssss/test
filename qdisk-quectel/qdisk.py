#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
移远网盘 (Quectel Netdisk) 下载工具
====================================

通过 qdisk.quectel.com 的 REST 接口，把网盘内容下载到本地指定目录。

认证方式（无需手动处理 RSA 加密）:
  - 账号密码模式（推荐，一次输入长期可用）：`auth --set-cred` 交互输入一次账号密码，
    用 Windows DPAPI 加密存到 .cred.dpapi.json（仅本机当前 Windows 用户可解密）。
    之后令牌过期时脚本会自动用账号密码重新登录，无需任何人工操作。
  - 刷新令牌 (refresh_token) 模式：首次用浏览器登录后，从 DevTools 的
    Cookie `quectel_refresh_token` 取值，执行 `auth --refresh-token <RT>` 即可。
    之后脚本会自动用 refresh_token 换取 access_token，并缓存到 .token_cache.json。
    该令牌过期后会回退到上面的账号密码模式（若已保存）。
  - 直接令牌 (access_token) 模式：从 Cookie `quectel_token`（去掉 "bearer" 前缀）取值，
    执行 `auth --token <TOKEN>`。

依赖：仅 Python 标准库（urllib / json / argparse / os / time）。

常见用法:
  python qdisk.py auth --refresh-token xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
  python qdisk.py ls --path "部门文件/IKOTEK/Project"
  python qdisk.py download --path "部门文件/IKOTEK/Project/ODM Project Files/SWE/external/MOB/QDM559/STM32G0B0/app" --output D:/qdisk/app
  python qdisk.py download --path "部门文件/IKOTEK/Project" --output D:/qdisk --recursive
  python qdisk.py download --path "部门文件/IKOTEK/Project" --output D:/qdisk --only "QDM559_STM32G0B0_APP"
"""

import argparse
import json
import os
import sys
import time
import datetime
import urllib.request
import urllib.error
import urllib.parse
import base64
import getpass
import hashlib
import secrets
import string

SSO_BASE = "https://sso-web.quectel.com"
QDISK_BASE = "https://qdisk.quectel.com"
CLIENT_ID = "quectel"
CLIENT_SECRET = "quectel"
DEVICESN = "bcd6de4cea58f2261fab3ee5ddb95320"

# RSA 公钥（从 SSO 登录页面 JS 中提取）
RSA_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAre5YnMJtO+gtwkeeq07f
5UfywHM2LQ5T4jzVzYUYJOQN0AUAYkmoIt7rIfAN6q5nEby3zupXznBo/Y5SsRtX
DoG53xHucpqE5SXD4J6kNnxj+JjecQ7ef0ev5MTOb+eREybymosgs7xr/eprv2O4
GmipUwXVTWusbL/xjPzfP603JGz/r6xR94k5K8NXqHLQVBKURa5QK3x9sUyX5ZxY
op6llF3BdkIafB8aERw5iJa7i8fFK6UmIbhGQ8rLYYGj61229NayMgIuWJ3SGmUW
Wq0RyCEjt96I6ZWwOqygkiEXj3PoQEmTUIxmEgrWQ5UxSHT/XDai5sbj7IueMqnc
PQIDAQAB
-----END PUBLIC KEY-----"""

import subprocess
import tempfile


def _pem_to_rsa_numbers(pem):
    """从 SubjectPublicKeyInfo PEM 中取出 (n, e)。纯标准库 DER 解析。"""
    b64 = "".join(l.strip() for l in pem.strip().splitlines() if "-" not in l)
    der = base64.b64decode(b64)

    def read_len(buf, i):
        ln = buf[i]
        i += 1
        if ln & 0x80:
            cnt = ln & 0x7F
            ln = int.from_bytes(buf[i:i + cnt], "big")
            i += cnt
        return ln, i

    def read_tlv(buf, i):
        tag = buf[i]
        ln, i = read_len(buf, i + 1)
        return tag, buf[i:i + ln], i + ln

    tag, body, _ = read_tlv(der, 0)              # 外层 SEQUENCE
    tag, alg, i = read_tlv(body, 0)              # AlgorithmIdentifier
    tag, bits, i = read_tlv(body, i)             # BIT STRING
    inner = bits[1:]                             # 去掉 unused-bits 字节
    tag, seq, _ = read_tlv(inner, 0)             # RSAPublicKey SEQUENCE
    tag, n_bytes, i = read_tlv(seq, 0)
    tag, e_bytes, i = read_tlv(seq, i)
    n = int.from_bytes(n_bytes, "big")
    e = int.from_bytes(e_bytes, "big")
    if not n or not e:
        raise RuntimeError("RSA 公钥解析失败")
    return n, e


def rsa_encrypt_password(password):
    """RSA PKCS#1 v1.5 加密密码，返回 base64 结果（纯 Python 实现，不依赖 openssl）。"""
    n, e = _pem_to_rsa_numbers(RSA_PUBLIC_KEY_PEM)
    msg = password.encode("utf-8")
    k = (n.bit_length() + 7) // 8
    if len(msg) > k - 11:
        raise RuntimeError("密码过长，超出 RSA 可加密长度")
    ps = b"\xff" * (k - len(msg) - 3)
    em = b"\x00\x01" + ps + b"\x00" + msg
    c = pow(int.from_bytes(em, "big"), e, n)
    return base64.b64encode(c.to_bytes(k, "big")).decode("ascii")


def password_login(username, password):
    """使用账号密码登录，返回 (access_token, refresh_token)。"""
    encrypted_pwd = rsa_encrypt_password(password)
    body = urllib.parse.urlencode({
        "grant_type": "password",
        "username": username,
        "password": encrypted_pwd,
        "scope": "ui",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "auth_type": "rsa_area",
    }).encode()
    req = urllib.request.Request(
        SSO_BASE + "/api/uaa/oauth/token",
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "terminal": "web",
            "devicesn": DEVICESN,
            "origin": SSO_BASE,
            "referer": SSO_BASE + "/login",
            "User-Agent": "Mozilla/5.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
            at = data.get("access_token")
            rt = data.get("refresh_token")
            if not at:
                raise RuntimeError(f"登录失败: {json.dumps(data, ensure_ascii=False)[:300]}")
            return at, rt
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"登录失败 HTTP {e.code}: {body}")


SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(SKILL_DIR, ".token_cache.json")
CRED_FILE = os.path.join(SKILL_DIR, ".cred.dpapi.json")
CRED_ENTROPY = b"qdisk-quectel-cred-v1"
TOKEN_EXPIRY_BUFFER = 300  # 提前 5 分钟刷新


# --------------------------------------------------------------------------
# 本地凭据（Windows DPAPI 加密，非明文）
# --------------------------------------------------------------------------
def _dpapi_transform(data, protect):
    """调用 Windows DPAPI 加/解密字节串。仅当前 Windows 用户 + 本机可解。"""
    if not sys.platform.startswith("win"):
        raise RuntimeError("DPAPI 仅在 Windows 上可用")
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    ent_buf = ctypes.create_string_buffer(CRED_ENTROPY, len(CRED_ENTROPY))
    blob_ent = DATA_BLOB(len(CRED_ENTROPY), ctypes.cast(ent_buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()

    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(blob_in), None, ctypes.byref(blob_ent),
            None, None, 0, ctypes.byref(blob_out))
    if not ok:
        raise RuntimeError("DPAPI 调用失败，错误码 %s" % kernel32.GetLastError())
    try:
        out = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)
    return out


def save_cred(username, password):
    payload = json.dumps({"username": username, "password": password},
                         ensure_ascii=False).encode("utf-8")
    enc = base64.b64encode(_dpapi_transform(payload, True)).decode("ascii")
    tmp = CRED_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"v": 1, "enc": enc, "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}, f)
    os.replace(tmp, CRED_FILE)
    try:
        os.chmod(CRED_FILE, 0o600)
    except Exception:
        pass


def load_cred():
    if not os.path.exists(CRED_FILE):
        return None
    try:
        with open(CRED_FILE, "r", encoding="utf-8") as f:
            rec = json.load(f)
        raw = _dpapi_transform(base64.b64decode(rec["enc"]), False)
        obj = json.loads(raw.decode("utf-8"))
        if obj.get("username") and obj.get("password"):
            return obj
    except Exception as e:
        sys.stderr.write("读取本地凭据失败（需重新 auth --set-cred）: %s\n" % e)
    return None


def clear_cred():
    if os.path.exists(CRED_FILE):
        os.remove(CRED_FILE)
        return True
    return False



# --------------------------------------------------------------------------
# 令牌管理
# --------------------------------------------------------------------------
def load_cache():
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_cache(c):
    tmp = TOKEN_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f)
    os.replace(tmp, TOKEN_FILE)


def refresh_access_token(refresh_token, fatal=True):
    """用 refresh_token 换取新的 access_token。返回解析后的 JSON；失败且 fatal=False 时返回 None。"""
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }).encode()
    req = urllib.request.Request(
        SSO_BASE + "/api/uaa/oauth/token",
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "terminal": "web",
            "devicesn": DEVICESN,
            "origin": SSO_BASE,
            "referer": SSO_BASE + "/login",
            "User-Agent": "Mozilla/5.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        msg = "刷新令牌失败 HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:400])
        if fatal:
            sys.stderr.write(msg + "\n")
            sys.exit(1)
        sys.stderr.write(msg + "\n")
        return None


def _expiry_from(expires_in, now):
    exp = now + 86400
    if isinstance(expires_in, str):
        try:
            exp = datetime.datetime.strptime(expires_in, "%Y-%m-%d %H:%M:%S").timestamp()
        except Exception:
            pass
    elif isinstance(expires_in, int):
        exp = now + expires_in
    return exp


def do_password_login(username=None, password=None):
    """用账号密码登录并缓存令牌。未传账号密码时读取本地 DPAPI 凭据。"""
    if not username or not password:
        cred = load_cred()
        if not cred:
            raise RuntimeError("本地没有保存账号密码，请先执行: python qdisk.py auth --set-cred")
        username = username or cred["username"]
        password = password or cred["password"]
    at, rt = password_login(username, password)
    exp = time.time() + 86400
    save_cache({"access_token": at, "refresh_token": rt, "access_token_exp": exp,
                "account": username})
    return at


def get_token():
    """返回可用的 access_token（自动刷新；refresh_token 失效时用本地账号密码自动重登）。"""
    env_rt = os.environ.get("QUECTEL_REFRESH_TOKEN")
    env_tk = os.environ.get("QUECTEL_TOKEN")
    cache = load_cache()
    now = time.time()

    if env_tk:
        return env_tk

    at = cache.get("access_token")
    exp = cache.get("access_token_exp")
    if at and exp and now < exp - TOKEN_EXPIRY_BUFFER:
        return at

    rt = env_rt or cache.get("refresh_token")
    if rt:
        data = refresh_access_token(rt, fatal=False)
        at = (data or {}).get("access_token")
        if at:
            new_rt = data.get("refresh_token", rt)
            save_cache({"access_token": at, "refresh_token": new_rt,
                        "access_token_exp": _expiry_from(data.get("expires_in"), now)})
            return at

    # refresh_token 不可用（过期/缺失）：回退到本地保存的账号密码自动登录
    try:
        sys.stderr.write("refresh_token 已失效，尝试用本地保存的账号密码自动登录...\n")
        return do_password_login()
    except Exception as e:
        sys.stderr.write(
            "未找到可用令牌，且自动登录失败：%s\n"
            "请先认证（二选一）：\n"
            "  python qdisk.py auth --set-cred        # 输入一次账号密码，长期有效（推荐）\n"
            "  python qdisk.py auth --refresh-token <RT>   # RT 取自浏览器 Cookie quectel_refresh_token\n" % e
        )
        sys.exit(2)


# --------------------------------------------------------------------------
# 网盘 API
# --------------------------------------------------------------------------
def _headers(token):
    return {
        "Authorization": "bearer" + token,
        "Content-Type": "application/json",
        "quectel-version": "mxz",
        "hiddenmsg": "false",
        "loading": "false",
        "origin": QDISK_BASE,
        "referer": QDISK_BASE + "/company/list?lang=zh-CN",
        "User-Agent": "Mozilla/5.0",
    }


def api(method, path, token, body=None):
    url = QDISK_BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=_headers(token), method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.stderr.write("HTTP %s %s: %s\n" % (e.code, url, e.read().decode("utf-8", "replace")[:500]))
        sys.exit(1)


def resolve_folder(path, token):
    """路径 -> (folderId, spaceId, spaceType)。path 形如 '部门文件/IKOTEK/...'。"""
    j = api("POST", "/api/disk/v1/file/qry/queryFolderIdByPath", token, {"path": path})
    if not j.get("success") or not j.get("data"):
        sys.stderr.write("路径解析失败: %s\n%s\n" % (path, json.dumps(j, ensure_ascii=False)[:300]))
        sys.exit(1)
    fid = j["data"]
    d = api("GET", "/api/disk/v1/file/qry/deatil/%s" % fid, token)
    dd = d["data"]
    return fid, dd["spaceId"], dd["spaceType"]


def list_folder(folder_id, space_id, space_type, token, page_size=200):
    items = []
    n = 1
    while True:
        body = {
            "spaceId": space_id,
            "fileId": folder_id,
            "pageNumber": n,
            "pageSize": page_size,
            "validSpaceTypes": ["COMPANY", "DEPARTMENT", "PERSON", "PROJECT"],
        }
        j = api("POST", "/api/disk/v1/file/qry/file/page", token, body)
        recs = j.get("data", {}).get("records", [])
        items.extend(recs)
        total = j.get("data", {}).get("total", 0)
        if not recs or len(items) >= total:
            break
        n += 1
    return items


def sign_url(rec, token):
    """返回文件的预签名下载地址。"""
    body = {
        "bucket": "disk",
        "dataAction": "DOWNLOAD",
        "id": rec["fileId"],
        "name": rec["fileName"],
        "key": rec.get("fileKey"),
        "fileType": "FILE",
        "fileId": rec["fileId"],
        "folderId": rec["folderId"],
        "fileName": rec["fileName"],
        "spaceId": rec["spaceId"],
        "spaceType": rec["spaceType"],
        "fileKey": rec.get("fileKey"),
    }
    j = api("POST", "/api/disk/v1/sign", token, body)
    return j["data"]["url"]


# --------------------------------------------------------------------------
# 下载
# --------------------------------------------------------------------------
def sanitize(name):
    """Windows / 通用文件名安全化。"""
    bad = '\\/:*?"<>|\t\n\r'
    s = "".join("_" if c in bad else c for c in name).strip().strip(".")
    return s or "untitled"


def download_file(url, out_path, token=None):
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Referer": QDISK_BASE + "/", "Origin": QDISK_BASE},
    )
    n = 0
    with urllib.request.urlopen(req, timeout=120) as r, open(out_path, "wb") as f:
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            f.write(chunk)
            n += len(chunk)
    return n


def safe_extract(zip_path, dest_dir):
    """解压 zip 到 dest_dir，并防御 zip slip 路径穿越。"""
    import zipfile
    os.makedirs(dest_dir, exist_ok=True)
    abs_dest = os.path.abspath(dest_dir)
    with zipfile.ZipFile(zip_path) as z:
        for member in z.namelist():
            target = os.path.abspath(os.path.join(dest_dir, member))
            if target != abs_dest and not target.startswith(abs_dest + os.sep):
                raise Exception("非法 zip 成员路径，已拒绝: %s" % member)
        z.extractall(dest_dir)
    return dest_dir


def match_filter(rec, only):
    if not only:
        return True
    name = rec.get("fileName", "")
    return only in name


def download_folder(folder_id, space_id, space_type, token, out_dir, recursive, only, extract, depth=0):
    items = list_folder(folder_id, space_id, space_type, token)
    count = 0
    for rec in items:
        ftype = rec.get("fileType")
        name = rec.get("fileName", "")
        if ftype == "FOLDER":
            if not recursive:
                continue
            sub_dir = os.path.join(out_dir, sanitize(name))
            cnt = download_folder(
                rec["fileId"], rec.get("spaceId", space_id), rec.get("spaceType", space_type),
                token, sub_dir, recursive, only, extract, depth + 1,
            )
            count += cnt
        elif ftype == "FILE":
            if not match_filter(rec, only):
                continue
            key = rec.get("fileKey")
            if not key:
                sys.stderr.write("  跳过(无 fileKey): %s\n" % name)
                continue
            url = sign_url(rec, token)
            out_path = os.path.join(out_dir, sanitize(name))
            try:
                size = download_file(url, out_path, token)
                print("  %s %s  (%d bytes)" % ("  " * depth, name, size))
                count += 1
                if extract and name.lower().endswith(".zip"):
                    ex_dir = os.path.join(out_dir, sanitize(name)[:-4])
                    safe_extract(out_path, ex_dir)
                    print("  %s解压 -> %s" % ("  " * depth, ex_dir))
            except Exception as e:
                sys.stderr.write("  下载失败 %s: %s\n" % (name, e))
        else:
            sys.stderr.write("  未知类型 %s: %s\n" % (ftype, name))
    return count


# --------------------------------------------------------------------------
# 命令行
# --------------------------------------------------------------------------
def cmd_auth(args):
    cache = load_cache()

    if getattr(args, "status", False):
        cred = load_cred()
        print("本地凭据文件: %s  (%s)" % (CRED_FILE, "存在" if os.path.exists(CRED_FILE) else "不存在"))
        print("保存的账号: %s" % (cred["username"] if cred else "无"))
        at = cache.get("access_token")
        exp = cache.get("access_token_exp")
        if at:
            print("access_token: %s***  (%s)" % (
                at[:10],
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(exp)) if exp else "过期时间未知"))
        else:
            print("access_token: 无")
        rt = cache.get("refresh_token")
        print("refresh_token: %s" % ("已缓存（%s***）" % rt[:8] if rt else "无"))
        return

    if getattr(args, "clear_cred", False):
        print("已清除本地凭据。" if clear_cred() else "本地没有凭据文件。")
        return

    if getattr(args, "set_cred", False):
        username = args.username
        password = args.password
        try:
            if not username:
                username = input("账号: ").strip()
            if not password:
                password = getpass.getpass("密码: ")
        except (EOFError, KeyboardInterrupt):
            sys.stderr.write("当前环境不支持交互输入，请用 --username/--password 直接传参。\n")
            sys.exit(2)
        if not username or not password:
            sys.stderr.write("账号或密码为空，已取消。\n")
            sys.exit(2)
        save_cred(username, password)
        print("凭据已用 Windows DPAPI 加密保存（仅本机当前用户可解密）：%s" % CRED_FILE)
        try:
            do_password_login(username, password)
            print("登录成功，access_token 已缓存。之后令牌过期会自动用该凭据重登。")
        except Exception as e:
            sys.stderr.write("凭据已保存，但登录失败：%s\n" % e)
            sys.exit(1)
        return

    if getattr(args, "login", False):
        try:
            at = do_password_login(args.username, args.password)
        except Exception as e:
            sys.stderr.write("账号密码登录失败：%s\n" % e)
            sys.exit(1)
        print("登录成功（access_token %s***），令牌已缓存。后续将自动续期/自动重登。" % at[:10])
        return

    if args.token:
        save_cache({
            "access_token": args.token,
            "refresh_token": cache.get("refresh_token"),
            "access_token_exp": time.time() + 86400,
        })
        print("已缓存 access_token（有效期约 24h，到期将尝试用 refresh_token 刷新）。")
        return
    if args.refresh_token:
        data = refresh_access_token(args.refresh_token)
        at = data.get("access_token")
        if not at:
            sys.stderr.write("获取 access_token 失败: %s\n" % json.dumps(data, ensure_ascii=False)[:300])
            sys.exit(1)
        new_rt = data.get("refresh_token", args.refresh_token)
        exp = time.time() + 86400
        ei = data.get("expires_in")
        if isinstance(ei, str):
            try:
                exp = datetime.datetime.strptime(ei, "%Y-%m-%d %H:%M:%S").timestamp()
            except Exception:
                pass
        elif isinstance(ei, int):
            exp = time.time() + ei
        save_cache({"access_token": at, "refresh_token": new_rt, "access_token_exp": exp})
        print("认证成功。access_token 已缓存，refresh_token 也已保存，后续将自动续期。")
        return
    # 无参数：尝试用缓存刷新
    rt = cache.get("refresh_token")
    if not rt:
        sys.stderr.write("用法: python qdisk.py auth --refresh-token <RT> | --token <TOKEN>\n")
        sys.exit(2)
    data = refresh_access_token(rt)
    at = data.get("access_token")
    new_rt = data.get("refresh_token", rt)
    exp = time.time() + 86400
    ei = data.get("expires_in")
    if isinstance(ei, str):
        try:
            exp = datetime.datetime.strptime(ei, "%Y-%m-%d %H:%M:%S").timestamp()
        except Exception:
            pass
    elif isinstance(ei, int):
        exp = time.time() + ei
    save_cache({"access_token": at, "refresh_token": new_rt, "access_token_exp": exp})
    print("已用缓存的 refresh_token 刷新 access_token。")


def cmd_ls(args):
    token = get_token()
    if args.folder_id:
        fid, sid, stype = args.folder_id, args.space_id, args.space_type or "COMPANY"
        if not args.space_id:
            d = api("GET", "/api/disk/v1/file/qry/deatil/%s" % fid, token)
            sid = d["data"]["spaceId"]
            stype = d["data"]["spaceType"]
    else:
        fid, sid, stype = resolve_folder(args.path, token)
    items = list_folder(fid, sid, stype, token)
    print("路径: %s   空间: %s   共 %d 项" % (args.path or args.folder_id, stype, len(items)))
    for rec in items:
        tag = "[" + rec.get("fileType", "?") + "]"
        size = rec.get("fileSizeStr") or ""
        print("  %-7s %s   %s" % (tag, rec.get("fileName", ""), size))


def cmd_tree(args):
    token = get_token()
    if args.folder_id:
        fid, sid, stype = args.folder_id, args.space_id, args.space_type or "COMPANY"
    else:
        fid, sid, stype = resolve_folder(args.path, token)

    def walk(fid, sid, stype, prefix):
        items = list_folder(fid, sid, stype, token)
        for rec in items:
            if rec.get("fileType") == "FOLDER":
                print("%s[DIR] %s" % (prefix, rec.get("fileName", "")))
                walk(rec["fileId"], rec.get("spaceId", sid), rec.get("spaceType", stype), prefix + "  ")
            else:
                print("%s      %s   %s" % (prefix, rec.get("fileName", ""), rec.get("fileSizeStr") or ""))

    print("[ROOT] %s" % (args.path or args.folder_id))
    walk(fid, sid, stype, "  ")


def cmd_download(args):
    token = get_token()
    if args.folder_id:
        fid, sid, stype = args.folder_id, args.space_id, args.space_type or "COMPANY"
    else:
        fid, sid, stype = resolve_folder(args.path, token)
    # 顶层输出目录：
    #   默认以末级路径名建子目录，避免文件散落；
    #   加 --flat 则直接落到 --output，不再套一层子目录。
    if args.flat:
        out_dir = args.output
    else:
        leaf = args.path.rstrip("/").split("/")[-1] if args.path else (args.folder_id or "qdisk")
        out_dir = os.path.join(args.output, sanitize(leaf))
    os.makedirs(out_dir, exist_ok=True)
    print("下载到: %s  (递归=%s 过滤=%s 扁平=%s 解压=%s)" % (
        out_dir, args.recursive, args.only or "*", args.flat, args.extract))
    total = download_folder(fid, sid, stype, token, out_dir, args.recursive, args.only, args.extract)
    print("完成，共下载 %d 个文件。" % total)


def build_parser():
    p = argparse.ArgumentParser(description="移远网盘 (Quectel Netdisk) 下载工具")
    sub = p.add_subparsers(dest="cmd")

    a = sub.add_parser("auth", help="认证并缓存令牌")
    g = a.add_mutually_exclusive_group(required=False)
    g.add_argument("--refresh-token", help="刷新令牌 (Cookie quectel_refresh_token)")
    g.add_argument("--token", help="直接提供 access_token (Cookie quectel_token 去掉 bearer 前缀)")
    g.add_argument("--set-cred", action="store_true",
                   help="交互输入一次账号密码，DPAPI 加密保存到本地（推荐，长期免登录）")
    g.add_argument("--login", action="store_true",
                   help="用本地保存的账号密码（或 --username/--password）立即登录一次")
    g.add_argument("--clear-cred", action="store_true", help="清除本地保存的账号密码")
    g.add_argument("--status", action="store_true", help="查看本地凭据与令牌状态")
    a.add_argument("--username", help="配合 --set-cred / --login：账号（如 venus.li@ikotek.com）")
    a.add_argument("--password", help="配合 --set-cred / --login：密码（不建议写在命令行里，交互输入更安全）")
    a.set_defaults(func=cmd_auth)

    l = sub.add_parser("ls", help="列出目录内容")
    l.add_argument("--path", help="网盘路径，如 '部门文件/IKOTEK/Project'")
    l.add_argument("--folder-id", help="直接指定 folderId")
    l.add_argument("--space-id", help="与 --folder-id 配合：空间 ID")
    l.add_argument("--space-type", help="与 --folder-id 配合：COMPANY/DEPARTMENT/PERSON/PROJECT")
    l.set_defaults(func=cmd_ls)

    t = sub.add_parser("tree", help="以树形展示目录结构")
    t.add_argument("--path", help="网盘路径")
    t.add_argument("--folder-id", help="直接指定 folderId")
    t.add_argument("--space-id", help="空间 ID")
    t.add_argument("--space-type", help="空间类型")
    t.set_defaults(func=cmd_tree)

    d = sub.add_parser("download", help="下载目录 / 文件到本地")
    d.add_argument("--path", help="网盘路径")
    d.add_argument("--folder-id", help="直接指定 folderId")
    d.add_argument("--space-id", help="空间 ID")
    d.add_argument("--space-type", help="空间类型")
    d.add_argument("--output", "-o", required=True, help="本地输出目录")
    d.add_argument("--recursive", "-r", action="store_true", help="递归下载子目录")
    d.add_argument("--only", help="仅下载文件名包含该子串的文件")
    d.add_argument("--flat", action="store_true",
                   help="扁平输出：直接下载到 --output，不再套用末级路径名作为子目录")
    d.add_argument("--extract", action="store_true",
                   help="下载后自动解压 .zip（解压到与 zip 同名的子目录，防路径穿越）")
    d.set_defaults(func=cmd_download)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
