---
description: 'Use this skill when generating/iterating a version SystemTestReport
  (系统测试报告) from a historical report, and optionally pushing it to the 妙搭 report
  platform: 写测试报告, 版本测试报告, 生成系统测试报告, SystemTestReport, 常规功能新增列,
  问题统计表, 摘要/测试计划/常规压力更新, QDM559 V22 报告, 推送平台, 出正式页面, 平台导出摘要.
  Needs 历史报告 + TestCase 执行表 + JIRA. 「路测」Sheet 的截图与 CEP 数据由上游 `路测全流程`
  / `路测场景截图` skill 从 NMEA 日志生成后喂入.'
name: 版本系统测试报告生成
---

# 版本系统测试报告生成

## ⚠️ 第一规则：缺信息就问，不许猜、不许沿用上一个项目

**本 skill 的输入缺任何一项，必须先向用户提问确认，凑齐后才开跑；严禁拿上一个项目/上一个版本的
配置默认顶替**（真出过事：用户做的是 QDM562 `LTE01R07A05_BT_C_SDK_A_SDK_QDM562CNAK_01.001.01.001_763`，
助手按 QDM559 V22 的上下文继续跑，产出了完全不相干的报告）。

必问清单（缺哪个问哪个，一次问全，别挤牙膏）：

| # | 缺什么 | 怎么问 |
|---|---|---|
| 1 | **历史报告路径** `base_report` | 迭代版必须用户给；**新项目第一份报告**没有历史报告 → 用内置首份模板 `templates/【模板】IK-QP-012_SystemTestReport_首份_V1.0.xlsx` 当 base_report（见「首份报告模式」），别拿别的项目的报告冒充 |
| 2 | **版本号口径** | `version`（列组名 Vxx）/ `full_version`（全串）/ `prev_version` / 主版本号怎么切——用户版本串格式各异，问 |
| 3 | **执行表清单与归属** | 哪些表算数；上传文件重名/多版本（模板 vs 修正版）→ 列清单请用户点 |
| 4 | **本轮实际跑了什么** | 哪些功能项跑了/没跑/不支持；升 V 只跑 P0 属正常，不许拿历史轮结果填 |
| 5 | **测试人 / 测试日期 / 时间区间 / 人力人日** | 直接问 |
| 6 | **压力测试** | 哪几行跑了、设备号、时长次数、数据统计；没跑的行要隐藏 |
| 7 | **路测** | 有没有；有就要三件套目录（走 `路测全流程` skill） |
| 8 | **项目固定值** | `configs/platform_defaults.json` 的 `projects` 里没有这个项目 → 密级/审核人/批准人/测试平台/项目行业/Baselines/报告路径**逐项问一次**，答完写进 defaults，之后不再问 |
| 9 | **JIRA 取数口径** | 用户给过滤器链接/现成 JQL 就照用；`jira.bug_keys`（Bug 号清单）最稳、不受搜索剔除已关闭影响；缺陷链接替换的 prev→version 字符串要跟用户确认 |
| 10 | **输出路径** | 目录习惯 + 文件名 |

规则细则：

- 能从**本次输入**推出的绝不问（执行表分组结果、聚合判定、JIRA 明细、功能矩阵勾选）；推不出的**必须问**。
- 提问要带**具体候选项**（比如"上传的 整车_V0 有两份：A 有 890 条实测结果 / B 是空模板 501 条全空，用哪份？"），
  不要问"请提供更多信息"这种空话。
- 换项目 = `base_report`、`configs/*.json`、`platform_defaults.projects` 全部重新确认；
  旧项目的零部件叫法（如 QDM559 的 ECU/DIS/MCU/BMS/TFT/CHG）**不许**带进新项目。
- 用户没确认的东西，宁可报告缺段并标注待补，也不许编数据填进去。


把一份**历史 SystemTestReport**（IKOTEK 组织基线模板，8 个 Sheet）迭代成**新版本**的报告：
从 TestCase 执行表聚合出「常规功能」的新列组、从 JIRA 生成「问题统计表」、从压力截图/JIRA 评论填「常规压力」新列组，
并同步「摘要」和「测试计划」。**历史版本的数据一律原样保留**。

## 适用场景

- 用户给「历史系统测试报告 + 本版本 TestCase 执行表（+ JIRA / 压力数据）」，要出一版新报告
- **新项目第一份报告**（无历史报告）：用内置首份模板当底稿，见「首份报告模式」
- 触发词：写测试报告 / 生成系统测试报告 / 版本测试报告 / SystemTestReport / 常规功能列 / 问题统计表 / 常规压力列组 / 摘要矩阵 / 第一份报告 / 首份报告模板

