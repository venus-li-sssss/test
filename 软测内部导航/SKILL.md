---
name: 软测内部导航
description: 移远/IKOTEK 软件测试部门内部工具导航中枢（读 + 写）。读：当用户（软件测试工程师）要做任何与内部测试工作相关的事情时使用，包括烧录（Aboot/FreqChip/Jlink/QFLASH/QFIL）、抓取日志（串口/CAN/Jlink RTT）、做升级包、生成测试用例、JIRA 提交/查询/修改 BUG、生成内部测试报告/路测报告、修改点系统导入导出、下载基础软件/版本（飞书云盘/移远网盘 qdisk）、查 GNSS 资料/模组文档、BPM 领用样机、样机/物资管理、IT 工单、工时与考勤、九号客户平台、会议室/工位/快递/绩效/QHR 等内部系统，或询问"某某工具在哪/怎么用/有没有现成 skill"。写：维护导航页本身 —— 新增/修改/删除链接、新增/改名/删除分类、给链接挂 skill 或附件。本 skill 通过内部导航 OpenAPI 查入口并按入口关联的 GitHub skill 执行实际功能。
---

# Quectel 软测内部导航

这是一个内部工具聚合导航（妙搭应用），把测试环境搭建、测试流程、资源、知识库、内部系统等入口集中在一个 OpenAPI 后面。本 skill 负责**查导航 → 路由到对应入口或已实现的 GitHub skill**，不重复实现各子工具的逻辑；同时也能**反向维护这份导航**（增删改链接和分类）。

接口基址（读、写同一把 Key、同一个前缀，无需额外授权）：

```
https://scnrhostplnc.feishuapp.com/app/app_17fwfnp4pvy/openapi/nav
```

## 快速开始（读）

所有查询都走脚本 `scripts/nav.py`（API 地址和 token 从配置读取）：

```powershell
python <skill目录>/scripts/nav.py --cats        # 看有哪些分类
python <skill目录>/scripts/nav.py 烧录          # 按关键词搜（中文名/英文均可，大小写不敏感）
python <skill目录>/scripts/nav.py jira 报告      # 多关键词 = AND
python <skill目录>/scripts/nav.py --json 串口    # 输出 JSON，便于程序化解析
python <skill目录>/scripts/nav.py cat list      # 分类 + 分类 id + 链接数
python <skill目录>/scripts/nav.py link list     # 所有链接 + 链接 id（改/删要用 id）
python <skill目录>/scripts/nav.py link show <id>  # 单条链接完整 JSON（含 skills/attachments 原值）
python <skill目录>/scripts/gen_catalog.py      # 重新生成 references/catalog.md 快照（纯读）
```

脚本会实时拉取最新导航数据，**不要把目录硬编码进对话**；先搜，再按命中结果行动。

## 命中后怎么处理

对每条命中结果，按它带的字段决定下一步：

1. **带 `skill:` 条目（即 `skills[]` 非空）** —— 该功能已有现成 GitHub skill 实现。按下面"加载关联 GitHub skill"的步骤读取并执行，不要自己重写逻辑。
2. **`skills[]` 为空，但 description 含"还没做/占位/没实现"** —— 功能未实现。直接告诉用户该入口暂未自动化，给出 `url` 让其手动访问，不要假装能做。
3. **`skills[]` 为空，是文档/网盘/系统链接** —— 这是资料入口：
   - 飞书 wiki / drive / base 链接：优先用对应的 `lark-wiki` / `lark-drive` / `lark-base` skill 读取内容；
   - 其他内网系统（JIRA、qdisk、smod、BPM、QHR 等）：用浏览器打开对应 `url` 操作，或告知用户链接。
4. **没搜到** —— 换更短的关键词（如"日志""报告""版本"），或先 `--cats` 看分类名再缩小范围。

## 维护导航（写入接口）

读和写用**同一把 Key、同一个前缀**，写到库后导航页面**立即生效**。

| 方法 | 路径（接在基址后） | 用途 |
|---|---|---|
| POST | `/links` | 新增链接，分类必须已存在 |
| PATCH | `/links/{id}` | 修改链接，只改传入的字段 |
| DELETE | `/links/{id}` | 删除链接，被引用时会被拒绝 |
| GET | `/categories` | 分类列表，拿分类 id |
| POST | `/categories` | 新增分类 |
| PATCH | `/categories/{id}` | 分类改名，链接自动跟随 |
| DELETE | `/categories/{id}` | 删除空分类 |

脚本已经把增删改都封好了（**优先用脚本，别手搓 curl**，脚本会做本地查重、打印原值、把服务端拒绝原因翻译成人话）：

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
2. **同一分类下重名返回 409**，并给出已有链接 id → 改用 `link update`，不要换个名字硬塞。
3. **`skills` / `attachments` 是整体替换不是合并** → 改之前先 `link show <id>` 读原值，把要保留的条目一起传。脚本在覆盖前会打印原值。
4. **不传 `sortOrder` 自动排到该分类末尾**。
5. **链接被别的链接的 `skills` 引用时不能删**（409，会列出引用方）→ 先改引用方的 skills。
6. **分类下还有链接时不能删**（400）→ 先清空。
7. **删除只在用户明确要求时执行**；被拒绝时把原因（引用方/非空）如实转述给用户，不要绕过。
8. `skills[]` 里的 GitHub 树链接中文要 URL 编码（`%E7%89%88%E6%9C%AC...`）；服务端会把「引用型条目」展开成实际地址，`description` 可能带 `经「某链接」：` 前缀，属于正常现象。

