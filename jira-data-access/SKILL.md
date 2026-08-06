---
name: jira-data-access
description: 提供JIRA系统数据访问和处理能力，支持通过JQL或JIRA搜索URL查询缺陷数据，进行过滤、排序、统计，并生成标准化的DOCX缺陷报告。当用户需要查询JIRA缺陷、生成缺陷报告或分析JIRA数据时使用此技能。
agent_created: true
disable: false
---

# JIRA数据访问技能

## Overview

该技能封装了JIRA系统的交互能力，支持从JIRA提取缺陷数据，提供数据过滤、排序、统计功能，并可生成符合规范的DOCX格式缺陷报告。适用于需要定期从JIRA获取数据并生成报告的场景。

## 核心功能

该技能提供以下核心能力：

### 1. JIRA数据查询
- 支持通过JQL查询语句直接查询JIRA缺陷数据
- 支持通过JIRA搜索页面URL提取数据
- 自动处理JIRA登录和会话管理
- 解析并返回结构化的缺陷数据（包含Bug号、描述、状态、严重等级等字段）

### 2. 数据处理能力
- 过滤已关闭的缺陷（默认过滤ST_Closed状态）
- 按严重等级过滤（支持指定最小等级）
- 按项目名称过滤
- 按严重等级排序（A>B>C>D>E>F）
- 按状态排序
- 生成统计信息（按等级、状态、项目维度统计）

### 3. 报告生成功能
- 自动生成标准化DOCX格式缺陷报告
- 支持生成Markdown格式数据输出
- 报告包含统计信息汇总和缺陷详情表格
- 缺陷详情表格含「备注」列；根据调用方式可写入：**空 / 原始 JIRA 评论 / AI 分析后的类人工备注**
- 支持自定义版本号和输出路径
- **一键输出三份报告**（见「6. 三份报告 + AI 分析备注」）：`JIRA缺陷报告.docx`（基础）、`JIRA缺陷报告_含备注.docx`（原始评论）、`JIRA缺陷报告_含备注_AI处理备注生成新的备注信息.docx`（AI 类人工备注）

### 4. 单个JIRA问题详情访问（访问具体JIRA页面）
- 支持通过问题Key（如 `QDM565EA-396`）访问**单个** JIRA 问题的完整详情页面数据
- 采用 JIRA 标准 REST 接口 `GET /rest/api/2/issue/{issueKey}` 获取结构化数据（详见 `references/jira_issue_page_interface.md`）
- 自动解析并返回：问题Key、标题、状态、优先级、类型、报告人、处理人、创建/更新时间、描述、所有自定义字段（自动映射中文名称）、评论（作者/时间/内容）、附件（文件名/时间/链接）、关联问题
- 字段中文名称通过 `GET /rest/api/2/field` 动态获取并缓存，内置常用字段兜底映射
- 自动过滤系统噪声字段（全局公告栏、开发状态对象dump、排名序号等）
- 支持生成单个问题的 Markdown 与 DOCX 详情报告

### 5. 完整数据集导出（推荐：先取全部列表，再逐个取详情）
- **两阶段流程**：先用 `search_issues()` 通过 `GET /rest/api/2/search` 分页拉取**全部** JIRA 问题列表（轻量、快），再并发对每个 Key 调 `get_issue_detail()` 取**完整详情**，最终汇成一份「完整数据集」
- 完整数据集 = `list[detail]`（每个元素的 `detail` 结构与单个问题详情一致，含全部自定义字段/评论/附件/关联问题）
- **默认排除 ST_Closed**：所有基于 JQL 的搜索/报告/完整数据集导出，当 JQL 中未显式写 `status` 时，会自动追加 `AND status != "ST_Closed"`（会自动处理 `ORDER BY`，放在排序之前）
- 一键落盘为 JSON 文件（`jira_complete_dataset.json`），**后续所有操作直接读 JSON，无需再访问 JIRA**
- 并发拉取（默认 4 线程，可调），单条失败自动用基础信息兜底，不中断整体
- 基于完整数据集可直接生成 Markdown / DOCX 报告（含统计概览 + 问题清单），或做任意自定义过滤/统计
- 问题清单表格包含「备注」列，展示每个问题的最新 JIRA 评论/备注内容
- 推荐作为「取数据」与「用数据」解耦的入口：一次拉全，多次复用

