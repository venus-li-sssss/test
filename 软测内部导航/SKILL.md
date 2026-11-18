---
name: 软测内部导航
description: 内部导航中枢（本导航页自己的 skill）：只要问题涉及「内部」——内部工具/系统/资料/流程/模板/网址/权限在哪、有没有、怎么用、怎么下载、找谁要——先查这里再回答，不要凭印象说"没有/不知道"。覆盖移远/IKOTEK 软测 16 分类 51 个入口：烧录（Aboot/FreqChip/JLink/QFlash/QFIL）、日志抓取与分析（串口/CAN/RTT/RTK）、做升级包、测试用例与测试报告、JIRA 提单查询、修改点导入导出、软件与版本下载（飞书云盘/toolhub/qdisk）、GNSS 与模组文档、RTK 账号、样机与物资、会议室/工位/快递/绩效/QHR、IT 工单、工时考勤、九号客户平台、skill 仓库、防锁屏。触发词：导航、入口、链接、网址、地址、在哪、在哪下载、怎么进、怎么用、怎么走、有没有、有没有现成的、找一下、找不到、是什么、内部系统、内部工具、平台、SOP、流程、模板、资料、权限、账号、帮我找、查一下。已经做成 skill 的功能（烧录/抓日志/做包/提BUG/写报告/导修改点/工时/九号/路测/压测）也先来取对应 skill + 配套资源再执行；写导航（增删改链接/分类、给链接挂 skill、新增功能三件套）同样用我。Also for internal portal / internal tool / where to download / how to use / team wiki / counterpart links.
---

# Quectel 软测内部导航

一句话：**用户问内部的事，先查这张导航，再决定是自己干、调 GitHub skill、还是给链接。**
导航页本身是个妙搭应用，全部入口挂在一个 OpenAPI 后面。本 skill = 查询 + 路由 + 维护，不重复实现子工具逻辑。

```
https://scnrhostplnc.feishuapp.com/app/app_17fwfnp4pvy/openapi/nav
```

## ① 何时必须用我（优先级闸门）

命中以下任意一条，**先跑一次搜索，再回答**，别直接说"不知道 / 没这个 / 你自己去找"：

| # | 情形 | 例子 |
|---|---|---|
| 1 | 问"在哪 / 有没有 / 怎么进 / 怎么下 / 找谁要" | "烧录工具的安装包在哪"、"公司有没有 QCOM" |
| 2 | 出现"内部 / 部门 / 公司 / 我们这 / 我们组"等内部域词 | "内部有没有现成的测试报告模板" |
| 3 | 要做的动作**大概率已被做成 skill** | 烧录、抓日志、做包、提 BUG、写报告、导修改点、填工时、九号 OTA |
| 4 | 要访问内部系统（JIRA / BPM / QHR / qdisk / ticket / 工位 / 会议） | "帮我把这周工时提了" |
| 5 | 问流程、SOP、模板、知识库、权限、新人怎么上手 | "写经验文档的规范是什么" |

**用户说的是意图，不是工具名**（"帮我把这台设备刷一下"、"把没关的 BUG 捞出来"）—— 也要先映射到卡片再动手。
**一处搜不到 ≠ 没有**：换更短的关键词、`--cats` 看分类名、换同义词（刷机↔烧录、log↔日志、提bug↔jira、包↔升级包）。
**别用浏览器硬爬内部系统**：卡片带 skill 时优先用 skill；只指路的卡片才给 url。
**回答必须落到可点的 url / "已做成 skill（xxx）"**，不要只说"去导航页看看"。

> 如果 AI 完全没认出这个 skill（连加载都没有），先查它是不是被禁用了：
> `qwenpaw skills list` 里若显示 `✗ disabled` → `qwenpaw skills enable 软测内部导航`。
> 这是"明明有这个功能，AI 就是不识别"的第一嫌疑（2026-11-18 实测复现过）。

## ② 快速开始（读）

