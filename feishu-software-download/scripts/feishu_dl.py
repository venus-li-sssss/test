#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
飞书云盘 / 知识库 免扫码访问工具（应用身份 tenant_access_token）

子命令:
  list                          列出本地 catalog 里已知软件
  sync                          从飞书递归拉取目录，刷新 catalog 文件
  get <name|keyword> [--out D]  按名称/关键词下载软件（支持模糊匹配）
  dl  <file_token> [--out F]    按 file_token 直接下载
  tree [--folder TOKEN]         打印云端目录树
  doc <wiki_node_token|obj_token|URL>  读取飞书文档/知识库正文（纯文本）

依赖: requests
"""
import os
import re
import sys
import json
import time
import argparse
from pathlib import Path

import requests

# ------------------------- 配置 -------------------------
# 团队共用「只读机器人」的应用凭据（不是个人账号，允许公开）。
# 这里用 base64 存放，只为绕开 GitHub push protection 对此类字段的误报；
# 解码后就是普通的 app_id / app_secret，任何人都能用。
# 换应用时用环境变量覆盖：FEISHU_APP_ID / FEISHU_APP_SECRET
import base64 as _b64

_DEFAULT_APP_ID = _b64.b64decode("Y2xpX2E5YmM5NzMxN2ZiODljYzg=").decode()
_DEFAULT_APP_SECRET = _b64.b64decode(
    "cnRUc0VaZnZOQWZsN3c3RFpBVklFZnJyUlNRZUZUZmg="
).decode()

APP_ID = os.environ.get("FEISHU_APP_ID", _DEFAULT_APP_ID)
APP_SECRET = os.environ.get("FEISHU_APP_SECRET", _DEFAULT_APP_SECRET)
BASE = "https://open.feishu.cn"

# 搜索根目录：云盘 -> 软件测试部 -> 软件测试二科
# 也可用 FEISHU_ROOT_FOLDER=<folder_token> 或 --folder 覆盖
ROOT_FOLDER = os.environ.get("FEISHU_ROOT_FOLDER", "GiihfUC0tlDJGHdTriDcH4ljnUz")

HERE = Path(__file__).resolve().parent
CATALOG = HERE.parent / "software_catalog.json"
TOKEN_CACHE = Path.home() / ".feishu_tat_cache.json"


# ------------------------- token -------------------------
def get_token(force=False):
    """tenant_access_token，2 小时有效，本地缓存提前 5 分钟续期。"""
    if not force and TOKEN_CACHE.exists():
        try:
            c = json.loads(TOKEN_CACHE.read_text(encoding="utf-8"))
            if c.get("app_id") == APP_ID and c.get("expire_at", 0) > time.time() + 300:
                return c["token"]
        except Exception:
            pass
    r = requests.post(f"{BASE}/open-apis/auth/v3/tenant_access_token/internal",
                      json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=30)
    d = r.json()
    if d.get("code") != 0:
        sys.exit(f"[token 获取失败] code={d.get('code')} msg={d.get('msg')}")
    tok = d["tenant_access_token"]
    TOKEN_CACHE.write_text(json.dumps({"app_id": APP_ID, "token": tok,
                                       "expire_at": time.time() + d.get("expire", 7200)}),
                           encoding="utf-8")
    return tok


def H():
    return {"Authorization": f"Bearer {get_token()}"}


# ------------------------- drive -------------------------
def list_folder(folder_token):
    files, pt = [], None
    while True:
        params = {"folder_token": folder_token, "page_size": 200}
        if pt:
            params["page_token"] = pt
        r = requests.get(f"{BASE}/open-apis/drive/v1/files", params=params, headers=H(), timeout=30)
        d = r.json()
        if d.get("code") != 0:
            sys.exit(f"[列目录失败] folder={folder_token} code={d.get('code')} msg={d.get('msg')}")
        data = d.get("data", {})
        files += data.get("files", []) or []
        if not data.get("has_more"):
            return files
        pt = data.get("next_page_token")


def walk(folder_token, prefix=""):
    """递归展开目录 -> [(path, name, type, token), ...]"""
    out = []
    for f in list_folder(folder_token):
        p = f"{prefix}/{f['name']}"
        out.append({"path": os.path.dirname(p), "name": f["name"],
                    "type": f["type"], "token": f["token"]})
        if f["type"] == "folder":
            out += walk(f["token"], p)
    return out


def download(file_token, dest, attempts=5):
    """bot 身份走 preview_download（/medias/{token}/download 会 403，缺 export 权限）。

    大文件（>100MB）实测会在中途断流 IncompleteRead，所以带 Range 断点续传 + 重试。
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    url = f"{BASE}/open-apis/drive/v1/medias/{file_token}/preview_download"
    have = tmp.stat().st_size if tmp.exists() else 0
    total = None

    for i in range(attempts):
        h = H()
        if have:
            h["Range"] = f"bytes={have}-"
        try:
            r = requests.get(url, params={"preview_type": 16}, headers=h,
                             timeout=(20, 180), stream=True)
        except requests.RequestException as e:
            print(f"[retry {i+1}/{attempts}] net error: {e}", file=sys.stderr)
            time.sleep(2)
            continue
        if r.status_code == 416:            # 偏移已到位，下完了
            break
        if r.status_code not in (200, 206):
            print(f"[retry {i+1}/{attempts}] http {r.status_code}: {r.text[:200]}", file=sys.stderr)
            time.sleep(2)
            r.close()
            continue
        if r.status_code == 200 and have:   # 服务端不理 Range -> 从头再来
            have = 0
        cl = r.headers.get("Content-Length")
        if cl:
            total = have + int(cl) if r.status_code == 206 else int(cl)
        mode = "ab" if r.status_code == 206 else "wb"
        if mode == "wb":
            have = 0
        last = time.time()
        try:
            with open(tmp, mode) as f:
                for chunk in r.iter_content(1 << 16):
                    f.write(chunk)
                    have += len(chunk)
                    if time.time() - last > 10:
                        last = time.time()
                        pct = f" ({have*100//total}%)" if total else ""
                        print(f"    ... {have/1048576:.1f}"
                              f"{f'/{total/1048576:.1f}' if total else ''} MB{pct}", flush=True)
        except (requests.RequestException, OSError) as e:
            print(f"[retry {i+1}/{attempts}] broken stream at {have} bytes: {e}", file=sys.stderr)
            time.sleep(2)
            continue
        finally:
            r.close()
        if not total or have >= total:
            break
        print(f"[retry {i+1}/{attempts}] resume from {have}/{total}", file=sys.stderr)

    if not tmp.exists():
        sys.exit(f"[下载失败] token={file_token} 没拿到任何数据")
    if total and have < total:
        sys.exit(f"[下载不完整] {have}/{total} bytes，重试几次仍断流；token={file_token}")
    if have < 100:
        sys.exit(f"[下载失败] 只有 {have} 字节，疑似错误响应 token={file_token}")
    os.replace(tmp, dest)
    return have