### 7. 创建 JIRA 问题（Create Issue）

该技能不仅「读」JIRA，还能「写」——直接创建新的 JIRA 问题（含附件上传）。接口来自 `ticket.ikotek.com.txt` 的 HAR 抓包，走的是 JIRA 传统表单端点 `POST /secure/QuickCreateIssue.jspa`，并配套 `GET /secure/CreateIssue.jspa`（取令牌）、`POST /rest/internal/2/AttachTemporaryFile`（传附件）。选项型字段（下拉框）的值必须是**选项 ID（数字）**，ID 通过 `createmeta` 由中文 label 自动解析。详细接口契约见 `references/jira_create_issue_interface.md`。

**典型调用**（模块级快捷入口，自动登录）：

```python
from scripts.jira_client import create_issue

key = create_issue(
    account="venus.li@ikotek.com",
    password="@@@@@Aa13106680957",
    project_key="IKQDM551EA",      # 或 project_id="10800"
    issuetype_name="ST-BUG",       # 默认 ST-BUG
    summary="ST[QDM_551][OTA]新版本组合升级耗时变长",
    description="[测试环境]\n模块IMEI:860813079216961\nSIM卡:8986...\n[测试步骤]\n1. ...\n[测试现象]\n...\n[概率]\n必现",
    assignee="siliver.nong@ikotek.com",
    priority="10003",              # 优先级：label（如 'High'）或 id（'10003'）
    components="FM33FK545_APP",    # 模块：label 或 id（'10700'）
    fields={
        "问题归属": "ODM",          # 选项型字段：可传中文 label 或选项 id（'11869'）
        "BUG严重等级": "B-Major",    # label 自动解析为 id（11647）
        "BUG优先级": "P5",
        "功能类别": ["Tracker", "WIFI"],   # 级联选择：[父, 子]（label 或 id）
        "BUG发现的软件版本": "QDM551_FM33FK545_01.001.01.001",
    },
    attachments=[r"D:\logs\QDM551_DEBUG.txt", r"D:\logs\script_log.txt"],  # 本地附件路径
    links=[{"type": "blocks", "key": "IKQDM551EA-600"}],                  # 可选关联
)
print("已创建：", key)   # 如 'IKQDM551EA-700'
```

> **推荐流程（先草稿、后创建）**：先用 `create_issue_draft(...)`（或 `create_issue(..., draft=True)`）拿到只读草稿并展示给用户确认；用户同意后，用同样的参数（去掉 `draft`）真正创建。例如：
> ```python
> from scripts.jira_client import create_issue_draft, create_issue
> args = dict(account=account, password=password, project_key="IKQDM551EA",
>             issuetype_name="ST-BUG", summary=summary, description=description,
>             fields=fields, assignee="venus.li@ikotek.com", priority="10002",
>             components="FM33FK545_APP", attachments=[r"D:\logs\script_log.txt"])
> # 1) 先出草稿，展示给用户确认（不创建、不上传附件）
> draft = create_issue_draft(**args)
> #    -> 展示 draft["summary"] / draft["description"] / draft["resolved_fields"] / draft["attachments"]
> # 2) 用户确认后，真正创建（draft 默认 False，这里显式写出来强调）
> key = create_issue(draft=False, **args)
> ```

> **⚠️ 创建前必须：先出草稿、经用户确认**
> 调用创建接口前，**必须先**用 `build_create_draft()`（或 `create_issue(..., draft=True)`）生成一份只读草稿（标题 / 描述 / 各字段解析后的选项 ID / 待上传附件清单），完整展示给用户，**获得用户明确同意后**才能用 `create_issue(draft=False)` 真正创建。**绝不允许在用户未确认时直接创建 JIRA。**
> 缺字段时，先用 `get_issue_raw_fields(历史同类问题Key)` 借鉴默认值，把存疑项列出来与用户确认，再补全草稿。

**历史测试 JIRA 内容样式（必须遵循，参考 IKQDM551EA-609/-603/-646）**

创建测试类缺陷时，标题与描述必须严格套用历史版式，禁止自由发挥写成长篇大论：

- **标题**：`ST[QDM_551][OTA]<现象>；期望<期望>；<概率>`
  例：`ST[QDM_551][OTA]挂测组合升级，升级失败；期望升级成功；大概率`
