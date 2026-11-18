#!/usr/bin/env python3
"""
Microsoft Graph API wrapper — /me/* endpoints (Delegated OAuth mode).
All operations scoped to the currently signed-in user.
"""
import json, sys, time, re
from typing import Any
import requests
from token_manager import get_valid_token

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

class GraphMailError(Exception):
    def __init__(self, message, status_code=0, response_body=""):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body

class GraphMailClient:
    def __init__(self):
        self._base = GRAPH_BASE

    def _headers(self):
        return {"Authorization": f"Bearer {get_valid_token()}", "Content-Type": "application/json"}

    def _request(self, method, path, **kwargs):
        url = f"{self._base}{path}"
        resp = requests.request(method, url, headers=self._headers(), **kwargs, timeout=30)
        if resp.status_code == 200: return resp.json()
        if resp.status_code == 401:
            time.sleep(0.5)
            resp = requests.request(method, url, headers=self._headers(), **kwargs, timeout=30)
        if resp.status_code == 200: return resp.json()
        raise GraphMailError(f"Graph API error: {resp.status_code}", resp.status_code, resp.text[:500])

    def get_me(self):
        return self._request("GET", "/me")

    def list_messages(self, top=10, unread_only=False, folder="inbox", select=None):
        if select is None: select = "id,subject,from,receivedDateTime,isRead,bodyPreview,hasAttachments"
        params = {"$top": top, "$orderby": "receivedDateTime desc", "$select": select}
        if unread_only: params["$filter"] = "isRead eq false"
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return self._request("GET", f"/me/mailFolders/{folder}/messages?{qs}").get("value", [])

    def get_message(self, message_id, body_type="text"):
        select = "id,subject,from,receivedDateTime,isRead,body,bodyPreview,hasAttachments,toRecipients,ccRecipients"
        result = self._request("GET", f"/me/messages/{message_id}?$select={select}")
        body = result.get("body", {})
        if body_type == "text" and body.get("contentType") == "html":
            content = re.sub(r"<[^>]+>", " ", body.get("content", ""))
            result["body_preview_clean"] = re.sub(r"\s+", " ", content).strip()[:2000]
        return result

    def mark_read(self, message_id, is_read=True):
        return self._request("PATCH", f"/me/messages/{message_id}", json={"isRead": is_read})

    def move_message(self, message_id, destination_folder_id):
        return self._request("POST", f"/me/messages/{message_id}/move", json={"destinationId": destination_folder_id})

    def delete_message(self, message_id):
        resp = requests.delete(f"{self._base}/me/messages/{message_id}", headers=self._headers(), timeout=30)
        if resp.status_code not in (204, 200): raise GraphMailError(f"Delete failed: {resp.status_code}")

    def send_mail(self, to, subject, body, content_type="Text", cc=None):
        to_list = [to] if isinstance(to, str) else to
        cc_list = [cc] if isinstance(cc, str) else (cc or [])
        msg = {"subject": subject, "body": {"contentType": content_type, "content": body},
               "toRecipients": [{"emailAddress": {"address": a}} for a in to_list]}
        if cc_list: msg["ccRecipients"] = [{"emailAddress": {"address": a}} for a in cc_list]
        return self._request("POST", "/me/sendMail", json={"message": msg})

    def reply_mail(self, message_id, body):
        draft = self._request("POST", f"/me/messages/{message_id}/createReply", json={"comment": body})
        return self._request("POST", f"/me/messages/{draft['id']}/send")

    def search_messages(self, query, folder="inbox", top=10, select_fields=None):
        if select_fields is None: select_fields = "id,subject,from,receivedDateTime,isRead,bodyPreview,hasAttachments"
        path = f"/me/mailFolders/{folder}/messages?$search=\"{query}\"&$top={top}&$select={select_fields}"
        headers = self._headers(); headers["ConsistencyLevel"] = "eventual"
        resp = requests.get(f"{self._base}{path}", headers=headers, timeout=30)
        if resp.status_code == 200: return resp.json().get("value", [])
        raise GraphMailError(f"Search failed: {resp.status_code}")

    def list_folders(self):
        return self._request("GET", "/me/mailFolders?$top=50").get("value", [])

    def get_child_folders(self, parent_folder_id):
        return self._request("GET", f"/me/mailFolders/{parent_folder_id}/childFolders?$top=50").get("value", [])

    def list_events(self, start=None, end=None, top=10):
        select = "id,subject,start,end,location,organizer"
        path = f"/me/events?$top={top}&$select={select}&$orderby=start/dateTime asc"
        if start: path += f"&$filter=start/dateTime ge '{start}'"
        if end: path += f" and end/dateTime le '{end}'"
        return self._request("GET", path).get("value", [])

    def create_event(self, subject, start_time, end_time, timezone="China Standard Time", location=None, body=""):
        event = {"subject": subject, "start": {"dateTime": start_time, "timeZone": timezone},
                 "end": {"dateTime": end_time, "timeZone": timezone}}
        if body: event["body"] = {"contentType": "Text", "content": body}
        if location: event["location"] = {"displayName": location}
        return self._request("POST", "/me/events", json=event)

    def delete_event(self, event_id):
        resp = requests.delete(f"{self._base}/me/events/{event_id}", headers=self._headers(), timeout=30)
        if resp.status_code not in (204, 200): raise GraphMailError(f"Delete event failed: {resp.status_code}")


def parse_folder_path(client, folder_path):
    """Parse a folder path or direct Graph folder ID."""
    if "/" not in folder_path and len(folder_path) > 50: return folder_path
    parts = folder_path.strip("/").split("/")
    well_known = {"inbox": "inbox", "收件箱": "inbox", "sentitems": "sentitems", "drafts": "drafts", "deleteditems": "deleteditems"}
    current_id = well_known.get(parts[0].lower())
    if current_id is None:
        root = client.list_folders()
        found = next((f for f in root if f.get("displayName") == parts[0]), None)
        if not found: raise GraphMailError(f"Root folder not found: '{parts[0]}'")
        current_id = found["id"]
    for part in parts[1:]:
        children = client.get_child_folders(current_id)
        found = next((f for f in children if f.get("displayName") == part), None)
        if not found: raise GraphMailError(f"Folder not found: '{part}'")
        current_id = found["id"]
    return current_id


if __name__ == "__main__":
    try:
        client = GraphMailClient()
        me = client.get_me()
        print(f"👤 {me.get('displayName')} ({me.get('userPrincipalName')})")
        msgs = client.list_messages(top=3)
        print(f"📬 Recent 3 messages:")
        for m in msgs:
            s = m.get('from',{}).get('emailAddress',{}).get('name','?') or '?'
            print(f"  [{  m.get('isRead') and '✓' or '●'}] {m.get('subject','(none)')[:50]} — {s}")
        print("✅ graph_mail.py working!")
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
