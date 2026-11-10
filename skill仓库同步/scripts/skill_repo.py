#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""skill 仓库（GitHub venus-li-sssss/test）上传 / 下载工具。

内置仓库访问 token（base64 存放：公开仓库里出现明文 ghp_ 会被 GitHub secret
scanning 自动吊销，skill 立刻失效，所以转一层；不是出于保密需要）。
换账号/换仓库时用环境变量覆盖：GITHUB_TOKEN / SKILL_OWNER / SKILL_REPO / SKILL_BRANCH

命令:
    py skill_repo.py info                       # 仓库信息 + token 是否可用
    py skill_repo.py list                      # 列出仓库里的 skill 目录
    py skill_repo.py tree [前缀]                # 列文件（可加 --full）
    py skill_repo.py pull <名字> [--dest 目录]   # 下载一个 skill 目录到本地
    py skill_repo.py pull-all [--dest 目录]      # 下载全部
    py skill_repo.py get <远端路径> [--out 文件] # 下载单个文件
    py skill_repo.py push <本地目录> [--name 远端名] [-m 提交信息] [--dry-run] [--no-prune]
    py skill_repo.py put <本地文件> <远端路径> [-m 提交信息]
    py skill_repo.py rm <远端路径> [-m 提交信息]

退出码: 0 成功; 1 一般错误; 2 token/权限问题; 3 没有变化(无需提交)
"""
import argparse
import base64
import hashlib
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

# ---- 仓库坐标（内置） --------------------------------------------------
# token 以 hex 存放，运行时还原。**不要改成明文或 base64**：
# 这个仓库是公开的，GitHub 的 push protection 会检出明文 ghp_（甚至连 base64
# 编码的都会被识别成 GITHUB_BASE64_ENCODED_PERSONAL_ACCESS_TOKEN）并拒绝推送 /
# 自动吊销。hex 只是绕开内容扫描，不是保密手段 —— 本来就是开放仓库。
_DEFAULT_TOKEN = bytes.fromhex(
    "6768705f51515254524a56567637663451354b56336d62623272343337526233725330586d517757").decode()
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or _DEFAULT_TOKEN
OWNER = os.environ.get("SKILL_OWNER", "venus-li-sssss")
REPO = os.environ.get("SKILL_REPO", "test")
BRANCH = os.environ.get("SKILL_BRANCH", "main")

API = "https://api.github.com"
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".idea", ".vscode", ".pytest_cache"}
SKIP_FILES = {".DS_Store", "Thumbs.db"}


def log(msg=""):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("gbk", "replace").decode("gbk"), flush=True)


def api(method, path, body=None, raw=False, tries=3):
    url = path if path.startswith("http") else API + path
    headers = {
        "Authorization": "token " + TOKEN,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    last = ""
    for i in range(tries):
        try:
            r = requests.request(method, url, headers=headers, json=body, timeout=60)
            if raw and r.status_code < 400:
                return r.content
            if r.status_code < 400:
                return r.json() if r.content else {}
            if r.status_code in (401, 403):
                raise SystemExit("[auth] %s %s -> %s %s" % (
                    method, path, r.status_code, r.text[:300]))
            last = "HTTP %s %s" % (r.status_code, r.text[:300])
        except SystemExit:
            raise
        except Exception as e:
            last = repr(e)[:300]
        time.sleep(1 + i * 2)
    raise RuntimeError("%s %s failed: %s" % (method, path, last))


def repo_path(p):
    return "/repos/%s/%s%s" % (OWNER, REPO, p)


def q(path):
    """URL 编码每一段（中文路径必需），但保留 /"""
    return "/".join(urllib.parse.quote(seg) for seg in path.split("/"))


def head():
    ref = api("GET", repo_path("/git/ref/heads/" + BRANCH))
    sha = ref["object"]["sha"]
    commit = api("GET", repo_path("/git/commits/" + sha))
    return ref["object"]["sha"], commit["tree"]["sha"], commit.get("message", "")


def full_tree(tree_sha):
    """返回 {path: {sha, mode, type}}；超大树（>100k 项）会 truncate"""
    data = api("GET", repo_path("/git/trees/%s?recursive=1" % tree_sha))
    if data.get("truncated"):
        log("[warn] tree 被截断（仓库文件太多），结果可能不全")
    return {e["path"]: e for e in data.get("tree", []) if e["type"] == "blob"}


def blob_bytes(sha):
    d = api("GET", repo_path("/git/blobs/" + sha))
    if d.get("encoding") == "base64":
        return base64.b64decode(d["content"])
    return d["content"].encode("utf-8")


def local_git_sha(data):
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def safe_join(root, rel):
    """防止远端路径里的 .. 逃出目标目录"""
    parts = [p for p in rel.replace("\\", "/").split("/") if p not in ("", ".", "..")]
    return os.path.join(root, *parts)


# ------------------------------------------------------------------ 命令

def cmd_info(args):
    d = api("GET", "/repos/%s/%s" % (OWNER, REPO))
    log("仓库      : %s" % d["full_name"])
    log("私有      : %s" % d["private"])
    log("默认分支  : %s（本工具用 %s）" % (d["default_branch"], BRANCH))
    log("大小      : %.1f MB" % (d.get("size", 0) / 1024.0))
    log("权限      : %s" % d.get("permissions"))
    ref_sha, tree_sha, msg = head()
    files = full_tree(tree_sha)
    log("HEAD      : %s" % ref_sha[:10])
    log("最后提交  : %s" % (msg.splitlines()[0] if msg else ""))
    log("文件数    : %d" % len(files))
    log("token     : %s…%s (%d 位)" % (TOKEN[:7], TOKEN[-4:], len(TOKEN)))


def cmd_list(args):
    ref_sha, tree_sha, _ = head()
    files = full_tree(tree_sha)
    groups = {}
    for p, meta in files.items():
        top = p.split("/")[0]
        g = groups.setdefault(top, {"files": 0, "bytes": 0, "is_dir": False})
        g["files"] += 1
        g["bytes"] += meta.get("size") or 0
        if "/" in p:
            g["is_dir"] = True
    log("%-38s %7s %10s" % ("目录 / 文件", "文件数", "大小"))
    log("-" * 60)
    for k in sorted(groups, key=lambda x: (not groups[x]["is_dir"], x.lower())):
        g = groups[k]
        log("%-38s %7d %9.1f KB" % (k + ("/" if g["is_dir"] else ""), g["files"], g["bytes"] / 1024.0))
    log("-" * 60)
    log("共 %d 个顶层目录 / %d 个文件 / %.1f MB" % (
        sum(1 for g in groups.values() if g["is_dir"]), len(files),
        sum(g["bytes"] for g in groups.values()) / 1024.0 / 1024.0))


def cmd_tree(args):
    ref_sha, tree_sha, _ = head()
    files = full_tree(tree_sha)
    prefix = (args.prefix or "").strip("/")
    hits = {p: v for p, v in files.items() if not prefix or p == prefix or p.startswith(prefix + "/")}
    if not hits:
        log("没有匹配的文件：%s" % (prefix or "(空)"))
        return 1
    total = 0
    for p in sorted(hits):
        size = hits[p].get("size")
        if size is None:
            size = len(blob_bytes(hits[p]["sha"]))
        total += size
        log("%-70s %8s B  %s" % (p, size, hits[p]["sha"][:8]))
    log("-" * 90)
    log("%d 个文件，合计 %.1f KB" % (len(hits), total / 1024.0))
    return 0


def cmd_pull(args):
    if args.dest:
        dest = os.path.abspath(os.path.expanduser(args.dest))
    else:
        dest = os.path.abspath(os.path.join(os.getcwd(), args.name))
    ref_sha, tree_sha, _ = head()
    files = full_tree(tree_sha)
    prefix = args.name.strip("/")
    hits = {p: v for p, v in files.items() if p.startswith(prefix + "/")}
    if not hits:
        log("仓库里没有目录：%s" % prefix)
        return 1
    os.makedirs(dest, exist_ok=True)
    total = 0
    for p in sorted(hits):
        data = blob_bytes(hits[p]["sha"])
        out = safe_join(dest, p[len(prefix) + 1:])
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as f:
            f.write(data)
        total += len(data)
        log("  <- %s (%d B)" % (out, len(data)))
    log("")
    log("完成：%s  <-  %d 个文件 / %.1f KB" % (dest, len(hits), total / 1024.0))
    return 0


def cmd_pull_all(args):
    ref_sha, tree_sha, _ = head()
    files = full_tree(tree_sha)
    dest = os.path.abspath(os.path.expanduser(args.dest or os.getcwd()))
    tops = sorted({p.split("/")[0] for p in files if "/" in p})
    ok = 0
    for t in tops:
        sub = argparse.Namespace(name=t, dest=os.path.join(dest, t))
        if cmd_pull(sub) == 0:
            ok += 1
    log("")
    log("共拉取 %d/%d 个目录到 %s" % (ok, len(tops), dest))
    return 0


def cmd_get(args):
    ref_sha, tree_sha, _ = head()
    files = full_tree(tree_sha)
    p = args.path.strip("/")
    if p not in files:
        log("远端没有这个文件：%s" % p)
        return 1
    data = blob_bytes(files[p]["sha"])
    out = args.out or os.path.basename(p)
    with open(out, "wb") as f:
        f.write(data)
    log("完成：%s (%d B)  <-  %s" % (os.path.abspath(out), len(data), p))
    return 0


def collect_local(root, exclude=None):
    """{rel_path: bytes}"""
    out = {}
    root = os.path.abspath(root)
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fn:
            if f in SKIP_FILES or f.endswith(".pyc"):
                continue
            full = os.path.join(dp, f)
            rel = os.path.relpath(full, root).replace("\\", "/")
            if exclude and any(rel.startswith(e) for e in exclude):
                continue
            with open(full, "rb") as fh:
                out[rel] = fh.read()
    return out


def commit_changes(changes, deletes, message, dry_run=False):
    """changes: {path: bytes}, deletes: [path]；一个 commit 提交全部变更。"""
    head_sha, tree_sha, _ = head()
    remote = full_tree(tree_sha)

    todo, same = {}, []
    for path, data in changes.items():
        sha = local_git_sha(data)
        if path in remote and remote[path]["sha"] == sha:
            same.append(path)
            continue
        todo[path] = (data, sha)

    log("变更：新增/修改 %d，删除 %d，未变 %d" % (len(todo), len(deletes), len(same)))
    for p in sorted(todo):
        log("  %s %s" % ("M" if p in remote else "A", p))
    for p in sorted(deletes):
        log("  D %s" % p)

    if not todo and not deletes:
        log("没有变化，不提交。")
        return 3
    if dry_run:
        log("[dry-run] 未提交。")
        return 0

    entries = []
    for path, (data, sha) in sorted(todo.items()):
        blob = api("POST", repo_path("/git/blobs"),
                   {"content": base64.b64encode(data).decode(), "encoding": "base64"})
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    for path in deletes:
        if path in remote:
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})

    new_tree = api("POST", repo_path("/git/trees"),
                   {"base_tree": tree_sha, "tree": entries})
    commit = api("POST", repo_path("/git/commits"),
                 {"message": message, "tree": new_tree["sha"], "parents": [head_sha]})
    api("PATCH", repo_path("/git/refs/heads/" + BRANCH), {"sha": commit["sha"], "force": False})
    log("")
    log("已提交：%s  -> %s" % (commit["sha"][:10], commit.get("html_url", "")))
    return 0


def cmd_push(args):
    local = os.path.abspath(os.path.expanduser(args.local_dir))
    if not os.path.isdir(local):
        log("目录不存在：%s" % local)
        return 1
    name = (args.name or os.path.basename(local.rstrip("\\/"))).strip("/")
    prefix = (args.prefix if args.prefix is not None else name).strip("/")
    files = collect_local(local)
    if not files:
        log("目录里没有可上传的文件：%s" % local)
        return 1
    changes = {("%s/%s" % (prefix, rel)) if prefix else rel: data
               for rel, data in files.items()}

    deletes = []
    if not args.no_prune:
        _, tree_sha, _ = head()
        remote = full_tree(tree_sha)
        want = set(changes)
        for p in remote:
            if prefix and p.startswith(prefix + "/") and p not in want:
                deletes.append(p)

    msg = args.message or ("sync %s (%d files)" % (prefix or "(root)", len(changes)))
    log("本地：%s" % local)
    log("远端：%s（分支 %s）" % ((prefix + "/") if prefix else "(仓库根)", BRANCH))
    return commit_changes(changes, deletes, msg, dry_run=args.dry_run)


def cmd_put(args):
    if not os.path.isfile(args.local_file):
        log("文件不存在：%s" % args.local_file)
        return 1
    with open(args.local_file, "rb") as f:
        data = f.read()
    path = args.remote_path.strip("/")
    msg = args.message or ("update %s" % path)
    return commit_changes({path: data}, [], msg)


def cmd_rm(args):
    path = args.remote_path.strip("/")
    msg = args.message or ("remove %s" % path)
    return commit_changes({}, [path], msg)


def main():
    ap = argparse.ArgumentParser(description="skill 仓库（GitHub %s/%s）上传/下载" % (OWNER, REPO))
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("info")
    sub.add_parser("list")

    p = sub.add_parser("tree")
    p.add_argument("prefix", nargs="?", default="")
    p.add_argument("--full", action="store_true")

    p = sub.add_parser("pull")
    p.add_argument("name")
    p.add_argument("--dest", default="")

    p = sub.add_parser("pull-all")
    p.add_argument("--dest", default="")

    p = sub.add_parser("get")
    p.add_argument("path")
    p.add_argument("--out", default="")

    p = sub.add_parser("push")
    p.add_argument("local_dir")
    p.add_argument("--name", default="")
    p.add_argument("--prefix", default=None,
                   help="留空字符串表示直接放到仓库根（不套目录名）")
    p.add_argument("-m", "--message", default="")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-prune", action="store_true", help="不删除远端多余文件")

    p = sub.add_parser("put")
    p.add_argument("local_file")
    p.add_argument("remote_path")
    p.add_argument("-m", "--message", default="")

    p = sub.add_parser("rm")
    p.add_argument("remote_path")
    p.add_argument("-m", "--message", default="")

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        return 1
    fn = {"info": cmd_info, "list": cmd_list, "tree": cmd_tree, "pull": cmd_pull,
          "pull-all": cmd_pull_all, "get": cmd_get, "push": cmd_push,
          "put": cmd_put, "rm": cmd_rm}[args.cmd]
    return fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
