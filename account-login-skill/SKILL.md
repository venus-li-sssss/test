---
name: account-login-skill
description: 写/审「需要账号登录」的 skill 时用本 skill。触发词：账号登录、需要登录的skill、skill要账号密码、拉下来要问账号、每人账号不同、token 怎么存、自动续期、refresh token、MFA 验证码、密码不要上传、凭证不能进仓库、前端密码加密、RSA 登录、逆向登录接口、skill 交付前检查凭证、账号登录型 skill。
metadata:
  qwenpaw:
    emoji: "🔐"
    requires:
      bins: ["python"]
---

# 账号登录型 skill 的写法与红线

给「必须用某个人的账号才能跑」的 skill 定一套统一做法：**仓库里零凭证、每人用自己的账号、
首次问一次之后不再问、密码永不落盘**。本 skill 自带可复制的骨架和交付前自检工具。

触发场景：你要写一个新 skill，而它得登录某个系统（OA、会议室、JIRA、测试平台…）；
或者你要 review 别人的 skill，确认它没把账号/密码/真实数据带出去。

## 1. 五条铁律

| # | 铁律 | 反例（不要这样） |
|---|---|---|
| 1 | **仓库/交付物里没有任何账号信息** | 把真实同事邮箱、`userId`、cookie、token 写进代码或示例 |
| 2 | **每个人用自己的账号** | 内置一个公共账号，大家共用（日志、权限、审计全乱） |
| 3 | **首次问一次，之后不再问** | 每次运行都让用户输密码（会被骂） |
| 4 | **密码永不落盘** | 存进 `token.json` / 配置文件 / 日志 / 命令历史 |
| 5 | **非交互环境给指引，不许死等输入** | 在 cron/Agent 里调用时卡在 `input()` |

> 第 1 条和第 4 条是**能被审计发现的**，别抱侥幸。

## 2. 标准结构

```
<your-skill>/
├── SKILL.md                  ← 说明「第一次怎么登录」，不写任何账号
├── reference/xxx.md          ← 接口/字段文档，示例一律占位符
└── scripts/
    ├── <app>.py              ← 业务命令
    └── account_auth.py       ← 从本 skill 复制：TokenStore / ask_credentials / AuthGuard
```

运行期状态**必须放在用户目录**，不在 skill 目录里：

```
~/.<app>/token.json     # access_token / refresh_token / expires_at / username
                        # 权限 600；不含密码
```

为什么必须是用户目录：skill 目录会被同步/上传/打包，用户目录不会。**这也是"每人各自账号"的物理保证** ——
A 和 B 共用一份 skill 代码，token 各在各的 `%USERPROFILE%` 下，互不干扰。

## 3. 状态机（照这个写就不会被打断）

| 本地状态 | 动作 | 用户感受 |
|---|---|---|
| access_token 有效 | 直接用 | 无感 |
| 距过期 < 2 分钟，有 refresh_token | 静默续期（记得**覆盖保存轮换后的 refresh_token**） | 无感 |
| refresh 失败 / 没有 refresh_token | 有 `APP_USERNAME`+`APP_PASSWORD` 环境变量就用；否则**交互式询问** | 问一次账号密码 |
| 什么都没有且不在终端里 | 打印三条登录路径后退出（`login --ask` / `--devtools` / `--token`） | 明确知道该怎么办 |
| 401/403 中途返回 | 强制刷一次 token 再重试 1 次，别无限重试 | 无感或一次重登 |

## 4. 骨架怎么接（30 行以内接完）

```python
import sys
sys.path.insert(0, os.path.dirname(__file__))
from account_auth import TokenStore, AuthGuard, post_form

BASE = 'https://your.site.com'

def login_fn(user, pwd):
    j = post_form(BASE + '/oauth/token', {
        'grant_type': 'password', 'username': user, 'password': pwd,
        'client_id': 'xxx', 'client_secret': 'xxx'})
    return j            # 需要 access_token / refresh_token / expires_in

def refresh_fn(rt):
    return post_form(BASE + '/oauth/token', {
        'grant_type': 'refresh_token', 'refresh_token': rt.strip('bearer '),
        'client_id': 'xxx', 'client_secret': 'xxx'})

guard = AuthGuard(TokenStore('your_app'), login_fn, refresh_fn, app='your_app')
TOKEN = guard.token()          # ← 有效就用、快过期就续、续不了才问
```

再给一个显式的登录命令，方便用户主动切账号：

```python
def cmd_login(args):
    guard.login(args.username, args.password)   # --ask 时走交互
```

## 5. 四类登录方式（细节见 reference/patterns.md）

| 类型 | 典型 | 关键点 |
|---|---|---|
| **OAuth2 密码模式 + refresh** | 自建平台、企业 SSO | refresh_token **会轮换**，用完必须覆盖；`grant_type` 走表单而非 JSON |
| **表单 + 前端加密密码** | 登录页把密码 RSA/AES 加密后提交 | 必须复刻前端的加密算法；公钥是**公开信息**可以内嵌，密码不是 |
| **Cookie 型** | 老系统、只认 session | 引导用户从 DevTools 复制 cookie，或导出 HAR 由脚本解析 |
| **个人访问令牌（PAT）** | GitHub、MCP 平台 | 让用户去后台生成，绝不代存；支持环境变量注入 |

