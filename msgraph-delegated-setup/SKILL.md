---
name: msgraph-delegated-setup
description: Outlook/Microsoft 365 邮箱接入与邮件读写（MS Graph 委托 OAuth）。配置邮箱、设备码登录、令牌过期重登；新建/回复邮件草稿（只进草稿箱不发送，HTML 正文、附件、回复引用链）；查收件箱/搜索邮件/多文件夹监控、日历读写。Triggers: outlook, 邮箱, 配置邮箱, 重新登录邮箱, 邮箱登录过期, 写邮件, 新建草稿, 存草稿, 回复邮件, 回复草稿, 发邮件草稿, 邮件带附件, HTML邮件, 查收件箱, 今天有什么邮件, 搜索邮件, 邮件监控, 微软邮箱, M365, msgraph, AADSTS700082, refresh token 过期
tags: [outlook, 邮箱, email, msgraph, microsoft-graph, quectel-email, delegated-mail]
aliases: ["outlook技能", "邮箱技能", "outlook skill", "email skill"]
---

<!-- LABEL: outlook 技能 / 邮箱技能。提到 outlook/邮箱 相关任务时定位本技能。
     安装位置: <工作区>/scripts/delegated-outlook/（通用）或 scripts/delegated-outlook-ikotek/（Ikotek 租户）
     账号相关：本技能只含公共 App 标识（tenant_id / client_id），
     不含任何人的邮箱账号、密码、令牌；每个使用者用自己的公司账号走设备码登录。 -->


# AI Agent Instructions

When a user asks to configure Delegated email ("配置邮箱", "setup email", etc.), do everything automatically.

## Fixed constants (same for everyone)

```
TENANT_ID = "7730d043-e129-480c-b1ba-e5b6a9f476aa"
CLIENT_ID = "7ae83858-7de6-48ba-852e-2c4631961abc"
SCRIPTS_DIR = ~/.hermes/profiles/main-assistant/scripts/delegated-outlook/
```

## Automated setup flow

1. **No Client ID needed** — use the shared CLIENT_ID above. Do NOT ask the user for anything.

2. **Install dependencies** (do NOT ask — just run):
   ```
   pip install msal cryptography requests
   ```

3. **Create directory and copy scripts** from skill templates to SCRIPTS_DIR:
   - Read each template via `skill_view(name='msgraph-delegated-setup', file_path='templates/...')` then write to SCRIPTS_DIR/

4. **Set environment variables** — write MSGRAPH_TENANT_ID and MSGRAPH_DELEGATED_CLIENT_ID into a `.env` file **inside SCRIPTS_DIR** (the scripts auto-load a sibling `.env`), AND append to the profile `.env`. token_manager.py also has these two values hardcoded as fallback defaults, so refresh keeps working even if env is missing (e.g. cron runs):
   ```
   MSGRAPH_TENANT_ID=7730d043-e129-480c-b1ba-e5b6a9f476aa
   MSGRAPH_DELEGATED_CLIENT_ID=7ae83858-7de6-48ba-852e-2c4631961abc
   ```

5. **Get device code** — run `python SCRIPTS_DIR/auth_login.py --request`. This prints JSON with `user_code`, `device_code`, and `verification_uri`. Show user the `user_code` and https://microsoft.com/devicelogin clearly. Tell them to enter it NOW (15-min window). **Save the `device_code` field** — you need it for Step 6.

   > ⚠️ CRITICAL: Do NOT run `auth_login.py` without `--request` here. The default mode re-requests a NEW device code AND blocks on polling in the same process — the user would enter a code that's already been superseded, and the poll never succeeds. Always use `--request` first, then `--poll` after.

   > Alternative: you can also POST manually to `https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/devicecode` with `client_id={CLIENT_ID}` and scope `openid profile offline_access User.Read Mail.ReadWrite Mail.Send Calendars.ReadWrite`. Capture `device_code` from the JSON response.