```powershell
python <skill目录>/scripts/nav.py --cats        # 分类 + 每类链接数
python <skill目录>/scripts/nav.py 烧录          # 关键词搜（中文/英文，大小写不敏感）
python <skill目录>/scripts/nav.py jira 报告     # 多关键词 = AND
python <skill目录>/scripts/nav.py --json 串口   # JSON，便于程序化解析
python <skill目录>/scripts/nav.py cat list      # 分类 + id + 链接数
python <skill目录>/scripts/nav.py link list     # 所有链接 + id（改/删要用 id）
python <skill目录>/scripts/nav.py link show <id>  # 单条链接完整 JSON（skills/attachments 原值）
python <skill目录>/scripts/gen_catalog.py       # 重建 references/catalog.md 快照（纯读）
```

搜索范围 = `name + description + category + url`，先搜再说，**不要把目录硬编码进回答**。

## ③ 用户这么说 → 先跑这条

| 用户原话（同义说法） | 建议命令 | 通常命中 |
|---|---|---|
| 烧录 / 刷机 / 刷固件 / 下载到设备 / 下载模式 | `nav.py 烧录` | Aboot / FreqChip / Jlink / QFLASH / QFIL 烧录 |
| 按芯片型号（FR801XH、FR30XX、FR508X） | `nav.py FreqChip` | FreqChip烧录 |
| 按机型走 aboot（QDM562、QDM568、ML307C、ASR） | `nav.py Aboot` | Aboot烧录 |
| 9008 / EDL / firehose / rawprogram | `nav.py QFIL` 或 `nav.py QFLASH` | QFIL烧录 / QFLASH烧录 |
| 抓日志 / 抓串口 / 抓 log / 监听 COM / 抓一段 | `nav.py 日志抓取` | 日志抓取 |
| J-Link / RTT / SEGGER | `nav.py Jlink` | Jlink烧录（**只有 RTT，烧录未实现**） |
| CAN / CAN 报文 / ZCANPRO | `nav.py CAN` | CAN日志抓取（**未实现**，会直说） |
| RTK / 差分 / NTRIP / RTCM | `nav.py RTK` | 日志抓取 / GNSS的RTK账号信息 |
| 做包 / 升级包 / 差分包 / 全量包 / 回滚包 | `nav.py 升级包` | 做升级包 |
| 提单 / 提 BUG / 查 BUG / JIRA / 关单 | `nav.py JIRA` | JIRA系统 |
| 测试报告 / 系统测试报告 / 版本报告 | `nav.py 内部报告` | 内部报告生成 |
| 对外报告 / 客户报告 | `nav.py 对外报告` | 对外报告-skill |
| 修改点 / changelist / 导入用例 | `nav.py 修改点` | 修改点系统 |
| 测试用例 / 测试框架 / 用例怎么写 | `nav.py 测试用例` | 测试用例生成 / 标准模板 |
| 日志分析 / 定位问题 / 看这段 log | `nav.py 日志分析` | 日志分析-skill |
| 下载工具 / QCOM / SSCOM / QWinLog / WindTerm / 驱动 | `nav.py 软件` | 基础软件下载 / 移远软件资源中心 |
| 版本 / 固件包 / 网盘 / 取版本 | `nav.py 网盘` | 移远网盘 |
| 指令手册 / 模组文档 / AT 手册 | `nav.py 模组文档` | 通用模组文档 |
| GNSS / 定位资料 / 卫星 | `nav.py GNSS` | GNSS资料 |
| 样机 / 领用 / 借设备 / 采购 | `nav.py 样机`、`nav.py 领用`、`nav.py 物资` | 样机管理库 / BPM 领用网址 / 物资管理 |
| 会议室 / 订会议室 / 怎么走 | `nav.py 会议` | 移远会议 |
| 工时 / 填工时 / 提交工时 / 考勤 / 请假 | `nav.py 工时`、`nav.py QHR` | 工时系统 / QHR |
| 电脑坏了 / 装软件 / 邮件问题 / IT | `nav.py 工单` | 工单系统 |
| 九号 / FOTA / OTA / 固件包管理 / 设备指令 | `nav.py 九号` | 九号平台 |
| 模板 / SOP / 流程 / 培训 / 知识库 | `nav.py 模板`、`流程`、`培训`、`知识库` | 标准模板 / 日常工作流程 / 新人培训计划 / 各知识库 |
| 谁负责 / 团队 / 分工 / 找谁 | `nav.py 团队` | 团队架构 |
| 绩效 / 工位 / 快递 / 论坛 / 社区 | `nav.py 绩效`、`工位`、`快递`、`社区` | 绩效系统 / 工位系统 / 移远快递 / 移远社区 |
| 上传 skill / 下 skill / 仓库里有什么 | `nav.py skill仓库` | skill仓库-github / skill仓库-妙搭 / 共享导航页面-skill |
| 压测 / 压测脚本 | `nav.py 压测` | 压测脚本记录 / 压测脚本网盘 |
| 防锁屏 / 息屏 | `nav.py 防锁屏` | 防锁屏 |