前三种都要实现「降级链」：**账号密码 → HAR/Cookie → 手工 token**，总有一条能通。

## 6. 前端把密码加密了，怎么逆（实战步骤）

1. 打开登录页，从 `index.html` 的 `img src` 里拿到 `app.<hash>.js`；
2. 在 app bundle 里搜 `chunk` 映射表（形如 `{Login:"2a226c8d"}`），拼出 `js/Login.<hash>.js`；
3. 在登录 chunk 里 `grep -i "encrypt\|MII\|publicKey\|auth_type\|grant_type"`；
4. 找到 `setPublicKey/importKey` 的硬编码公钥（`MII` 开头的 392 字符 = 2048 位）
   以及加密方式（`pkcs1` / `pkcs8-public-pem` / OAEP）；
5. 用 `account_auth.rsa_encrypt_pkcs1v15(text, pubkey_b64)` 复刻（纯标准库，无需三方库）；
6. **验证**：见第 7 节，别拿真人密码去试错。

## 7. 拿不到真密码时，怎么证明「登录实现了」

| 手法 | 说明 |
|---|---|
| **自建密钥对往返** | 自己生成 RSA 密钥对，用你的加密函数加密（换成自建公钥），再用 `cryptography` 私钥解密，比对原文（中文也要测） |
| **长度/格式对照** | 抓包里的密文是 256 字节 / 344 base64 字符；你的输出必须一模一样 |
| **假账号打接口** | 用 `no.such.user@example.com` + 任意密码请求，返回「账号或密码错误」而不是 500/解密失败 → 说明**格式**被接受 |
| **端到端交给用户** | 让用户在本地 `login --ask` 输一次（密码由他自己敲，不经你手），你看 `whoami` 的输出即可 |

⚠️ 绝对不要拿真账号 + 猜的密码反复试：可能触发**锁定/风控**。

## 8. MFA / 验证码 / SSO 跳转

- 有 MFA 的账号，纯密码登录走不通 → 检测到就**明确告知**「改用 HAR/Cookie」，不要静默失败；
- 常见信号：token 接口返回 `code: 102`、预检接口返回 `needMFA`/`isJumpMfaStep`；
- 短信/邮件验证码属于**必须人工完成**的步骤：`browser.handoff(...)` 或直接让用户操作，不要自动化；
- SSO 跳转类（OAuth 授权码）：引导用户浏览器登录后复制 cookie/HAR，比自己实现跳转稳。

## 9. 交付前自检（必做）

```bash
python scripts/scan_credentials.py <skill目录>
```

扫：邮箱、bearer token、UUID、GitHub/OpenAI key、`password=` 字面量、cookie 串、手机号、
`userId` 字面量、`username` 字面量。**退出码 1 = 有高危项，别上传**。

再人工过一遍清单：

- [ ] 所有示例用占位符：`<your-account>`、`name@example.com`、`<userId>`
- [ ] 代码里没有任何"默认账号"或 fallback 公共账号
- [ ] token 文件路径指向用户目录，且 `.gitignore`/同步规则排除
- [ ] 文档里没有真实人名、真实会议主题、真实内部 URL 里的敏感参数
- [ ] `login --ask` 在无参数时可用；非 tty 时给指引而不是卡住
- [ ] 密码只经 `getpass` 输入，不进命令行参数（除非用户显式给 `-p`，且文档提醒会留 history）
- [ ] 日志/异常里不打印密码、token 全文（打前 6 位 + 省略号）

## 10. 反模式清单（都真实踩过）

1. **refresh_token 带着 `bearer` 前缀去刷新** → 服务端回 "login information has expired"，看着像密码错了。
2. **refresh 后不覆盖 refresh_token** → 第二次续期就失效（服务端轮换机制）。
3. **把 userId 当姓名去搜人** → 会匹配到完全无关的人（需用按 id 精确查询的接口）。
4. **每次运行都问账号** → 应该只在「没 token 且没 refresh」时问。
5. **在 Agent 里 `input()`** → 无 tty 直接挂住；先判断 `sys.stdin.isatty()`。
6. **示例里留真实邮箱** → 最容易被漏掉，上线后才被发现。
7. **静默捕获异常** → 登录失败却继续跑业务请求，最后报一堆无关错误。
8. **只支持一种登录方式** → 用户账号开了 MFA / 换了站点就彻底不能用。
9. **token 存到 skill 目录** → 被同步到仓库/市场，等于泄密。
10. **拿真账号反复试密码** → 触发账号锁定。

## 11. 参考资料

- 具体响应样例、错误码、Cookie 结构、HAR 解析法、多环境（测试/生产）切换：
  见 [`reference/patterns.md`](reference/patterns.md)
- 现成骨架：`scripts/account_auth.py`（`--selftest` 可直接跑）
- 交付自检：`scripts/scan_credentials.py`