## 报告结构（模板固定，不要改 Sheet 名和 Title）

| Sheet | 处理方式 |
|---|---|
| `Revision` | **不动**（组织基线只在 V1.0 建过一次） |
| `摘要` | 主测版本号 + 测试人 + 日期 + 测试小结文本 + **功能项矩阵追加本版本 2 行**；下方图例块整体下移 2 行 |
| `测试计划` | 追加本版本的功能项块（整车/GNSS/POWERONOFF/Network/PRETEST/OTA/FCT） |
| `测试指南` | **不动**（与版本无关） |
| `常规功能` | 每个 V 版本占 **4 列**：`<V>测试结果 / Blocked-NoRun原因 / 测试人员 / Fail或者Block的原因`；可在平台数据交互段插入新行；旧版本列组要隐藏，**顶部「功能点测试」标题条必须横跨整表合并**（`B2:<最新列组末列>2`）且**文字居中**（`gf_title_center`）——隐藏旧列后如果只有原来的 `D2:I2`，中间会断开、看起来像两张独立的表；**B 列测试项必须按分区合并居中**（`gf_col_merges`，插行后底稿合并不会自动扩） |
| `问题统计表` | 缺陷数量统计 + 三条缺陷链接（模板内 `prev_version` → `version` 字符串替换）+ 问题点记录 |
| `常规压力` | 每个 V 版本占 **7 列**：`测试版本 / 测试设备 / 测试时长·次数 / 测试结果 / 测试数据统计 / 测试人 / 备注`；本轮没跑的行整行隐藏 |
| `路测` | 有本轮路测产物就补：`编号 / 测试日期 / 测试版本 / 测试内容 / 场景 / 测试数据(图片) / 测试结果 / 备注`——**一个场景一行**，场景内多张截图**横向拼成一张长图**放进 F 列（`road_test.py` 的 `build_strip`），B/C/D 跨整块合并；**列含义与「路测全流程」出的独立路测报告 Excel 一一对应**（本 Sheet 是 A-H：编号/日期/版本/内容/场景/测试数据 F/测试结果 G/备注 H；**实测 prod 出的独立报告**图占 **F:I 合并**、测试结果在 **J(10)**、备注在 **K(11)**——那份 skill 的文档写的 F:G/H/I 已经过期，照抄列号会错位）；没有数据就不动。截图和 CEP 从哪来见下面「路测数据来源」 |

**摘要的功能项矩阵是「版本按行」**：每个版本 2 行（勾选行 `√`/`x` + 结果行 `PASS/FAIL/BLOCK`），
B 列两行合并。图例块（`Sheet名称/摘要/用例概要/…`）带**内部跳转超链接**（`'测试指南'!A1` 这种），
下移时要连超链接一起搬，配对关系不能错行。

## 首份报告模式（新项目无历史报告，2026-10-23 QDM562 763 实战定型）

新项目第一份系统测试报告**不需要**借别项目的报告当底稿——直接用内置模板：

```
base_report = <本skill目录>/templates/【模板】IK-QP-012_SystemTestReport_首份_V1.0.xlsx
```

模板特点（由 `scripts/make_first_template.py --src <某份已生成报告> --out <模板>` 剥离生成，可再生成）：

- 8 Sheet 结构/样式/合并/隐藏状态与正式报告一致；**所有版本级数据已清空**（列组结果、摘要矩阵/小结/
  项目字段、测试计划块、问题统计、压力数据、隐藏旧列组里的历史值、路测旧截图），0.5MB。
- 常规功能行骨架已含插入行：GNSS 可见 B4:B8（4 组）+ 备用隐藏行 9~17、OTA 可见 31~45 + 备用隐藏 46~52、
  NETWORK 18~23、powerONOFF 24~30、平台数据交互 53~75（21 行）、PRETEST 76~79、FCT 81~82。
  分组更多的新项目：把备用隐藏行 `unhide_rows` 放开再 `gf_relabel` 改名即可，**不要再写 gf_inserts**
  （模板里行已经插好了，再插会翻倍）。
- 摘要图例块在 50 行 → build 时版本对会写到 49/50、图例挪到 52（每版下移 2 行是设计行为，正常）。
- 参考配置：`configs/qdm562_763_V1.json`（首份模式完整示例：下划线分组键、force PASS、压力 relabel+数据、
  摘要项目字段 cells、unhide_rows 全套）。

首份模式必问清单里可豁免的：#1（模板兜底）；其余照问。项目固定值答完一次写进
`configs/platform_defaults.json` 的 `projects.<项目号>`（QDM562 条目 2026-10-23 已建：
测试平台 ASR1602S、行业 Tracker/两轮车、Baselines 同 QDM559、For Windows QCOM、报告路径暂空）。