- **描述**分块（标点敏感：`[测试环境]：`、`[测试步骤]：` 带全角冒号；`期望结果:` 仅半角冒号；`[测试现象]` 无冒号；`[概率]：` 再带全角冒号）：
  ```
  [测试环境]：
  模块IMEI编号：xxx
  SIM卡：xxx
  AT通信口：/
  网络配置：xxx
  产品线：xxx
  [测试步骤]：
  1.动作
  期望结果:
  1.期望
  [测试现象]
  <现象，通常直接等于标题>
  [概率]：<概率>
  ```
- 用模块级函数可直接生成合规内容（已内置上述版式）：
  ```python
  from scripts.jira_client import build_bug_summary, build_bug_description
  summary = build_bug_summary(phenomenon="挂测组合升级，升级失败",
                              expectation="升级成功", probability="大概率")
  description = build_bug_description(
      env={"imei":"860813079216961","sim":"8986...","at_port":"/","network":"移动","product_line":"TRACKER"},
      steps="运行XXX升级压力脚本，对设备执行自定义组合升级（T-BOX、BMS、VCU、TFT、MCU、TCU 六个部件同时升级）",
      expected="组合升级成功，6个部件均升级到预期版本",
      phenomenon=summary, probability="大概率")
  ```

**创建后修正（update_issue）**：若创建后需要改描述/标题/字段（如把描述改成历史版式），用 `update_issue(issue_key, description=..., summary=..., assignee=..., fields=...)`（REST PUT）。模块级快捷入口 `update_issue(account, password, issue_key, ...)`。

**`create_issue` / `JIRAClient.create_issue` 参数说明**：
- `project_key` / `project_id`：项目 Key（如 `IKQDM551EA`）或 ID（如 `10800`），二选一。
- `issuetype_name`：问题类型，默认 `ST-BUG`。
- `summary`：标题（必填）。
- `description`：描述，映射到本实例的「BUG描述」字段（`customfield_10244`）。
- `fields`：其它自定义字段字典；`key` 可为 `customfield_XXXXX` 或中文名称；`value` 对选项型字段可为**选项 ID**或**中文 label**，级联选择用 `[父, 子]`，多选用 list。
- `assignee`：处理人邮箱；`priority` / `components`：label 或 id。
- `attachments`：本地附件文件路径列表（自动上传并挂接）。
- `links`：关联问题列表，每项 `{"type":"blocks","key":"..."}`。

**缺数据怎么办（与历史 JIRA 对齐）**：当调用方只给了部分字段时，可先用 `JIRAClient.get_issue_raw_fields(某历史问题Key)` 读取同类历史问题的原始字段（含选项 ID），借鉴其默认值（如 问题归属 / BUG严重等级 / 模块 / 处理人等），再与用户确认缺失或存疑项，最后补全并创建。

### 6. 三份报告 + AI 分析备注（推荐入口：export_three_reports）
- 一次调用同时产出三份 DOCX 报告：
  1. `JIRA缺陷报告.docx` —— 基础缺陷报告（备注列留空）
  2. `JIRA缺陷报告_含备注.docx` —— 备注列写入**原始 JIRA 评论/备注**（作者+时间+正文，最多前 5 条、单条截断 200 字）
  3. `JIRA缺陷报告_含备注_AI处理备注生成新的备注信息.docx` —— 备注列写入 **AI 分析后的类人工备注**
- 同时落盘 `jira_ai_input.json`：供 AI（WorkBuddy）分析的结构化输入，含每个问题的 严重等级/状态/描述/关键自定义字段/评论。
- **AI 备注生成流程（WorkBuddy 自身分析，无需任何 API key）**：
  1. 先调用 `export_three_reports(..., ai_notes=None)` 生成报告 1、2 与 `jira_ai_input.json`（报告 3 此时备注留空占位）。
  2. 由 WorkBuddy 读取 `jira_ai_input.json`，结合 JIRA 信息与评论，参考历史报告的人工备注风格（例：「未复现问题，需要客户提供日志」「暂未分析到原因，小概率出现，需要复现问题且抓模组日志」「主要原因：http下载返回错误码719，服务器主动断开导致(服务器问题)」），为每个问题生成 1~4 行中文类人工备注（结论 + 根因 + 下一步），并写入 `ai_notes`（`dict{Bug号: 备注文本}`）。
  3. 再次调用 `export_three_reports(..., ai_notes=ai_notes)` 重新生成报告 3（报告 1、2 内容不变）。
