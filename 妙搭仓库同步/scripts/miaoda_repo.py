#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""妙搭仓库（scnrhostplnc.aiforce.cloud）skill 上传 / 下载工具。

内置 apikey，开箱即用。换账号/换仓库用环境变量覆盖：
    MIAODA_API_KEY / MIAODA_USER / MIAODA_REPO / MIAODA_BASE

命令:
    py miaoda_repo.py repos                    # 平台上所有仓库
    py miaoda_repo.py branches                 # 当前仓库的分支
    py miaoda_repo.py info                     # 仓库 + 分支 + 最近提交
    py miaoda_repo.py list                     # 顶层目录概览
    py miaoda_repo.py tree [前缀]               # 文件清单
    py miaoda_repo.py log [-n 10]              # 最近提交
    py miaoda_repo.py get <path> [--out 文件]   # 下载单文件
    py miaoda_repo.py pull <目录> [--dest 目录] # 下载一个 skill 目录
    py miaoda_repo.py push <本地目录> [--name 远端名] [-m 说明] [--dry-run] [--no-prune]
    py miaoda_repo.py rm <path> [-m 说明]       # 删除远端单文件

退出码: 0 成功; 1 一般错误; 2 鉴权问题; 3 没有变化(未提交)
"""
import argparse
import json
import os
import sys
import time
import urllib.parse

try:
    import requests
except ImportError:
    print("缺少 requests：pip install requests")
    sys.exit(1)

# ---- 平台坐标（内置） --------------------------------------------------
# apikey 以 hex 存放，运行时还原。与 GitHub 那份 skill 保持同一套做法，
# 换环境请用 MIAODA_API_KEY 覆盖，不要注入到别的地方。
_DEFAULT_KEY = bytes.fromhex(
    "704a4c51485453393831724c5758646e44796c3859454a7348487367367a484a764e4a573433524c4c5f77").decode()
API_KEY = os.environ.get("MIAODA_API_KEY") or _DEFAULT_KEY
USER = os.environ.get("MIAODA_USER", "venus.li@ikotek.com")
BASE = os.environ.get("MIAODA_BASE", "https://scnrhostplnc.aiforce.cloud/app/app_17b0ap920df")
DEFAULT_REPO_NAME = os.environ.get("MIAODA_REPO", "user-skills")

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".idea", ".vscode", ".pytest_cache"}
SKIP_FILES = {".DS_Store", "Thumbs.db"}

_cache_repos = None
_cache_tree = {}


def log(msg=""):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("gbk", "replace").decode("gbk"), flush=True)


def req(method, path, params=None, body=None, tries=3):
    url = BASE + path
    headers = {"Authorization": "Bearer " + API_KEY, "x-user-name": USER}
    last = ""
    for i in range(tries):
        try:
            kwargs = {"headers": headers, "timeout": 120}
            if params:
                kwargs["params"] = params
            if body is not None:
                kwargs["json"] = body
            r = requests.request(method, url, **kwargs)
            if r.status_code < 400:
                return r.json() if r.content else {}
            if r.status_code in (401, 403):
                raise SystemExit("[auth] %s %s -> %s %s" % (method, path, r.status_code, r.text[:300]))
            if r.status_code == 404:
                return None
            last = "HTTP %s %s" % (r.status_code, r.text[:300])
        except SystemExit:
            raise
        except Exception as e:
            last = repr(e)[:300]
        time.sleep(1 + i * 2)
    raise RuntimeError("%s %s failed: %s" % (method, path, last))


# ---- 仓库 / 分支解析 ---------------------------------------------------

def all_repos():
    global _cache_repos
    if _cache_repos is None:
        _cache_repos = req("GET", "/openapi/repos").get("items", [])
    return _cache_repos


def resolve_repo(name_or_id=None):
    """返回 (repo_dict)"""
    target = (name_or_id or DEFAULT_REPO_NAME).strip()
    for r in all_repos():
        if r["id"] == target or r["name"] == target:
            return r
    names = ", ".join(r["name"] for r in all_repos())
    raise SystemExit("找不到仓库 %r；现有：%s" % (target, names))


def first_line(s, n=70):
    s = (s or "").strip()
    return s.splitlines()[0][:n] if s else ""


def resolve_branch(repo, branch_name=None):
    branches = req("GET", "/openapi/repos/%s/branches" % repo["id"]) or []
    if isinstance(branches, dict):
        branches = branches.get("items") or []
    if branch_name:
        for b in branches:
            if b["name"] == branch_name or b["id"] == branch_name:
                return b
        raise SystemExit("找不到分支 %r" % branch_name)
    for b in branches:
        if b.get("isDefault"):
            return b
    return branches[0]


def ctx(args):
    repo = resolve_repo(getattr(args, "repo", None))
    branch = resolve_branch(repo, getattr(args, "branch", None))
    return repo, branch


# ---- 树 ----------------------------------------------------------------

def flatten_tree(branch_id, refresh=False):
    """{path: node}（只含文件）"""
    if not refresh and branch_id in _cache_tree:
        return _cache_tree[branch_id]
    data = req("GET", "/openapi/files/tree", params={"branchId": branch_id}) or []
    out = {}

    def walk(nodes):
        for n in nodes:
            if n.get("type") == "directory":
                walk(n.get("children") or [])
            else:
                out[n["path"]] = n

    walk(data if isinstance(data, list) else data.get("items", []))
    _cache_tree[branch_id] = out
    return out


def read_file(branch_id, path):
    d = req("GET", "/openapi/files", params={"branchId": branch_id, "path": path})
    if not d:
        return None
    return d.get("content", "")


def norm(p):
    return p.replace("\\", "/").strip("/")


def safe_join(root, rel):
    parts = [x for x in norm(rel).split("/") if x not in ("", ".", "..")]
    return os.path.join(root, *parts)


# ---- 命令 --------------------------------------------------------------

def cmd_repos(args):
    log("%-14s %-10s %6s %8s  %s" % ("仓库", "默认分支", "分支", "提交", "说明"))
    log("-" * 100)
    for r in all_repos():
        log("%-14s %-10s %6d %8d  %s" % (
            r["name"], r.get("defaultBranch") or "-", r.get("branchCount", 0),
            r.get("commitCount", 0), (r.get("description") or "")[:44]))
    log("-" * 100)
    log("默认使用：%s（可用 --repo <名称> 切换）" % DEFAULT_REPO_NAME)


def cmd_branches(args):
    repo, _ = ctx(args)
    branches = req("GET", "/openapi/repos/%s/branches" % repo["id"])
    if isinstance(branches, dict):
        branches = branches.get("items") or []
    log("仓库：%s" % repo["name"])
    for b in branches:
        log("  %-10s %s  HEAD=%s  %s" % (
            b["name"], "默认" if b.get("isDefault") else "    ",
            (b.get("headCommitId") or "")[:8], first_line(b.get("headCommitMessage"), 50)))


def cmd_info(args):
    repo, branch = ctx(args)
    log("平台      : %s" % BASE)
    log("仓库      : %s  (%s)" % (repo["name"], repo["id"]))
    log("说明      : %s" % (repo.get("description") or "-"))
    log("分支      : %s  (head=%s)" % (branch["name"], (branch.get("headCommitId") or "")[:10]))
    log("最后提交  : %s" % first_line(branch.get("headCommitMessage")))
    log("提交数    : %s   分支数: %s" % (repo.get("commitCount"), repo.get("branchCount")))
    files = flatten_tree(branch["id"], refresh=True)
    log("文件数    : %d" % len(files))
    log("apikey    : %s…%s (%d 位)" % (API_KEY[:6], API_KEY[-4:], len(API_KEY)))


def cmd_list(args):
    repo, branch = ctx(args)
    files = flatten_tree(branch["id"], refresh=True)
    groups = {}
    for p in files:
        top = p.split("/")[0]
        g = groups.setdefault(top, {"files": 0, "is_dir": False})
        g["files"] += 1
        if "/" in p:
            g["is_dir"] = True
    log("仓库：%s / %s" % (repo["name"], branch["name"]))
    log("%-40s %6s" % ("目录 / 文件", "文件数"))
    log("-" * 50)
    for k in sorted(groups, key=lambda x: (not groups[x]["is_dir"], x.lower())):
        g = groups[k]
        log("%-40s %6d" % (k + ("/" if g["is_dir"] else ""), g["files"]))
    log("-" * 50)
    log("共 %d 个目录 / %d 个文件" % (sum(1 for g in groups.values() if g["is_dir"]), len(files)))


def cmd_tree(args):
    repo, branch = ctx(args)
    files = flatten_tree(branch["id"], refresh=True)
    prefix = norm(args.prefix or "")
    hits = [p for p in sorted(files) if not prefix or p == prefix or p.startswith(prefix + "/")]
    if not hits:
        log("没有匹配的文件：%s" % (prefix or "(空)"))
        return 1
    for p in hits:
        log("%-72s %s" % (p, (files[p].get("status") or "")[:8]))
    log("-" * 82)
    log("%d 个文件" % len(hits))


def cmd_log(args):
    repo, branch = ctx(args)
    d = req("GET", "/openapi/repos/%s/commits" % repo["id"],
            params={"branchId": branch["id"], "pageSize": args.n})
    items = d.get("items", []) if isinstance(d, dict) else (d or [])
    log("仓库：%s / %s   共 %s 个提交（显示 %d）" % (
        repo["name"], branch["name"], d.get("total", "?") if isinstance(d, dict) else "?", len(items)))
    for c in items:
        log("  %s  %-28s %s" % (c["id"][:8], (c.get("createdAt") or "")[:19],
                                (c.get("message") or "").splitlines()[0][:60]))


def cmd_get(args):
    repo, branch = ctx(args)
    path = norm(args.path)
    content = read_file(branch["id"], path)
    if content is None:
        log("远端没有这个文件：%s" % path)
        return 1
    out = args.out or os.path.basename(path)
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    log("完成：%s (%d 字符)  <-  %s" % (os.path.abspath(out), len(content), path))
    return 0


def cmd_pull(args):
    repo, branch = ctx(args)
    prefix = norm(args.name)
    files = flatten_tree(branch["id"], refresh=True)
    hits = [p for p in sorted(files) if p.startswith(prefix + "/")]
    if not hits:
        log("仓库里没有目录：%s" % prefix)
        return 1
    dest = os.path.abspath(os.path.expanduser(args.dest or os.path.join(os.getcwd(), prefix)))
    total = 0
    for p in hits:
        content = read_file(branch["id"], p)
        if content is None:
            continue
        out = safe_join(dest, p[len(prefix) + 1:])
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        total += len(content)
        log("  <- %s (%d 字符)" % (out, len(content)))
    log("")
    log("完成：%s  <-  %d 个文件 / %d 字符" % (dest, len(hits), total))
    return 0


def collect_local(root):
    out = {}
    root = os.path.abspath(root)
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fn:
            if f in SKIP_FILES or f.endswith(".pyc"):
                continue
            full = os.path.join(dp, f)
            rel = norm(os.path.relpath(full, root))
            try:
                # newline="" 保留文件原始换行：默认的通用换行会把 CRLF 折成 LF，
                # 导致"传上去的"和"本地文件"永远不一致，下次 push 又是一次假变更。
                with open(full, "r", encoding="utf-8", newline="") as fh:
                    out[rel] = fh.read()
            except UnicodeDecodeError:
                log("  [skip] 非 UTF-8 文本，平台仓库只收文本：%s" % rel)
    return out


def cmd_push(args):
    repo, branch = ctx(args)
    local = os.path.abspath(os.path.expanduser(args.local_dir))
    if not os.path.isdir(local):
        log("目录不存在：%s" % local)
        return 1
    name = norm(args.name or os.path.basename(local.rstrip("\\/")))
    prefix = norm(args.prefix if args.prefix is not None else name)
    local_files = collect_local(local)
    if not local_files:
        log("目录里没有可上传的文本文件：%s" % local)
        return 1

    remote = flatten_tree(branch["id"], refresh=True)
    remote_paths = set(remote)

    # 平台没有"内容 sha"，只能逐个读回比较；目录里文件不多时完全够用
    changes, same = [], 0
    for rel, text in sorted(local_files.items()):
        path = ("%s/%s" % (prefix, rel)) if prefix else rel
        if path in remote_paths:
            old = read_file(branch["id"], path)
            if old == text:
                same += 1
                continue
            changes.append({"path": path, "action": "update", "content": text})
        else:
            changes.append({"path": path, "action": "create", "content": text})

    deletes = []
    if not args.no_prune and prefix:
        want = {("%s/%s" % (prefix, rel)) if prefix else rel for rel in local_files}
        for p in sorted(remote_paths):
            if p.startswith(prefix + "/") and p not in want:
                deletes.append({"path": p, "action": "delete"})
    changes.extend(deletes)

    log("仓库    ：%s / %s" % (repo["name"], branch["name"]))
    log("远端前缀：%s" % (prefix + "/" if prefix else "(仓库根)"))
    log("变更    ：新增/修改 %d，删除 %d，未变 %d" % (
        len(changes) - len(deletes), len(deletes), same))
    for c in changes:
        log("  %s %s" % ({"create": "A", "update": "M", "delete": "D"}[c["action"]], c["path"]))

    if not changes:
        log("没有变化，不提交。")
        return 3
    if args.dry_run:
        log("[dry-run] 未提交。")
        return 0

    msg = args.message or ("sync %s from local (%d files)" % (prefix or "(root)", len(local_files)))
    res = req("POST", "/openapi/repos/%s/commits" % repo["id"],
              body={"branchId": branch["id"], "message": msg,
                    "changes": changes, "userName": USER})
    cid = (res or {}).get("id") or (res or {}).get("commitId") or "?"
    log("")
    log("已提交：%s  %s" % (str(cid)[:10], msg))
    return 0


def cmd_rm(args):
    repo, branch = ctx(args)
    path = norm(args.path)
    remote = flatten_tree(branch["id"], refresh=True)
    if path not in remote:
        log("远端没有这个文件：%s" % path)
        return 1
    msg = args.message or ("remove %s" % path)
    req("POST", "/openapi/repos/%s/commits" % repo["id"],
        body={"branchId": branch["id"], "message": msg,
              "changes": [{"path": path, "action": "delete"}], "userName": USER})
    log("已删除：%s  （%s）" % (path, msg))
    return 0


def main():
    ap = argparse.ArgumentParser(description="妙搭仓库（%s）上传/下载" % DEFAULT_REPO_NAME)
    ap.add_argument("--repo", default="", help="仓库名或 id，默认 %s" % DEFAULT_REPO_NAME)
    ap.add_argument("--branch", default="", help="分支名或 id，默认仓库默认分支")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("repos")
    sub.add_parser("branches")
    sub.add_parser("info")
    sub.add_parser("list")

    p = sub.add_parser("tree")
    p.add_argument("prefix", nargs="?", default="")

    p = sub.add_parser("log")
    p.add_argument("-n", type=int, default=10)

    p = sub.add_parser("get")
    p.add_argument("path")
    p.add_argument("--out", default="")

    p = sub.add_parser("pull")
    p.add_argument("name")
    p.add_argument("--dest", default="")

    p = sub.add_parser("push")
    p.add_argument("local_dir")
    p.add_argument("--name", default="")
    p.add_argument("--prefix", default=None)
    p.add_argument("-m", "--message", default="")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-prune", action="store_true")

    p = sub.add_parser("rm")
    p.add_argument("path")
    p.add_argument("-m", "--message", default="")

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        return 1
    fn = {"repos": cmd_repos, "branches": cmd_branches, "info": cmd_info,
          "list": cmd_list, "tree": cmd_tree, "log": cmd_log, "get": cmd_get,
          "pull": cmd_pull, "push": cmd_push, "rm": cmd_rm}[args.cmd]
    return fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
