# JIRA 创建问题接口参考（Create Issue）

> 来源：`ticket.ikotek.com.txt`（浏览器网络抓包 HAR）。本文档记录「在 ticket.ikotek.com 创建 JIRA 问题」所涉及的真实接口、参数与调用顺序，供 `scripts/jira_client.py` 的 `create_issue` 实现参考。

## 0. 总览（调用顺序）

```
1) 登录 → 获得 JSESSIONID + atlassian.xsrf.token（cookie）
2) GET  /secure/CreateIssue.jspa?pid={projectId}
       → 从 HTML 隐藏域提取 formToken、atl_token（注意：表单里的 atl_token 可能与 cookie 不同，必须用表单里的）
3) （可选）对每个附件：
       POST /rest/internal/2/AttachTemporaryFile?filename=&size=&atl_token=&formToken=&projectId=
       body = 文件原始字节（Content-Type: text/plain）
       → 返回 {"id":"tempXXXX", "name":..., "attachmentUrl":...}；temp id 即 filetoconvert 值
4) POST /secure/QuickCreateIssue.jspa?decorator=none
       Content-Type: application/x-www-form-urlencoded; charset=UTF-8
       X-Requested-With: XMLHttpRequest
       → 返回 JSON，含 "issueKey"（新建问题 Key）
```

> 说明：该实例的创建走的是**传统表单端点**（`QuickCreateIssue.jspa`），而非 REST `/rest/api/2/issue`。
> 选项型字段（如下拉框）的值必须是**选项 ID（数字字符串）**，不是中文 label；
> 选项 ID 通过 `GET /rest/api/2/issue/createmeta?projectKeys=&issuetypeNames=&expand=projects.issuetypes.fields` 解析（label → id）。

## 0.1 IKQDM551EA / ST-BUG 创建时的「必填字段」（实测）

首次创建若缺下列字段会返回 HTTP 400（`customfield_xxxx 是必需的`）。这些字段在 `createmeta` 里 `required=true`，但**不在**历史同类问题的「展示字段」里（历史问题靠默认值/工作流后置填），容易遗漏：

| 字段 | customfield | 类型 | 取值（组合升级类问题沿用值） |
|---|---|---|---|
| 项目阶段 | `customfield_10600` | option | `EVT`(13048) / `DVT`(13049) / `MP`(13050) / `PVT`(13053) / `KO`(13051) / `Pre-KO`(13052) |
| BUG发现的V版本 | `customfield_10223` | string | 如 `V11`（与历史 -609/-603 一致） |

其余常见「只在历史问题展示、不在创建表单」的字段（createmeta 无返回，创建时会被忽略、保留默认/空）：`customfield_10204`(如 QuecOpen)、`10213`(EC616)、`10245`(内部)、`10200`(Open)、`10301`(ST_Open)、`10201`(自动化任务)、`10251`(标准方案)、`10519`(Common)、`10252`(关注人)、`11301`(日期)、`10253`(中)。如需补齐，创建后用 REST 编辑接口补设。

> `components`(模块) 可正常创建时提交（如 `FM33FK545_APP`→`10700`）；详情读取时 `custom_fields` 中可能显示 `None`，但 REST 直查 `fields.components` 确认已写入，属解析映射显示问题，非未写入。

---

## 0.2 历史测试 JIRA 内容样式（创建时必须套用）

参考真实测试类缺陷 **IKQDM551EA-609 / -603 / -646** 整理。创建测试类缺陷时，标题与描述必须严格套用下列版式，**禁止写成自由发挥的长篇描述**（早期版本曾因描述过长被用户退回重做）。

### 标题格式
```
ST[QDM_551][OTA]<现象>；期望<期望>；<概率>
```
- 例（609）：`ST[QDM_551][OTA]进行5个零部件的组合升级失败；期望组合升级正常；大概率`
- 例（646）：`ST[QDM_551][OTA]新版本组合升级时间比之前版本组合升级时间长太多，需要1.5H-2H才能升级成功；期望升级时间正常；必现`

