#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Query the Quectel soft-test navigation portal and filter links by keyword.

Usage:
    python nav.py                # list all categories + link names (compact)
    python nav.py 烧录           # search links whose name/desc/category/url match
    python nav.py jira 报告      # multiple keywords (AND)
    python nav.py --json 串口    # machine-readable JSON output
    python nav.py --cats         # list category names only

Tokens are read from (in order):
  1. environment variables  NAV_PORTAL_TOKEN / GITHUB_TOKEN
  2. a local untracked file  scripts/config.local.json  (see config.example.json)
Never commit real tokens to git.
"""
import os
import sys
import json
import pathlib
import urllib.request

API = "https://scnrhostplnc.feishuapp.com/app/app_17fwfnp4pvy/openapi/nav/links"
GH_REPO = "venus-li-sssss/test"

_cfg_path = pathlib.Path(__file__).parent / "config.local.json"
_cfg = {}
if _cfg_path.exists():
    _cfg = json.loads(_cfg_path.read_text(encoding="utf-8"))

TOKEN = os.environ.get("NAV_PORTAL_TOKEN") or _cfg.get("nav_portal_token", "")
GH_TOKEN = os.environ.get("GITHUB_TOKEN") or _cfg.get("github_token", "")

if not TOKEN:
    sys.exit("ERROR: nav portal token missing. Set env NAV_PORTAL_TOKEN or scripts/config.local.json")


def fetch():
    req = urllib.request.Request(
        API, headers={"Authorization": "Bearer " + TOKEN, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def flatten(data):
    items = []
    for cat in data.get("categories", []):
        cname = cat.get("name", "")
        for link in cat.get("links", []):
            link = dict(link)
            link["_category"] = cname
            items.append(link)
    return items


def match(items, kws):
    if not kws:
        return items
    out = []
    for it in items:
        hay = " ".join(
            str(it.get(k, "")) for k in ("name", "description", "category", "url")
        ).lower()
        if all(k.lower() in hay for k in kws):
            out.append(it)
    return out


def print_text(hits):
    if not hits:
        print("(no match; try a broader or different keyword, e.g. 烧录 / jira / 工时 / 串口 / 报告 / 网盘)")
        return
    for it in hits:
        print("[%s] %s" % (it.get("_category", ""), it.get("name", "")))
        print("  url: %s" % it.get("url", ""))
        desc = (it.get("description") or "").strip()
        if desc:
            print("  desc: %s" % desc)
        for s in it.get("skills", []) or []:
            print("  skill: %s  -- %s" % (s.get("url", ""), s.get("description", "")))
        print()


def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]

    data = fetch()
    items = flatten(data)

    if args and args[0] == "--cats":
        seen = []
        for c in data.get("categories", []):
            n = c.get("name", "")
            cnt = len(c.get("links", []))
            seen.append("%s (%d links)" % (n, cnt))
        print("\n".join(seen))
        return

    hits = match(items, args)
    if as_json:
        print(json.dumps(hits, ensure_ascii=False, indent=2))
    else:
        print_text(hits)


if __name__ == "__main__":
    main()
