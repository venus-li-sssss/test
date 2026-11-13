# -*- coding: utf-8 -*-
"""Regenerate references/catalog.md from the live navigation API.

Usage:
    python gen_catalog.py            # rewrite ../references/catalog.md
    python gen_catalog.py --out X.md

Only touches the local snapshot file; the API call is a plain GET.
"""
import datetime
import json
import os
import pathlib
import re
import sys
import urllib.request

# 导航条目的 description 里偶尔会贴进真实 token。生成的快照要提交进公开仓库，
# 所以落盘前必须脱敏（实测：不脱敏会被 GitHub push protection 直接 422 拦下）。
SECRET_PATTERNS = [
    re.compile(r"gh[pousr]_[0-9A-Za-z]{20,}"),
    re.compile(r"github_pat_[0-9A-Za-z_]{20,}"),
    re.compile(r"sk-[0-9A-Za-z\-_]{20,}"),
    re.compile(r"(?i)(bearer\s+)[0-9A-Za-z\-_.]{20,}"),
    re.compile(r"(?i)(token|key|secret|密码)\s*[:=：]\s*[0-9A-Za-z\-_.]{16,}"),
]


def redact(text):
    for pat in SECRET_PATTERNS:
        text = pat.sub(lambda m: (m.group(1) if m.groups() else "") + "***已脱敏（原值见导航页面该条目）***", text)
    return text

API = "https://scnrhostplnc.feishuapp.com/app/app_17fwfnp4pvy/openapi/nav/links"
_cfg = pathlib.Path(__file__).parent / "config.local.json"
TOKEN = os.environ.get("NAV_PORTAL_TOKEN") or (
    json.loads(_cfg.read_text(encoding="utf-8")).get("nav_portal_token", "") if _cfg.exists() else ""
)
if not TOKEN:
    sys.exit("ERROR: nav portal token missing (env NAV_PORTAL_TOKEN or scripts/config.local.json)")

PLACEHOLDER = ("还没做", "占位", "还在完善", "未实现")


def status_of(link):
    if link.get("skills"):
        return "✅"
    desc = link.get("description") or ""
    return "🚧" if any(p in desc for p in PLACEHOLDER) else "🔗"


def cell(text):
    return redact((text or "").replace("|", "/").replace("\n", " "))


def main():
    out_path = pathlib.Path(__file__).parent.parent / "references" / "catalog.md"
    if "--out" in sys.argv:
        out_path = pathlib.Path(sys.argv[sys.argv.index("--out") + 1])

    req = urllib.request.Request(API, headers={"Authorization": "Bearer " + TOKEN})
    data = json.load(urllib.request.urlopen(req, timeout=20))
    cats = data.get("categories", [])

    today = datetime.date.today().isoformat()
    lines = [
        "# 导航目录快照（%s）" % today,
        "",
        "> 静态快照，仅供快速了解全貌。**实时状态以 `python scripts/nav.py <关键词>` 为准**；"
        "写入（增删改）前用 `cat list` / `link list` 取 id。",
        "> 图例：✅ 已有 GitHub skill 可自动化；🔗 仅链接（文档/系统，无 skill）；🚧 占位/未实现。",
        "",
    ]
    total = 0
    for c in cats:
        links = c.get("links", [])
        total += len(links)
        lines.append("## %s（%d 条）" % (cell(c.get("name", "")), len(links)))
        lines.append("")
        if not links:
            lines += ["（空分类）", ""]
            continue
        lines.append("| 入口 | 状态 | 关联 skill / 说明 |")
        lines.append("|---|---|---|")
        for l in links:
            sk = l.get("skills") or []
            if sk:
                det = "<br>".join(
                    "%s -- %s" % (cell(s.get("url", "")), cell(s.get("description", ""))) for s in sk
                )
            else:
                det = cell(l.get("description", ""))
            lines.append("| %s | %s | %s |" % (cell(l.get("name", "")), status_of(l), det))
        lines.append("")

    lines += [
        "## 写入接口速查",
        "",
        "读、写**同一把 Key、同一个前缀**"
        " `https://scnrhostplnc.feishuapp.com/app/app_17fwfnp4pvy/openapi/nav`，写库后页面立即生效。",
        "",
        "| 方法 | 路径 | 用途 |",
        "|---|---|---|",
        "| POST | `/links` | 新增链接，分类必须已存在 |",
        "| PATCH | `/links/{id}` | 修改链接，只改传入字段 |",
        "| DELETE | `/links/{id}` | 删除链接，被引用时拒绝 |",
        "| GET | `/categories` | 分类列表，拿分类 id |",
        "| POST | `/categories` | 新增分类 |",
        "| PATCH | `/categories/{id}` | 分类改名，链接自动跟随 |",
        "| DELETE | `/categories/{id}` | 删除空分类 |",
        "",
        "脚本封装：`nav.py cat add|rename|delete`、`nav.py link add|update|delete`。",
        "",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print("wrote %s  (%d categories, %d links)" % (out_path, len(cats), total))


if __name__ == "__main__":
    main()