- 类人工备注要点：简洁、有结论、有下一步；忽略系统通知类评论（如 `admin：你正在处理的JIRA即将超时`）。

## 使用方法

### 快速开始

当用户需要查询JIRA数据或生成缺陷报告时，按照以下步骤操作：

1. **获取必要参数**：
   - JIRA账号和密码（默认账号：`venus.li@ikotek.com`，默认密码：`@@@@@Aa13106680957`；如用户未提供，使用默认值）
   - 查询条件：JQL语句 或 JIRA搜索URL
     - **默认会自动排除 `ST_Closed` 状态的问题**（当 JQL 未显式包含 `status` 时）
     - 如果需要搜索已关闭问题，在 JQL 中显式写 `status = "ST_Closed"` 或传 `exclude_closed=False`
   - 版本号（可选，用于报告显示）
   - 输出路径（可选，建议使用原始字符串r"路径"处理Windows路径）
   - 输出格式（可选，支持'docx'或'markdown'，默认'docx'）

2. **调用脚本**：
   使用scripts/jira_client.py中的`generate_report`函数：
   
   生成DOCX格式报告：
   ```python
   from scripts.jira_client import generate_report
   report_path = generate_report(
       account="your_account@example.com",
       password="your_password",
       jql_query="issuetype = ST-BUG AND text ~ 'QDM565' ORDER BY status ASC",
       version="LTE01R07A01_C_SDK_E_QDM565_01.001.01.003_V04",
       output_file="JIRA缺陷报告.docx",
       output_format="docx"
   )
   ```

   生成Markdown格式数据：
   ```python
   from scripts.jira_client import generate_report
   report_path = generate_report(
       account="your_account@example.com",
       password="your_password",
       jql_query="issuetype = ST-BUG AND text ~ 'QDM565' ORDER BY status ASC",
       version="LTE01R07A01_C_SDK_E_QDM565_01.001.01.003_V04",
       output_file="JIRA缺陷报告.md",
       output_format="markdown"
   )
   ```

   或使用URL方式：
   ```python
   report_path = generate_report(
       account="your_account@example.com",
       password="your_password",
       jira_url="https://ticket.ikotek.com/issues/?filter=12921&jql=issuetype%20%3D%20ST-BUG%20AND%20text%20~%20%22QDM565%22%20ORDER%20BY%20status%20ASC",
       version="LTE01R07A01_C_SDK_E_QDM565_01.001.01.003_V04",
       output_format="markdown"
   )
   ```

   **推荐：一次输出三份报告（基础 / 含原始备注 / 含 AI 分析备注）**：
   ```python
   from scripts.jira_client import export_three_reports
   # 第一步：ai_notes=None → 生成报告1、2 与 jira_ai_input.json（报告3备注先留空）
   res = export_three_reports(
       account="your_account@example.com",
       password="your_password",
       jql="issuetype = ST-BUG AND text ~ 'QDM565' ORDER BY status ASC",
       version="LTE01R07A01_C_SDK_E_QDM565_01.001.01.003_V04",
       output_dir="./output"
   )
   # 第二步：WorkBuddy 读取 res["ai_input"] 生成 ai_notes = {Bug号: 类人工备注}
   # 第三步：回填 AI 备注，重新生成报告3
   res = export_three_reports(
       account="your_account@example.com",
       password="your_password",
       jql="issuetype = ST-BUG AND text ~ 'QDM565' ORDER BY status ASC",
       version="LTE01R07A01_C_SDK_E_QDM565_01.001.01.003_V04",
       output_dir="./output",
       ai_notes=ai_notes
   )
   ```

3. **返回结果**：
   - 报告生成成功后，向用户提供生成的报告文件路径
   - 如果需要，展示报告的统计摘要信息

### 访问单个JIRA问题详情

当用户需要查看某个具体 JIRA 问题（而非列表）的完整信息时，使用 `generate_issue_report` / `generate_issue_markdown` / `generate_issue_docx`：

生成单个问题的 Markdown 详情：
```python
from scripts.jira_client import generate_issue_markdown
md_path = generate_issue_markdown(
    account="your_account@example.com",
    password="your_password",
    issue_key="QDM565EA-396",
    output_file="QDM565EA-396_详情.md"
)
```

