#!/usr/bin/env python3
"""
Token Manager — encrypted token storage for Microsoft Graph Delegated OAuth.

Uses Fernet (symmetric AES-128-GCM) encryption with a machine-derived key
to persist Access Token + Refresh Token. Auto-refreshes when expired.

Storage:
  Encrypted file: ./.tokens.enc
  Key file:        ./.token_key
  Both chmod 600.

Required env vars:
  MSGRAPH_TENANT_ID
  MSGRAPH_DELEGATED_CLIENT_ID

Usage:
  from token_manager import get_valid_token, store_tokens, clear_tokens, is_authenticated
"""

import base64
import hashlib
import json
import os
import socket
import sys
import time
from pathlib import Path

from cryptography.fernet import Fernet

import requests

TOKEN_FILE = Path(__file__).parent / ".tokens.enc"
KEY_FILE = Path(__file__).parent / ".token_key"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"
TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

# Built-in defaults (shared Azure App). Env vars override these if set.
# These guarantee token refresh + key derivation keep working even when the
# process env does not carry MSGRAPH_* (e.g. cron runs). See report缺陷1.
_DEFAULT_TENANT_ID = "7730d043-e129-480c-b1ba-e5b6a9f476aa"
_DEFAULT_CLIENT_ID = "7ae83858-7de6-48ba-852e-2c4631961abc"


def _load_dotenv():
    """Best-effort: load MSGRAPH_* from a sibling .env if not already in env."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k.startswith("MSGRAPH_") and not os.environ.get(k):
                os.environ[k] = v
    except Exception:
        pass


_load_dotenv()


def _get_tenant_id():
    return os.environ.get("MSGRAPH_TENANT_ID") or _DEFAULT_TENANT_ID


def _get_client_id():
    return os.environ.get("MSGRAPH_DELEGATED_CLIENT_ID") or _DEFAULT_CLIENT_ID


def _derive_key() -> bytes:
    """Derive a machine-specific Fernet key from hostname + tenant_id."""
    material = f"{socket.gethostname()}:{_get_tenant_id()}:hermes-delegated-mail"
    digest = hashlib.sha256(material.encode()).digest()
    return base64.urlsafe_b64encode(digest[:32])


def _load_cipher() -> Fernet:
    """Load or create a Fernet cipher instance."""
    if not KEY_FILE.exists():
        key = _derive_key()
        KEY_FILE.write_bytes(key)
        KEY_FILE.chmod(0o600)
    else:
        key = KEY_FILE.read_bytes()
    return Fernet(key)


def store_tokens(access_token: str, refresh_token: str, expires_in: int):
    """Encrypt and persist tokens to file."""
    cipher = _load_cipher()

    data = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": int(time.time() + expires_in - 300),  # 5 min buffer
    }

    encrypted = cipher.encrypt(json.dumps(data).encode())
    TOKEN_FILE.write_bytes(encrypted)
    TOKEN_FILE.chmod(0o600)


def load_tokens() -> dict | None:
    """Load and decrypt stored tokens. Returns None if not found."""
    if not TOKEN_FILE.exists():
        return None
    try:
        cipher = _load_cipher()
        encrypted = TOKEN_FILE.read_bytes()
        decrypted = cipher.decrypt(encrypted)
        return json.loads(decrypted)
    except Exception:
        return None


def clear_tokens():
    """Delete stored tokens."""
    for f in (TOKEN_FILE, KEY_FILE):
        try:
            f.unlink(missing_ok=True)
        except Exception:
            pass


def _refresh_access_token(refresh_token: str) -> dict:
    """Use refresh token to get new access token."""
    tenant = _get_tenant_id()
    client_id = _get_client_id()

    resp = requests.post(
        TOKEN_URL.format(tenant=tenant),
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": refresh_token,
            "scope": GRAPH_SCOPE,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_valid_token() -> str:
    """
    Return a valid access token. Auto-refreshes if expired.
    Raises RuntimeError if login is needed.
    """
    tokens = load_tokens()
    if tokens is None:
        raise RuntimeError(
            "No tokens found. Run auth_login.py first to authenticate."
        )

    if time.time() < tokens["expires_at"]:
        return tokens["access_token"]

    # Token expired, try refresh
    if "refresh_token" not in tokens:
        raise RuntimeError("Access token expired and no refresh token available.")

    print("[token_manager] Refreshing expired token...", file=sys.stderr)
    try:
        new = _refresh_access_token(tokens["refresh_token"])
        store_tokens(
            access_token=new["access_token"],
            refresh_token=new.get("refresh_token", tokens["refresh_token"]),
            expires_in=new.get("expires_in", 3600),
        )
        return new["access_token"]
    except Exception as e:
        # Do NOT clear tokens on refresh failure — a transient network error or a
        # missing env var must not force a full re-auth. Keep the stored refresh
        # token so a later call can retry. Only re-auth clears tokens explicitly.
        raise RuntimeError(
            f"Token refresh failed: {e}\n"
            "Tokens preserved — retry later, or run auth_login.py to re-authenticate."
        ) from e


def is_authenticated() -> bool:
    """Check if we have stored tokens (may or may not be valid)."""
    return load_tokens() is not None


if __name__ == "__main__":
    try:
        token = get_valid_token()
        print(f"✅ Token valid, length={len(token)}")
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)