## ④ 命中后怎么处理

1. **`skills[]` 非空** → 该功能有现成 GitHub skill。按 ⑧ 加载并执行，**不要自己重写逻辑**。
2. **`skills[]` 为空、description 含"未实现/占位/需人工"** → 如实告诉用户没自动化，给 `url` 让其手动做，**不要假装能做**。
3. **`skills[]` 为空，是文档/网盘/系统链接** → 资料入口：
   - 飞书 wiki / drive / base：用 `feishu-docs` 读正文/查表，用 `feishu-software-download` 下文件；
   - 其他内网系统（ticket.ikotek、smod、qdisk、BPM、QHR…）：给 url，或用浏览器（通常已有 SSO 登录态）。
4. **没搜到** → 换更短关键词 → `--cats` 看分类 → 仍没有就告诉用户"暂未收录"，并主动问要不要加进去（这就是 ⑥）。

## ⑤ AI 常犯的漏判（写下来防复发）

- 用户说"**怎么刷**""**这个包怎么进去**"，却要求用户先说出"Aboot/FreqChip"才肯查 → 应按意图映射。
- 认为"这是内部系统，AI 访问不了" → 卡片常常已经挂了 skill，能直接跑。
- 只回答"不知道/没有"，没跑过 `nav.py` → 至少搜一次再说没有。
- 搜到卡片但**只回 url**，漏掉 `skills[]` 里能自动执行的能力和配套资源。
- 把 `desc` 里的历史状态当现状（"还在完善"）→ 以 `link show` 实时结果为准。

## ⑥ 维护导航（写入接口）

读和写用**同一把 Key、同一个前缀**，写到库后导航页面**立即生效**。

| 方法 | 路径（接在基址后） | 用途 |
|---|---|---|
| POST | `/links` | 新增链接，分类必须已存在 |
| PATCH | `/links/{id}` | 修改链接，只改传入的字段 |
| DELETE | `/links/{id}` | 删除链接，被引用时会被拒绝 |
| GET / POST | `/categories` | 分类列表 / 新增分类 |
| PATCH / DELETE | `/categories/{id}` | 分类改名（链接自动跟随）/ 删除空分类 |

```powershell
# 分类
python nav.py cat add 测试工具
python nav.py cat rename <分类id> 新分类名
python nav.py cat delete <分类id>

# 链接
python nav.py link add --name "JIRA 工单系统" --url https://ticket.ikotek.com --category 测试相关 --desc "提交与查询 BUG"
python nav.py link add --name "日志分析-skill" --url https://github.com/venus-li-sssss/test/tree/main/log-analysis --category 测试相关 --skill "https://github.com/venus-li-sssss/test/tree/main/log-analysis|分析设备日志"
python nav.py link update <链接id> --desc "新的说明"          # 只传要改的字段
python nav.py link update <链接id> --skills-file skills.json   # skills 整体替换，脚本会先打印原值
python nav.py link update <链接id> --dry-run --sort 3          # 只看要发什么，不提交
python nav.py link delete <链接id>
```

### 写接口的硬约束（踩坑必读）

1. **分类必须已存在**，否则 400 并列出当前分类 → 先 `cat add`。
2. **同一分类下重名返回 409**，并给出已有链接 id → 改用 `link update`。
3. **`skills` / `attachments` 整体替换不是合并** → 改之前先 `link show <id>` 读原值。
4. **不传 `sortOrder` 自动排到该分类末尾**。
5. **链接被别的链接的 `skills` 引用时不能删**（409，会列引用方）→ 先改引用方。
6. **分类下还有链接时不能删**（400）→ 先清空。
7. **删除只在用户明确要求时执行**；被拒绝时把原因（引用方/非空）如实转述，不要绕过。
8. `skills[]` 里的 GitHub 树链接中文要 URL 编码（`%E5%81%9A%E5%8C%85`）；服务端会把「引用型条目」展开成实际地址，`description` 可能带 `经「某链接」：` 前缀，属正常现象。