### 描述格式（分块，标点敏感）
```
[测试环境]：
模块IMEI编号：860813079216961
SIM卡：898604F1092380612253
AT通信口：/
网络配置：移动
产品线：TRACKER
[测试步骤]：
1.进行5个零部件的组合升级失败
期望结果:
1.期望升级正常
[测试现象]
ST[QDM_551][OTA]进行5个零部件的组合升级失败；期望组合升级正常；大概率
[概率]：大概率
```
> 标点规则：`[测试环境]：`、`[测试步骤]：` 带**全角冒号**；`期望结果:` 仅**半角冒号**；`[测试现象]` **无冒号**；`[概率]：<概率>` 带**全角冒号**。`[测试现象]` 段通常**直接重复标题整句**。

### 代码生成（已内置版式 helper）
`scripts/jira_client.py` 提供两个模块级函数，直接产出合规内容：
```python
from scripts.jira_client import build_bug_summary, build_bug_description

summary = build_bug_summary(phenomenon="挂测组合升级，升级失败",
                            expectation="升级成功", probability="大概率")
# -> ST[QDM_551][OTA]挂测组合升级，升级失败；期望升级成功；大概率

description = build_bug_description(
    env={"imei":"860813079216961","sim":"898604F1092380612253",
         "at_port":"/","network":"移动","product_line":"TRACKER"},
    steps="运行QDM551平台IOT升级压力脚本，对设备执行自定义组合升级（T-BOX、BMS、VCU、TFT、MCU、TCU 六个部件同时升级）",
    expected="组合升级成功，6个部件均升级到预期版本",
    phenomenon=summary, probability="大概率")
```

### 创建前强制：先草稿、后确认
无论用 helper 还是手写内容，正式 `create_issue` 之前**必须先**调 `build_create_draft()`（或 `create_issue(..., draft=True)`）生成只读草稿（含标题、描述、各字段解析后的选项 ID、待上传附件清单），完整展示给用户并取得明确同意后，才用 `create_issue(draft=False)` 真正创建。**未经确认不得创建。**

### 创建后修正：update_issue
若创建后需要改描述/标题/字段（例如把描述改成上述历史版式），用 `JIRAClient.update_issue(issue_key, description=..., summary=..., assignee=..., fields=...)`（REST `PUT /rest/api/2/issue/{key}`）。选项型字段值会自动解析为 `{"id": ...}`；级联字段暂不支持。

---

## 1. 登录

- `POST /login.jsp`，form 编码：`os_username`、`os_password`、`os_destination`、`user_role`、`atl_token`、`login=Log+In`
- 成功后 cookie 含 `JSESSIONID`、`atlassian.xsrf.token`（如 `BDG5-BJ9J-ALI2-02OR_xxxx_lin`）。
- 默认账号：`venus.li@ikotek.com`。

---

## 2. 获取创建表单令牌

- `GET https://ticket.ikotek.com/secure/CreateIssue.jspa?pid=10800`
- 返回 HTML（约 127KB），其中含隐藏域：

```html
<input name="formToken" type="hidden" value="9c7c4878bfe688644302398f42d89096f18c33fb" />
<input name="atl_token"  type="hidden" value="BDG5-BJ9J-ALI2-02OR_cb7e879bd8e1a66c165ab2624cae9c6356bd30ec_lin" />
```

- **必须用表单里的 `atl_token` + `formToken`** 发起后续请求（表单里的 `atl_token` 与登录 cookie 的 `atlassian.xsrf.token` 可能不一致）。
- 属性在 HTML 中跨行，正则需容忍换行，例如：
  `re.search(r'name="formToken"[^>]*?value="([^"]*)"', html, re.S)`

---

## 3. 附件上传（临时区）

