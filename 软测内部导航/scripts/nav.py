#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Query and maintain the Quectel soft-test navigation portal (妙搭 nav app).

Read:
    python nav.py                            # list every link (compact)
    python nav.py 烧录                       # search links (name/desc/category/url, AND across keywords)
    python nav.py jira 报告                  # multiple keywords = AND
    python nav.py --json 串口                # machine-readable JSON
    python nav.py --cats                     # category names only
    python nav.py cat list                   # categories WITH id + link count
    python nav.py link list [--cat 测试相关]  # links WITH id (ids are what PATCH/DELETE need)
    python nav.py link show <id>             # one link, full JSON

Write (same Key, same prefix, no extra authorization; nav page updates immediately):
    python nav.py cat add 测试工具
    python nav.py cat rename <id> 新名字
    python nav.py cat delete <id>                          # only empty categories

    python nav.py link add --name JIRA工单系统 --url https://ticket.ikotek.com \
        --category 测试相关 --desc "提交与查询 BUG"
    python nav.py link add --name X --url Y --category Z \
        --skill "https://github.com/user/repo|JIRA 数据读写" --skill "https://...|另一个"
    python nav.py link update <id> --desc "新的说明"        # only the fields you pass change
    python nav.py link update <id> --skills-file skills.json
    python nav.py link update <id> --name 新名 --sort 3
    python nav.py link delete <id>