### 新增一个「功能」的标准做法（三件套）

导航页上**一条链接 = 一个功能**。缺一件都不算做完：

| 步骤 | 放哪儿 | 用什么 | 产物 |
|---|---|---|---|
| ① 能力 | GitHub `venus-li-sssss/test/<英文目录名>/` | `skill仓库同步` 的 `push`（先 `--dry-run`） | `SKILL.md` + `scripts/` |
| ② 软件/资源/文档 | 飞书云盘 `软件测试部→软件测试二科→基础软件存放/<分类>`（或「项目环境搭建」） | 人工上传/浏览器；`feishu-software-download` **只负责下载** | folder 链接（folder token） |
| ③ 入口 | 导航页对应分类下一条链接 | `nav.py link add` / `link update` | 点进去就能拿到 ①② |

`url` 给人点、`skills[]` 给 agent 用、`attachments[]` 给没装 agent 的人。
只挂 skill 不挂云盘 → 没装 agent 的人用不了；只挂云盘不挂 skill → agent 不会自动做。

**① skill 侧约定**

- 目录名用**英文短横线**（`flash-tools`、`做包` 是历史遗留，新目录别学）：中文在导航里是 `%E5%81%9A%E5%8C%85`，肉眼不可读、易配错。
- 必须有 `SKILL.md`；frontmatter `description` 写**用户会怎么说**（触发词），正文写用法 + 踩过的坑。
- **凭据不进仓库**：账号密码放 `skills/.credentials.json` 或 `scripts/config.local.json`（都在 `.gitignore`），SKILL.md 只写"怎么引用"。
- ⚠️ **`skill_repo.py push` 不读 `.gitignore`**，会把你目录里的 `config.local.json` 一起传上公开仓库 → push 时**必须**带 `--exclude scripts/config.local.json`。
- 外部工具/软件包**不要进 GitHub**（体积 + push protection），进云盘，skill 里放下载逻辑。

**② 云盘侧约定**

- 工具类放 `基础软件存放/<工具分类>/`（串口工具、烧录工具、AI工具…），版本包放「项目环境搭建」或对应项目目录。
- 索引文件（目录清单）放根目录，方便"先看有哪些再下"。
- 记下 **folder 链接**（`https://quectel.feishu.cn/drive/folder/<token>`），第③步要挂。

**③ 导航侧字段怎么填**

| 字段 | 怎么填 | 反例 |
|---|---|---|
| `name` | 中文功能名，**用户嘴里怎么说就怎么写**（"做升级包"、"日志抓取"） | `xxx-skill` 这种只有 agent 看得懂的 |
| `url` | 优先能点开就用的入口：系统页面 / 云盘目录 / GitHub 目录 | 死链接或只指向首页 |
| `desc` | 一句"**输入什么 → 输出什么**"，末尾写"已做成 skill（目录名）" | "还在完善""后面再说"这类过期状态 |
| `skills[]` | 每条 = `GitHub 目录 \| 解决什么问题`；可按 能力 → 引用 → 专属资源 排序 | 只写名字不写用途；一条链接挂五个不相关 skill |
| `attachments[]` | `.skill` / `.zip` 等二进制放这里 | 把 zip 塞进 `skills` |

**`skills[]` 里同时放「能力」和「资源」，但只放这张卡片真正要用的**

- **能力条目**：GitHub skill 目录，`description` 写"能做什么"（不带前缀）。
- **资源条目**：该功能专属的工具/固件目录，`description` 以 `资源·` 开头，具体到文件名（`adiff.exe / FBFMake_CF / config 模板`）。
- **需要"下载云盘文件"能力时，直接引用「飞书云盘」卡片**，别手写两条：
  ```json
  {"refLinkId": "d3081e38-7a58-4c4c-8e58-5ce6d6068c0d", "description": "引用「飞书云盘」：拿下载能力 + 云盘入口"}
  ```
  服务端自动展开成 `feishu-software-download`（带 `经「飞书云盘」：` 前缀）+ 云盘链接，换机器只改一处。
