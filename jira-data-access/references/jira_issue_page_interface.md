# JIRA 具体页面接口参考（基于 HAR 抓包）

本文件记录了对 `ticket.ikotek.com` 具体 JIRA 问题页面（`/browse/{issueKey}`）进行浏览器网络抓包（HAR 文件 `ticket.ikotek.com.txt`）后整理出的接口信息，供 `jira-data-access` 技能访问「单个 JIRA 问题详情」使用。

## 1. 抓包中出现的接口清单

| 接口 | 方法 | 用途 | 是否用于本技能 |
|------|------|------|----------------|
| `/secure/AjaxIssueAction!default.jspa` | POST | 渲染具体问题的编辑/查看面板（字段表单、评论框、人员模块等） | 作为参考/补充（不直接取值） |
| `/rest/api/2/search` | GET | **标准搜索 REST 接口，分页返回问题列表（key/summary/status 等基础字段）** | ✅ 完整数据集「第一阶段」：拉全部列表 |
| `/rest/api/2/issue/{issueKey}` | GET | **标准问题详情 REST 接口，返回结构化 JSON** | ✅ 完整数据集「第二阶段」：逐条取详情 + 单问题详情 |
| `/rest/api/2/field` | GET | 字段 ID → 中文名称映射 | ✅ 用于自定义字段命名 |
| `/rest/issueNav/1/issueTable` | GET | 问题列表表格（AJAX） | ❌ |
| `/rest/servicedesk/noeyeball/1/issueview/{key}/opened` | GET | 埋点：记录问题被打开（返回 204） | ❌ |
| `/rest/scriptrunner/1.0/message` | POST | ScriptRunner 消息 | ❌ |
| `/rest/bamboo/latest/deploy/...` | GET | Bamboo 部署信息 | ❌ |
| `/rest/proformalite/api/2/issues/{key}/forms` | GET | ProForma 表单 | ❌ |

## 2. 选用方案说明

HAR 中抓到的 `AjaxIssueAction!default.jspa` 是浏览器渲染「问题编辑/查看页」的接口，其返回体结构为：

```json
{
  "fields": [ { "id": "...", "label": "...", "editHtml": "..." } ],
  "issue":  { "id": "...", "key": "...", "status": {...}, "project": {...} },
  "panels": { "leftPanels": [...], "rightPanels": [...], "infoPanels": [...] },
  "atl_token": "..."
}
```

其中 `fields[].editHtml` 为**空的编辑表单**（不含字段实际取值），`panels` 只含评论框、关联模块、人员模块等渲染片段，**无法直接取出描述/评论正文等真实数据**，因此不适合作为取值源。

最终采用 JIRA 标准 REST 接口 `GET /rest/api/2/issue/{issueKey}` 作为主要数据接口：返回完整结构化 JSON（含所有自定义字段取值、描述、评论、附件、关联问题），稳定且易于解析。字段中文名称通过 `GET /rest/api/2/field` 动态获取并缓存，并内置常用字段兜底映射。

## 3. AjaxIssueAction 接口细节（HAR 原文，供二次开发参考）

- **URL**: `https://ticket.ikotek.com/secure/AjaxIssueAction!default.jspa`
- **Method**: `POST`
- **Content-Type**: `application/x-www-form-urlencoded; charset=UTF-8`
- **关键请求头**: `X-Requested-With: XMLHttpRequest`、`X-SITEMESH-OFF: true`
- **请求体关键参数**（注意 `fields`/`panels`/`links`/`issue` 可重复出现）:
  - `issueKey={问题Key}`（如 `QDM565EA-396`）
  - `decorator=none`
  - `prefetch=false`
  - `shouldUpdateCurrentProject=false`
  - `lastReadTime={毫秒时间戳}`
  - `fields={字段ID}`（可多个，部分带版本哈希，如 `fields=summary:a4acb84e...`）
  - `panels={面板完整Key}`（如 `panels=com.atlassian.jira.jira-view-issue-plugin:descriptionmodule`）
  - `links={操作Key}`、`issue={字段Key}`
- **返回**: `application/json`，结构见上。⚠️ 直接复用 HAR 原文 `fields=...:hash` 时，`hash` 为字段版本标识，缺失会导致 500；本技能不依赖该接口取值，仅作接口备案。

## 4. 自定义字段 ID → 名称映射（HAR + /rest/api/2/field 验证）