### 接入 Agent 的标准写法

用户问"某系统的网址/资源"或"执行某操作（提交 JIRA、下载软件）"时：

1. `link list` / 关键词搜索拉导航数据；
2. 按 name/description/category/url 关键词匹配；
3. 命中后：本地已有对应 skill → 直接用；本地没有但链接带 `attachments` → 走 `downloadUrl` 下载 skill 文件；带 `skills` → 按各项 description 选合适的，去 GitHub 仓库取该 skill 的 SKILL.md 并执行；都没有 → 把 url/name/description 给用户自行访问；
4. 未命中 → 告知"暂未收录"，可顺手问用户要不要新增进去。

用户要求新增/修改/删除链接或分类时：

1. 先 `link list` + `cat list` 按名称定位 id；
2. 新增前确认同分类下没有同名链接，category 必须是已有分类；
3. 修改用 `link update`（只传改动字段），改 `skills`/`attachments` 前先读原值；
4. 删除只在明确要求时做，被 409/400 拒绝时把原因转述给用户。

## 加载关联 GitHub skill

命中条目的 `skill:` 指向 `https://github.com/venus-li-sssss/test/tree/main/<subdir>`。加载步骤：

1. 把 `<subdir>` 做 URL 解码（树链接里中文是 `%XX` 编码）。
2. 调 GitHub 列目录接口读这个子目录下的文件列表：
   ```
   GET https://api.github.com/repos/venus-li-sssss/test/contents/<subdir>
   Header: Authorization: token <GH_TOKEN>
   ```
   `GH_TOKEN` 从 `scripts/config.local.json`（或环境变量 `GITHUB_TOKEN`）读取，见下文"凭据配置"。
3. 找到该目录下的 `SKILL.md`（或 `.md` 说明文件），用 raw 地址读取：
   `https://raw.githubusercontent.com/venus-li-sssss/test/main/<subdir>/SKILL.md`
4. 按那份 SKILL.md 的指引执行（它会告诉你具体脚本、参数、配置文件怎么写）。

常见已实现的子目录（以导航实时返回为准）：
- `flash-tools` —— Aboot / FreqChip / QFLASH / QFIL 烧录
- `抓取串口日志` —— 串口日志自动抓取（注意：工具只能放 C 盘运行）
- `log-analysis` —— 脚本日志 + 设备日志分析
- `jira-data-access` —— JIRA 提交/修改/查询 BUG
- `版本系统测试报告生成` —— 内部测试报告生成
- `路测全流程` —— 输入 NMEA，输出截图+路测报告
- `对外报告` —— 由内部报告/测试用例生成对外报告
- `changelist2xlsx` —— 修改点系统数据获取/导出
- `qdisk-quectel` —— 移远网盘下载版本/数据
- `toolhub-software` —— 移远软件资源中心（toolhub.quectel.com）查/下软件（QWinLog、QCOM、QFlash、驱动、LOG 工具）
- `feishu-software-download` —— 飞书云盘下载软件
- `quectel-workhours` —— 创建/修改/提交工时
- `quectel-attendance` —— 考勤数据获取
- `ninebot-project` —— 九号客户平台

## 凭据配置

token 不写死在代码里，按以下优先级读取：

1. 环境变量 `NAV_PORTAL_TOKEN`（导航 Bearer token，**读和写共用这一把**）、`GITHUB_TOKEN`（GitHub PAT）；
2. 本地文件 `scripts/config.local.json`（参考 `scripts/config.example.json`）。

`config.local.json` 已在 `.gitignore` 中，**不要提交到 git**。换机器时复制 `config.example.json` 为 `config.local.json` 填入真实 token 即可。

## 注意事项

- **token 可能过期**：若 `nav.py` 报 "nav portal token missing" 或返回 401/403，或 GitHub API 报 401，说明导航 Bearer token 或 GitHub token 轮换了，更新 `scripts/config.local.json`（或环境变量）即可。写接口 401 和读接口 401 是同一个原因，不用另找授权。
- **导航是活的**：分类和链接会增删，`references/catalog.md` 只是快照；执行前以 `nav.py` 实时结果为准。
- **写入会直接改线上导航页**：改动前先 `--dry-run`（`link update` 支持）或先把 payload 念给用户确认，尤其涉及删除。
- **内网链接需要登录态**：ticket.ikotek.com、smod.quectel.com、qdisk.quectel.com、BPM、QHR 等内网系统在浏览器里通常已有 SSO 登录态；无登录态时引导用户手动登录。
- 完整分类快照和每个入口的状态见 `references/catalog.md`；批量改动导航后刷新快照：`python scripts/gen_catalog.py`（纯读，只重写本地 md）。
