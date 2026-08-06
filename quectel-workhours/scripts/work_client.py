#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
移远工时系统 (work.ikotek.com) API 客户端
- SSO 登录
- 获取工时列表
- 获取项目列表
- 提交工时
"""
import base64
import json
import sys
import requests
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

SSO = "https://sso.ikotek.com"
WORK = "https://work.ikotek.com"

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


class WorkClient:
    def __init__(self, username, password):
        self.u, self.p = username, password
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA})
        self.user_id = None
        self.token = None

    def login(self):
        """SSO 登录获取 token"""
        s = self.s
        s.cookies.set("quectel_lang", "cn", domain="sso.ikotek.com")

        # 1. 获取 token
        r = s.post(f"{SSO}/api/uaa/oauth/token",
                   data={"grant_type": "password", "username": self.u,
                         "password": rsa_enc(self.p), "scope": "ui",
                         "client_id": "quectel", "client_secret": "quectel",
                         "auth_type": "rsa_area"},
                   headers={"terminal": "web",
                            "devicesn": "bcd6de4cea58f2261fab3ee5ddb95320"},
                   timeout=30)
        tok = r.json()
        access = tok.get("access_token") or tok.get("data", {}).get("access_token")
        if not access:
            raise RuntimeError(f"登录失败: {json.dumps(tok, ensure_ascii=False)[:400]}")

        # Normalize token format
        if not access.startswith("bearer"):
            access = "bearer" + access
        self.token = access

        # 2. 设置认证头
        s.headers.update({"Authorization": access})
        s.cookies.set("quectel_token", access, domain="work.ikotek.com")

        # 3. 访问 work.ikotek.com 建立会话
        s.get(f"{WORK}/", timeout=30)
        return self

    def _get(self, path, params=None):
        r = self.s.get(f"{WORK}{path}", params=params, timeout=30)
        return r.json()

    def _post(self, path, data=None):
        r = self.s.post(f"{WORK}{path}", json=data, timeout=30)
        return r.json()

    def _put(self, path, data=None):
        r = self.s.put(f"{WORK}{path}", json=data, timeout=30)
        return r.json()

    def get_projects(self):
        """获取项目列表"""
        resp = self._get("/api/mh/project-info/project-name")
        if resp.get("success"):
            return resp["data"]
        return []

    def get_work_list(self, start_time, end_time):
        """获取工时列表"""
        resp = self._post("/api/mh/work-info/list", {
            "status": "",
            "startTime": start_time,
            "endTime": end_time,
            "orderDirection": "",
            "orderBy": ""
        })
        if resp.get("success"):
            return resp["data"]
        return []

    def get_work_detail(self, work_id):
        """获取工时详情"""
        resp = self._post("/api/mh/work-info/detail", {"id": str(work_id)})
        if resp.get("success"):
            return resp["data"]
        return None

    def get_edit_detail(self, work_id):
        """获取工时编辑详情（用于重新提交）"""
        resp = self._get(f"/api/mh/work-info/update/{work_id}")
        if resp.get("success"):
            return resp["data"]
        return None

    def withdraw_work(self, work_id):
        """撤销已提交的工时"""
        resp = self._post(f"/api/mh/work-info/withdraw/{work_id}", {})
        return resp

    def submit_work(self, payload):
        """提交/重新提交工时"""
        resp = self._put("/api/mh/work-info/submit", payload)
        return resp


if __name__ == "__main__":
    import os
    c = WorkClient(os.environ["WORK_USER"], os.environ["WORK_PASS"]).login()
    projects = c.get_projects()
    print(f"共 {len(projects)} 个项目:")
    for p in projects[:5]:
        print(f"  {p['id']}: {p['projectName']} ({p['projectPhase']})")
