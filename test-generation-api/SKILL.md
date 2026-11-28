---
name: test-generation-api
description: 用妙搭「测试用例生成」OpenAPI 把需求文档变成测试用例（分模块 → 建任务 → 轮询 → 取结果 / 导出 Excel）。触发词：测试用例生成, 生成测试用例, 用例生成接口, test-generation, 把需求生成用例, 需求文档出用例, AI 生成测试用例, 自动生成测试用例, 导入需求生成用例, 用例导出 Excel, taskId 轮询。
---

# 测试用例生成（OpenAPI 客户端）

一句话：**给一份需求文档 → 拿到分组好的测试用例（JSON / Markdown / CSV / Excel）**。
导航页「测试用例生成」卡片背后就是这个接口；卡片上人工点的网页 = 本 skill 的自动化版本。

| 项 | 值 |
|---|---|
| 预览域（**实测可用，默认**） | `https://scnrhostplnc.feishuapp.com/app/app_4k5zy309bb5wx` |
| 官方域（文档写的；**2026-11-27 复测仍不可用**） | `https://scnrhostplnc-app_4k5zy309bb5wx-1865305019607353.aiforce.run` |
| 认证 | `Authorization: Bearer 1jX01Ur_-RVIoyy7SsQ3nFvtD2KrotIPmO_DRzJjLxk`（**已内置，公开共享，开箱即用**） |
| 能力 | `GET /openapi/test-generation/ping` → `{"ok":true,"appName":"测试用例自动生成系统"}` |

> 官方域两个坑（2026-11-25 首测、**2026-11-27 平台更新后复测仍一样**）：根路径下 `/openapi/...` 直接 **404 page not found**；
> 加上 `/app/app_4k5zy309bb5wx` 后返回 **403 `api key not allowed to access preview`**
> （该域指向未发布的 preview 部署）；`/app/openapi/...` 返回 200 但内容是 SPA 的 HTML。脚本会自动按「配置域 → 预览域 → 官方域」回退，不用管。

## ① 凭据（已内置，不用配）

**token 直接写在 `scripts/testcase_gen.py` 的 `BUILTIN_TOKEN` 里，公开共享，`python testcase_gen.py ping` 就能直接跑**，
不需要环境变量、不需要建配置文件。这是团队公用的服务账号 token，随 skill 一起发布，**不保密**。

| 项 | 值 |
|---|---|
| token | `1jX01Ur_-RVIoyy7SsQ3nFvtD2KrotIPmO_DRzJjLxk` |
| 位置 | `scripts/testcase_gen.py` → `BUILTIN_TOKEN`（也可用 `scripts/config.local.json`） |

需要临时换凭据（换账号 / 换应用）时才用覆盖，优先级 `环境变量 > config.local.json > 内置`：

```powershell
$env:TEST_GEN_TOKEN = "别的 token"
$env:TEST_GEN_BASE  = "别的 base_url"
```

## ② 命令速查

```powershell
set PY=python "<此 SKILL.md 所在目录>\scripts\testcase_gen.py"

%PY% ping                                        # 验证 token（先跑这个）
%PY% run --doc 需求.md --name "QDM562 V23 送测需求" --test-object QDM562 --export --md 用例.md --cases-csv 用例.csv
%PY% create --doc 需求.md --name "..." --modules modules.json
%PY% status <taskId> --watch                     # 每 20s 轮询，最长 40 分钟
%PY% result <taskId> --md 用例.md --cases-csv 用例.csv [--out r.json]
%PY% cases  <taskId> --page 1 --pageSize 200     # 结果被截断（>2000 条）时用
%PY% export <taskId> --dest docs                 # 下载 Excel 用例表（文件名服务端给）
%PY% framework <taskId> --dest docs              # 下载测试框架：模块结构脑图 .xmind（2026-11-27 新增）
```

