#!/usr/bin/env python3
"""
OAuth2 Device Code Login — WSL-friendly authentication for Microsoft Graph.
User visits https://microsoft.com/devicelogin and enters a code displayed in terminal.
Produces Delegated tokens scoped to /me/* endpoints.

Required env vars: MSGRAPH_TENANT_ID, MSGRAPH_DELEGATED_CLIENT_ID
  (token_manager.py has hardcoded fallback defaults, so these are optional)

Usage:
  # Full interactive flow (human runs it directly):
  python auth_login.py

  # Agent flow — Step 1: get device code only (prints JSON for agent to parse):
  python auth_login.py --request

  # Agent flow — Step 2: poll with a known device_code (after user confirmed login):
  python auth_login.py --poll <device_code>
"""
import os, sys, time, json, subprocess
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from token_manager import store_tokens, clear_tokens, is_authenticated, _get_tenant_id, _get_client_id

AUTHORITY = "https://login.microsoftonline.com/{tenant}"
SCOPES = ["openid","profile","offline_access","User.Read","Mail.ReadWrite","Mail.Send","Calendars.ReadWrite"]
POLL_INTERVAL, MAX_WAIT = 5, 300

def request_device_code(tenant_id, client_id):
    resp = requests.post(AUTHORITY.format(tenant=tenant_id)+"/oauth2/v2.0/devicecode",
                         data={"client_id":client_id,"scope":" ".join(SCOPES)}, timeout=30)
    resp.raise_for_status()
    return resp.json()

def poll_for_token(tenant_id, client_id, device_code):
    url = AUTHORITY.format(tenant=tenant_id)+"/oauth2/v2.0/token"
    data = {"grant_type":"urn:ietf:params:oauth:grant-type:device_code","client_id":client_id,"device_code":device_code}
    start = time.time()
    while time.time()-start < MAX_WAIT:
        resp = requests.post(url, data=data, timeout=15)
        result = resp.json()
        if "access_token" in result: return result
        err = result.get("error","")
        if err == "authorization_pending": time.sleep(POLL_INTERVAL); continue
        elif err == "slow_down": time.sleep(POLL_INTERVAL+2); continue
        elif err == "expired_token": raise RuntimeError("Device code expired. Try again.")
        elif err == "authorization_declined": raise RuntimeError("Authorization declined.")
        else: raise RuntimeError(f"Unexpected: {result}")
    raise RuntimeError("Timed out waiting for device login.")

def verify_and_show(access_token):
    """Verify token works by calling /me."""
    me = requests.get("https://graph.microsoft.com/v1.0/me",
                      headers={"Authorization":f"Bearer {access_token}"},timeout=15).json()
    print(f"  👤 {me.get('displayName')} ({me.get('mail') or me.get('userPrincipalName')})")
    print("🎉 Setup complete!")

# ── Mode 1: --request (agent gets device code only) ──
def mode_request():
    """Get a device code, print JSON for agent to parse. No polling."""
    tenant_id = _get_tenant_id()
    client_id = _get_client_id()
    if not tenant_id or not client_id:
        print("ERROR: TENANT_ID and CLIENT_ID must be available (env or defaults).", file=sys.stderr)
        sys.exit(1)
    try:
        device = request_device_code(tenant_id, client_id)
    except requests.HTTPError as e:
        body = e.response.text[:500] if e.response else ""
        print(f"❌ HTTP error: {e}\n   {body}", file=sys.stderr)
        sys.exit(1)
    # Print JSON for agent to parse device_code + user_code
    print(json.dumps({
        "user_code": device["user_code"],
        "device_code": device["device_code"],
        "verification_uri": device.get("verification_uri", "https://microsoft.com/devicelogin"),
        "expires_in": device.get("expires_in", 900),
    }))

# ── Mode 2: --poll <device_code> (agent polls after user confirmed) ──
def mode_poll(device_code):
    """Poll for token using a known device_code. Store on success."""
    tenant_id = _get_tenant_id()
    client_id = _get_client_id()
    if not tenant_id or not client_id:
        print("ERROR: TENANT_ID and CLIENT_ID must be available (env or defaults).", file=sys.stderr)
        sys.exit(1)
    try:
        tokens = poll_for_token(tenant_id, client_id, device_code)
    except RuntimeError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
    store_tokens(tokens["access_token"], tokens["refresh_token"], tokens["expires_in"])
    print("✅ Tokens stored!")
    verify_and_show(tokens["access_token"])

# ── Mode 3: default (full interactive flow for humans) ──
def mode_interactive():
    """Full flow: get code → show user → poll → store. For direct human use."""
    tenant_id = _get_tenant_id()
    client_id = _get_client_id()
    if not tenant_id or not client_id:
        print("ERROR: MSGRAPH_TENANT_ID and MSGRAPH_DELEGATED_CLIENT_ID must be set."); sys.exit(1)
    print(f"Tenant ID: {tenant_id}\nClient ID: {client_id}\nScopes: {' '.join(SCOPES)}\n")
    if is_authenticated():
        print("⚠️ Existing tokens found. Overwrite?")
        if input("Continue? [y/N]: ").strip().lower() != "y": print("Aborted."); return
        clear_tokens()
    print("Requesting device code...")
    try: device = request_device_code(tenant_id, client_id)
    except requests.HTTPError as e:
        body = e.response.text[:500] if e.response else ""
        print(f"❌ HTTP error: {e}\n   {body}")
        if "AADSTS700016" in body: print("App not found. Check client_id.")
        elif "unsupported_grant_type" in body.lower(): print("Enable 'Allow public client flows' in Azure Portal.")
        sys.exit(1)
    print(f"\n{'='*60}\n  Open: https://microsoft.com/devicelogin\n  Enter code: {device['user_code']}\n{'='*60}\n")
    try: subprocess.run(["cmd.exe","/c","start","https://microsoft.com/devicelogin"],timeout=3,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    except: pass
    print("⏳ Waiting for login...")
    try: tokens = poll_for_token(tenant_id, client_id, device["device_code"])
    except RuntimeError as e: print(f"❌ {e}"); sys.exit(1)
    store_tokens(tokens["access_token"], tokens["refresh_token"], tokens["expires_in"])
    print("✅ Tokens stored!")
    verify_and_show(tokens["access_token"])

if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--request":
        mode_request()
    elif args and args[0] == "--poll":
        if len(args) < 2:
            print("Usage: auth_login.py --poll <device_code>", file=sys.stderr)
            sys.exit(1)
        mode_poll(args[1])
    else:
        mode_interactive()
