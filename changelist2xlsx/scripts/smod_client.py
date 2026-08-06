# -*- coding: utf-8 -*-
"""
SMOD (smod.quectel.com) API 客户端

依据浏览器抓包 (HAR) 分析生成，实现以下流程：
    1. 登录（获取 access_token）
    2. 搜索项目（betaver 列表，支持关键字）
    3. 新建项目（创建一个 betaver）

关键说明（抓包结论）
--------------------------------------------------------------------
1. 业务接口域名： https://smod.quectel.com
2. 鉴权方式：请求头 Authorization = token_type + access_token 直接拼接，**中间没有空格**
   例如： Authorization: bearer<你的access_token>
3. 登录是一套 SSO + OAuth 流程。login_by_password() 已实现：
   - SSO 现在**要求密码用 RSA（PKCS#1 v1.5）加密**后发送（auth_type=rsa_area），明文会被拒；
     默认使用内置公钥（`SSO_RSA_PUBLIC_KEY`，必要时由 `_fetch_sso_public_key()` 从前端动态抓取）加密，
     再写入 `quectel_token` 会话 cookie 并跟随 OAuth 重定向拿到 code，最后换 smod access_token。
   - 也可直接传 encrypted_password（已加密好的密码）或 rsa_public_key（自定义公钥）。
4. 统一响应格式： {"code":"10000","msg":"Success","data": ...}，code==10000 表示成功。

依赖：
    pip install requests pycryptodome
    # pycryptodome 用于 login_by_password() 的密码 RSA 加密（已内置公钥，默认需要）
"""

import base64
import hashlib
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs

import requests


class SmodApiError(Exception):
    """业务接口返回非成功 code 时抛出"""


# SSO RSA 公钥（密码加密登录用，JSEncrypt pkcs1 方案）。
# 抓包 /api/uaa/oauth/token 请求体可见 auth_type=rsa_area + 密文密码；
# 公钥来自前端 https://sso-web.quectel.com/js/Login~factoryLogin.<hash>.js 的
# function f(){ ... r="MIIB..." } 中（n.a 即 JSEncrypt，setOptions({encryptionScheme:"pkcs1"})）。
# 若登录报 RSA/解密相关错误，可能密钥已轮换：调用 _fetch_sso_public_key() 动态拉取，
# 或从上述 chunk 重新提取后用新值覆盖本常量。
SSO_RSA_PUBLIC_KEY = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAre5YnMJtO+gtwkeeq07f5Ufyw"
    "HM2LQ5T4jzVzYUYJOQN0AUAYkmoIt7rIfAN6q5nEby3zupXznBo/Y5SsRtXDoG53xHuc"
    "pqE5SXD4J6kNnxj+JjecQ7ef0ev5MTOb+eREybymosgs7xr/eprv2O4GmipUwXVTWusb"
    "L/xjPzfP603JGz/r6xR94k5K8NXqHLQVBKURa5QK3x9sUyX5ZxYop6llF3BdkIafB8aER"
    "w5iJa7i8fFK6UmIbhGQ8rLYYGj61229NayMgIuWJ3SGmUWWq0RyCEjt96I6ZWwOqygkiE"
    "Xj3PoQEmTUIxmEgrWQ5UxSHT/XDai5sbj7IueMqncPQIDAQAB"
)



