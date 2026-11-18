#!/usr/bin/env python3
"""
Cron-friendly direct-address email monitor (message-ID based dedup).

Only alerts when: user in To: (not CC) AND body has direct greeting.
Uses message IDs for dedup — never misses emails, even if cron is delayed.
Queries ALL folders (not just inbox) — Outlook rules route TO emails elsewhere.

State file: ~/.hermes/profiles/main-assistant/run/monitor_direct_state.json
Usage: python monitor_direct.py
Environment: MONITOR_MAX_RESULTS (default 20), MONITOR_MY_NAMES (optional),
             MONITOR_EXCLUDE_SENDERS (comma-separated, e.g. "bpm@info.quectel.com")
"""

import json, os, re, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from graph_mail import GraphMailClient, GraphMailError
from token_manager import get_valid_token
import requests

MAX_RESULTS = int(os.environ.get("MONITOR_MAX_RESULTS", 20))
MY_NAMES_ENV = os.environ.get("MONITOR_MY_NAMES", "")
EXCLUDE_SENDERS = os.environ.get("MONITOR_EXCLUDE_SENDERS", "").lower()

STATE_FILE = Path(os.path.expanduser("~/.hermes/profiles/main-assistant/run/monitor_direct_state.json"))

GREETING_PREFIXES = r'(hi|hello|dear|hey|hi\s+there|good\s+(morning|afternoon|evening))\b'
GREETING_SUFFIXES = r'(你好|您好|在吗|在么|请|麻烦)'

# ── System email filters (auto-generated, not from humans) ──
SYSTEM_SENDERS = re.compile(
    r'(bpm@|noreply@|no-reply@|donotreply@|do_not_reply@|'
    r'notification@|notifications@|alert@|alerts@|'
    r'system@|admin@|automated@|auto@)', re.IGNORECASE)
SYSTEM_SUBJECTS = re.compile(
    r'(BPM审批|BPM Approve|DO NOT REPLY|Updates for|'
    r'consent request|待入职人员通知|'
    r'Quectel Ticket Notice|QHR|月度提单|日报|周报|'
    r'资源更新通知|验证码|OTP|Auto-Reply|自动答复|Out of Office)', re.IGNORECASE)
SYSTEM_BODY_PATTERNS = re.compile(
    r'(BPM系统平台中有一项新的审批|BPM Approve Notice|'
    r'您在BPM系统平台|You have a new approval)', re.IGNORECASE)

def is_system_email(message):
    """Check if this is an auto-generated system email, not from a human."""
    sender_addr = ""
    if message.get('from') and message['from'].get('emailAddress'):
        sender_addr = message['from']['emailAddress'].get('address', '') or ''
    if SYSTEM_SENDERS.search(sender_addr): return True
    if SYSTEM_SUBJECTS.search(message.get('subject', '') or ''): return True
    body = (message.get('bodyPreview') or '') + ' '
    fb = message.get('body', {})
    if fb: body += fb.get('content', '')[:500]
    if SYSTEM_BODY_PATTERNS.search(body): return True
    return False


def build_greeting_pattern(names):
    escaped = [re.escape(n) for n in names if n and len(n) >= 2]
    name_alt = '|'.join(escaped)
    patterns = [
        rf'\b{GREETING_PREFIXES}\s+({name_alt})\b',
        rf'({name_alt})\s*[,，]\s*{GREETING_SUFFIXES}',
        rf'({name_alt})\s*[:：]',
        rf'@({name_alt})\b',
    ]
    return re.compile('|'.join(patterns), re.IGNORECASE)


def get_my_names(access_token):
    if MY_NAMES_ENV:
        return [n.strip() for n in MY_NAMES_ENV.split(',') if n.strip() and len(n.strip()) >= 2]
    resp = requests.get('https://graph.microsoft.com/v1.0/me',
                        headers={'Authorization': f'Bearer {access_token}'}, timeout=10)
    me = resp.json()
    names = set()
    if me.get('givenName'): names.add(me['givenName'])
    if me.get('displayName'):
        parts = re.split(r'[()（）\s]+', me['displayName'])
        for p in parts:
            p = p.strip()
            if p and (len(p) >= 2 and not p.isascii()) or (p.isascii() and len(p) >= 3):
                names.add(p)
    for n in list(names):
        if '.' in n: names.add(n.split('.')[0])
    return [n for n in names if len(n) >= 2]


def load_state():
    if STATE_FILE.exists():
        try: return json.loads(STATE_FILE.read_text())
        except: pass
    return {}


def save_state(last_id):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({
        "last_seen_id": last_id,
        "last_seen_time": datetime.now(timezone.utc).isoformat(),
    }))


def is_in_to_recipients(message, my_email):
    for r in message.get('toRecipients', []):
        if my_email.lower() in (r.get('emailAddress', {}).get('address') or '').lower():
            return True
    return False


def is_excluded_sender(message):
    if not EXCLUDE_SENDERS: return False
    addr = ''
    if message.get('from') and message['from'].get('emailAddress'):
        addr = (message['from']['emailAddress'].get('address') or '').lower()
    return any(ex in addr for ex in EXCLUDE_SENDERS.split(','))


def has_direct_greeting(message, pattern):
    body = (message.get('bodyPreview') or '') + ' '
    fb = message.get('body', {})
    if fb: body += fb.get('content', '')[:500]
    return bool(pattern.search(body))


def main():
    try:
        client = GraphMailClient()
        token = get_valid_token()
        me = client.get_me()
        my_email = me.get('mail') or me.get('userPrincipalName') or ''
        my_names = get_my_names(token)
        if not my_names:
            print("❌ Could not determine names. Set MONITOR_MY_NAMES.", file=sys.stderr)
            sys.exit(1)

        greeting_re = build_greeting_pattern(my_names)
        state = load_state()
        last_seen_id = state.get("last_seen_id", "")

        # Query ALL folders (Outlook rules route TO emails outside inbox)
        select = "id,subject,from,receivedDateTime,isRead,bodyPreview,body,toRecipients,ccRecipients"
        params = {"$top": MAX_RESULTS, "$orderby": "receivedDateTime desc",
                  "$select": select, "$filter": "isRead eq false"}
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        messages = client._request("GET", f"/me/messages?{qs}").get("value", [])

        matches = []
        for m in messages:
            msg_id = m.get('id', '')
            if msg_id == last_seen_id: break
            if not is_in_to_recipients(m, my_email): continue
            if is_system_email(m): continue
            if not has_direct_greeting(m, greeting_re): continue
            matches.append(m)

        if messages:
            new_top_id = messages[0].get('id', '')
            if new_top_id and (not last_seen_id or new_top_id != last_seen_id):
                save_state(new_top_id)

        if not matches: sys.exit(0)

        lines = ["📬 【直接点名】需要你回复的邮件", f"{len(matches)} 封", ""]
        for i, m in enumerate(matches, 1):
            sender = "?"
            if m.get("from") and m["from"].get("emailAddress"):
                ea = m["from"]["emailAddress"]
                sender = ea.get("name") or ea.get("address", "?")
            subject = m.get("subject", "(无主题)")
            received_time = m.get("receivedDateTime", "?")
            preview = (m.get("bodyPreview") or "")[:200].replace('\r', '').replace('\n', ' ')
            lines.append(f"{i}. {subject}")
            lines.append(f"   发件人: {sender}  |  {received_time}")
            if preview: lines.append(f"   摘要: {preview}")
        print("\n".join(lines))

    except Exception as e:
        print(f"❌ Direct monitor error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
