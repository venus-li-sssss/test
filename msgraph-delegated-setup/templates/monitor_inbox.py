#!/usr/bin/env python3
"""
Cron-friendly email monitor — check folder for new unread mail.
Silent exit (0) when no new mail; outputs formatted message when there are new emails.

Usage: python monitor_inbox.py <folder_path_or_id>
Environment: MONITOR_LOOKBACK_MINUTES (default 10), MONITOR_MAX_RESULTS (default 5)
"""
import os, sys
from datetime import datetime, timedelta, timezone
from graph_mail import GraphMailClient, parse_folder_path

LOOKBACK = int(os.environ.get("MONITOR_LOOKBACK_MINUTES", 10))
MAX_RESULTS = int(os.environ.get("MONITOR_MAX_RESULTS", 5))

def main():
    if len(sys.argv) < 2:
        print("Usage: monitor_inbox.py <folder_path>", file=sys.stderr)
        sys.exit(1)

    folder_path = sys.argv[1]

    try:
        client = GraphMailClient()
        # Use directly if it's a Graph folder ID
        if "/" not in folder_path and len(folder_path) > 50:
            folder_id = folder_path
        else:
            folder_id = parse_folder_path(client, folder_path)

        since = (datetime.now(timezone.utc) - timedelta(minutes=LOOKBACK)).isoformat()
        messages = client.list_messages(top=MAX_RESULTS, unread_only=True, folder=folder_id,
                                        select="id,subject,from,receivedDateTime,isRead,bodyPreview,hasAttachments")
        new = [m for m in messages if m.get("receivedDateTime", "") >= since]

        if not new:
            sys.exit(0)  # Silent — no notification

        folder_display = folder_path.split("/")[-1]
        lines = [f"📬 【{folder_display}】新邮件通知", f"最近 {LOOKBACK} 分钟内 {len(new)} 封新邮件", ""]
        for i, m in enumerate(new, 1):
            sender = "?"
            if m.get("from") and m["from"].get("emailAddress"):
                ea = m["from"]["emailAddress"]
                sender = ea.get("name") or ea.get("address", "?")
            preview = (m.get("bodyPreview") or "")[:200].replace("\r", "").replace("\n", " ")
            lines.append(f"{i}. {m.get('subject', '(无主题)')}")
            lines.append(f"   发件人: {sender}  |  {m.get('receivedDateTime', '?')}")
            if preview: lines.append(f"   摘要: {preview}")
        print("\n".join(lines))

    except Exception as e:
        print(f"❌ Monitor error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