摘要 Sheet 项目字段单元格映射（`summary.cells` 直接按这些格写）：
`K8`=主测版本号（build 自动）｜`D5`=测试平台｜`D6`=版本号（矩阵上方）｜`D7`=项目行业｜
`D11`/`D12`=测试人/日期（build 自动）｜`D13`=报告存放路径｜`D15`=BaselinesVersion｜
`D16`=Baselines项目级路径｜`D17`/`D18`=For Windows/Linux｜`C19`=测试小结（runs 富文本）。
密级(C1)/审核人(J1)/批准人(L1)/测试等级(D9)/测试内容(D10)/送测单(D14) 是组织固定值，模板里保留不动。

## 核心聚合规则（用户拍板）

> 同一功能项 / 报告行下：**有 FAIL 就是 FAIL，否则有 PASS 就是 PASS，全是 BLOCK 才记 Blocked**。

原因：升 V 测试通常只跑 P0，所以「1 个 PASS + 一堆 BLOCK」是常态，应当记 PASS。

BLOCK 的取值：全是 `Blocked-NonSupport` → `Blocked-NonSupport`，否则 `Blocked-NoRun`。
原因列的取值顺序：① 执行表「Blocked-NoRun原因」列第一条非空原文 → ② 该列全空时退回「备注」列
（有的表把 `只测4G` 写在备注里，K 列是空的）→ ③ 配置里的 `block_reason`。
碰到「K 列空、备注也不合适」的行，直接在 `gf_rows` 里给该行写 `block_reason` 覆盖。

## 从执行表取数

执行表（`【绝密】【模板】IK-QP-012-07_ODM_QDMxxx_TestCase_*_V0.xlsx`）结构：
- 定位表头行：含「用例编号 / Case ID」+「实测结果 / Actual Result」
- `group_by = "sheet"`：按 **Sheet 名**分组（整车用例表每张 Sheet 对应报告「平台数据交互-xx」一行），key 也支持直接写**精确 caseId**
- `group_by = "case_prefix"`：按 **用例编号前缀** `XXX-NN` 分组（GNSS-11-003 → `GNSS-11`），key 也支持直接写**精确 caseId**（如 `NETWORK-01-002` 单独取 CFUN 那条）
- **只统计「实测结果」非空的行**；整表为空（如某 Sheet 0 条结果）就说明本轮没执行

匹配顺序：先按精确 caseId 找，找不到再按前缀/Sheet 名找。

## 前置条件

- 历史报告必须是**同组织基线模板**的 SystemTestReport（Sheet 名与列结构一致），否则 `build_report.py` 找不到锚点
- JIRA 取数依赖工作区里的 `jira-data-access` skill（`scripts/jira_client.py`），账号在配置里给
- 本机要有 Excel（`excel_check.py` 用 COM 做「能否无修复提示打开」的验证）；没有就跳过该步

### Execution

本 skill 自带批处理文件 `scripts/main.json`。

**严格用下面的形式调用 `run_tool_batch`，用 `file_path` 加载该文件；不要自己内联拼 `actions`。**

`run_tool_batch` 需要**绝对路径**。用你读到本 SKILL.md 时看到的那个绝对目录拼出完整路径。

```
run_tool_batch(
  file_path="<本 skill 目录>/scripts/main.json",
  args={
    "skill_dir": "<本 skill 目录>",
    "config": "<本 skill 目录>/configs/qdm559_V22.json"
  }
)
```

批处理做 6 件事：拉 JIRA 明细 → 生成报告 → **补路测截图** → 校验内容 → 用 Excel 真实打开验证 →
**推送报告平台出正式页面**（第 6 步由 `platform.enabled` 控制，关掉就跳过）。
（配置里没有 `road_test` 段时，第 3 步自动跳过。）

⚠️ 第 3 步**只消费截图，不出图**。手上只有 NMEA 日志时，先用 `路测全流程` / `路测场景截图` skill 出三件套，
再把 `road_test.dir` 指到三件套的输出根目录（详见「路测数据来源」）。

### 路测数据来源（上游 skill：`路测全流程` / `路测场景截图`）

本轮没跑路测就没有这一段；**跑过但手上只有 NMEA 日志时，不要让用户手动截图**，先走上游 skill 出数：