Server-side constraints (this script just prints the server's reason):
  * category must already exist -> 400, response lists current categories (run `cat list`)
  * same name in same category -> 409, response gives the existing link id (use `link update`)
  * link referenced by another link's skills -> 409, response lists the referrers
  * category still has links -> 400
  * sortOrder omitted -> appended to the end of that category
  * skills / attachments are REPLACED wholesale, not merged -- read the old value first
    (`link show <id>`), and `link update` prints the old value before overwriting it.

Tokens are read from (in order):
  1. environment variables  NAV_PORTAL_TOKEN / GITHUB_TOKEN
  2. a local untracked file  scripts/config.local.json  (see config.example.json)
The read and write APIs share the same nav token. Never commit real tokens to git.
"""
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

BASE = "https://scnrhostplnc.feishuapp.com/app/app_17fwfnp4pvy/openapi/nav"
LINKS = BASE + "/links"
CATS = BASE + "/categories"
GH_REPO = "venus-li-sssss/test"

_cfg_path = pathlib.Path(__file__).parent / "config.local.json"
_cfg = {}
if _cfg_path.exists():
    _cfg = json.loads(_cfg_path.read_text(encoding="utf-8"))

TOKEN = os.environ.get("NAV_PORTAL_TOKEN") or _cfg.get("nav_portal_token", "")
GH_TOKEN = os.environ.get("GITHUB_TOKEN") or _cfg.get("github_token", "")

USAGE = __doc__


def _request(method, url, payload=None):
    """Return (status, body_dict). Never raises on 4xx/5xx."""
    data = None
    headers = {"Authorization": "Bearer " + TOKEN, "Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            body = json.loads(raw) if raw.strip() else {}
        except Exception:
            body = {"raw": raw}
        return e.code, body


def fetch():
    status, body = _request("GET", LINKS)
    if status != 200:
        sys.exit("ERROR: GET /links failed (%s): %s" % (status, json.dumps(body, ensure_ascii=False)))
    return body


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
        print("  id: %s" % it.get("id", ""))
        print("  url: %s" % it.get("url", ""))
        desc = (it.get("description") or "").strip()
        if desc:
            print("  desc: %s" % desc)
        for s in it.get("skills", []) or []:
            print("  skill: %s  -- %s" % (s.get("url", ""), s.get("description", "")))
        print()


# ---------------------------------------------------------------- write helpers


def _dump(body):
    return json.dumps(body, ensure_ascii=False, indent=2)


def die(status, body, hint=""):
    """Print the server's rejection reason in a copy-pasteable form."""
    msg = body.get("message") or body.get("msg") or body.get("error") or ""
    print("FAILED %s%s" % (status, (": " + msg) if msg else ""))
    print(_dump(body))
    if hint:
        print("hint: " + hint)
    sys.exit(1)


def find_link(data, link_id):
    for it in flatten(data):
        if str(it.get("id")) == str(link_id):
            return it
    return None


def find_category(data, ref):
    """Resolve a category by id or by exact name (case-insensitive fallback)."""
    cats = data.get("categories", [])
    for c in cats:
        if str(c.get("id")) == str(ref):
            return c
    for c in cats:
        if (c.get("name") or "").strip() == str(ref).strip():
            return c
    low = str(ref).strip().lower()
    for c in cats:
        if (c.get("name") or "").strip().lower() == low:
            return c
    return None


def parse_skills(flag_skills, skills_file, skills_json):
    """Build the skills[] array; returns list or None when the user passed nothing."""
    out = []
    if skills_json:
        raw = skills_json.strip()
        if not raw.startswith("["):
            path = pathlib.Path(raw)
            if path.exists():
                raw = path.read_text(encoding="utf-8")
        out = json.loads(raw)
    if skills_file:
        out = json.loads(pathlib.Path(skills_file).read_text(encoding="utf-8"))
    for s in flag_skills:
        sep = "|" if "|" in s else ("::" if "::" in s else ",")
        parts = s.split(sep, 1)
        if len(parts) != 2:
            sys.exit("ERROR: --skill must be 'url|description', got: %r" % s)
        out.append({"url": parts[0].strip(), "description": parts[1].strip()})
    return out or None


def opt_parser(argv):
    """Tiny flag parser: --k v, --k=v, boolean --dry-run."""
    opts, flags = {}, set()
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            if "=" in a:
                k, v = a[2:].split("=", 1)
                opts[k] = v
            elif i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                opts[a[2:]] = argv[i + 1]
                i += 1
            else:
                flags.add(a[2:])
        else:
            sys.exit("ERROR: unexpected argument %r\n\n%s" % (a, USAGE))
        i += 1
    return opts, flags


# ----------------------------------------------------------------- link verbs


def link_list(argv):
    opts, _ = opt_parser(argv)
    data = fetch()
    cats = data.get("categories", [])
    want = opts.get("cat")
    for c in cats:
        if want and want not in (c.get("name", ""), str(c.get("id"))):
            continue
        print("%s  (%d links, sortOrder=%s)" % (c.get("name", ""), len(c.get("links", [])), c.get("sortOrder")))
        for link in c.get("links", []):
            print("  %s  %s" % (link.get("id", ""), link.get("name", "")))
            print("      url: %s" % link.get("url", ""))
            desc = (link.get("description") or "").strip()
            if desc:
                print("      desc: %s" % desc)
            for s in link.get("skills", []) or []:
                print("      skill: %s -- %s" % (s.get("url", ""), s.get("description", "")))
        print()


def link_show(argv):
    if not argv:
        sys.exit("ERROR: link show <id>\n\n" + USAGE)
    data = fetch()
    it = find_link(data, argv[0])
    if not it:
        sys.exit("ERROR: no link with id %r (run `link list`)" % argv[0])
    print(_dump(it))


def link_add(argv):
    opts, flags = opt_parser(argv)
    for k in ("name", "url", "category"):
        if not opts.get(k):
            sys.exit("ERROR: link add needs --%s (category must already exist)\n\n%s" % (k, USAGE))
    data = fetch()
    cat = find_category(data, opts["category"])
    if not cat:
        names = [c.get("name", "") for c in data.get("categories", [])]
        sys.exit("ERROR: category %r does not exist.\ncurrent categories: %s\n"
                 "create it first: python nav.py cat add %s"
                 % (opts["category"], ", ".join(names), opts["category"]))
    cat_name = cat.get("name", "")
    # local duplicate pre-check (server also returns 409, but a hint is cheaper than a rollback)
    for it in cat.get("links", []):
        if (it.get("name") or "").strip() == opts["name"].strip():
            sys.exit("ERROR: %r already exists in category %r (id=%s).\n"
                     "use: python nav.py link update %s --desc \"...\""
                     % (opts["name"], cat_name, it.get("id"), it.get("id")))

    payload = {"name": opts["name"].strip(), "url": opts["url"].strip(), "category": cat_name}
    if opts.get("desc"):
        payload["description"] = opts["desc"]
    if opts.get("icon"):
        payload["icon"] = opts["icon"]
    if opts.get("sort"):
        payload["sortOrder"] = int(opts["sort"])
    skills = parse_skills(_multi(argv, "skill"), opts.get("skills-file"), opts.get("skills"))
    if skills:
        payload["skills"] = skills

    print("POST /links -> %s" % _dump(payload))
    status, body = _request("POST", LINKS, payload)
    if status not in (200, 201):
        die(status, body, "check `cat list` for valid categories / use link update for duplicates")
    print("OK %s" % _dump(body))
    print("新增已生效：%s / %s" % (cat_name, payload["name"]))


def link_update(argv):
    if not argv:
        sys.exit("ERROR: link update <id> [--name --url --desc --category --icon --sort --skill]\n\n" + USAGE)
    link_id = argv[0]
    opts, flags = opt_parser(argv[1:])

    data = fetch()
    cur = find_link(data, link_id)
    if not cur:
        sys.exit("ERROR: no link with id %r (run `link list`)" % link_id)

    payload = {}
    if opts.get("name") is not None:
        payload["name"] = opts["name"]
    if opts.get("url") is not None:
        payload["url"] = opts["url"]
    if opts.get("desc") is not None:
        payload["description"] = opts["desc"]
    if opts.get("icon") is not None:
        payload["icon"] = opts["icon"]
    if opts.get("sort") is not None:
        payload["sortOrder"] = int(opts["sort"])
    if opts.get("category") is not None:
        cat = find_category(data, opts["category"])
        if not cat:
            names = [c.get("name", "") for c in data.get("categories", [])]
            sys.exit("ERROR: category %r does not exist.\ncurrent categories: %s" % (opts["category"], ", ".join(names)))
        payload["category"] = cat.get("name", "")

    skills = parse_skills(_multi(argv, "skill"), opts.get("skills-file"), opts.get("skills"))
    if skills is not None:
        print("WARNING: skills is REPLACED wholesale. old value:")
        print(_dump(cur.get("skills", [])))
        print("new value:")
        print(_dump(skills))
        payload["skills"] = skills
    if opts.get("attachments"):
        print("WARNING: attachments is REPLACED wholesale. old value:")
        print(_dump(cur.get("attachments", [])))
        payload["attachments"] = json.loads(opts["attachments"])

    if not payload:
        sys.exit("ERROR: nothing to update.\n\n" + USAGE)

    print("PATCH /links/%s -> %s" % (link_id, _dump(payload)))
    if "dry-run" in flags:
        print("(--dry-run: nothing sent)")
        return
    status, body = _request("PATCH", "%s/%s" % (LINKS, link_id), payload)
    if status not in (200, 201):
        die(status, body, "run `link show %s` to inspect current values" % link_id)
    print("OK %s" % _dump(body))
    print("修改已生效：%s" % (payload.get("name") or cur.get("name")))


def link_delete(argv):
    if not argv:
        sys.exit("ERROR: link delete <id>\n\n" + USAGE)
    link_id = argv[0]
    data = fetch()
    cur = find_link(data, link_id)
    if not cur:
        sys.exit("ERROR: no link with id %r (run `link list`)" % link_id)
    print("about to DELETE: [%s] %s  %s" % (cur.get("_category"), cur.get("name"), cur.get("url")))
    status, body = _request("DELETE", "%s/%s" % (LINKS, link_id))
    if status not in (200, 204):
        die(status, body, "被别的链接 skills 引用时无法删除；先把引用方的 skills 改掉再删")
    print("OK %s" % (_dump(body) if body else "(deleted)"))


# ------------------------------------------------------------- category verbs


def cat_list(argv):
    data = fetch()
    print("%-38s %-28s %s" % ("id", "name", "links"))
    for c in data.get("categories", []):
        print("%-38s %-28s %d" % (c.get("id", ""), c.get("name", ""), len(c.get("links", []))))


def cat_add(argv):
    if not argv:
        sys.exit("ERROR: cat add <name>\n\n" + USAGE)
    name = " ".join(argv).strip()
    status, body = _request("POST", CATS, {"name": name})
    if status not in (200, 201):
        die(status, body, "重名分类会返回 409，用 `cat list` 看已有分类名")
    print("OK %s" % _dump(body))
    print("新增分类已生效：%s" % name)


def cat_rename(argv):
    if len(argv) < 2:
        sys.exit("ERROR: cat rename <id> <new name>\n\n" + USAGE)
    cat_id, new_name = argv[0], " ".join(argv[1:]).strip()
    status, body = _request("PATCH", "%s/%s" % (CATS, cat_id), {"name": new_name})
    if status not in (200, 201):
        die(status, body, "id 用 `cat list` 查；只改名，链接会自动跟随")
    print("OK %s" % _dump(body))
    print("分类改名已生效：%s（链接已自动跟随）" % new_name)


def cat_delete(argv):
    if not argv:
        sys.exit("ERROR: cat delete <id>\n\n" + USAGE)
    status, body = _request("DELETE", "%s/%s" % (CATS, argv[0]))
    if status not in (200, 204):
        die(status, body, "分类下还有链接时不能删 -> 先 `link delete` 清空")
    print("OK %s" % (_dump(body) if body else "(deleted)"))


def _multi(argv, key):
    """Collect repeated --key value occurrences in order."""
    vals, i = [], 0
    while i < len(argv):
        a = argv[i]
        if a == "--" + key and i + 1 < len(argv):
            vals.append(argv[i + 1])
            i += 2
            continue
        if a.startswith("--" + key + "="):
            vals.append(a.split("=", 1)[1])
        i += 1
    return vals


# ------------------------------------------------------------------------ main


def main():
    args = sys.argv[1:]
    if args and args[0] in ("-h", "--help", "help"):
        print(USAGE)
        return
    if not TOKEN:
        sys.exit("ERROR: nav portal token missing. Set env NAV_PORTAL_TOKEN or scripts/config.local.json\n"
                 "(read 和 write 用同一把 token)")

    if args and args[0] == "link":
        verb, rest = (args[1] if len(args) > 1 else ""), args[2:]
        table = {"list": link_list, "show": link_show, "add": link_add,
                 "update": link_update, "delete": link_delete, "rm": link_delete}
        if verb not in table:
            sys.exit("ERROR: link <list|show|add|update|delete>\n\n" + USAGE)
        return table[verb](rest)

    if args and args[0] in ("cat", "cats"):
        verb, rest = (args[1] if len(args) > 1 else "list"), args[2:]
        table = {"list": cat_list, "add": cat_add, "rename": cat_rename,
                 "delete": cat_delete, "rm": cat_delete}
        if verb not in table:
            sys.exit("ERROR: cat <list|add|rename|delete>\n\n" + USAGE)
        return table[verb](rest)

    # read / search mode
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    data = fetch()
    items = flatten(data)

    if args and args[0] == "--cats":
        print("\n".join("%s (%d links)" % (c.get("name", ""), len(c.get("links", [])))
                        for c in data.get("categories", [])))
        return

    hits = match(items, args)
    if as_json:
        print(json.dumps(hits, ensure_ascii=False, indent=2))
    else:
        print_text(hits)


if __name__ == "__main__":
    main()
