---
name: cred-card
version: 1.0.0
description: 统一凭据卡片。集中管理内部/外部系统的账号密码，按账号身份分三层：飞书场景直接用飞书身份免密；公司邮箱账号（@ikotek.com / @quecagent.com / @quectel.com）用 Windows DPAPI 加密存储，禁止明文；其他账号（客户邮箱、测试账号）明文保存在卡片里即可。触发词：账号密码、凭据、登录、要密码、保存密码、免登录、这个系统的账号在哪、迁移机器怎么办。
type: tool
---

# 统一凭据卡片 (cred-card)

一个地方管所有系统的“能不能进、用什么身份进”。
目标：**一次配置，后面所有 agent 自动用；该加密的加密，不该加密的别折腾。**

## 三层策略（先判层，再决定存哪）

| 场景 | 取什么身份 | 存哪 |
|---|---|---|
| 飞书内（云文档/云盘/IM/妙搭内嵌页/多维表格） | **直接用飞书身份**，不需要账号密码 | 不存 |
| 脚本/命令行访问支持 SSO 的内部系统（网盘、内部导航等） | 先用系统自身的 SSO 令牌链路 | 令牌缓存（过期再用下一层兜底） |
| 账号是**公司邮箱**（`@ikotek.com` / `@quecagent.com` / `@quectel.com`） | 账号 + 密码 | `%USERPROFILE%\.cred-card\vault.dpapi.json`（**DPAPI 加密**，仅本机本用户可解） |
| 其他账号（客户邮箱如 `@ninebot.com`、测试/临时账号） | 账号 + 密码 | `%USERPROFILE%\.cred-card\accounts.json`（**明文**，方便复用） |

运行期状态**一律在用户目录，不在 skill 目录**——skill 目录会被同步/上传/打包，用户目录不会。这也是「每人各自凭据」的物理保证：代码共用，凭据各在各的 `%USERPROFILE%` 下。

判定由 `policy.json` 的 `protected_domains` 决定，脚本自动识别，不需要人记规则。
公司邮箱账号想强行明文存会被**直接拒绝**（这是硬约束，不是提示）。

## 常用命令

```powershell
$cred = "<本 skill 目录>\scripts\cred.py"

python $cred set --id qdisk --username venus.li@ikotek.com      # 交互输入密码，自动判层→加密
python $cred set --id ninebot --username xxx@ninebot.com --password 123456      # 非公司账号→明文
python $cred get  --id qdisk --field password                    # 取密码（给其他脚本用）
python $cred get  --id qdisk --json                              # 取整条（含 username/note）
python $cred list                                                # 看有哪些、分别在哪一层（不显示密码）
python $cred where --id qdisk                                    # 只输出 protected/plain，便于脚本分支
python $cred remove --id ninebot
python $cred classify --username venus.li@ikotek.com             # 只判断该账号该不该加密
```

## 给其他 skill 的调用约定

1. **先问有没有**：`python cred.py get --id <系统> --missing-ok --field password`，空串表示没有，别直接报错。
2. **取到就用**：不要打印、不要写进日志/文档/测试报告，直接用。
3. **没有就引导用户配一次**，不要自己猜密码，也不要去扒别人机器上的配置。
4. **公司邮箱账号永远不进明文文件**，包括 `device.yaml`、`.env`、脚本注释、SKILL.md 示例。

## 安全边界

- `vault.dpapi.json` / `accounts.json` 都在 `%USERPROFILE%\.cred-card\`，**skill 目录里零凭证**（符合 `account-login-skill` 的「仓库零凭证」红线）。
- DPAPI 绑机器 + 绑 Windows 用户，**换机器解不开**，迁移时在那台机器上重新 `set` 一次。
- 明文层只放“泄露了也无所谓”的账号（客户提供的测试号、临时账号）。
- 不要把密码写进命令行参数（会进 PowerShell 历史），用交互输入。
- 飞书场景不要为了“统一”而额外存一份账号密码，那只是多一个泄露面。
- 本 skill 可以正常推上 GitHub：仓库里只有代码和策略，没有凭据。

## 与“移远网盘(qdisk)”的关系

`qdisk-quectel` 已内置同一套机制（`auth --set-cred` → `.cred.dpapi.json`，refresh_token 失效时自动用账号密码重登）。
两者语义一致，互不依赖：网盘那边用它自己的凭据文件，本卡片管理的 `--id qdisk` 是给其他脚本/其他系统复用的副本。
如果只想维护一份，可以只配 `qdisk-quectel`，本卡片里不重复登记。

## 与 `account-login-skill` 的关系

仓库里的 `account-login-skill` 是「怎么写账号登录型 skill」的规范。
本卡片的定位是它落地后的**统一入口**：规范说“每人用自己账号、首次问一次、状态放用户目录”，本卡片把这件事做成一条命令，并补上“哪些账号必须加密”的分层规则。
两者冲突时以 `account-login-skill` 的红线为准；本卡片已按红线把状态全部放到了 `%USERPROFILE%`。

## 排错

| 现象 | 原因 | 处理 |
|---|---|---|
| `受保护凭据解密失败` | 换了机器/换了 Windows 用户，或 vault 被破坏 | 重新 `set` 一次 |
| `当前系统不支持 DPAPI` | 非 Windows 环境 | 公司邮箱账号在非 Windows 上不做本地存储 |
| `get` 返回空但 `list` 里有 | id 拼错 | 用 `list` 核对 id |
| 公司账号被拒绝明文 | 策略拦截（预期行为） | 去掉 `--plain`，走加密 |