- `路测场景截图` = 只出**三件套**（对比 KML + 截图 + `CEP_列表.xlsx`），适合"内部报告要配图，独立路测报告另说"。
- `路测全流程` = 三件套 + Word 路测报告 + 调接口出 Excel 路测报告，适合"三件套 + 对外/独立报告一起交付"。
- 两者的输入契约一样：**设备 NMEA + 高精度 NMEA + 区域划分**（`区域划分.json`，KML 多边形 / 时间段 / 帧编号三选一，KML 优先）。
- 出数命令、区域划分配置、CEP 口径、颜色/图钉/标注等细节**全部由那两个 skill 自己维护，本 skill 不改它们**，只消费产物。

**产物 → 内部报告的接法**（关键：`road_test.dir` 指向三件套的输出根目录）：

| 三件套产物 | 喂给内部报告哪里 |
|---|---|
| `<out_root>/整体/整体.jpg`、`<out_root>/<场景>/区域整体.jpg`、`<out_root>/<场景>/NN_HHMMSS.jpg` | `road_test.dir` = `<out_root>`；**每个子目录名就是场景名**，与 `scene_order` 一一对应（例：`整体/公司周边/大马路/小区/村子`） |
| `<out_root>/CEP_列表.xlsx`（行=CEP60…95，列=整体+各场景） | 不嵌表，**挑数写进 `road_test.remark` / `摘要`测试小结 / `问题统计表`**（如"开阔路段 CEP95 x m，原始 NMEA 存在漂移，已提 QDMxxx-###"） |
| `帧清单.txt` | 只用来核对场景边界与帧数，别往报告里塞 |
| `对比轨迹_*.kml` + 两个 `*.png` 图钉 | 不嵌 xlsx；作为附件单独给用户（图钉要和 KML 同目录才自包含） |

⚠️ 场景目录里只要还放了**环境/整车实拍照片**（竖图），`road_test.py` 会把它们和轨迹图拼在同一条长图里；不想拼就把实拍图挪出该场景目录。

### 路测截图（`config.road_test`）

`road_test.py` 读 `road_test.dir` 下的场景子目录（**一个场景 = 一行**），会：

- 每个子目录 = 一个场景；同一场景内**先横图（轨迹对比图）后竖图（实拍照片）**排序
- 默认 `one_per_scene=false` → 该场景**所有图横向拼成一张长图**放进 `测试数据`(F) 列；
  `one_per_scene=true` 时只取一张代表图（配 `pick="largest"` 取最大文件那张）
- **行高自动**：`max(60, 拼图显示高 × 0.75)` 磅（`row_height` 已不再起作用，别在配置里给）
- **F 列宽自动加宽**到能放下最宽的那条拼图（`col_width` 只作为下限）
- E 列写场景名（单行不需要合并）；B/C/D 列（日期/版本/内容）跨整块合并，与历史块一致
- 物理缩放（box × 1.2~1.25）再存 JPEG 控制体积；WEBP 自动转 JPEG
- `编号` 从 `number_start` 接着历史编号排
- ⚠️ 这一步是"再 load/save 一次"，会拍平 `摘要` 富文本红字，所以脚本内会**按 `summary.runs` 重写测试小结**——配置里必须带上 `summary.runs`

实测：32 张图 → xlsx 只涨 2.7 MB（原图共 20 MB）。

### 版本级数据的来源（sidecar，别再反解析报告）

本 skill 生成新报告的机制就是**复制历史报告再叠新版本内容**：`build_report.py` 从 `base_report`
load 一份副本 → 把本版本写进新列组/新行（常规功能 26-29 列、常规压力 57-63 列、测试计划新块、
摘要矩阵两行、问题统计表）→ 另存成 `out_report`；历史版本的数据一律原样保留（只隐藏旧行/旧列）。

为了让「推送平台」这一步不必再去 xlsx 里反解析（合并单元格、公式无缓存值、标签换行被拍平，
都很脆弱），`build_report.py` 落报告时**顺手写一份 sidecar**：

```
<out_report 去扩展名>.data.json        （platform.data_file 可改路径）
{ meta:{version,full_version,prev_version,tester,test_date,test_period,base_report,out_report,generated_at},
  summary_text, matrix,
  function:[{row,sheetName,testNumber,testItem,testContent,priority,result,blockReason,tester,failReason,subCases}],
  plan:[{seqNo,item,count,manpower,status,planEndDate,actualEndDate,remark}],
  bugs:{new:[…],old:[…],counts:{new,old,bySeverity},jql},
  pressure:[{row,seqNo,functionItem,testContent,scriptName,priority,networkSetting,+7个版本组值}],
  road_test:{…} }
```

- `platform_push.py` **优先读 sidecar**，日志里 `来源=sidecar: xxx.data.json`；没有 sidecar 才回退解析 xlsx。
- sidecar 比 `out_report` **旧**（说明报告生成后被人手改过）会自动判过期 → 打印 `! sidecar 比报告旧`
  并回退解析，避免推到旧值。手工核对过：两条路径得到的条数一致（功能43/计划6/压力3/路测5）。
