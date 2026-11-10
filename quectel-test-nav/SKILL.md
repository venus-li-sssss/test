---
name: quectel-test-nav
description: 移远/IKOTEK 软件测试部门内部工具导航中枢。当用户（软件测试工程师）要做任何与内部测试工作相关的事情时使用，包括：烧录（Aboot/FreqChip/Jlink/QFLASH/QFIL）、抓取日志（串口/CAN/Jlink RTT）、做升级包、生成测试用例、JIRA 提交/查询/修改 BUG、生成内部测试报告/路测报告、修改点系统导入导出、下载基础软件/版本（飞书云盘/移远网盘 qdisk）、查 GNSS 资料/模组文档、BPM 领用样机、样机/物资管理、IT 工单、工时与考勤、九号客户平台、会议室/工位/快递/绩效/QHR 等内部系统，或询问"某某工具在哪/怎么用/有没有现成 skill"。本 skill 通过查询内部导航 OpenAPI 找到对应入口，并按入口关联的 GitHub skill 仓库执行实际功能。
---

# Quectel 软测内部导航

这是一个内部工具聚合导航（妙搭应用），把测试环境搭建、测试流程、资源、知识库、内部系统等入口集中在一个 OpenAPI 后面。本 skill 负责**查导航 → 路由到对应入口或已实现的 GitHub skill**，不重复实现各子工具的逻辑。

## 快速开始

所有查询都走脚本 `scripts/nav.py`（API 地址和 token 已内置）：

```powershell
python <skill目录>/scripts/nav.py --cats        # 看有哪些分类
python <skill目录>/scripts/nav.py 烧录          # 按关键词搜（中文名/英文均可，大小写不敏感）
python <skill目录>/scripts/nav.py jira 报告      # 多关键词 = AND
python <skill目录>/scripts/nav.py --json 串口    # 输出 JSON，便于程序化解析
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

## 加载关联 GitHub skill

命中条目的 `skill:` 指向 `https://github.com/venus-li-sssss/test/tree/main/<subdir>`。加载步骤：

1. 把 `<subdir>` 做 URL 解码（树链接里中文是 `%XX` 编码）。
2. 调 GitHub 列目录接口读这个子目录下的文件列表：
   ```
   GET https://api.github.com/repos/venus-li-sssss/test/contents/<subdir>
   Header: Authorization: token <GH_TOKEN>
   ```
   `GH_TOKEN` 已内置在 `scripts/nav.py` 顶部（`ghp_...`），直接复用。
3. 找到该目录下的 `SKILL.md`（或 `.md` 说明文件），用 raw 地址读取：
   `https://raw.githubusercontent.com/venus-li-sssss/test/main/<subdir>/SKILL.md`
4. 按那份 SKILL.md 的指引执行（它会告诉你具体脚本、参数、配置文件怎么写）。

常见已实现的子目录（以导航实时返回为准）：
- `flash-tools` —— Aboot / FreqChip / QFLASH / QFIL 烧录
- `抓取串口日志` —— 串口日志自动抓取（注意：工具只能放 C 盘运行）
- `jira-data-access` —— JIRA 提交/修改/查询 BUG
- `版本系统测试报告生成` —— 内部测试报告生成
- `路测全流程` —— 输入 NMEA，输出截图+路测报告
- `changelist2xlsx` —— 修改点系统数据获取/导出
- `qdisk-quectel` —— 移远网盘下载版本/数据
- `feishu-software-download` —— 飞书云盘下载软件
- `quectel-workhours` —— 创建/修改/提交工时
- `quectel-attendance` —— 考勤数据获取
- `ninebot-project` —— 九号客户平台

## 注意事项

- **token 可能过期**：若 `nav.py` 返回 401/403，或 GitHub API 报 401，说明导航 Bearer token 或 GitHub token 轮换了，向用户要新 token 后更新 `scripts/nav.py` 顶部常量。
- **导航是活的**：分类和链接会增删，`references/catalog.md` 只是快照；执行前以 `nav.py` 实时结果为准。
- **内网链接需要登录态**：ticket.ikotek.com、smod.quectel.com、qdisk.quectel.com、BPM、QHR 等内网系统在浏览器里通常已有 SSO 登录态；无登录态时引导用户手动登录。
- 完整分类快照和每个入口的状态见 `references/catalog.md`。