- `POST https://ticket.ikotek.com/rest/internal/2/AttachTemporaryFile`
- Query 参数：`filename`、`size`、`atl_token`、`formToken`、`projectId`
- Header：`Content-Type: text/plain`、`X-Requested-With: XMLHttpRequest`、`Origin: https://ticket.ikotek.com`
- Body：文件原始字节（整个文件内容作为 request body）
- 响应（201）：
  ```json
  {"name":"QDM551_DEBUG_20260727.txt","id":"temp610248881901061604","attachmentUrl":"secure/temporaryattachment/.../temp610248881901061604___probe.txt"}
  ```
- `id` 字段（`temp` 前缀）即创建表单里的 `filetoconvert` 值。
- 注意：未成功创建问题时，上传的临时文件为孤立文件；创建成功后会挂接到问题。

---

## 4. 创建问题（核心）

- `POST https://ticket.ikotek.com/secure/QuickCreateIssue.jspa?decorator=none`
- Header：`Content-Type: application/x-www-form-urlencoded; charset=UTF-8`、`X-Requested-With: XMLHttpRequest`、`Origin`、`Referer`、`Accept: */*`
- Body（form 编码，多值同名键用列表）：

| 参数 | 说明 | 示例 |
|---|---|---|
| `pid` | 项目 ID | `10800`（IKQDM551EA） |
| `issuetype` | 问题类型 ID | `10101`（ST-BUG） |
| `atl_token` | 取自创建表单 | `BDG5-BJ9J-ALI2-02OR_..._lin` |
| `formToken` | 取自创建表单 | `9c7c...33fb` |
| `summary` | 标题 | `ST[QDM_551][OTA]新版本组合升级...` |
| `isCreateIssue` | 固定 `true` | `true` |
| `customfield_10244` | **BUG描述**（本实例“描述”映射到该自定义字段，非标准 description） | 多行文本（含 `[测试环境]`/`[测试步骤]`/`[测试现象]`/`[概率]` 等段落） |
| `priority` | 优先级 ID | `10003` |
| `components` | 模块/组件 ID | `10700`（FM33FK545_APP） |
| `assignee` | 处理人邮箱 | `siliver.nong@ikotek.com` |
| `customfield_10227` | 问题归属（选项 ID） | `11869`（ODM） |
| `customfield_10203` | BUG严重等级（选项 ID） | `11647`（B-Major） |
| `customfield_10221` | BUG优先级（选项 ID） | `10990`（P5） |
| `customfield_10249` | BUG发现的软件版本（文本） | `QDM551_FM33FK545_01.001.01.001` |
| `customfield_10707` | 功能类别（级联父 ID） | `13111`（Tracker） |
| `customfield_10707:1` | 功能类别（级联子 ID） | `13181` |
| `customfield_10226` | ST BUG评估意见（选项 ID） | — |
| `customfield_10239` | SW BUG评估意见（选项 ID） | — |
| `customfield_10202` | PM BUG评估意见（选项 ID） | — |
| `customfield_10215` | P4_Status（选项 ID） | `11332` |
| `customfield_10246` | BUG发现的caseID（文本） | — |
| `customfield_10223` | BUG发现的V版本（文本） | `V22` |
| `customfield_10211` | BUG发现的A版本（文本） | — |
| `customfield_10240` | BUG发现的项目（文本） | `QDM551` |
| `customfield_10214` | BUG解决状态（选项 ID，`-1`=空） | `-1` |
| `customfield_10250` | BUG修复描述（文本） | — |
| `customfield_10229` | BUG关闭日期（日期） | — |
| `customfield_10237` | P4_Changelists（文本） | — |
| `customfield_10234` | 任务总结(对FAE不可见)（文本） | — |
| `customfield_10219` | 软件开发工程师（用户） | — |
| `customfield_10247` | 影响版本（数组） | — |
| `customfield_10105` | Sprint（数组） | — |
| `customfield_10101` | 史诗链接 | — |
| `customfield_10218` | legacy id | — |
| `customfield_10241` | Test UUID | — |
| `dnd-dropzone` | 固定空 | （空） |
| `timetracking_originalestimate` / `timetracking_remainingestimate` | 预估工时 | （空） |
| `hasWorkStarted` | 固定空 | （空） |
| `duedate` | 到期日 | （空） |
| `filetoconvert` | 每个附件的 temp id（可重复） | `temp5074469164084830263` |
| `issuelinks` | 固定 `issuelinks`（保留字段） | `issuelinks` |
| `issuelinks-linktype` | 关联类型 | `blocks` |
| `issuelinks-issueLink-{i}` | 关联目标 Key | `IKQDM551EA-600` |
| `fieldsToRetain` | 需保留的字段清单（可重复，每个字段一个） | `project` / `issuetype` / `summary` / `priority` / `components` / `assignee` / `customfield_*` / 每个 `filetoconvert-tempXXXX` 等 |

