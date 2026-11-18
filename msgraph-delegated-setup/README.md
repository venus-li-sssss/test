# Microsoft 365 Email — Hermes 邮箱接入

一套给 Quectel 员工用的自动化邮箱接入方案。**无需 IT 创建个人 App，全员共享一个 App**。

## 怎么用

对 Hermes 说一句话：

> 帮我配置邮箱

然后浏览器打开 https://microsoft.com/devicelogin，输入 Hermes 显示的 8 位代码，Quectel 账号登录即可。

全程 1 分钟，无需任何 IT 支持。

## 文件

```
msgraph-delegated-setup/
├── README.md
├── SKILL.md              ← Hermes Skill（AI 指令 + 用户指南）
└── templates/
    ├── token_manager.py  ← Token 加密存储 + 自动刷新
    ├── auth_login.py     ← Device Code 登录（--request / --poll 两段式）
    ├── graph_mail.py     ← Graph API 封装（/me/*）
    ├── make_draft.py     ← 新建/回复邮件草稿（不发送，支持 HTML 与附件）
    └── monitor_inbox.py  ← Cron 邮件监控（直接点名检测）
```

## 账号与数据边界

- 技能包里**没有**任何人的邮箱账号 / 密码 / 令牌，只有共享 App 的 `tenant_id` + `client_id`（Azure 应用公开标识）。
- 每个使用者**第一次**都要用自己的公司账号走设备码登录（平台/IT 不提供现成账号）。
- 登录后的 `refresh_token` **只存本机** `.tokens.enc`（Fernet 加密，密钥与机器绑定），直接调云端 Graph 接口取数据，不经过任何中转。
- `.tokens.enc` / `.token_key` / `.env` 永不提交、不上传、不共享；换机器要重新登录。

## 导入

```bash
mkdir -p ~/.hermes/profiles/main-assistant/skills/email-integration/msgraph-delegated-setup/
cp -r * ~/.hermes/profiles/main-assistant/skills/email-integration/msgraph-delegated-setup/
```

## 技术

| 层 | 实现 |
|----|------|
| 认证 | OAuth 2.0 Device Code Flow |
| API | Microsoft Graph v1.0 `/me/*` |
| 加密 | Fernet AES-128-GCM |
| 依赖 | msal, cryptography, requests |

## 安全

- 共享 App（所有人同一 Client ID），各自独立 Token
- 只能看自己邮箱，天然隔离
- Token 加密存储，密钥与机器绑定
- 不存密码
