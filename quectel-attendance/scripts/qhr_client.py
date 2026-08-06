#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quectel QHR (hr.quectel.com) 考勤客户端
- SSO 登录 (RSA 加密密码 -> uaa oauth token -> hr session)
- 拉取月度打卡明细 (SE0302) 与日考勤汇总 (SE0398)
"""
import base64
import json
import sys
import requests
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

SSO = "https://sso-web.quectel.com"
HR = "https://hr.quectel.com"
SSOTOKEN = "6DehZxYDUzhQJ9hk"
APP = "G8_TRwtFegd0QeO2BfN6kg"  # 我的考勤 应用 key

PUBKEY = (
    "-----BEGIN PUBLIC KEY-----\n"
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAre5YnMJtO+gtwkeeq07f"
    "5UfywHM2LQ5T4jzVzYUYJOQN0AUAYkmoIt7rIfAN6q5nEby3zupXznBo/Y5SsRtX"
    "DoG53xHucpqE5SXD4J6kNnxj+JjecQ7ef0ev5MTOb+eREybymosgs7xr/eprv2O4"
    "GmipUwXVTWusbL/xjPzfP603JGz/r6xR94k5K8NXqHLQVBKURa5QK3x9sUyX5ZxY"
    "op6llF3BdkIafB8aERw5iJa7i8fFK6UmIbhGQ8rLYYGj61229NayMgIuWJ3SGmUW"
    "Wq0RyCEjt96I6ZWwOqygkiEXj3PoQEmTUIxmEgrWQ5UxSHT/XDai5sbj7IueMqnc"
    "PQIDAQAB\n-----END PUBLIC KEY-----"
)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0")


def rsa_enc(text: str) -> str:
    cipher = PKCS1_v1_5.new(RSA.import_key(PUBKEY))
    return base64.b64encode(cipher.encrypt(text.encode())).decode()


class QHR:
    def __init__(self, username, password):
        self.u, self.p = username, password
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "terminal": "web",
                               "devicesn": "bcd6de4cea58f2261fab3ee5ddb95320"})

    def login(self):
        s = self.s
        s.cookies.set("quectel_lang", "cn", domain="sso-web.quectel.com")
        ref = (f"{SSO}/login?grant_type=login&oauth_callback="
               f"https%3A%2F%2Fhr.quectel.com%2Fcustom%2Fpcsso%3Fssotoken%3D{SSOTOKEN}")
        h = {"Origin": SSO, "Referer": ref}

        # 1. MFA 检查（同时验证账号密码）
        r = s.post(f"{SSO}/api/uaa/mfa-open/check",
                   json={"username": self.u, "password": rsa_enc(self.p)},
                   headers=h, timeout=30)
        try:
            mfa = r.json().get("data") or {}
            if mfa.get("isPass") is False:
                raise RuntimeError(f"账号密码校验失败: {mfa.get('errorMessage')}")
        except ValueError:
            pass

        # 2. 换 token
        r = s.post(f"{SSO}/api/uaa/oauth/token",
                   data={"grant_type": "password", "username": self.u,
                         "password": rsa_enc(self.p), "scope": "ui",
                         "client_id": "quectel", "client_secret": "quectel",
                         "auth_type": "rsa_area"},
                   headers={**h, "Content-Type": "application/x-www-form-urlencoded"},
                   timeout=30)
        tok = r.json()
        access = (tok.get("access_token") or tok.get("data", {}).get("access_token")
                  if isinstance(tok, dict) else None)
        if not access:
            raise RuntimeError(f"登录失败: {json.dumps(tok, ensure_ascii=False)[:400]}")
        bearer = access if access.startswith("bearer") else "bearer" + access

        # 3. 用 token 换 HR 会话
        s.get(f"{HR}/custom/pcsso?ssotoken={SSOTOKEN}&lang=cn", timeout=30)
        s.post(f"{HR}/?ssotoken={SSOTOKEN}&lang=cn",
               data={"tk": bearer, "quectel_token": bearer, "lang": "cn"},
               headers={"Content-Type": "application/x-www-form-urlencoded",
                        "Origin": HR, "Referer": f"{HR}/custom/pcsso?ssotoken={SSOTOKEN}&lang=cn"},
               timeout=30)
        s.get(f"{HR}/view/portal/index", timeout=30)
        s.get(f"{HR}/view/app/app!{APP}", timeout=30)
        return self

    def _ajax(self, path, payload):
        r = self.s.post(f"{HR}/ajax/function/{path}", json=payload,
                        headers={"Content-Type": "application/json",
                                 "X-Requested-With": "XMLHttpRequest",
                                 "Referer": f"{HR}/view/app/app!{APP}"}, timeout=30)
        try:
            return r.json()
        except Exception:
            raise RuntimeError(f"{path} 返回非 JSON（会话可能失效）: {r.text[:200]}")

    def punches(self, month):
        """month: 'YYYY-MM' -> [{'CARDTIME','SHIFTTERM'}...] 原始打卡记录"""
        p = {"appParam": {"TERM": f"{month}-01T00:00:00.000Z"},
             "appFnKey": "SE0302", "formData": {}}
        return self._ajax(f"alist!{APP}.220302", p)

    def daily(self, month):
        """month: 'YYYY-MM' -> 每日班次/迟到/缺勤汇总"""
        p = {"appParam": {"TERM": f"{month}-01T00:00:00.000Z"},
             "appFnKey": "SE0398", "formData": {}}
        return self._ajax(f"alist!{APP}.220398", p)


if __name__ == "__main__":
    import os
    c = QHR(os.environ["QHR_USER"], os.environ["QHR_PASS"]).login()
    m = sys.argv[1] if len(sys.argv) > 1 else "2026-08"
    print(json.dumps({"punches": c.punches(m), "daily": c.daily(m)}, ensure_ascii=False))
