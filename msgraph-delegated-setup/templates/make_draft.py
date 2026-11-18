#!/usr/bin/env python3
"""Create (never send) an Outlook DRAFT via Microsoft Graph.

Drafts land in the Drafts folder so the user can review and send manually.

Usage:
  # plain text new draft
  python make_draft.py --to a@x.com [--cc b@x.com] --subject "Hi" --body "Hello"

  # body from file (supports utf-8 / html)
  python make_draft.py --to a@x.com --subject "Hi" --body-file body.html --html

  # reply draft to an existing message (keeps quoted thread)
  python make_draft.py --reply-to <message-id> --body "thanks"

  # with attachment(s)
  python make_draft.py --to a@x.com --subject s --body b --attach "C:\\path\\f.pdf"

Prints JSON: {"id":..., "webLink":..., "subject":...}
"""
import argparse
import base64
import json
import mimetypes
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from token_manager import get_valid_token

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _headers():
    return {
        "Authorization": f"Bearer {get_valid_token()}",
        "Content-Type": "application/json",
    }


def _addr(lst):
    out = []
    for item in lst or []:
        for a in item.split(","):
            a = a.strip()
            if a:
                out.append({"emailAddress": {"address": a}})
    return out


def _attachment(path):
    p = Path(path)
    ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    return {
        "@odata.type": "#microsoft.graph.fileAttachment",
        "name": p.name,
        "contentType": ctype,
        "contentBytes": base64.b64encode(p.read_bytes()).decode(),
    }


def create_new(args, body):
    msg = {
        "subject": args.subject or "",
        "body": {"contentType": "HTML" if args.html else "Text", "content": body},
        "toRecipients": _addr(args.to),
    }
    if args.cc:
        msg["ccRecipients"] = _addr(args.cc)
    if args.bcc:
        msg["bccRecipients"] = _addr(args.bcc)
    if args.attach:
        msg["attachments"] = [_attachment(a) for a in args.attach]

    r = requests.post(f"{GRAPH_BASE}/me/messages", headers=_headers(), json=msg, timeout=60)
    if r.status_code not in (200, 201):
        raise SystemExit(f"❌ create draft failed {r.status_code}: {r.text[:600]}")
    return r.json()


def create_reply(args, body):
    # createReply → returns a draft message with quoted original; then patch body/to
    r = requests.post(
        f"{GRAPH_BASE}/me/messages/{args.reply_to}/createReply",
        headers=_headers(),
        json={},
        timeout=60,
    )
    if r.status_code not in (200, 201):
        raise SystemExit(f"❌ createReply failed {r.status_code}: {r.text[:600]}")
    draft = r.json()

    patch = {
        "body": {"contentType": "HTML" if args.html else "Text", "content": body},
    }
    if args.to:
        patch["toRecipients"] = _addr(args.to)
    if args.cc:
        patch["ccRecipients"] = _addr(args.cc)
    if args.attach:
        patch["attachments"] = [_attachment(a) for a in args.attach]

    r2 = requests.patch(
        f"{GRAPH_BASE}/me/messages/{draft['id']}", headers=_headers(), json=patch, timeout=60
    )
    if r2.status_code not in (200, 201):
        raise SystemExit(f"❌ patch draft failed {r2.status_code}: {r2.text[:600]}")
    return r2.json()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", nargs="*", help="recipient address(es), comma or space separated")
    ap.add_argument("--cc", nargs="*")
    ap.add_argument("--bcc", nargs="*")
    ap.add_argument("--subject")
    ap.add_argument("--body", default="")
    ap.add_argument("--body-file")
    ap.add_argument("--html", action="store_true", help="treat body as HTML")
    ap.add_argument("--reply-to", help="message id to reply to (creates reply draft)")
    ap.add_argument("--attach", action="append", default=[])
    args = ap.parse_args()

    if args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8")
    else:
        body = args.body

    if args.reply_to:
        result = create_reply(args, body)
    else:
        if not args.to:
            raise SystemExit("❌ --to is required for a new draft")
        result = create_new(args, body)

    print(
        json.dumps(
            {
                "ok": True,
                "id": result.get("id"),
                "subject": result.get("subject"),
                "webLink": result.get("webLink"),
                "isDraft": result.get("isDraft"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
