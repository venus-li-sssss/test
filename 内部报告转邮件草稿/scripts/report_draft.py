# -*- coding: utf-8 -*-
"""把内部测试报告写成 Outlook「全部回复」草稿（只进草稿箱，绝不发送）。

用法:
    python report_draft.py --source-mail-id <ID> --body-html body.html \
        --attach "报告.xlsx" --attach "修改点报告.xlsx" [--dry-run] [--replace-draft <ID>]

流程:
    1. POST /me/messages/{source}/createReplyAll   （收件人+抄送自动带全）
    2. 取回草稿 body（含引用链），把 body-html 插到 <body> 之后，PATCH 回去
    3. 逐个上传附件（大文件 timeout 600s）
    4. 回读校验（isDraft / 收件人 / 附件 / 残留旧版本号）

--replace-draft：直接 PATCH 已有草稿，避免 createReplyAll 出重复草稿。
"""
import argparse
import base64
import io
import json
import mimetypes
import os
import re
import sys
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SKILLS = Path(r"C:\Users\venus.li\.qwenpaw\workspaces\default\scripts\delegated-outlook-ikotek")
sys.path.insert(0, str(DEFAULT_SKILLS))

from token_manager import get_valid_token  # noqa: E402

GRAPH = "https://graph.microsoft.com/v1.0"


def H():
    return {"Authorization": "Bearer %s" % get_valid_token(), "Content-Type": "application/json"}


def attachment_payload(path):
    p = Path(path)
    return {
        "@odata.type": "#microsoft.graph.fileAttachment",
        "name": p.name,
        "contentType": mimetypes.guess_type(p.name)[0] or "application/octet-stream",
        "contentBytes": base64.b64encode(p.read_bytes()).decode(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-mail-id", required=True, help="上一版测试报告邮件的 id")
    ap.add_argument("--body-html", required=True, help="改好的正文 HTML（片段或整页）")
    ap.add_argument("--attach", action="append", default=[], help="附件路径，可重复")
    ap.add_argument("--replace-draft", default=None, help="直接更新这个草稿 id")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    body_html = io.open(a.body_html, encoding="utf-8").read()

    # ---------- 1) 建/取草稿
    if a.replace_draft:
        did = a.replace_draft
        d = requests.get("%s/me/messages/%s?$select=subject,body,toRecipients,ccRecipients"
                         % (GRAPH, did), headers=H(), timeout=60).json()
        old_html = (d.get("body") or {}).get("content") or ""
    else:
        r = requests.post("%s/me/messages/%s/createReplyAll" % (GRAPH, a.source_mail_id),
                          headers=H(), json={}, timeout=60)
        if r.status_code not in (200, 201):
            raise SystemExit("createReplyAll 失败 %s: %s" % (r.status_code, r.text[:500]))
        draft = r.json()
        did = draft["id"]
        old_html = (draft.get("body") or {}).get("content") or ""
        d = draft

    to_addrs = [t["emailAddress"]["address"] for t in d.get("toRecipients", [])]
    cc_addrs = [t["emailAddress"]["address"] for t in d.get("ccRecipients", [])]
    print("草稿:", did[:28], "...")
    print("主题:", d.get("subject"))
    print("收件(%d): %s" % (len(to_addrs), ", ".join(to_addrs)))
    print("抄送(%d): %s" % (len(cc_addrs), ", ".join(cc_addrs[:14])))
    print("附件(%d): %s" % (len(a.attach), [Path(p).name for p in a.attach]))
    if a.dry_run:
        print("\n[dry-run] 未做任何修改。")
        return

    # ---------- 2) 合并正文（保留引用链）
    idx = old_html.lower().find("<body")
    if idx >= 0:
        end = old_html.find(">", idx) + 1
        merged = old_html[:end] + body_html + old_html[end:]
    else:
        merged = body_html + old_html

    r2 = requests.patch("%s/me/messages/%s" % (GRAPH, did), headers=H(),
                        json={"body": {"contentType": "HTML", "content": merged}}, timeout=120)
    print("PATCH body:", r2.status_code)
    if r2.status_code not in (200, 201):
        raise SystemExit(r2.text[:600])

    # ---------- 3) 附件（已存在同名就跳过）
    have = [x.get("name") for x in requests.get(
        "%s/me/messages/%s/attachments?$select=name" % (GRAPH, did), headers=H(),
        timeout=60).json().get("value", [])]
    for p in a.attach:
        name = Path(p).name
        if name in have:
            print("  跳过（已存在）:", name)
            continue
        rr = requests.post("%s/me/messages/%s/attachments" % (GRAPH, did), headers=H(),
                           json=attachment_payload(p), timeout=900)
        print("  上传 %s -> %s (%.2f MB)" % (name, rr.status_code, Path(p).stat().st_size / 1048576))
        if rr.status_code not in (200, 201):
            print("     ERR:", rr.text[:300])

    # ---------- 4) 回读校验
    d2 = requests.get("%s/me/messages/%s?$select=subject,isDraft,body,hasAttachments,webLink"
                      % (GRAPH, did), headers=H(), timeout=120).json()
    atts = requests.get("%s/me/messages/%s/attachments?$select=name,size" % (GRAPH, did),
                        headers=H(), timeout=60).json().get("value", [])
    txt = re.sub(r"<[^>]+>", " ", d2.get("body", {}).get("content") or "")
    print("\n=== 回读 ===")
    print("isDraft:", d2.get("isDraft"), "| hasAttachments:", d2.get("hasAttachments"))
    print("附件:", [(x["name"], round(x.get("size", 0) / 1048576, 2)) for x in atts
                    if not x["name"].startswith("image")])
    for pat in ("_763", "当前报告的版本"):
        if pat in txt:
            print("⚠ 正文里还有:", pat)
    print("webLink:", d2.get("webLink"))


if __name__ == "__main__":
    main()