- sidecar 里**没有** JIRA 账号、密码、API Key（只存 bug 号/等级/状态/描述/版本/jql 文本）。
- `--no-sidecar` 可以强制走 xlsx 解析（对拍调试用）。

### 推送报告平台出正式页面（`config.platform`，`scripts/platform_push.py`）

报告做完后可以一键把内容推给妙搭报告平台（`app_4jxgwzvqczpd2`），平台出 6 份正式 Excel 并下载回本地。

```
python "<skill目录>/scripts/platform_push.py" --config "<config.json>" [--dry-run]
        [--only summary,test-plan,function,pressure,road-test,jira] [--env prod|dev] [--out-dir DIR]
```

- **唯一数据源是 `out_report` 那份生成好的报告**（不是执行表）——所以必须排在 build/road_test/verify 之后；
  报告里改成什么就推什么，推之前建议先 `--dry-run` 看映射结果（各段条数 + 摘要字段）。
- 字段映射（**全按模板标签文本找，不写死行号**）：

| 平台接口 | 从报告哪里取 |
|---|---|
| `report-export/summary-report` | `摘要`：密级(■)/文档类型/审核人/批准人/版本号/项目行业/测试等级/测试内容勾选/测试人/日期/报告与送测单路径/BaselinesVersion/Baselines项目级路径/For Windows/For Linux/测试小结；`platform.overrides` 补平台上叫法不同或报告里没有的字段（`testType`、`implementationTime`…） |
| `report-export/test-plan` + 摘要的 `testPlanData` | `测试计划`本版本块：**按 `plan_start_row` + `plan` 条数定位**（模板里版本/日期是 `=摘要!K8` 公式，openpyxl 读不到缓存值） |
| `report-export/function-report` + `functionTestTable` | `常规功能`本版本 4 列组（结果/Blocked原因/测试人/Fail原因），分类取 B 列向下继承，`编号="--"` 的说明行跳过 |
| `report-export/pressure-report` | `常规压力`**最后一组**表头为「测试版本」的 7 列组 + 左侧 功能项/测试内容/脚本/优先级/网络设置 |
| `road-test-report/generate` | `config.road_test.dir` 的场景目录（自动降档压体积） |
| `reports/generate` + `/status` | `config.jira`（账号/密码/JQL）拼成 `https://ticket.ikotek.com/issues/?jql=…`，轮询到 success 再下载；`platform.jira_url` 可写死过滤器链接 |
| 摘要的 `basicFunctionStates` / `functionItems` | `摘要`功能矩阵：上一行 `Basic Function` / `Function` 两个标签决定列归属（**标签列本身算进本组**）；主测版本取 B 列等于完整版本号（或去掉 `_Vxx` 后缀）的那对行，本 V 版本取 B 列等于 `version` 的**最后**那对行 |

- 产物落到 `<报告目录>/平台导出/`，并写 `推送清单_<版本>_<时间戳>.json`（每项含 `fileName`/`local`/`reportId`/`downloadUrl`）。
  某个接口失败不拦其它项，最后非 0 退出并打印报错原文。
- **口径差异已处理**：报告写 `Pass with comments`，平台路测 H 列只认 `PASS / FAIL / PASS WITH COMMAND`，
  客户端 `normalize_result()` 会翻译（认不出的直接报错，不静默丢）。
- 路测图自动降档：`1200/80 → 1000/78 → 800/75 → 640/72`，请求体预算 ≤6MB（实测 >6MB 服务端传桶易超时），
  网关硬上限 12MB；V22 那份 32 张/18MB 原图第一档就压到 3.2MB。
- 平台侧偶发 **500 `fetch failed`**（服务端调文件服务失败），客户端 3 次退避重试一般第 2 次就过——别把重试去掉。
- 生产环境 8 个路由 2026-10-21 已全部发布；dev 域名证书 hostname 不匹配，客户端在 dev 下自动关校验。

### Batch Parameters

- `skill_dir`：本 skill 的绝对目录（就是你在系统提示里看到 `Check "<dir>/SKILL.md"` 的那个 `<dir>`）。用来定位 `scripts/*.py`。示例：`C:\Users\venus.li\.qwenpaw\workspaces\default\skills\版本系统测试报告生成`
- `config`：报告生成配置 JSON 的**绝对路径**。默认用自带的示例 `configs/qdm559_V22.json`；新版本要**先复制一份改内容**（见下）。示例：`C:\Users\venus.li\.qwenpaw\workspaces\default\skills\版本系统测试报告生成\configs\qdm559_V22.json`