6. **After user confirms login**, poll for token and store it by running: `python SCRIPTS_DIR/auth_login.py --poll <device_code>` where `<device_code>` is the value from Step 5. The script polls Microsoft's token endpoint, stores encrypted tokens via token_manager, and calls /me to show the user's name as confirmation.

7. **For cron monitoring** (if user asks): find folder IDs via `list_folders()`, always use direct IDs in scripts. Check ALL folders (not just inbox) — Outlook rules route emails to various folders.

## Pitfalls

- **[FIXED] Agent deadlock: do NOT run auth_login.py interactively during agent-driven setup.** The old SKILL.md told agents to "GET device code" (Step 5) then "poll for token" (Step 6) as separate actions, but auth_login.py was a single monolithic script that always re-requested a NEW device code at startup. So: agent gets code A → user enters code A → agent runs auth_login.py → it requests code B → polls code B forever → user never enters B → 300s timeout. Fix: auth_login.py now has `--request` (get code only, print JSON) and `--poll <device_code>` (poll with a known code) modes. Use those for agent-driven flows.
- WSL localhost forwarding unreliable → use Device Code Flow only
- Execute_code sandbox lacks env vars → pass values explicitly or use terminal()
- Device codes single-use → if storage step fails, get new code
- Check ALL folders (`/me/messages`), not just inbox — Outlook rules route TO emails elsewhere
- System emails (BPM, noreply, etc.) should be filtered in monitor scripts
- **SCRIPTS_DIR is profile-specific.** The `main-assistant` path above is an example. For a fresh install pick the CURRENT profile's dir (e.g. `~/.hermes/skills/email-integration/msgraph-delegated-setup/` or `~/.hermes/profiles/<profile>/scripts/delegated-outlook/`). The Fernet key is derived from `hostname + tenant_id`, so tokens are machine-bound and NOT portable — each new machine/user must run device-code login once.
- **[FIXED] Token refresh no longer self-destructs.** token_manager.py used to call `clear_tokens()` on any refresh failure (transient network error or missing env var), forcing a full re-auth. It now preserves tokens and only warns — retry later or run auth_login.py explicitly.
- **[FIXED] MSGRAPH_* env no longer mandatory.** token_manager.py auto-loads a sibling `.env` and falls back to hardcoded shared-app defaults, so refresh + key derivation work under cron/naked env. Still write `.env` for clarity.
- **Never distribute `.tokens.enc` / `.token_key` / `.env`.** These are per-user secrets. Ship only SKILL.md + README + templates/. Each recipient authenticates themselves.
- Default $top=50 → check `totalItemCount` before fetching "all"
- **[坑] 令牌会因「90 天不活动」彻底失效**：刷新时报 `400 invalid_grant / AADSTS700082: The refresh token has expired due to inactivity ... inactive for 90.00:00:00`。这不是网络问题，重试永远失败，**只能重新做一次设备码登录**。判断方法：手动 POST token 端点看 `error_codes`。报错里会写清签发时间和失效原因，可直接回给用户解释。因此**不要**把"能收发邮件"当成长期能力，隔一段时间没用就要预备重登。
- **[坑] 中文参数在 Windows cmd 下乱码**：跑 `make_draft.py --subject "测试"` 前先 `set PYTHONIOENCODING=utf-8`，否则主题/正文可能变成 `??`。
- **[坑] 别把草稿当成"已发"**：`POST /me/messages` 产生的 `isDraft=true` 才在草稿箱；`/me/sendMail` 是即时发送。验收统一回读 `folder="drafts"`。

---

## 写邮件 / 建草稿（只进草稿箱，绝不自动发送）

用户说「写个草稿 / 回复这封 / 把这封存成草稿」时，用 `templates/make_draft.py`。**永远先落草稿，等用户点头再谈发送。**