class SmodClient:
    """SMOD 平台 API 客户端，自动维护 session / cookie / token"""

    SUCCESS_CODE = "10000"

    def __init__(
        self,
        base_url: str = "https://smod.quectel.com",
        sso_url: str = "https://sso-web.quectel.com",
        oauth_url: str = "https://st-oauth.quectel.com",
        platform_code: str = "odmm",
        timeout: int = 30,
        verify_ssl: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.sso_url = sso_url.rstrip("/")
        self.oauth_url = oauth_url.rstrip("/")
        self.platform_code = platform_code
        self.timeout = timeout

        self.session = requests.Session()
        self.session.verify = verify_ssl
        self.session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "User-Agent": "Mozilla/5.0 SmodClient/1.0",
            }
        )

        self.token_type: str = "bearer"
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None

    # ================================================================
    # 通用请求 & 响应处理
    # ================================================================
    def _auth_header(self) -> Dict[str, str]:
        """构造鉴权头：token_type + access_token 直接拼接（无空格）"""
        if not self.access_token:
            return {}
        return {"Authorization": f"{self.token_type}{self.access_token}"}

    def _request(self, method: str, path_or_url: str, **kwargs) -> Any:
        """发起请求并统一解析 {code,msg,data} 结构"""
        url = path_or_url if path_or_url.startswith("http") else f"{self.base_url}{path_or_url}"
        headers = kwargs.pop("headers", {}) or {}
        headers.update(self._auth_header())

        resp = self.session.request(
            method, url, headers=headers, timeout=self.timeout, **kwargs
        )
        resp.raise_for_status()

        # 尝试解析统一 JSON 结构
        try:
            payload = resp.json()
        except ValueError:
            return resp.text

        if isinstance(payload, dict) and "code" in payload:
            if str(payload.get("code")) != self.SUCCESS_CODE:
                raise SmodApiError(
                    f"接口失败 code={payload.get('code')} msg={payload.get('msg')} url={url}"
                )
            return payload.get("data")
        return payload

    # ================================================================
    # 1. 登录
    # ================================================================
    def set_token(self, access_token: str, token_type: str = "bearer") -> None:
        """【推荐】直接注入从浏览器复制的 access_token

        浏览器获取方式：登录 smod.quectel.com 后打开 DevTools → Network，
        找到任意 /api/ 请求，复制其 Authorization 头（形如 bearerxxxx），
        去掉开头的 token_type 前缀，剩下的即 access_token。
        """
        self.access_token = access_token
        self.token_type = token_type

    def login_by_code(self, code: str) -> Dict[str, Any]:
        """用 OAuth code 换取 smod 的 access_token

        对应抓包： GET /api/login/authorizeToken?code=xxxx
        返回： {access_token, token_type, refresh_token, expires_in, scope}
        """
        data = self._request(
            "GET", "/api/login/authorizeToken", params={"code": code}
        )
        self.access_token = data["access_token"]
        self.token_type = data.get("token_type", "bearer")
        self.refresh_token = data.get("refresh_token")
        return data

    def _fetch_sso_public_key(self) -> str:
        """从 SSO 前端动态抓取 RSA 公钥（密钥轮换时无需改代码）。

        路径：/js/app.<hash>.js 的 chunk 映射里找到 Login~factoryLogin 的 hash
              -> /js/Login~factoryLogin.<hash>.js 中 function f(){ ... r="MIIB..." }
        成功则返回 base64 公钥字符串；失败回退到模块常量 SSO_RSA_PUBLIC_KEY。
        """
        try:
            html = self.session.get(
                f"{self.sso_url}/login", timeout=self.timeout
            ).text
            import re
            m = re.search(r'src="(/js/app\.[0-9a-f]+\.js)"', html)
            if not m:
                return SSO_RSA_PUBLIC_KEY
            app_js = self.session.get(
                f"{self.sso_url}{m.group(1)}", timeout=self.timeout
            ).text
            hm = re.search(r'"Login~factoryLogin":"([0-9a-f]+)"', app_js)
            if not hm:
                return SSO_RSA_PUBLIC_KEY
            chunk = self.session.get(
                f"{self.sso_url}/js/Login~factoryLogin.{hm.group(1)}.js",
                timeout=self.timeout,
            ).text
            km = re.search(
                r'"(MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA[^\"]+)"', chunk
            )
            if km:
                return km.group(1)
        except Exception:
            pass
        return SSO_RSA_PUBLIC_KEY

    def _get_sso_public_key(self, rsa_public_key: Optional[str]) -> str:
        """优先用调用方显式传入的公钥；否则尝试动态抓取；再否则用常量。"""
        if rsa_public_key:
            return rsa_public_key
        return self._fetch_sso_public_key()

    def login_by_password(
        self,
        username: str,
        password: str,
        rsa_public_key: Optional[str] = None,
        encrypted_password: Optional[str] = None,
        client_id: str = "quectel",
        client_secret: str = "quectel",
    ) -> Dict[str, Any]:
        """走完整 SSO OAuth 流程完成账号密码登录，自动拿到 SMOD access_token。

        流程（依据抓包）：
          1) POST {sso}/api/uaa/oauth/token   —— 用【RSA 加密后的密码】建立 SSO 会话
          2) GET  {oauth}/login/oss?next_url=...  —— 借助 SSO 会话跳转授权，随重定向拿到 code
          3) GET  {base}/api/login/authorizeToken?code=xxx  —— 换取 smod access_token

        密码方式（SSO 现已要求加密，明文会被拒）：
          - 默认用 SSO_RSA_PUBLIC_KEY（或自动从前端抓取）做 RSA/PKCS#1 v1.5 加密后发送，
            请求体带 auth_type=rsa_area。
          - 也可直接传 encrypted_password（已加密好的密码）；或传 rsa_public_key 用自定义公钥。
        """
        # 未提供密文时，用 RSA 公钥加密明文密码
        if encrypted_password is None:
            pub = self._get_sso_public_key(rsa_public_key)
            encrypted_password = self._rsa_encrypt(password, pub)

        data = {
            "grant_type": "password",
            "username": username,
            "password": encrypted_password,
            "scope": "ui",
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_type": "rsa_area",
        }

        # 1) SSO 取 token（建立会话 cookie）
        token_resp = self.session.post(
            f"{self.sso_url}/api/uaa/oauth/token",
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "devicesn": self._devicesn(),
                "terminal": "web",
            },
            timeout=self.timeout,
        )
        token_resp.raise_for_status()
        token_json = token_resp.json()

        # 接口可能直接返回 access_token，也可能包在 {code,msg,data} 里
        sso_token: Optional[str] = None
        if isinstance(token_json, dict):
            if "access_token" in token_json:
                sso_token = token_json["access_token"]
            elif str(token_json.get("code")) == self.SUCCESS_CODE:
                sso_token = token_json.get("data", {}).get("access_token")
        if not sso_token:
            raise SmodApiError(
                f"SSO 登录失败，未拿到 access_token：{token_json}"
            )

        # 密码 grant 不会下发会话 cookie，但后续 OAuth 跳转依赖它，
        # 需像浏览器一样把 token 写入 quectel_token cookie（带 bearer 前缀、无空格）。
        refresh_token = None
        if isinstance(token_json, dict):
            refresh_token = token_json.get("refresh_token")
        self.session.cookies.set(
            "quectel_token", f"bearer{sso_token}", domain=".quectel.com"
        )
        if refresh_token:
            self.session.cookies.set(
                "quectel_refresh_token", refresh_token, domain=".quectel.com"
            )

        # 2) 走 OAuth 授权链路，随重定向拿到 code
        next_url = (
            f"{self.oauth_url}/oauth/authorize?response_type=code"
            f"&grant_type=authorization_code&socpe=code&client_id=qt-revise"
            f"&redirect_uri={self.base_url}/auth-redirect"
        )
        login_oss = f"{self.oauth_url}/login/oss"
        r = self.session.get(
            login_oss,
            params={"next_url": next_url, "lang": "cn"},
            allow_redirects=True,
            timeout=self.timeout,
        )
        code = self._extract_code_from_history(r)
        if not code:
            raise SmodApiError(
                "未能从 OAuth 重定向中获取 code，可能是 SSO 会话未正确建立。"
                "建议改用 set_token() 手动注入浏览器复制的 access_token。"
            )

        # 3) code 换 access_token
        return self.login_by_code(code)

    @staticmethod
    def _extract_code_from_history(resp: requests.Response) -> Optional[str]:
        """从重定向历史与最终 URL 中提取 ?code= 参数"""
        urls = [h.url for h in resp.history] + [resp.url]
        for u in urls:
            qs = parse_qs(urlparse(u).query)
            if "code" in qs and qs["code"]:
                return qs["code"][0]
        return None

    @staticmethod
    def _devicesn() -> str:
        """生成固定格式的 devicesn（32 位十六进制），与抓包一致即可。"""
        # 用 User-Agent 字符串做 MD5，保证同一台机器/脚本多次运行相同
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 SmodClient/1.0"
        return hashlib.md5(ua.encode("utf-8")).hexdigest()

    @staticmethod
    def _rsa_encrypt(plaintext: str, public_key: str) -> str:
        """用 RSA 公钥加密密码，返回 base64 字符串（PKCS1_v1_5）。

        public_key 支持 PEM 文本，或纯 base64 DER（会自动补全 PEM 头尾）。
        需要 pycryptodome： pip install pycryptodome
        """
        try:
            from Crypto.Cipher import PKCS1_v1_5
            from Crypto.PublicKey import RSA
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("需要 pycryptodome： pip install pycryptodome") from exc

        key_text = public_key.strip()
        if "BEGIN PUBLIC KEY" not in key_text:
            key_text = (
                "-----BEGIN PUBLIC KEY-----\n"
                + "\n".join(key_text[i : i + 64] for i in range(0, len(key_text), 64))
                + "\n-----END PUBLIC KEY-----"
            )
        rsa_key = RSA.import_key(key_text)
        cipher = PKCS1_v1_5.new(rsa_key)
        encrypted = cipher.encrypt(plaintext.encode("utf-8"))
        return base64.b64encode(encrypted).decode("utf-8")

    def get_user(self) -> Dict[str, Any]:
        """获取当前登录用户信息（可用于校验 token 是否有效）"""
        return self._request("GET", "/api/user")

    # ================================================================
    # 2. 搜索项目
    # ================================================================
    def search_projects(
        self,
        keyword: str = "",
        page: int = 1,
        size: int = 10,
        platform_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """搜索项目（betaver 列表）

        对应抓包： GET /api/projects/{platform_code}/betavers?platform_code=&page=&size=&keyword=
        返回 data： {"records":[...], "total":..., ...}
        """
        platform = platform_code or self.platform_code
        params = {
            "platform_code": platform,
            "page": page,
            "size": size,
            "keyword": keyword,
        }
        return self._request(
            "GET", f"/api/projects/{platform}/betavers", params=params
        )

    # ================================================================
    # 3. 新建项目
    # ================================================================
    def get_hardware_platforms(self) -> List[Dict[str, Any]]:
        """获取硬件平台列表（用于查 id_plat_ver）

        对应抓包： GET /api/simpleHardwarePlatforms
        返回 data： [{"id":10024,"name":"AF20"}, ...]
        """
        return self._request("GET", "/api/simpleHardwarePlatforms")

    def find_platform_id(self, name: str) -> Optional[int]:
        """按名称（精确、忽略大小写）查找硬件平台 id"""
        target = name.strip().lower()
        for item in self.get_hardware_platforms():
            if str(item.get("name", "")).strip().lower() == target:
                return item.get("id")
        return None

    def create_project(
        self,
        code: str,
        id_plat_ver: int,
        platform_code: Optional[str] = None,
    ) -> Any:
        """新建项目（创建一个 betaver）

        对应抓包： POST /api/projects/{platform_code}/betavers
        请求体： {"id_plat_ver": 730029, "code": "QDM559_..._V19"}
        返回 data： true 表示成功
        """
        platform = platform_code or self.platform_code
        body = {"id_plat_ver": id_plat_ver, "code": code}
        return self._request(
            "POST",
            f"/api/projects/{platform}/betavers",
            json=body,
            headers={"Content-Type": "application/json;charset=UTF-8"},
        )

    # ================================================================
    # 4. 导入 Excel（修改点导入）
    # ================================================================
    def import_points_excel(
        self,
        id_beta_ver: int,
        file_path: str,
        platform_code: Optional[str] = None,
    ) -> Any:
        """向指定 betaver 导入 Excel（修改点 points 导入）

        对应抓包：
            POST /api/projects/{platform}/betavers/{id_beta_ver}/pointsImport?access_token=xxx
            Content-Type: multipart/form-data
            表单字段： file = <xlsx 二进制>
            返回 data： {} （code==10000 即成功）

        注意（抓包结论）：
            该上传接口的 token 是通过 **URL query 参数 access_token** 传递的，
            而不是走 Authorization 头，这里按抓包原样实现。

        Args:
            id_beta_ver: 目标 betaver（项目）的 id，例如搜索结果里的 record["id"]
            file_path:   本地要上传的 .xlsx 文件路径
            platform_code: 平台代码，默认 self.platform_code (odmm)

        Returns:
            接口返回的 data（成功时通常为 {}）
        """
        import os

        if not self.access_token:
            raise SmodApiError("未登录：请先 set_token() 或 login_*() 再导入")
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"文件不存在：{file_path}")

        platform = platform_code or self.platform_code
        url = (
            f"{self.base_url}/api/projects/{platform}/betavers/"
            f"{id_beta_ver}/pointsImport"
        )
        filename = os.path.basename(file_path)
        xlsx_mime = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        with open(file_path, "rb") as fp:
            files = {"file": (filename, fp, xlsx_mime)}
            # token 走 query 参数；不手动设 Content-Type，交给 requests 生成 boundary
            resp = self.session.post(
                url,
                params={"access_token": self.access_token},
                files=files,
                headers={"X-Requested-With": "XMLHttpRequest"},
                timeout=self.timeout,
            )
        resp.raise_for_status()

        try:
            payload = resp.json()
        except ValueError:
            return resp.text
        if isinstance(payload, dict) and "code" in payload:
            if str(payload.get("code")) != self.SUCCESS_CODE:
                raise SmodApiError(
                    f"导入失败 code={payload.get('code')} msg={payload.get('msg')}"
                )
            return payload.get("data")
        return payload

    # ================================================================
    # 5. 测试用例 & 测试结果
    # ================================================================
    # 测试结论取值（来自 /api/dict/test_result）
    TR_IN_PROCESS = "ti"          # Test-in-Process
    TR_BLOCKED_NORUN = "bnr"      # Blocked-NoRun
    TR_NA = "na"                  # NA

    def get_new_case_code(self) -> str:
        """获取一个新的测试用例编号（如 TC-20260721140406）

        对应抓包： GET /api/newCaseCode
        """
        return self._request("GET", "/api/newCaseCode")

    def get_test_result_dict(self) -> Dict[str, Any]:
        """获取测试结论字典（label/value 对照）

        对应抓包： GET /api/dict/test_result
        """
        return self._request("GET", "/api/dict/test_result")

    def list_points(
        self,
        id_beta_ver: int,
        page: int = 1,
        size: int = 500,
        platform_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """列出某版本下的所有修改点（含 description 字段）

        对应抓包： GET /api/projects/{platform}/betavers/{id_beta_ver}/points
        返回 data： {"records":[...], "total":..., ...}
        """
        platform = platform_code or self.platform_code
        params = {
            "platform_code": platform,
            "id_beta_ver": id_beta_ver,
            "page": page,
            "size": size,
        }
        return self._request(
            "GET",
            f"/api/projects/{platform}/betavers/{id_beta_ver}/points",
            params=params,
        )

    def create_case(
        self,
        code: str,
        summary: str,
        id_revise: int,
        pre_condition: str = "",
        test_step: str = "",
        expected_result: str = "",
        test_result: str = "ti",
        platform_code: Optional[str] = None,
    ) -> int:
        """新建一条测试用例

        对应抓包： POST /api/projects/{platform}/cases
        请求体： {"code","test_result":"ti","summary","pre_condition",
                  "test_step","expected_result","id_revise":<point_id>}
        返回 data： 新建的用例 id（int）
        """
        platform = platform_code or self.platform_code
        body = {
            "code": code,
            "test_result": test_result,
            "summary": summary,
            "pre_condition": pre_condition,
            "test_step": test_step,
            "expected_result": expected_result,
            "id_revise": id_revise,
        }
        return self._request(
            "POST",
            f"/api/projects/{platform}/cases",
            json=body,
            headers={"Content-Type": "application/json;charset=UTF-8"},
        )

    def set_point_test_result(
        self,
        point_id: int,
        value: str,
        platform_code: Optional[str] = None,
    ) -> Any:
        """修改某修改点的测试结论

        对应抓包： PATCH /api/projects/{platform}/points/{point_id}/test_result
        请求体： {"value":"ti" | "bnr" | ...}
        """
        platform = platform_code or self.platform_code
        return self._request(
            "PATCH",
            f"/api/projects/{platform}/points/{point_id}/test_result",
            json={"value": value},
        )

    def set_point_remark(
        self,
        point_id: int,
        value: str,
        platform_code: Optional[str] = None,
    ) -> Any:
        """修改某修改点的备注

        对应抓包： PATCH /api/projects/{platform}/points/{point_id}/remark
        请求体： {"value":"无需测试"}
        """
        platform = platform_code or self.platform_code
        return self._request(
            "PATCH",
            f"/api/projects/{platform}/points/{point_id}/remark",
            json={"value": value},
        )

    def list_cases_for_point(
        self,
        id_revise: int,
        platform_code: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """列出某修改点下的所有测试用例

        对应抓包： GET /api/projects/{platform}/points/{id_revise}/cases
        返回 data： [ {id, code, summary, test_result, ...}, ... ]
        """
        platform = platform_code or self.platform_code
        data = self._request(
            "GET", f"/api/projects/{platform}/points/{id_revise}/cases"
        )
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("records") or data.get("list") or []
        return []

    def delete_cases(
        self,
        ids: List[int],
        platform_code: Optional[str] = None,
    ) -> Any:
        """批量删除测试用例

        对应抓包： DELETE /api/projects/{platform}/cases
        请求体： {"ids": [id1, id2, ...]}   （注意：ids 在 JSON 体里，不在 URL）
        返回 data： true 表示成功

        说明：该接口早期用 GET/POST 探测会返回 405/500（HttpRequestMethodNotSupported），
              正确姿势是 DELETE + JSON 体 {"ids":[...]}。
        """
        platform = platform_code or self.platform_code
        if not ids:
            return None
        return self._request(
            "DELETE",
            f"/api/projects/{platform}/cases",
            json={"ids": [int(x) for x in ids]},
            headers={"Content-Type": "application/json;charset=UTF-8"},
        )


# ====================================================================
# 使用示例
# ====================================================================
def main():
    client = SmodClient()

    # ---------- 1. 登录 ----------
    # 【推荐】直接注入浏览器复制的 access_token（去掉 Authorization 里的 bearer 前缀）
    ACCESS_TOKEN = "<YOUR_ACCESS_TOKEN>"  # TODO: 换成你自己的 token
    client.set_token(ACCESS_TOKEN)

    # 【可选】走完整账号密码登录（需 RSA 公钥，密码切勿硬编码，建议用环境变量）
    # client.login_by_password(
    #     username="venus.li@ikotek.com",
    #     password="你的明文密码",
    #     rsa_public_key="MIGfMA0GCSq...（登录页 JS 中的 RSA 公钥）",
    # )

    # 校验 token 是否有效
    try:
        user = client.get_user()
        print(f"当前用户：{user.get('name')} ({user.get('email')})")
    except Exception as e:
        print(f"登录/鉴权失败，请检查 token：{e}")
        return

    # ---------- 2. 搜索项目 ----------
    keyword = "QDM559"
    result = client.search_projects(keyword=keyword, page=1, size=10)
    records = result.get("records", []) if isinstance(result, dict) else []
    print(f"\n搜索关键字『{keyword}』，共匹配 {result.get('total')} 条，前 {len(records)} 条：")
    for r in records:
        print(f"  - id={r.get('id')}  code={r.get('code')}  平台={r.get('name_plat_ver')}")

    # ---------- 3. 新建项目 ----------
    # 3.1 先确定硬件平台版本 id（id_plat_ver）。抓包示例用的是 730029。
    #     可通过名称查找，例如：
    # id_plat_ver = client.find_platform_id("STM32G0B0") or 730029
    id_plat_ver = 730029
    new_code = "QDM559_STM32G0B0_APP_01.001.01.001_V20"  # TODO: 换成你的新项目名

    print(f"\n新建项目：code={new_code}, id_plat_ver={id_plat_ver}")
    try:
        ok = client.create_project(code=new_code, id_plat_ver=id_plat_ver)
        print(f"创建结果：{ok}")
    except SmodApiError as e:
        print(f"创建失败：{e}")

    # 3.2 创建后再次搜索确认，并取回新项目的 id_beta_ver
    result2 = client.search_projects(keyword=keyword, page=1, size=10)
    records2 = result2.get("records", []) if isinstance(result2, dict) else []
    print("\n创建后再次搜索：")
    for r in records2[:5]:
        print(f"  - id={r.get('id')}  code={r.get('code')}  创建时间={r.get('time_create')}")

    # ---------- 4. 导入 Excel（向某个项目导入修改点） ----------
    # id_beta_ver 即搜索结果里的 record["id"]；抓包示例是 1572041
    id_beta_ver = records2[0]["id"] if records2 else 1572041
    excel_path = r"C:\Users\venus.li\Downloads\changelist_all_QDM559_001V19.xlsx"  # TODO: 换成你的 xlsx
    print(f"\n导入 Excel 到项目 id_beta_ver={id_beta_ver}: {excel_path}")
    try:
        data = client.import_points_excel(id_beta_ver=id_beta_ver, file_path=excel_path)
        print(f"导入成功：{data}")
    except FileNotFoundError as e:
        print(f"跳过导入（文件不存在）：{e}")
    except SmodApiError as e:
        print(f"导入失败：{e}")


if __name__ == "__main__":
    main()