调用时两个参数都要给真实值，**不要传 `args={}`**。

### Batch failure handling

1. 先确认两个参数都传了真实值（尤其是没有传空 `args={}`），再按报错信息改参数重试。
2. 仍失败就改用 `run_tool_batch` 的内联 `actions` 列表跑。
3. 还不行就按下面「Step-by-step」手工逐步执行。
4. 完成后告诉用户：「批处理执行遇到问题，我改用手工完成了；要不要我把 skill 里的批处理脚本修一下，下次能一次跑通？」

## Step-by-step reference

1. **准备 config**：`cp configs/qdm559_V22.json configs/<新版本>.json`，改 `version / full_version / prev_version / out_report / exec_tables / gf_rows / plan / summary_matrix / summary_text / jira.jql / new_bugs` 等。
2. **确认执行表清点**：先扫一遍 `exec_tables` 里每个文件的 Sheet 与结果分布（`python -c` 用 openpyxl 打开，按表头找「实测结果」列统计 PASS/Blocked 数量），确认「本轮哪些功能项跑了」。
3. **确认报告行的锚点**：打开历史报告 `常规功能`，核对每个 V 版本列组的位置（本次的前一组是第 22-25 列，新组写 26-29 列）、以及各报告行的行号；配置里的 `label` 会被脚本拿来断言，不匹配会告警。
4. **跑 `scripts/main.json`**（正常路径）。
5. **人工核对 + 回报用户**：把「本版本列的结果」「改了哪些 Sheet」「还缺什么数据」写成一份说明 md 一起给用户；把需要她拍板的（某行算 PASS 还是 Blocked、路测、人力人日）单独列出来。

### 配置说明（`configs/*.json`）

```
base_report   历史报告 xlsx（底稿，绝不覆盖）
out_report    产物路径（另存，别动原文件）
version / full_version / prev_version   本次版本号 / 完整版本号 / 上一版本号（prev 用于缺陷链接替换）
tester / test_date / test_period        测试人 / 日期 / 测试时间区间（如 2026-09-16~2026-09-28）
exec_tables   [{file, group_by}]        group_by = sheet | case_prefix
gf_rows       {"<常规功能行号>": {label, sources:[{table:序号, keys:[...]}], force:{result,block_reason,fail_reason}, block_reason}}
              —— 行号一律指「插入新行之后」的最终行号；force 用来覆盖脚本算出来的结果（要人工判定时用）
gf_insert     {at_row, count, style_from, merges:[["旧合并","新合并"]]}  在平台数据交互段插新行时用
gf_new_rows   {"<行号>": {num, content, priority, result}}                插进去的新行
gf_title_center true   「功能点测试」绿条(B2)文字居中（2026-10-23 用户要求，首份/迭代都该开）
gf_col_merges ["B4:B8","B18:B23",...]  B 列测试项按分区重建合并+居中。⚠️ 插行后底稿的分区合并
              不会跟着扩（NETWORK-05 这种插出来的行会漏在合并外），按最终几何逐段重并；
              只并**可见**行，隐藏备用行别并进去（合并居中的字会跑到隐藏区中间）。
pressure_relabel {"<行号>": {seq,item,content,script,priority,network}}
              常规压力行左侧标签（列2~7）按本项目改写；功能项列常见竖向合并，非锚点格写入
              会被 try/except 跳过并打印告警。
hide          {<Sheet>: {cols:[...], rows:[...], unhide_rows:[...]}}
              ⚠️ 底稿里本来就隐藏的行（如 V22 没跑的上位机升级/开关机找网压力行）hide 只加不减，
              本轮有数据要显示的行必须列进 unhide_rows，否则生成后仍是隐藏的。
summary       {matrix:[7 个结果], text:"8 点测试小结全文"}
plan          [{item, count, manpower, status, remark}]                  测试计划本版本块
jira          {account, password, jql, bug_keys, scripts_dir, project_label}
              bug_keys 优先：问题统计表是**人工维护的清单**，直接给 Bug 号列表最稳。
              不写 bug_keys 才退回 jql 搜索，但 search_issues 默认会注入 status != ST_Closed，
              已关闭的历史缺陷会整条消失（实测 QDM559EA-131 被关闭后就从搜索结果里没了，
              而它在上一版报告里是列着的）。
new_bugs      ["QDM559EA-135"]                                           本版本新提的 bug（其余自动算历史）
bug_remarks   {"Bug号": "备注"}                                          问题统计表备注列
pressure      {"<行号>": [7 个值]}
pressure_hide_rows [11,13,14]                                            本轮没跑的压力行，整行隐藏
road_test     {dir, scene_order, start_row, number_start, date, version, content, result,
               remark, box:[宽px,高px], quality, one_per_scene, pick, col_width}
              —— dir = 三件套输出根目录（见「路测数据来源」）；一个场景一行；没有路测就整段省略
              —— result 口径与上游路测报告一致：`Pass` / `Fail` / `Pass with comments`，细节写 remark
platform      {enabled, env, out_dir, do, jira_url, jira_timeout, overrides, defaults, data_file}
              —— enabled=false 或整段省略 = 第 6 步跳过（不影响本地报告产物）
              —— **摘要里每次都不变的字段不放在这里**，放 `configs/platform_defaults.json`：
                 `global`（密级/文档类型/testType/测试等级/送测单路径/testContent 勾选）+
                 `projects.<项目号>`（审核人/批准人/项目行业/测试平台/Baselines 版本与路径/报告路径/For Windows），
                 路径里可写 `{stem}` `{version}` `{full_version}` `{tester}` `{test_date}` 占位符；
                 项目号取 `jira.project_label`。报告值与固定值不一致会打印冲突提示（按固定值推）。
              —— 摘要字段优先级：报告解析 < 固定值(defaults) < 本版本 config(versionNumber/tester/testDate/
                 implementationTime) < platform.overrides；`--dry-run` 会列出每个字段的来源
              —— do 子集如 ["summary","jira"]；--only 可临时覆盖；--dry-run 只看映射不调接口
              —— out_dir 不给就用 <out_report 同目录>/平台导出
              —— API Key 不进配置文件：环境变量 REPORT_PLATFORM_API_KEY → ~/.report_platform_key → ~/.roadtest_key
```