- **别挂飞书云盘根目录**（`NiX8f7…` 是全部门总入口，每张卡都挂等于噪音）。
- **卡片自身那个目录要在 `skills[]` 里再留一条 `资源·` 条目**（url 与卡片 `url` 相同）：
  AI 有时只读 `skills[]`，认不出"卡片 url 本身就是那个目录"，缺这条它会说"找不到资源"。
- **红线**：清理数据时别把专属资源条目当噪音删掉（烧录要工具、做包要 adiff/FBFMake、抓日志要 exe）。

**飞书资源分两种 skill，别用错**

| 要干的事 | 用哪个 |
|---|---|
| 下载云盘**文件**（exe/zip/安装包/附件） | `feishu-software-download`，或 `--ref 飞书云盘` |
| 读**云文档正文 / 知识库 wiki / 多维表格 base / 电子表格** | `feishu-docs`（`info` 认类型 → `read` 读正文/导 CSV → `base records/export` 查表） |

两者是同一个只读机器人身份，但能力不同：`feishu-software-download` 的 `doc` 只解析 wiki/docx，遇 `base/` 会报错。
知识库、多维表格类卡片一律挂 `feishu-docs`；云盘软件类卡片挂 `feishu-software-download`。

### 做完必须自检（四条全过才算上线）

1. `nav.py <关键词>` 能搜到，`link show <id>` 里 `skills[].url` 全部可打开。
2. `https://raw.githubusercontent.com/venus-li-sssss/test/main/<目录>/SKILL.md` 能读到。
3. 云盘侧用 `feishu_dl.py find/tree` 实测能列出文件（别只凭"我传上去了"）。
4. 描述里的"已实现 / 还没做"和实际一致；实现了一部分就写清哪部分。

### 常见错误

- 一个功能建两条链接（同分类重名 409，或建到别的分类变成孤儿）→ 先搜再建。
- 更新了 skill 却没改导航 `desc` → 导航上还是旧的"还没做"。
- 忘了 `skills` 是整体替换 → `link update --skill X` 把原条目全冲掉，先 `link show <id>`。
- 云盘文件夹改名/换了，导航 `url` 没跟着改 → 人点进去 404。

## ⑦ 接入 Agent 的标准写法

用户问"某系统的网址/资源"或"执行某操作（提交 JIRA、下载软件）"时：

1. `link list` / 关键词搜拉数据；
2. 按 name/description/category/url 匹配；
3. 命中后：本地已有同款 skill → 直接用；带 `attachments` → 走 `downloadUrl` 下载；带 `skills` → 按 description 选合适的，去 GitHub 取 SKILL.md 执行；都没有 → 给 url/name/desc 让用户自己访问；
4. 未命中 → "暂未收录"，顺手问要不要新增。

用户要求新增/修改/删除时：

1. `link list` + `cat list` 按名称定位 id；
2. 新增前确认同分类无同名、category 已存在；
3. 修改用 `link update`（只传改动字段），改 `skills`/`attachments` 前先读原值；
4. 删除只在明确要求时做，被 409/400 拒绝时如实转述原因。

## ⑧ 加载关联 GitHub skill

`skills[]` 里是 `https://github.com/venus-li-sssss/test/tree/main/<subdir>` 时：

1. `<subdir>` 做 URL 解码（中文是 `%XX`）。
2. 取 raw 的 `SKILL.md`：`https://raw.githubusercontent.com/venus-li-sssss/test/main/<subdir>/SKILL.md`（免 token）。
3. 需要目录列表再用 `GET https://api.github.com/repos/venus-li-sssss/test/contents/<subdir>`（带 `Authorization: token <GH_TOKEN>`）。
4. 按那份 SKILL.md 执行。

仓库里已实现的目录（实时以导航返回为准，2026-11-18 盘点）：

