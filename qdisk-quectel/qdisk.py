#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
移远网盘 (Quectel Netdisk) 下载工具
====================================

通过 qdisk.quectel.com 的 REST 接口，把网盘内容下载到本地指定目录。

认证方式（无需手动处理 RSA 加密）:
  - 刷新令牌 (refresh_token) 模式：最耐用。首次用浏览器登录后，从 DevTools 的
    Cookie `quectel_refresh_token` 取值，执行 `auth --refresh-token <RT>` 即可。
    之后脚本会自动用 refresh_token 换取 access_token，并缓存到 .token_cache.json。
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

SSO_BASE = "https://sso-web.quectel.com"
QDISK_BASE = "https://qdisk.quectel.com"
CLIENT_ID = "quectel"
CLIENT_SECRET = "quectel"
DEVICESN = "bcd6de4cea58f2261fab3ee5ddb95320"

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(SKILL_DIR, ".token_cache.json")
TOKEN_EXPIRY_BUFFER = 300  # 提前 5 分钟刷新


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


def refresh_access_token(refresh_token):
    """用 refresh_token 换取新的 access_token。返回解析后的 JSON。"""
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
        sys.stderr.write("刷新令牌失败 HTTP %s: %s\n" % (e.code, e.read().decode("utf-8", "replace")[:400]))
        sys.exit(1)


def get_token():
    """返回可用的 access_token（自动刷新并缓存）。"""
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
    if not rt:
        sys.stderr.write(
            "未找到可用令牌。请先认证：\n"
            "  python qdisk.py auth --refresh-token <RT>\n"
            "  （RT 取自浏览器 DevTools 的 Cookie quectel_refresh_token）\n"
        )
        sys.exit(2)

    data = refresh_access_token(rt)
    at = data.get("access_token")
    if not at:
        sys.stderr.write("刷新失败，响应中无 access_token: %s\n" % json.dumps(data, ensure_ascii=False)[:300])
        sys.exit(1)
    new_rt = data.get("refresh_token", rt)
    exp = now + 86400
    ei = data.get("expires_in")
    if isinstance(ei, str):
        try:
            exp = datetime.datetime.strptime(ei, "%Y-%m-%d %H:%M:%S").timestamp()
        except Exception:
            pass
    elif isinstance(ei, int):
        exp = now + ei
    save_cache({"access_token": at, "refresh_token": new_rt, "access_token_exp": exp})
    return at


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
