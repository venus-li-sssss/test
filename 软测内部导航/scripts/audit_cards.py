#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导航卡片体检：每张卡片的 skills 指向的 GitHub 目录是否存在、有没有资源定位、是不是只指路。

用法：
    python scripts/audit_cards.py                # 体检表 + 分档统计
    python scripts/audit_cards.py --json         # 机器可读
    python scripts/audit_cards.py --cat 资源     # 只看某个分类

判据（这是本 skill 的评估口径）：
  ✅ 可执行  = 卡片挂了 GitHub skill 目录，且该目录在仓库里真的存在（有 SKILL.md）
  ⚠️ 待校验  = 挂了 skill，但拿不到仓库树（没网/没 token）无法确认
  ❌ 坏链    = 挂了 skill，但仓库里没有这个目录 -> AI 会 404
  ➖ 仅指路  = 没有可加载的 skill（纯网页系统 / 给人下载的工具 / 只是资料链接）—— 不算缺陷
另外单独标注：资源定位（云盘/网盘入口）、引用（refLinkId）、desc 是否写清"输入→输出"、是否标了【未实现】。

token 读取顺序（与 nav.py 一致）：环境变量 NAV_PORTAL_TOKEN -> scripts/config.local.json
仓库树走 GitHub 公共 API（可用 GITHUB_TOKEN 提高限额）。
"""
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://scnrhostplnc.feishuapp.com/app/app_17fwfnp4pvy/openapi/nav"
GH_REPO = "venus-li-sssss/test"
GH_API = "https://api.github.com"
_cfg_path = pathlib.Path(__file__).parent / "config.local.json"
_cfg = {}
if _cfg_path.exists():
    try:
        _cfg = json.loads(_cfg_path.read_text(encoding="utf-8"))
    except Exception:
        _cfg = {}
TOKEN = os.environ.get("NAV_PORTAL_TOKEN") or _cfg.get("nav_portal_token", "")
GH_TOKEN = os.environ.get("GITHUB_TOKEN") or _cfg.get("github_token", "")


def nav(path):
    req = urllib.request.Request(BASE + path, headers={
        "Authorization": "Bearer " + TOKEN, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.exit("ERROR: GET %s -> %s %s" % (path, e.code, e.read().decode("utf-8", "replace")[:200]))


_RAW_CACHE = {}


def raw_exists(d):
    """仓库里 <d>/SKILL.md 是否存在（raw HEAD，不吃 API 限额）。"""
    if d in _RAW_CACHE:
        return _RAW_CACHE[d]
    url = "https://raw.githubusercontent.com/%s/main/%s/SKILL.md" % (GH_REPO, urllib.parse.quote(d))
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=20) as r:
            _RAW_CACHE[d] = (r.status == 200)
    except urllib.error.HTTPError as e:
        _RAW_CACHE[d] = (e.code == 200)
    except Exception:
        _RAW_CACHE[d] = None
    return _RAW_CACHE[d]


def repo_skill_dirs():
    """仓库里有 SKILL.md 的一级目录集合；拿不到返回 None。"""
    h = {"Accept": "application/vnd.github+json"}
    if GH_TOKEN:
        h["Authorization"] = "token " + GH_TOKEN
    url = "%s/repos/%s/git/trees/main?recursive=1" % (GH_API, GH_REPO)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
            tree = json.loads(r.read().decode("utf-8")).get("tree") or []
    except Exception:
        return None
    return {t["path"].split("/")[0] for t in tree
            if t.get("type") == "blob" and re.fullmatch(r"[^/]+/SKILL\.md", t.get("path", ""))}


def main():
    want_json = "--json" in sys.argv
    only_cat = ""
    if "--cat" in sys.argv:
        i = sys.argv.index("--cat")
        if i + 1 < len(sys.argv):
            only_cat = sys.argv[i + 1]
    if not TOKEN:
        sys.exit("ERROR: nav portal token missing (set NAV_PORTAL_TOKEN or scripts/config.local.json)")
    data = nav("/links")
    dirs = repo_skill_dirs()
    rows = []
    for c in sorted(data.get("categories") or [], key=lambda x: x.get("sortOrder") or 0):
        if only_cat and only_cat not in (c.get("name") or ""):
            continue
        for L in c.get("links") or []:
            sk = L.get("skills") or []
            desc = L.get("description") or ""
            gh = [urllib.parse.unquote((s.get("url") or "").split("tree/main/")[-1]).strip("/")
                  for s in sk if "github.com" in (s.get("url") or "") and "tree/main/" in (s.get("url") or "")]
            refs = [s for s in sk if s.get("refLinkId")]
            res = [s for s in sk if "feishu.cn/drive" in (s.get("url") or "") or "qdisk" in (s.get("url") or "")]
            if gh:
                if dirs is not None:
                    exist = {d: (d in dirs) for d in gh}
                else:
                    exist = {d: raw_exists(d) for d in gh}
                ok = [d for d in gh if exist.get(d)]
                bad = [d for d in gh if exist.get(d) is False]
                unknown = [d for d in gh if exist.get(d) is None]
                if bad and not ok:
                    state = "❌ 坏链"
                elif ok and not unknown:
                    state = "✅ 可执行"
                else:
                    state = "⚠️ 待校验"
            elif refs:
                ok, bad, state = [], [], "✅ 可执行(经引用)"
            else:
                ok, bad, state = [], [], "➖ 仅指路"
            if any(k in desc for k in ("【未实现", "未实现】", "暂无 skill")) and state.startswith("✅"):
                state = "⚠️ 有 skill 但功能未完成"
            rows.append({"cat": c.get("name"), "name": L.get("name"), "state": state,
                         "skills": ok, "bad": bad, "ref": len(refs), "res": len(res),
                         "arrow": ("→" in desc) or ("输入" in desc and "输出" in desc),
                         "desc": desc})
    if want_json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return
    print("%-6s %-24s %-24s %s" % ("state", "name", "skills", "flags"))
    for r in rows:
        flags = []
        if r["res"]:
            flags.append("资源×%d" % r["res"])
        if r["ref"]:
            flags.append("引用×%d" % r["ref"])
        if not r["arrow"] and len(r["desc"]) < 30:
            flags.append("desc 太短")
        if r["bad"]:
            flags.append("坏链:" + ",".join(r["bad"]))
        print("%-6s %-24s %-24s %s" % (r["state"], r["name"],
                                       ",".join(r["skills"])[:24] or "-", " ".join(flags)))
    print()
    agg = {}
    for r in rows:
        agg[r["state"]] = agg.get(r["state"], 0) + 1
    print("合计 %d 张：%s" % (len(rows), "  ".join("%s=%d" % kv for kv in sorted(agg.items()))))
    if dirs is None:
        print("提示：GitHub API 不可用（限额），已改用 raw 地址逐个校验 SKILL.md。")


if __name__ == "__main__":
    main()