```bat
:: 新建草稿（纯文本）
python make_draft.py --to a@x.com --cc b@x.com --subject "标题" --body "正文"

:: HTML 正文（测试报告这类带表格/颜色的）
python make_draft.py --to a@x.com --subject "标题" --body-file body.html --html

:: 回复草稿（带原邮件引用链，回复时必须用这个而不是新建）
python make_draft.py --reply-to <message-id> --body "正文"

:: 带附件（可重复 --attach）
python make_draft.py --to a@x.com --subject s --body b --attach "D:\path\report.pdf"
```

输出 JSON `{"ok":true,"id":...,"webLink":...,"isDraft":true}`。
`--reply-to` 的 message-id 从 `search_mail` / `graph_mail.list_messages` 的 `id` 取。

底层就是 `POST /me/messages`（新草稿）或 `POST /me/messages/{id}/createReply` + `PATCH`（回复草稿）——**不要用 `/me/sendMail`**，那是直接发出去。

**写入后必须回读草稿箱验证**，不能只看返回 id：

```python
from graph_mail import GraphMailClient
c = GraphMailClient()
for m in c.list_messages(top=3, folder="drafts"):
    print(m["subject"], [t["emailAddress"]["address"] for t in m.get("toRecipients", [])], m["isDraft"])
```

### 两个部署实例（tenant/client 不同，别混用）

| 部署 | TENANT_ID | CLIENT_ID | 环境变量前缀 | 工作脚本目录 |
|---|---|---|---|---|
| Quectel（共享 App，通用） | `7730d043-e129-480c-b1ba-e5b6a9f476aa` | `7ae83858-7de6-48ba-852e-2c4631961abc` | `MSGRAPH_TENANT_ID` / `MSGRAPH_DELEGATED_CLIENT_ID` | `scripts/delegated-outlook/` |
| Ikotek（另一企业租户示例） | `35a5aa27-35d2-43f6-b632-6bb3e066544b` | `22a0736e-97f9-493f-b4e9-1c308dbcf746` | `MSGRAPH_IKOTEK_TENANT_ID` / `MSGRAPH_IKOTEK_CLIENT_ID` | `scripts/delegated-outlook-ikotek/` |

> **表中只有 tenant_id / client_id —— 这是 Azure 应用（App Registration）的公开标识，不是账号、不是密码、不是令牌。** 换人换机器必须各自走一次设备码登录，登录后拿到的 refresh_token 只存在本机 `.tokens.enc`（机器绑定加密），不进仓库、不上传、不共享。`.tokens.enc` / `.token_key` / `.env` 三个文件永远不要提交。

两套 `token_manager.py` 的环境变量前缀、`_derive_key()` 盐串都不同，**Fernet 密钥互不通用**，换租户必须重新走一次设备码登录。

---

# Microsoft 365 Personal Email — 用户指南

自动接入 Quectel 邮箱。一句话 + 一次扫码登录，全程 1 分钟。

## 操作

对 Hermes 说：

> 帮我配置邮箱

Hermes 会自动完成安装，然后显示一个 8 位代码。

1. 打开 https://microsoft.com/devicelogin
2. 输入代码
3. 用 Quectel 账号登录
4. 点击"接受"

✅ 完成。Hermes 显示你的名字确认。

## 可选：设置邮件监控

> 帮我监控收件箱，有人直接点名我的时候推送到飞书

Hermes 会自动创建 cron job，每 5 分钟检查。

## 故障

| 问题 | 解决 |
|------|------|
| "No tokens found" | 说"重新登录邮箱" |
| "code expired" | 重新说"配置邮箱" |
| 通知停了 | Token 过期，重新登录 |
| 监控漏了 | 邮件被 Outlook 规则移到了其他文件夹，监控已覆盖全文件夹 |

## 安全

- 同一个 App 给所有人用，但登录后各自独立 Token
- 只能看自己邮箱（`/me/*`），看不到别人
- Token 加密存储，不存密码