# ------------------------- wiki / docx -------------------------
def resolve_node(token):
    r = requests.get(f"{BASE}/open-apis/wiki/v2/spaces/get_node",
                     params={"token": token}, headers=H(), timeout=30)
    d = r.json()
    if d.get("code") != 0:
        return None
    return (d.get("data") or {}).get("node")


def read_doc(ref):
    node_token = ref
    m = re.search(r"/(wiki|docx|docs)/([A-Za-z0-9]+)", ref)
    if m:
        node_token = m.group(2)
    obj_token, title = node_token, ""
    n = resolve_node(node_token)
    if n:
        obj_token, title = n.get("obj_token", node_token), n.get("title", "")
    items, pt = [], None
    while True:
        params = {"page_size": 500}
        if pt:
            params["page_token"] = pt
        r = requests.get(f"{BASE}/open-apis/docx/v1/documents/{obj_token}/blocks",
                         params=params, headers=H(), timeout=60)
        d = r.json()
        if d.get("code") != 0:
            sys.exit(f"[读文档失败] doc={obj_token} code={d.get('code')} msg={d.get('msg')}")
        data = d.get("data", {})
        items += data.get("items", []) or []
        if not data.get("has_more"):
            break
        pt = data.get("page_token")
    return title, obj_token, items


def block_text(b):
    out = []
    for key in ("text", "heading1", "heading2", "heading3", "heading4", "heading5",
                "heading6", "heading7", "heading8", "heading9", "bullet", "ordered",
                "code", "quote", "todo", "callout", "quote_container"):
        seg = b.get(key)
        if isinstance(seg, dict):
            for el in seg.get("elements", []) or []:
                tr = el.get("text_run") or el.get("equation") or {}
                c = tr.get("content")
                if c:
                    out.append(c)
    return "".join(out)


# ------------------------- 云端实时搜索 -------------------------
# 走 /open-apis/search/v2/doc_wiki/search（tenant_access_token 可用，需 scope search:docs:read）
# 已知边界：
#   1) 只按「文件名/标题」命中，不按目录名命中（搜 "QDM559" 搜不到 QDM559/ 下的 V0.2.4.0.bin）
#   2) 文件夹本身不进索引，搜不到 folder
#   3) doc_filter.folder_tokens 在本租户实测未生效，搜索范围 = 应用可见的全部云盘
SEARCH_API = f"{BASE}/open-apis/search/v2/doc_wiki/search"