生成单个问题的 DOCX 详情：
```python
from scripts.jira_client import generate_issue_docx
docx_path = generate_issue_docx(
    account="your_account@example.com",
    password="your_password",
    issue_key="QDM565EA-396",
    output_file="QDM565EA-396_详情.docx"
)
```

或使用统一入口 `generate_issue_report`（output_format 可选 `'markdown'` / `'docx'`）。

在代码中分步获取原始数据：
```python
from scripts.jira_client import JIRAClient
client = JIRAClient(account, password)
raw_json, detail = client.get_issue_detail("QDM565EA-396")
# detail 为结构化字典，含 key/summary/status/custom_fields/comments/attachments/issuelinks 等
print(detail["custom_fields"])   # 自定义字段（中文名 -> 值）
print(detail["comments"])        # 评论列表
print(detail["attachments"])     # 附件列表
```

> 接口细节（HAR 抓包来源、字段映射、噪声过滤规则）见 `references/jira_issue_page_interface.md`。

### 导出完整数据集（推荐）

当用户需要**一批 JIRA 问题的完整数据**（而非列表快照或单个问题）时，使用 `export_complete_dataset`：
先按 JQL 拉全部列表，再并发取每个问题的完整详情，落盘 JSON 并同时生成报告。

```python
from scripts.jira_client import export_complete_dataset

res = export_complete_dataset(
    account="your_account@example.com",
    password="your_password",
    jql="issuetype = ST-BUG AND text ~ 'QDM565' ORDER BY status ASC",
    output_dir="./output",
    version="LTE01R07A01_C_SDK_E_QDM565_01.001.01.003_V04",
    max_results=None,        # None=全部；也可限制如 50
    concurrency=4,           # 并发拉取详情的线程数
    output_format="both",    # 'markdown' / 'docx' / 'both'
    include_full_details=False,  # True=报告追加每个问题完整详情
)
# res = {"json": 路径, "markdown": 路径, "docx": 路径, "stats": 统计, "errors": {key: 错误}}
```

**基于完整数据集做后续操作（无需再访问 JIRA）**——这正是「先取全量，再复用」的价值：

```python
from scripts.jira_client import JIRACompleteDataset, generate_complete_markdown

# 从已落盘的 JSON 读回完整数据
dataset = JIRACompleteDataset.load_json("output/jira_complete_dataset.json")

# 任意自定义过滤/统计，例如只取 B-Major 及以上
severity = JIRACompleteDataset.SEVERITY_LABEL_CANDIDATES
only_major = [d for d in dataset
              if JIRACompleteDataset._match_label(d["custom_fields"], severity) == "B-Major"]

# 直接生成子集报告（不再访问 JIRA）
generate_complete_markdown(only_major, version="仅B-Major",
                           output_file="output/B-Major子集.md")
```

分步调用（需要更精细控制时）：

```python
from scripts.jira_client import JIRAClient, JIRACompleteDataset, generate_complete_docx

client = JIRAClient(account, password)
details, errors = client.fetch_complete_dataset(
    jql="issuetype = ST-BUG AND text ~ 'QDM565'",
    max_results=None, concurrency=4,
    progress=lambda done, total: print(f"拉取 {done}/{total}"))   # 进度回调

JIRACompleteDataset.save_json(details, "output/jira_complete_dataset.json")  # 落盘
stats = JIRACompleteDataset.analyze(details)                                # 统计（不访问JIRA）

generate_complete_docx(details, version="V1", output_file="output/report.docx")
```

> 说明：
> - `search_issues()` 用 REST 分页，比旧版 `query_by_jql()` 的 HTML 抓取更稳、可拿全量；完整数据集的 `detail` 结构与单问题详情完全一致，字段中文名同样通过 `/rest/api/2/field` 动态映射。
> - **默认排除 ST_Closed**：当 JQL 里没有 `status` 条件时，会自动注入 `AND status != "ST_Closed"`；如果要显式搜索关闭的问题，在 JQL 里写 `status = "ST_Closed"`（或 `status in (...)`），或传 `exclude_closed=False`。
> - 自动注入的过滤条件会放在 `ORDER BY` 之前，因此带排序的 JQL 也能正常工作。