- **级联选择**（如 `customfield_10707` 功能类别）：父选项 ID 用 `customfield_10707` 提交，子选项 ID 用 `customfield_10707:1` 提交。
- **选项 ID 解析**：`GET /rest/api/2/issue/createmeta`（expand 字段）可拿到每个下拉框的 `allowedValues`（含 `id` 与 `value`/`name`），据此把中文 label 转成数字 ID。
- **响应**：HTTP 200，JSON 形如 `{"id":"105909","key":"IKQDM551EA-646","issueKey":"IKQDM551EA-646", ...}`，取 `issueKey` 或 `key` 即为新建问题 Key。

### 4.1 createmeta 字段 schema 速查（IKQDM551EA / ST-BUG）

| customfield | 名称 | 类型 | 值说明 |
|---|---|---|---|
| customfield_10227 | 问题归属 | option | id，如 11869=ODM |
| customfield_10600 | 项目阶段 | option | id |
| customfield_10249 | BUG发现的软件版本 | string | 文本 |
| customfield_10246 | BUG发现的caseID | string | 文本 |
| customfield_10221 | BUG优先级 | option | id，如 10990=P5 |
| customfield_10203 | BUG严重等级 | option | id，如 11647=B-Major |
| customfield_10226 | ST BUG评估意见 | option | id |
| customfield_10707 | 功能类别 | option-with-child（级联） | 父/子 id |
| customfield_10240 | BUG发现的项目 | string | 文本 |
| customfield_10223 | BUG发现的V版本 | string | 文本 |
| customfield_10211 | BUG发现的A版本 | string | 文本 |
| customfield_10214 | BUG解决状态 | option | id，`-1`=空 |
| customfield_10239 | SW BUG评估意见 | option | id |
| customfield_10250 | BUG修复描述 | string | 文本 |
| customfield_10244 | BUG描述 | string | **本实例的描述字段** |
| customfield_10229 | BUG关闭日期 | date | |
| customfield_10202 | PM BUG评估意见 | option | id |
| customfield_10237 | P4_Changelists | string | 文本 |
| customfield_10215 | P4_Status | option | id |
| customfield_10234 | 任务总结(对FAE不可见) | string | 文本 |

（完整字段以运行时 `createmeta` 返回为准；上述为抓包中出现过的字段。）

---

## 5. 与 `jira_client.py` 实现的对应关系

- `JIRAClient.create_issue(...)`：封装上述 1→4 全流程，自动解析 label→id，返回新建 Key。
- `JIRAClient.get_create_meta(...)`：封装 `createmeta`，返回 project/issuetype id 与字段 schema。
- `JIRAClient._get_create_form_tokens(pid)`：封装第 2 步，提取 `formToken`/`atl_token`。
- `JIRAClient.upload_attachment_temp(...)`：封装第 3 步，返回 temp id。
- `JIRAClient.get_issue_raw_fields(issue_key)`：读取历史问题的原始字段（含选项 ID），用于「根据历史 JIRA 借鉴默认值」。
- 模块级 `create_issue(account, password, ...)`：快捷入口（自动登录）。
