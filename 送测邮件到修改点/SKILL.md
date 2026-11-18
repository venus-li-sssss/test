---
name: 送测邮件到修改点
description: '流程 skill：读送测邮件 → 取 changelist 与版本号/平台 → 导入 SMOD 修改点系统 → 编写测试用例 → 下载修改点报告并归档。串联「邮箱(Outlook/MS Graph)」与「修改点(changelist2xlsx)」两套 skill，把一次送测从邮件走到平台闭环。Triggers: 送测邮件、版本送测、送测流程、邮件里的修改点、把修改点提到平台、读邮件导入修改点、送测到修改点、邮件串修改点、changelist 导入平台、送测邮件建用例、全流程导入修改点、邮件到 SMOD、sendtest flow。'
tags: [流程, 送测, 修改点, changelist, smod, 测试用例, workflow]
aliases: ["送测流程", "送测邮件流程", "送测到修改点", "sendtest"]
---

# 送测邮件 → 修改点系统 → 测试用例（流程 skill）

一条链路把「收到送测邮件」走到「平台上修改点+用例齐、报告落本地」。
本 skill **只做编排**，具体动作全交给两个兄弟 skill：

| 环节 | 复用的 skill | 落点 |
|---|---|---|
| 读邮件/取附件 | `msgraph-delegated-setup`（实现在 `<工作区>/scripts/delegated-outlook-ikotek`） | Outlook / M365，账号 venus.li@ikotek.com |
| 导入修改点 + 建用例 + 导报告 | `changelist2xlsx`（`skills/changelist2xlsx/scripts/smod_changelist_import.py`） | SMOD `smod.quectel.com` |

```
送测邮件(附件 changelist_*.txt + 版本号 + 平台)
   → [解析] → [闸门校验] → [导入 SMOD] → [建用例+置结论] → [导出修改点报告] → [归档命名]
```

## ① 何时用我

- "帮我看下 XX 的送测邮件，把修改点导进平台"
- "送测邮件收到了，修改点提了吗 / 用例建了吗"
- "从邮件一路做到修改点和用例"
- 收到 `【版本送测】...` 邮件后要开测，需要平台侧修改点/用例先就位

单环节请求不用我：只想看邮件 → 邮件 skill；已拿到 txt 只想导入 → `changelist2xlsx`。

## ② 一条命令（推荐）

```powershell
cd <skill目录>\scripts

# 1) 只读：找邮件、解析版本/平台/附件，输出计划（默认 dry-run，不写平台）
python sendtest_flow.py --project QDM562 --version-hint 766

# 2) 确认计划无误后落库（导入修改点 + 建用例 + 置结论 + 导报告）
python sendtest_flow.py --project QDM562 --version-hint 766 --apply ^
    --hw-platform ASR1602S --executor me --case-result ps ^
    --out-dir "D:\work\QDM562\版本测试\766"
```

参数：

| 参数 | 说明 |
|---|---|
| `--project QDM562` | 项目号，用于搜邮件与 SMOD 项目关键字（**必填**，别用版本号前缀猜） |
| `--version-hint 766` | 只用主题/附件含该串的邮件；不给则取最新一封送测邮件 |
| `--hw-platform ASR1602S` | SMOD 硬件平台；不给则从正文猜，猜不到就报错退出（**QDM562 固定 ASR1602S**） |
| `--executor me` | 修改点执行人，`me`=当前登录人 |
| `--case-result ps\|ti\|pc` | 用例与修改点结论，`ps`=PASS（已实测）、`ti`=Test-in-Process（默认） |
| `--apply` | 真写平台；不加只打印计划 |
| `--out-dir` | 报告归档目录；默认 `D:\work\<项目>\版本测试\<版本末段>` |

## ③ 必守的闸门（踩过的坑，别放松）

1. **邮件里没有 changelist 就不许导。**
   实测 2026-11-17 的 `【版本送测】【QDM562】【双频GNSS】专项测试`（766）**只给了网盘路径、没附修改点文件**。
   这时正确动作 = 停下来告诉用户"这封没带修改点，需要向发件人（Coco Xie）索要"，
   **绝不能拿上一版（765）的 changelist 顶替**——版本对不上会把旧修改点写进新版本。