### 高级用法

如果用户需要自定义数据处理逻辑，可以使用单独的类进行操作：

```python
from scripts.jira_client import JIRAClient, JIRADataProcessor

# 1. 提取数据
client = JIRAClient(account, password)
headers, raw_data = client.query_by_jql("your jql query")

# 2. 处理数据
processor = JIRADataProcessor(raw_data)
processor.filter_closed()
processor.filter_by_level("B-Major")  # 只保留B级及以上严重等级的缺陷
processor.sort_by_level()
processed_data = processor.get_processed_data()
statistics = processor.get_statistics()

# 3. 自定义输出
# 根据需要处理processed_data和statistics
```

## 资源说明

### scripts/
- `jira_client.py`：JIRA客户端核心实现，包含所有功能接口
  - `JIRAClient`：登录与会话管理；`query_by_jql` / `query_by_url` 查询问题列表（HTML，旧）；`search_issues` 分页拉全部列表（REST，推荐）；`get_issue_detail` 访问单个问题详情；`fetch_complete_dataset` 两阶段拉取完整数据集（并发）；**`create_issue` 创建 JIRA 问题（含附件上传，支持 `draft=True` 只读草稿）**；`build_create_draft` 生成只读创建草稿（创建前必须先用它征得确认）；`update_issue` 编辑已有问题（REST PUT）；`get_create_meta` 获取创建元数据（字段 schema + 选项 ID）；`_get_create_form_tokens` 取创建表单令牌；`upload_attachment_temp` 上传附件到临时区；`get_issue_raw_fields` 读取历史问题原始字段（借鉴默认值）
  - 模块级：`create_issue` / `create_issue_draft` / `update_issue`（快捷入口，自动登录）；`build_bug_summary` / `build_bug_description`（按历史测试 JIRA 版式生成标题/描述）
  - `JIRACompleteDataset`：完整数据集的 JSON 存取、统计分析与字段匹配（基于已拉取数据，不访问 JIRA）
  - `JIRADataProcessor`：列表数据的过滤、排序、统计
  - `DocxReportGenerator`：DOCX 报告生成（支持列表报告、单问题详情、完整数据集报告）
  - `generate_report` / `generate_markdown`：缺陷列表报告快捷入口（默认排除 ST_Closed；`with_comments` 控制备注列是否写原始评论，`remark_map` 可外部注入备注）
  - `export_three_reports`：一键输出三份报告（基础 / 含原始备注 / 含 AI 分析备注）+ `jira_ai_input.json`；`ai_notes` 传 `dict{Bug号: 备注}` 回填 AI 备注（默认排除 ST_Closed）
  - `generate_issue_report` / `generate_issue_markdown` / `generate_issue_docx`：单个问题详情报告快捷入口
  - `export_complete_dataset` / `generate_complete_report` / `generate_complete_markdown` / `generate_complete_docx`：完整数据集导出与报告入口（默认排除 ST_Closed）
  - 内部辅助：`_fetch_details_map`（并发拉取完整详情）、`_format_comments`（评论格式化）、`_build_defect_docx`（缺陷 DOCX 渲染）、`_build_ai_input`（构建 AI 分析输入）
  - `normalize_jql()`：JQL 规范化辅助，自动注入 `status != "ST_Closed"` 并正确处理 `ORDER BY`

### references/
- `jira_issue_page_interface.md`：基于 HAR 抓包（ticket.ikotek.com.txt）整理的「具体 JIRA 页面」接口参考，含端点清单、选用方案、字段映射与噪声过滤规则
- `jira_create_issue_interface.md`：基于同一 HAR 抓包整理的「创建 JIRA 问题」接口参考，含登录、取令牌、附件上传、QuickCreateIssue 表单参数与 createmeta 字段 schema 速查，以及 `jira_client.py` 各方法的对应关系

### 依赖要求
- Python 3.7+
- 依赖包：requests, beautifulsoup4, python-docx

安装依赖：
```bash
pip install requests beautifulsoup4 python-docx
```

> 注意：`search_issues` / `fetch_complete_dataset` / 完整数据集报告均基于 REST JSON，不依赖 `beautifulsoup4`；`beautifulsoup4` 仅供旧版 `query_by_jql`（HTML 抓取）使用。并发拉取使用标准库 `concurrent.futures`，无需额外依赖。