### Notes / 踩过的坑

- **`常规功能` 插行**：openpyxl 的 `insert_rows` **不会**自动搬合并单元格。先在插入前 `unmerge` 会受影响的两段合并（如 `B51:B55`、`B56:B57`），插入后再按新位置 `merge`。
- **`问题统计表` 清单行数变了要先清空整段**：原表可能有 9 行历史缺陷，本版本只有 8 条，直接写会留下一行旧记录（表现为同一个 Bug 号出现两次）。`build_report.py` 现在会先把 r22 起 40 行清空再写。
- **给单元格插图片**：`openpyxl.drawing.image.Image` 的 `width/height` **必须在 `ws.add_image()` 之前设**，因为 `add_image` 会把当时的宽高写死成 anchor 的 `ext`；之后再改不生效。想确认是否生效，解 zip 看 `xl/drawings/drawingN.xml` 里 `<ext cx/cy>`（EMU ÷ 9525 = px）。
- **一个单元格只能放一张图**（同格多图会重叠）。路测这种要展示多张的，就**一行一张图**。
- **WEBP 不能直接塞进 xlsx**，要先经 Pillow 转 JPEG。
- **搬图例块要逐行搬样式**：「Sheet名称」那行是**黄底（FFFFFF99）+ 加粗**，下面几行是右对齐/左对齐的普通字，最后两行的 B 列还是蓝色字（FF0563C1）。整块统一抄某一行的样式会把黄底和红字弄丢/弄反 —— 表现为「说明文字变成红色加粗居中、表头没底色」，一眼就看出不协调。
- **结果字色要按值重刷**：历史报告里 FAIL=红字（摘要矩阵还加粗）、PASS=蓝字加粗（仅摘要矩阵）、BLOCK=黑字加粗。样式是从旧列组抄来的，**值变了颜色不会跟着变**（会出现「FAIL 却显示蓝色」），所以写完值要按结果重设字体色。
- **两张表之间的空行必须把框线也清掉**：搬走图例块后，原来被图例占用的行只剩「值被清空、框线还在」，那条分隔空行带着框线就会把「功能项矩阵」和「图例表」连成一张表。做法：动手前先存一份**原空白分隔行的样式**（无框线），搬完后把它刷到新的分隔空行上。
- **测试小结（摘要!C19）是富文本**：`2. 测试结果判定` 的值和 `3. 测试风险` 下的各条是**红字 FFFF0000**，其余黑字。用 `CellRichText(*[TextBlock(InlineFont(sz=10, rFont="微软雅黑", color=Color(rgb=c)), s) for c, s in runs])` 写。⚠️ **openpyxl 读回富文本会拍平成纯文本** —— 所以任何「再 load/save 一次」的后续步骤（如补路测图片）都会把红字丢掉，必须在保存前**把富文本重新写一遍**（`road_test.py` 里就是这么补的）。
- **引用 JIRA 必须「号 + 内容」完整**：`QDM559EA-106\nST[QDM_559][OTA]组合升级压测失败，期望升级成功，小概率`。只写一个 Bug 号（如备注列只写 `QDM559EA-106`）会被打回；常规功能原因列、测试计划备注、常规压力备注、问题统计表都要带完整描述。
- **`摘要` 图例块位置**：新版本两行占 `legend_start-1` / `legend_start`（`legend_start` = B 列值为「Sheet名称」的那行），图例块必须整块下移到 `legend_start+2` 开始。若写成「接在原图例块后面」，会多空出一段、used range 变大。
- **摘要图例块**：先把整块（含 `cell.hyperlink.location`）读出来、清空、再写到新行并重建合并且**把超链接配对回对应文字行**；只搬 value 会让链接错行，还会把链接的 location 字符串写进单元格值。
- **样式保真**：新列组/新行一律 `copy.copy(src_cell._style)` 从对应旧列组/旧行抄，同时抄列宽（`ws.column_dimensions`）。不要用文字描述颜色。
- **缺陷链接**是模板里三条 JQL（全部 / 本次版本 / 历史版本），历史做法就是**把上一版本号字符串替换成本次版本号**（URL 里 `V20` → `V22`），value 和 hyperlink 都要换。
  - ⚠️ 这条 JQL 用 `text ~ <完整版本串>` 过滤，**文本里没有版本串的 bug 会被漏掉**（QDM559EA-131 就是），所以链接条数可能比「问题点记录」少 1-2 条。这是历史模板的口径，不要擅自改，但要主动告诉用户。