`run` 一条龙：create → 轮询 → result →（`--export` 时）下载 Excel。
已有 taskId 加 `--task-id <id>` 复用，**不要重复建任务**。

## ③ 标准流程（agent 照做）

### 第 1 步 · 拆分功能模块（人的活，不能甩给接口）

按「**一个完整业务功能 / 交互闭环**」拆模块，写 `modules.json`：

```json
[
  {"path": ["AT 指令管理", "固件版本查询"], "description": "该模块需求原文摘录 200-400 字", "type": "1"},
  {"path": ["版本记录"], "description": "文档里的历史版本表", "type": "0"}
]
```

硬要求：

- `description` 是**原文摘录**，200–400 字，不改写不编造
- 一个功能点的请求 / 响应 / 状态通知 / 错误码放**同一个模块**，别拆散
- 别按文档章节机械切，按**能力**切
- 可测功能 `type="1"`；目录 / 版本记录 / 术语表 / 免责声明 `type="0"`（不会被生成用例）
- 模块数 **5–30**，超 40 个请合并

> **两条实测必守（2026-11-27，QDM562 FCT 协议 94→70 条）**
> 1. **别让任何模块的 description 变成"整张表概览"**。给「通信帧格式与校验」写了全表介绍后，
>    平台把 30 多条指令全塞进这个模块，与各专项模块**大面积重复**（94 条里 40 条重复）。
>    公共/基础类模块只写它自己的规则（帧结构、长度字段、校验、偏移）。
> 2. **子能力要单列模块**。GNSS 塞在「模式切换」旁边时，生成的 GNSS 用例是 **0 条**；
>    单独拆成「GNSS NMEA 与 FCT 语句」后拿到 4 条。响应里 `moduleCount` 会比 `modules` 条数多
>    （平台会自己合并/细分，13 个 path → moduleCount 15），以 `moduleCount` 与 xmind 为准。

不传 `modules` 也能跑（按章节标题自动切），但**质量差一截**，能拆就拆。

### 第 2 步 · 建任务

字段：`name`、`content`（全文，≤20 万字符，优先传这个）、`modules`、`testObject`（型号）、
`background`、`fileUrl`（与 content 二选一）。
成功返回 **HTTP 201** + `{"taskId":"...","status":"splitting","statusPath":...,"resultPath":...}`。

### 第 3 步 · 轮询

`status <taskId> --watch`，20s 一次。状态流转实测：
`splitting → extracting → ... → completed`（自检任务 2 模块 / 102 秒完成）。

| status | 动作 |
|---|---|
| `completed` | 取结果 |
| `failed` / `stopped` | 停，把 `errorMsg` 原样反馈用户 |
| 超 40 分钟 | 告知「仍在执行，可稍后用同一 taskId 再查」，**别重建任务** |

一般 2–20 分钟。状态体里还有 `progress` / `successCount` / `failedCount` / `moduleCount` / `caseCount` / `duration`。

### 第 4 步 · 取结果

`result <taskId> --md x.md --cases-csv x.csv --out r.json`：

- `completed` / `caseCount` / `truncated` / `modules[]`
- `modules[]`：`modulePath`、`description`、`caseCount`、`cases[]`
- 单条用例：`caseId`、`name`、`precondition`、`testSteps[]`、`expectedResult`、`priority`、`moduleName`、`testContent`

`truncated=true`（>2000 条）时脚本自动转 `cases` 分页（pageSize ≤200）拉全量再落盘。
CSV 用 UTF-8 BOM，Excel 双击直接开，列序固定：用例编号/所属模块/用例名称/前置条件/测试步骤/预期结果/优先级/测试内容。

### 第 5 步 · Excel

`export <taskId> --dest docs` → 取 `fileName` / `downloadUrl`（1 小时有效）/ `size` / `caseCount` / `truncated`，
下载存成 `fileName`。**任务未完成返回 409**，继续轮询就行。

### 第 6 步 · 测试框架（.xmind，2026-11-27 平台新增）

