---
name: toolhub-software
description: Use this skill when 用户要从**移远软件资源中心 / toolhub.quectel.com** 查或下载软件、驱动、LOG 工具、烧录工具、APP：下载 QWinLog/QCOM/QFlash/驱动、看看资源中心有什么软件、查某个软件的版本/大小/发布日期、拿某个软件的下载直链。纯 requests 复刻 SSO 登录（账号密码走凭据文件/环境变量，脚本里不存任何账号），不需要浏览器、不需要扫码。触发词：toolhub、移远软件资源中心、软件资源中心、下载驱动、下载 LOG 工具、下载 QFlash、下载 QWinLog、下载 QCOM、资源中心下载、查软件版本、下载直链、software-center。
---

# 移远软件资源中心（toolhub.quectel.com）下载

一体化脚本 `scripts/toolhub.py`：**登录 → 搜索 → 查版本 → 下载**，纯 `requests`，不开浏览器、不扫码。

数据源就是内网资源中心 `https://toolhub.quectel.com/portal/resources`，里面托管驱动、LOG 工具、烧录/升级工具、APP 等资源，文件放在 `qos.quectel.com` 的私有桶里（预签名直链 15 分钟有效）。

## 登录怎么做的（不要改回浏览器方案）

整条链路都是 HTTP，没有验证码、没有二维码：

```
1  GET  toolhub  /api/software-center/auth/qauth/authorize-url      → SSO 授权页 + state
2  GET  auth     /api/v1/login/config                               → 身份源「移远SSO」id
3  POST auth     /api/v1/login/identitySourceLogin                  → openapi 授权 URL
4  GET  openapi  .../custom/authorize                               → 落到 sso-web 登录页，取出 oauth_callback
5  POST sso-web  /api/uaa/mfa-open/check  +  /api/uaa/oauth/token   → SSO access_token（密码 RSA 加密）
6  GET  sso-web  .../custom/authorize  → 302 → auth .../quectelSsoCode → 302 → auth /login?...&ticket=
7  POST auth     /api/v1/login/ticket    (multipart: code/clientId/type=IDENTITY_SOURCE/ticket)
8  GET  auth     .../api/oauth2/authorize → 302 → toolhub /auth/callback?code=&state=
9  POST toolhub  /api/software-center/auth/exchange {code,state}    → accessToken(qsc_at_…) 2 小时
```

三条硬事实，改脚本时别丢：

1. **密码是 RSA/PKCS#1 v1.5 加密后 base64**（`auth_type=rsa_area`），公钥就是 sso-web 登录页前端里那把（脚本里 `SSO_RSA_PUBKEY`，**是公开信息不是凭据**）。纯 Python `pow()` 复刻，不引入加密库。
2. **toolhub 自己的 OAuth 账号密码登录走不通**（外部/外包账号返回 `1028 账号或密码错误`），必须走 `identitySourceLogin` → 移远 SSO 这条身份源链。
3. `login/ticket` 是 **multipart**（不是 JSON），少一个字段就 403/失败。

## 凭据（密码只引用，不写进仓库）

脚本按顺序找 `username` + `password`，**仓库里一个字都不存**：

1. 环境变量 `TOOLHUB_USERNAME` / `TOOLHUB_PASSWORD`
2. 工作区 `skills/.credentials.json`（与 `quectel-workhours`/`quectel-attendance` 共用同一份，已在 `.gitignore`）
   ```json
   {"username": "你的工作邮箱", "password": "你的密码"}
   ```
3. `~/.toolhub/credentials.json`（同上格式）

拿到 token 后缓存在 `~/.toolhub/token.json`（只存 token 和账号，**不存密码**）；token 2 小时过期，脚本下一次调用会自动重新登录。

## 命令

```bat
set TH=python "<此 SKILL.md 所在目录>\scripts\toolhub.py"

%TH% login                          :: 强制重登（排查登录问题时用）
%TH% whoami                         :: 当前账号 + token 剩余分钟
%TH% cats                           :: 资源分类（Driver / Flash&Update / LOG / Backup / App / Other）
%TH% list                           :: 最新/最热资源（默认按下载量，20 条）
%TH% list QWinLog                   :: 按关键词搜（中文也行，如 `list 驱动`）
%TH% list --cat LOG --size 30       :: 按分类
%TH% list --sort modifyTime --size 10 :: downloads | modifyTime | name
%TH% list --os Windows              :: 按操作系统过滤
%TH% list 驱动 --all                :: 翻页取全部结果

%TH% info QWinLog                   :: 详情 + 全部版本（摘要/发布/大小/文件名/页面链接）
%TH% versions QFlash_CN             :: 只列版本
%TH% get-url QWinLog                :: 只拿预签名直链（900 秒有效），不下载
%TH% download QWinLog               :: 下最新版本到当前目录
%TH% download QWinLog --version 2.3 -o D:\tools
%TH% download 2112734777299042305 -o D:\tools   :: 也可以直接给资源 id
%TH% download QWinLog --dry-run      :: 只打印直链，不落盘
```

`<key>` 可以写**资源 id**（纯数字）或**名称关键词**。关键词会先搜一次，优先精确同名，再取名字里包含关键词且下载量最高的那个；`info`/`download` 打印出来的「资源：…（id）」就是它最终选中的对象——**下错东西先看这一行**。

## 下载行为

- 默认取 `reviewStatus=APPROVED` 里 `releaseDate` 最新的版本。
- 保存文件名取 S3 直链里的 `response-content-disposition`（比接口里的 `fileName` 更准），非法字符会被替换。
- 支持断点续传：目标文件已存在且服务器支持 `Range` 时从断点接着下，最后用接口给的 `fileSize` 校验大小，不一致直接报错（不会留下"看起来成功"的半截包）。

## 接口备忘（自己扩展功能时看）

| 用途 | 接口 |
|---|---|
| 搜/列资源 | `GET /api/software-center/portal/resources?pageNumber=&pageSize=&sort=&keyword=&field=&categoryId=&os=` |
| 资源详情 | `GET /portal/resources/{id}` |
| 版本列表 | `GET /portal/resources/{id}/versions` |
| 换下载直链 | `POST /portal/resources/{id}/download`，body `{versionId, version, fileSize}` → `data.url`（`expiresIn=900`） |
| 分类 | `GET /portal/categories` |
| 当前用户 | `GET /auth/userinfo` |

- 全部请求带 `Authorization: Bearer qsc_at_…`。
- `sort` 只认 `downloads` / `modifyTime` / `name`；`field` 只认 `name` / `description` / `tags` / `model`（不传就是全字段）。
- **数字字段是字符串**（`total`、`fileSize`、`downloads`），比较/相除前要 `int()`，不然 Windows 上直接 TypeError。

## 踩过的坑

1. **别用账号密码去打 `auth.quectel.com.cn/api/v1/login/account`**：外部账号必然 `1028 账号或密码错误`，会浪费时间。走身份源链。
2. **别把 `callback` 参数原样塞进 JSON**：`identitySourceLogin` 要的是**已 URL 编码**的 callback（`quote(callback, safe='')`）。
3. **`oauth_callback` 是二次编码的**：从 sso-web 登录页 URL 取出来要 `unquote` 一次再用，否则 302 链断。
4. **预签名直链 900 秒**：拿到就马上用；大文件断点续传要重新 `download` 换新直链，别复用旧 URL。
5. **不要在对话/日志里回显密码**：只打印账号、token 前几位、token 剩余时间。
6. 资源中心是**开发环境桶** `software-center-dev`，直链域名是 `qos.quectel.com`——这不是智能体在乱拼地址，是接口自己返回的。