2. **版本号前缀常常不是项目名。**
   `LTE01R07A05_BT_C_SDK_A_SDK_QDM562CNAK_01.001.01.001_765` 按第一个下划线切会得到 `LTE01R07A05`，
   必须用邮件里的项目号（`QDM562`）覆盖，否则 SMOD 历史搜索搜错关键字。
3. **硬件平台必须显式指定。**
   QDM562 历史记录里 ASR1602 / ASR1602S / ASR1606 混在一起，自动推断会选错。
4. **修改点文件只在附件里，不在正文。** 正文只有网盘路径；正文里的 `changelist` 字样不算数。
   （签名里的 `image001.png` 等内嵌图不是附件，别当输入。）
5. **先 dry-run 再 `--apply`。** 打印出来的"版本/平台/项目/附件/用例数"对不上就别写库。

## ④ 手工分步（脚本不适用的老邮件时）

1. **搜邮件**：Graph `$search` 关键词 = 项目号（如 `QDM562`），挑主题含「送测」的最新一封。
2. **取附件**：`GET /me/messages/{id}/attachments`，跳过 `isInline=true`，认 `changelist_*.txt`。
3. **解析**：正文取 `测试版本：/版本信息：/客户版本号：` 后的完整版本串；平台从正文芯片型号取。
4. **导入 + 建用例**（changelist2xlsx）：
   ```powershell
   python skills\changelist2xlsx\scripts\smod_changelist_import.py "<txt>" "<完整版本号>" ^
       --project QDM562 --hw-platform ASR1602S --executor me --case-result ps
   ```
   - 只导入不建用例：加 `--import-only`
   - 用例内容要按修改点需求写实（前置条件/步骤/期望），别用"测试xxx/xxx正常"式模板凑数
5. **导修改点报告**：`GET /api/projects/odmm/betavers/{id_beta_ver}/report` 返回 JSON 里带 stres 下载链，
   拉下来按命名口径改名（见 ⑤）。

## ⑤ 归档命名口径

```
<完整版本号>_修改点测试报告_Report.xlsx
```
例：`LTE01R07A05_BT_C_SDK_A_SDK_QDM562CNAK_01.001.01.001_765_修改点测试报告_Report.xlsx`
版本号用**完整长串不缩写**；平台导出的原名是 `..._765_Report.xlsx`，下载后要改名。

## ⑥ SMOD 侧已知的坑（已写进 changelist2xlsx，这里备查）

| 坑 | 现象 | 正确做法 |
|---|---|---|
| 登录 | `authorizeToken` 返回 `30001 Redirect URI mismatch` | `redirect_uri` 取 `/api/login/authorizeUrl` 动态值（2026-11 已迁到 `smod.phicotek.com`） |
| 执行人 | `PATCH .../points/{id}/executor` 返回 200 但不落库 | 用 `.../points/{id}/id_executor` |
| 用例编号 | 同一秒建两条拿到同一个 TC 号 | `/api/newCaseCode` 撞号要 sleep 1.05s 重取 |
| 分类 | `<Change Type>: new requirement`（单数）留空 | 已在 CATEGORY_MAP 支持单复数；事后可 `PATCH .../points/{id}/category {"value":"nw"}` |
| 出包记录 | 版本 release 那条没有 Change Type | 不建用例，置 `Blocked-NoRun` + 备注「无需测试」 |

## ⑦ 收尾汇报（固定几块，别省）

- 用的是哪封邮件（主题 + 时间 + Message-ID 后 8 位）
- 版本号 / 硬件平台 / SMOD 版本 id（新建 or 复用）
- 修改点条数（分类分布）+ 用例条数与编号 + 结论
- 报告落盘绝对路径（纯文本路径，中文路径别给可点击链接）
- 未做的事（比如"766 无 changelist，等你向 Coco 要"）