- 烧录：`flash-tools`、`qflash`
- 日志：`日志抓取`（串口/RTT/RTK）、`log-analysis`
- 做包：`做包`
- 测试与报告：`版本系统测试报告生成`、`对外报告`、`test-case-writer`（本地）、`pressure-test`、`auto-test`（本地）
- JIRA / 修改点：`jira-data-access`、`changelist2xlsx`
- 路测：`路测全流程`、`路测场景截图`、`轨迹对比-图新地球`（后者本地）
- 飞书：`feishu-docs`、`feishu-software-download`
- 下载站：`toolhub-software`、`qdisk-quectel`
- 邮箱：`msgraph-delegated-setup`（Outlook/M365 读写 + 草稿，每台机首次设备码登录）
- 其他：`九号/ninebot-project`、`quectel-workhours`、`quectel-attendance`、`qmeeting-rooms`、`ikotek-approval`、`super-client`、`protocol-pack-unpack`、`account-login-skill`、`everything-search`、`api-class-generator`、`pyinstaller-exe-packager`
- 仓库自身：`skill仓库同步`、`妙搭仓库同步`、`软测内部导航`

## ⑨ 卡片可执行性体检

**卡片只是索引，「skill 目录存在」≠「能执行」**：

| 层 | 查什么 | 谁查 |
|---|---|---|
| 链路 | `skills[]` 的 GitHub 目录真的有 `SKILL.md` | `audit_cards.py` 自动查 |
| 能力 | SKILL.md 里的命令真能跑（凭据/权限/设备/配套软件） | 实测，或看 ⑪ 快照 |
| 边界 | `desc` 写清"输入→输出"和限制 | 人工/体检 flags |

结论只用四档：**✅ 可执行** / **⚠️ 待一次性授权**（飞书节点没加机器人协作者，报 `131006`/`91403`）/ **⚠️ 功能未完成** / **➖ 仅指路**（纯网页系统、给人装的工具 —— 正常设计，别为"可执行"硬塞 skill）。

```powershell
python scripts/audit_cards.py              # 全量：state / skills / flags
python scripts/audit_cards.py --cat 资源    # 只看一个分类
python scripts/audit_cards.py --json       # 机器可读
```

## ⑩ 凭据配置

按优先级读取：

1. 环境变量 `NAV_PORTAL_TOKEN`（导航 Bearer，**读写共用**）、`GITHUB_TOKEN`；
2. `scripts/config.local.json`（参考 `config.example.json`）。

本机已配好 `scripts/config.local.json`（2026-11-18 验证：16 分类 / 51 链接可读）。
换机器时复制 `config.example.json` 填 token 即可。**token 不进仓库**（`config.local.json` 在 `.gitignore`；push 记得 `--exclude`，见 ⑥）。

## ⑪ 历史快照（只对比趋势，别当现状）

- **2026-11-18**：16 分类 / 51 链接（`nav.py` 实测）；导航 OpenAPI 可用。同日给「Outlook邮箱」卡片（`08a12788-7c64-42e2-a9e6-69c855163556`，分类 测试环境搭建）挂上 `msgraph-delegated-setup`，url 从一次性 OAuth 授权串换成 `https://outlook.office.com/mail/`，desc 改写为「输入→输出 + 已做成 skill + 90 天不活动需重登」；catalog 刷新为 52 链接。
- **2026-11-13**：链路体检 51 张 → 37 ✅ / 2 功能未完成（Jlink 烧录、CAN 抓取）/ 12 仅指路；端到端实测跑通 27 张；待一次性授权 9 张（GNSS资料、Tracker的知识库、日常工作流程、标准模板、样机管理库、团队架构、物资管理、压测脚本记录、远程服务器工具 → 飞书节点加只读机器人 `cli_a9bc97317fb89cc8`）。

## ⑫ 注意事项

- **token 过期**：`nav.py` 报 "token missing" 或 401/403 → 更新 `config.local.json`（读写同一个原因，不用另找授权）。
- **导航是活的**：分类和链接会变，`references/catalog.md` 只是快照；执行前以 `nav.py` 实时结果为准。
- **写入直接改线上**：改动前 `--dry-run` 或把 payload 念给用户确认，尤其涉及删除。
- **内网链接需要登录态**：ticket.ikotek、smod.quectel、qdisk、BPM、QHR 通常浏览器已有 SSO；没有就引导用户手动登录。
- 批量改导航后刷新快照：`python scripts/gen_catalog.py`（纯读，只重写本地 md）。