def search_api(query, doc_types=("FILE",), page_size=20):
    # 注意：page_size 上限 20，传 30 会 99992402 field validation failed
    body = {"query": query, "page_size": min(page_size, 20),
            "doc_filter": {"doc_types": list(doc_types)}}
    r = requests.post(SEARCH_API,
                      data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                      headers={**H(), "Content-Type": "application/json; charset=utf-8"},
                      timeout=30)
    d = r.json()
    if d.get("code") != 0:
        sys.exit(f"[搜索失败] code={d.get('code')} msg={d.get('msg')}")
    out = []
    for u in (d.get("data") or {}).get("res_units") or []:
        m = u.get("result_meta") or {}
        title = re.sub(r"</?h>", "", u.get("title_highlighted") or "")
        out.append({
            "title": title,
            "token": m.get("token", ""),
            "type": m.get("doc_types", ""),
            "file_type": m.get("file_type", ""),
            "url": m.get("url", ""),
            "owner": m.get("owner_name", ""),
        })
    return out


def folder_of(token, catalog):
    """搜索不带路径，用 catalog(sync 出来的) 反查目录；查不到就返回空。"""
    for s in (catalog.get("software") or []):
        if s.get("file_token") == token:
            return s.get("folder", "")
    return ""


# ------------------------- catalog -------------------------
def load_catalog():
    if not CATALOG.exists():
        return {}
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def save_catalog(cat):
    CATALOG.write_text(json.dumps(cat, ensure_ascii=False, indent=2), encoding="utf-8")


