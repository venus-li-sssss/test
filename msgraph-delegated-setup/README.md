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
    ├── auth_login.py     ← Device Code 登录
    ├── graph_mail.py     ← Graph API 封装（/me/*）
    └── monitor_inbox.py  ← Cron 邮件监控（直接点名检测）
```

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