`framework <taskId> --dest docs` → `GET /openapi/test-generation/tasks/{taskId}/framework`

返回：`fileName`（`<任务名>_模块结构_<时间戳>.xmind`）、`mimeType: application/xmind`、
`size`、`moduleCount`、`downloadUrl`（1 小时有效）。仍然是 409=任务未完成。

xmind 结构实测（QDM562 任务，38 KB / 15 模块）：根节点=任务名 → 一级=功能模块 →
二级=子模块（带 notes 存需求原文摘录）→ 三级叶子把该模块下的用例塞成 **JSON 数组字符串**
（`["1","IMEI号读取","P0","无","..."]`），导入 XMind 后显示为一行长文本，可读性一般。
要"框架 + 用例"一套交付，就是 `framework` + `export` 两个文件。

回报用户时按模块分节，每条列：用例编号、用例名称、前置条件、测试步骤、预期结果、优先级，末尾给总数与模块数。

## ④ 踩过的坑

1. **建任务成功码是 201 不是 200**，只认 200 会误判失败（脚本已按 2xx 判）。
2. **官方 `aiforce.run` 域不可用**：`/openapi/...` → 404，`/app/app_id/openapi/...` → 403
   `api key not allowed to access preview`；且该域证书在 Python 下会 `Hostname mismatch`。
   用 `scnrhostplnc.feishuapp.com/app/app_4k5zy309bb5wx` 作 base。
3. **接口返回的 `testSteps` 自带 "1./2." 前缀**，直接渲染会出现 "1. 1. xxx"（脚本 `clean_step` 已剥）。
4. **同一份需求只建一次任务**；创建后 `content` 不可改，结果以首次提交为准。
5. **`errorMsg` 说「没有可用的账号配置」** → 平台侧账号没配，原话转给系统管理员，别自己重试。
6. **`errorMsg` 说文件链接解析失败** → 别修链接，把需求正文塞进 `content` 重新提交。
7. **别把 409（任务未完成）当失败**。
8. Excel 导出上限 2000 条（`truncated=true` 说明只含前 2000），要全量走 `cases` 分页。
9. **2026-11-27 平台更新后的实测（重要，别再照旧经验说话）**：
   - **`export` 现在和网页下载完全一致**：同一 taskId 拉下来 vs 平台网页点下载，93 行 × 12 列
     **值 0 差异 + 样式 0 差异**（填充/字体/边框/对齐/行高/合并区全同）。此前那套
     「服务端另渲染一套模板（E–L 列刷白底细边框、说明行加粗、第 11 行行高 50）」的问题已修复。
   - 导出文件名**不再带时间戳后缀**（`测试用例_<任务名>.xlsx`），同名覆盖注意别弄混。
   - 新增 `GET /tasks/{taskId}/framework`（.xmind 模块结构），见「第 6 步」。
   - `run` 子命令曾报 `AttributeError: 'Namespace' object has no attribute 'watch'`（cmd_status 读 a.watch），已修。
10. **别自己重排平台导出的 Excel**：平台件本身就是 12 列产测执行模板（执行人/执行时间/设备编号/
    执行步骤/实测结果/实测记录/备注 + 合并表头 + 主题配色）。用 openpyxl 重写会丢样式、还会因
    `delete_rows` 造成样式漂移（说明行被加粗、行高变 50），用户一眼就看出"格式不对"。
    要清洗就**只改值不改样式**（别删行，直接清 `.value`），并跳过 `MergedCell`。
11. **统计条数只认 `B7` 格子或接口 `caseCount`，别数行**：导出件第 1–8 行是执行信息区、
    第 9 行是中英双语表头、每个模块前还有一行"模块名 + 需求摘录"的**分区说明行**（A 列有值、
    B 列被合并为空）。70 条用例的表现在有 82 个非空行，直接数行会数成 82。

## ⑤ 依赖

Python 3.8+，纯标准库（urllib），不需要 requests。