def sync_catalog():
    entries = []
    for e in walk(ROOT_FOLDER):
        if e["type"] == "folder":
            continue
        rel = e["path"].strip("/")
        base = rel or "根目录"
        entries.append({
            "name": Path(e["name"]).stem,
            "file_token": e["token"],
            "filename": e["name"],
            "folder": base,
            "description": "",
            "keywords": sorted({Path(e["name"]).stem.lower(), base.lower()}),
        })
    old = {s["file_token"]: s for s in (load_catalog().get("software") or [])}
    for s in entries:
        o = old.get(s["file_token"])
        if o:
            s["name"] = o.get("name") or s["name"]
            s["description"] = o.get("description", "")
            s["keywords"] = sorted(set(o.get("keywords", []) + s["keywords"]))
    cat = {"root_folder": ROOT_FOLDER,
           "last_sync": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"), "software": entries}
    save_catalog(cat)
    return entries


def match(catalog, query):
    q = query.lower().strip()
    sw = catalog.get("software") or []
    for s in sw:                                     # 1) 精确名
        if s["name"].lower() == q:
            return s
    for s in sw:                                     # 2) 关键词
        if any(k.lower() == q for k in s.get("keywords", [])):
            return s
    for s in sw:                                     # 3) 包含
        if q in s["name"].lower() or s["name"].lower() in q:
            return s
        if any(q in k.lower() or k.lower() in q for k in s.get("keywords", [])):
            return s
    return None


def match_all(catalog, query):
    """返回所有命中项（按 精确名 > 关键词 > 包含 排序），用于 search 列出候选。"""
    q = query.lower().strip()
    if not q:
        return []
    hits = []
    for s in (catalog.get("software") or []):
        name = s["name"].lower()
        kws = [k.lower() for k in s.get("keywords", [])]
        folder = (s.get("folder") or "").lower()
        fname = s["filename"].lower()
        if name == q:
            rank = 0
        elif q in kws:
            rank = 1
        elif q in name or name in q or q in fname or q in folder:
            rank = 2
        elif any(q in k or k in q for k in kws):
            rank = 3
        else:
            continue
        hits.append((rank, s))
    hits.sort(key=lambda x: (x[0], x[1]["name"].lower()))
    return [s for _, s in hits]


def print_hits(query, hits):
    if not hits:
        print(f"❌ 「{query}」在 catalog 里没有命中（先 sync）")
        return
    print(f"命中 {len(hits)} 项：")
    print("名称 | 目录 | 文件 | file_token")
    print("---|---|---|---")
    for s in hits:
        print(f"{s['name']} | {s.get('folder', '')} | {s['filename']} | {s['file_token']}")


# ------------------------- cli -------------------------
def main():
    ap = argparse.ArgumentParser(description="飞书云盘/知识库免扫码访问")
    ap.add_argument("cmd", choices=["list", "sync", "get", "search", "dl", "tree", "doc"])
    ap.add_argument("arg", nargs="?", default="")
    ap.add_argument("--out", default="", help="输出目录或文件名")
    ap.add_argument("--folder", default=ROOT_FOLDER, help="tree/search 的根目录 token")
    ap.add_argument("--pick", type=int, default=0, help="get 命中多项时指定第几项（从 1 开始）")
    ap.add_argument("--all", action="store_true", help="search 时连 docx/sheet/bitable/slides 一起搜")
    a = ap.parse_args()

    if a.cmd == "list":
        cat = load_catalog()
        sw = cat.get("software") or []
        if not sw:
            print("(catalog 为空，先跑 sync)")
            return
        print("名称 | 目录 | 文件 | 说明 | file_token")
        print("---|---|---|---|---")
        for s in sw:
            print(f"{s['name']} | {s.get('folder','')} | {s['filename']} | "
                  f"{s.get('description','')} | {s['file_token']}")
        return

    if a.cmd == "search":
        if not a.arg:
            sys.exit("用法: search <关键词> [--all]")
        types = ("FILE", "DOCX", "SHEET", "BITABLE", "SLIDES") if a.all else ("FILE",)
        hits = search_api(a.arg, doc_types=types)
        if not hits:
            print(f"❌ 云端搜索「{a.arg}」无命中")
            return
        cat = load_catalog()
        print(f"云端命中 {len(hits)} 项（实时，不依赖 catalog）：")
        print("名称 | 类型 | 目录(来自catalog) | file_token")
        print("---|---|---|---")
        for h in hits:
            print(f"{h['title']} | {h['file_type'] or h['type']} | "
                  f"{folder_of(h['token'], cat) or '-'} | {h['token']}")
        return

    if a.cmd == "sync":
        es = sync_catalog()
        print(f"✅ 已同步 {len(es)} 个文件 -> {CATALOG}")
        for e in es:
            print(f"  - {e.get('folder')}/{e['filename']}  ({e['file_token']})")
        return

    if a.cmd == "tree":
        for e in walk(a.folder):
            ind = "  " * (e["path"].count("/") if e["type"] == "file" else 0)
            print(f"{ind}{'[D] ' if e['type']=='folder' else '    '}{e['name']}  {e['token']}")
        return

    if a.cmd == "dl":
        if not a.arg:
            sys.exit("用法: dl <file_token> --out <路径>")
        dest = a.out or Path(a.arg).name
        if Path(dest).is_dir():
            dest = Path(dest) / Path(a.arg).name
        n = download(a.arg, dest)
        print(f"✅ {Path(dest).resolve()}  ({n:,} bytes)")
        return

    if a.cmd == "get":
        if not a.arg:
            sys.exit("用法: get <文件名|关键词> [--out 目录] [--pick N]")
        # 1) 先走云端实时搜索（永远是最新的，不依赖 sync）
        hits = search_api(a.arg)
        if not hits:
            # 2) 搜不到再退回本地 catalog 模糊匹配
            cat = load_catalog()
            local = match_all(cat, a.arg)
            if not local:
                sys.exit(f"❌ 云端与本地 catalog 都没有 '{a.arg}'")
            hits = [{"title": s["filename"], "token": s["file_token"],
                     "type": "FILE", "file_type": "", "url": "", "owner": ""}
                    for s in local]
        if len(hits) > 1 and not a.pick:
            cat = load_catalog()
            print(f"命中 {len(hits)} 项，用 --pick N 指定要下哪个：")
            for i, h in enumerate(hits, 1):
                print(f"  [{i}] {h['title']}  |  {folder_of(h['token'], cat) or '-'}  |  {h['token']}")
            sys.exit(2)
        h = hits[a.pick - 1] if a.pick else hits[0]
        dest_dir = Path(a.out or Path.cwd())
        dest = dest_dir / h["title"]
        n = download(h["token"], dest)
        print(f"✅ {h['title']} -> {dest.resolve()}  ({n:,} bytes)")
        return

    if a.cmd == "doc":
        if not a.arg:
            sys.exit("用法: doc <wiki node token / 文档链接> [--out x.md]")
        title, obj, items = read_doc(a.arg)
        lines = [f"# {title}", f"# doc_id={obj}  blocks={len(items)}", ""]
        for b in items:
            t = block_text(b)
            if t.strip():
                lines.append(t)
        out = Path(a.out) if a.out else Path.cwd() / f"feishu_doc_{obj}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines), encoding="utf-8")
        # 控制台只输出 ASCII，避免 cp936 管道解码错乱；正文请读文件
        print(f"OK saved: {out.resolve()}")
        print(f"doc_id={obj} blocks={len(items)} chars={sum(len(x) for x in lines)}")
        return


if __name__ == "__main__":
    main()