| 字段 ID | 中文名称 | 取值形态 |
|---------|----------|----------|
| `customfield_10203` | BUG严重等级 | 选项对象 `{"value":"B-Major",...}` |
| `customfield_10226` | ST BUG评估意见 | 选项对象 |
| `customfield_10239` | SW BUG评估意见 | 选项对象（可能为空） |
| `customfield_10240` | BUG发现的项目 | 字符串（如 `QDM565`） |
| `customfield_10249` | BUG发现的软件版本 | 字符串 |
| `customfield_10223` | BUG发现的V版本 | 字符串（如 `V01`） |
| `customfield_10227` | BUG来源 / 问题归属 | 选项对象（如 `ODM`） |
| `customfield_10221` | BUG优先级 | 选项对象（如 `P5`） |
| `customfield_10246` | BUG关闭版本 | 字符串（可能为空） |
| `customfield_10250` | BUG关闭V版本 | 字符串（可能为空） |

> 取值形态说明：REST 返回的「单选/多选自定义字段」为 `{"value": "...", "id": "...", "self": "..."}` 对象；文本类为普通字符串；空值为 `null`。`_flatten_value()` 统一将其转换为可读字符串。

## 5. 系统噪声字段（已在解析时过滤）

以下字段为 JIRA 全局公告栏 / 系统内部字段，对所有问题无意义，已在 `_parse_issue_detail` 中剔除：

- 提示信息、请注意、请注意！、注意事项（全局公告横幅）
- Development（开发状态，REST 返回 Java 对象字符串 dump，无法解析）
- Request participants（通常为空）
- 标签为「等级」且值形如 `0|i0dgrz:` 的排名序号字段

## 6. 默认行为：排除 ST_Closed

该技能所有基于 JQL 的搜索/报告/完整数据集导出，遵循「**除非特别说明，否则不搜索 ST_Closed 的问题**」的约定：

- 当用户传入的 JQL 中**未显式出现 `status` 条件**时，内部会自动注入 `AND status != "ST_Closed"`。
- 如果用户显式写了 `status = "ST_Closed"` 或 `status in (...)`，则尊重用户意图，不再注入。
- 也可以传 `exclude_closed=False` 来关闭自动注入。
- 注入逻辑会正确处理 `ORDER BY`，把过滤条件放在排序子句之前。例如：
  - 输入：`issuetype = ST-BUG AND text ~ "QDM565" ORDER BY status ASC`
  - 实际发送：`(issuetype = ST-BUG AND text ~ "QDM565") AND status != "ST_Closed" ORDER BY status ASC`

实测：同样的 `issuetype = ST-BUG AND text ~ "QDM565" ORDER BY status ASC`，未加过滤时 QDM565 的结果里大量是 `ST_Closed`；加过滤后只剩非关闭状态（原厂分析 / SW_Resolved / PENDING / Need Info / SPM_Assigned / DO），与网页 issue navigator 看到的默认列表一致。

## 7. 完整数据集两阶段拉取流程（新增能力）

用户目标：**先取全部 JIRA 列表，再逐个取完整详情**，得到一份完整数据集供后续复用。

```
阶段1  search_issues(jql)   ──GET /rest/api/2/search（分页 startAt/maxResults）──►  list[ {key, summary, status, priority, issuetype} ]
        │
        │  并发（ThreadPoolExecutor, 默认4线程；每线程独立 JIRAClient 登录一次）
        ▼
阶段2  fetch_complete_dataset()  ── 对每个 key 调 GET /rest/api/2/issue/{key} ──►  list[detail]（与阶段1顺序一致）
        │
        ▼
        JIRACompleteDataset.save_json(details, "jira_complete_dataset.json")   # 落盘，后续读 JSON 即可，不再访问 JIRA
        JIRACompleteDataset.analyze(details)                                    # 统计（按状态/严重等级/发现项目/类型）
        generate_complete_markdown / generate_complete_docx(details)           # 基于完整数据集生成报告
```

- 阶段1 用 REST 分页，比旧版 HTML 抓取（`query_by_jql`）更稳、可拿全量（受 `max_results` 限制，None=全部）。
- 阶段2 并发拉取：`requests.Session` 非线程安全，故每个工作线程持有一个独立 `JIRAClient`（各自登录一次）；单条失败不影响整体，自动用阶段1 基础信息兜底并在 `detail['_fetch_error']` 记录。
- `detail` 结构与单问题详情完全一致（见第 2、4 节），字段中文名经 `/rest/api/2/field` 动态映射。
- 落盘 JSON 后，任意「其他操作」（过滤、统计、二次报告、跨项目对比等）直接 `JIRACompleteDataset.load_json()` 读取，解耦「取数据」与「用数据」。