- **JIRA「发现版本」**：报告里显示 `QDM559_STM32G0B0_APP_01.001.01.001_V22`，是 JIRA 的 `BUG发现的A版本` + `_` + `BUG发现的V版本` 拼出来的。
- **每次重跑都从 `base_report` 重新生成**（脚本内部先 load 底稿），所以改配置后直接重跑即可，天然幂等，不会叠加两次。
- **执行表用例编号带下划线**（QDM562 V1.0 库是 `NETWORK_01-001`/`GNSS_01-001` 这种）：分组正则
  `^(.+?-\d+)-\d+$` 匹配不到两段连字符，group key 会退化成**完整 caseId**；`pick()` 有
  `k.startswith(key + "-")` 兜底，所以 config 里 `sources.keys` 写 `"NETWORK_01"`（下划线+两位组号）
  就能命中该组全部行。带连字符的 `OTA-15-001`/`POWER ON/OFF-01-001` 正常按前缀组匹配。
- **JIRA 只给 filter 链接**（`.../issues/?filter=14311`）时：`query_by_url` 会剥掉 filter 参数再找 `jql=`，
  纯 filter 链接直接报错。用 `GET /rest/api/2/filter/<id>`（登录 session 可用）拿 name+jql，
  再 search 出 key 列表填进 `jira.bug_keys`（含已关闭的也能逐单取详情）。问题统计表的「缺陷链接」行
  可以直接放 filter URL。
- **跑批前先查 Excel 锁**：目标 `out_report` 被 Excel 开着时 build 最后 `wb.save` 抛
  `PermissionError [Errno 13]`（目录里有 `~$<文件名>`）。让用户关掉再重跑，别硬杀 EXCEL 进程。
  用户可能把生成好的报告**改名/手工贴图**（比如把整车截图贴进常规功能行）——重跑会覆盖掉手工内容，
  重跑前提醒一句。
- **cmd 传中文路径参数会乱码**（`--src "…【机密】…"` 直接 FileNotFoundError；media 里的中文名附件
  read_file 也可能报不存在）：脚本里**硬编码路径**或用 `os.listdir`/`glob` 按关键片段解析，
  别依赖 argv。`make_first_template.py` 已内置 glob 兜底。
- **压力数据可以来自「记录.txt」**（用户口述格式：项目名+设备号+运行时间区间+次数/PASS/FAIL/ERR/PASS RATE+
  关联 bug 号）：整理成 `pressure` 的 7 元组 [测试版本,测试设备,时长/次数,结果,统计,测试人,备注]，
  行名对不上本项目时用 `pressure_relabel` 改左侧标签；备注里的 JIRA 必须「号+完整描述」。
  没跑的行进 `hide.rows`，本轮有数据的行记得 `unhide_rows`（底稿继承的隐藏态只加不减）。
- 交付前一定用**真实 Excel** 打开一次（`excel_check.py`），确认 8 个 Sheet 都在、没有「修复」提示。

**Execution reminder**：触发本 skill 时直接按上面 `run_tool_batch(file_path=..., args=...)` 调用即可，不用自己逐步写 action；只有批处理失败时才走「Batch failure handling」的兜底路径。