# 账号登录的响应样例与实现细节

所有样例都是**脱敏后**的真实结构（字段名保真、值替换为占位符）。

## 1. OAuth2 密码模式（表单提交）

```
POST {base}/api/uaa/oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=password&username=<账号>&password=<密码或密文>&scope=ui
  &client_id=<client>&client_secret=<client_secret>
```

成功：

```json
{"access_token":"<uuid>","refresh_token":"<uuid>","token_type":"bearer",
 "expires_in":86399,"scope":"ui","code":"0",
 "data":{"access_token":"<uuid>","expires_in":"<YYYY-MM-DD HH:MM:SS>",
         "userInfo":{"id":"<userId>","username":"<登录名>","tenantId":"1"}}}
```

失败（HTTP 200 + 业务码）：

```json
{"code":400,"msg":"Username or password is incorrect","data":null}
{"code":102,"msg":"<需要 MFA 验证>","data":null}
```

要点：
- `expires_in` 是**秒**（86399 ≈ 24h）；有的系统还额外给一个绝对时间的 `expires_in` 字符串，别搞混，只认秒。
- 业务错误可能返回 HTTP 200，必须看 body 里的 `code`，不能只看状态码。

## 2. refresh_token 续期（会轮换）

```
grant_type=refresh_token&refresh_token=<裸 uuid>&scope=ui&client_id=..&client_secret=..
```

成功返回**新的** access_token + **新的** refresh_token。旧 refresh 立刻作废。

```python
j = refresh_fn(old_refresh)
store.save({**tok,
            'access_token': j['access_token'],
            'refresh_token': j.get('refresh_token') or old_refresh,   # ← 必须覆盖
            'expires_at': int(time.time()) + int(j['expires_in'])})
```

踩过的坑：把 `bearer` 前缀一起塞进 refresh_token 字段，服务端返回
`The current user login information has expired, please log in again!` —— 看着像密码错了，
其实是**格式问题**。保存时存裸值，发出去前再 `strip` 一次。

## 3. 前端加密密码（RSA PKCS#1 v1.5）

前端典型写法（jsencrypt 派生库）：

```js
const rsa = new Encrypt();
rsa.setOptions({ encryptionScheme: 'pkcs1' });
rsa.importKey('<MII...392字符...>', 'pkcs8-public-pem');   // 2048 位公钥
password = rsa.encrypt(password, 'base64', 'utf8');        // → 344 字符
// 再把 auth_type 设成 'rsa_area'（或 'email'/'phone'，各系统不同）一起提交
```

Python 等价（标准库，无需 `cryptography`）：

```python
import account_auth as A
enc = A.rsa_encrypt_pkcs1v15(password, PUBKEY_B64)   # 256 字节 → 344 base64
```

结构细节：
- 公钥是 **SubjectPublicKeyInfo**（`MIIBIjANBgkqhkiG9w0BAQEF...`），DER 里是 `SEQUENCE{ AlgorithmIdentifier, BIT STRING{ SEQUENCE{ n, e } } }`
- 加密块：`0x00 || 0x02 || PS(非零随机, 长 k-3-len) || 0x00 || 明文`，k = 256
- `c = pow(int(EM), e, n)`，`e` 通常是 65537

**验证方法**（不碰真账号）：自己 `cryptography` 生成一对密钥 → 换成自建公钥调你的函数 →
用私钥 `PKCS1v15()` 解密比对。再拿真实公钥加密看长度是不是 256 B / 344 字符。

**公钥从哪来**：登录页 JS。`index.html` 里只有 `app.<hash>.js`；app 里有一张 chunk 表
（`{Login:"2a226c8d", ...}`），拼出 `js/Login.<hash>.js` 和共享块 `js/Login~xxx.<hash>.js`，
在共享块里 `grep -n "MII"` 就能拿到。若哪天登录报“密码错误”而密码没错，多半是公钥换了。

## 4. MFA 预检

```
POST {sso}/api/uaa/mfa-open/check
{"username":"<账号>","password":"<RSA密文>"}
```

- 通过：`{"code":0,"data":{"isPass":true,"mfaConfigVo":{"webMfaConfig":{...}},"isJumpMfaStep":"?"}}`
- 失败：`{"success":false,"code":400,"msg":"username or password is incorrect"}`

判断是否需要 MFA：非内网 且 `webMfaConfig` 里有值为 `'Y'` 的项。
需要时前端弹验证码框，再用 `auth_type=multi_acc_login` + `key=<loginKey>` 二次换 token。
**这类账号脚本别硬扛**，直接引导用 HAR/Cookie。

## 5. Cookie 型

浏览器里登录后 cookie 通常长这样（名字各家不同）：

```
app_token=bearer<uuid>; app_refresh_token=<uuid>; lang=cn; app_user_info={...}
```

- 让用户从 DevTools → Application → Cookies 复制整串，`login --cookie "..."`；
- 或者让他导出 HAR（Network 面板 → 右键 → Save all as HAR），脚本用正则提取：
  - 先找 `"access_token"\s*:\s*"([^"]+)"`（登录响应里就有）
  - 再退化到 `app_token=([^;\s"]+)`
- **HAR 里还包含大量其他请求**，解析时只取 token，别顺手把整份日志存进 skill。

## 6. 多环境 / 多站点

```python
BASE = os.environ.get('APP_BASE', 'https://prod.site.com')
TOKEN_PATH = os.path.expanduser(os.environ.get('APP_TOKEN_FILE', '~/.app/token.json'))
```

测试环境、不同租户各用各的 token 文件（`~/.app/token-test.json`），别混。

## 7. 凭证卫生速查

| 项 | 做法 |
|---|---|
| 密码输入 | `getpass.getpass()`；不要 echo，不要拼进命令行（除非用户明说） |
| 密码存储 | **不存**。要存也必须显式 opt-in + 操作系统密钥库（keyring / DPAPI） |
| token 存储 | 用户目录 + `os.chmod(0o600)` + 原子写（先写 `.tmp` 再 `os.replace`） |
| 日志 | token 只打前 6 位：`bearer91d9e3…`；密码永远不打 |
| 异常 | 不要把整个 request payload 打进错误消息（含密码/密文） |
| 交付 | `python scripts/scan_credentials.py <dir>` 必须干净 |
| 命令历史 | 文档里推荐 `--ask`，`-p` 标注「会留在 shell history」 |

## 8. 与 Agent / 自动化配合

- 在无人值守环境（cron、Agent 定时任务）：用 `APP_USERNAME` / `APP_PASSWORD` 环境变量，
  **不要**让它去 `input()`；
- 需要在对话里问用户账号时，只问账号，密码让用户自己在本机终端输入；
- 判断是否交互：`sys.stdin and sys.stdin.isatty()`（很多沙箱里 `stdin` 是 `None`）。

```python
if not sys.stdin or not sys.stdin.isatty():
    raise SystemExit('未登录。请先在终端执行：<cmd> login --ask')
```
