---
name: 内部报告转邮件草稿
description: '把内部测试报告（SystemTestReport）按历史邮件格式写成 Outlook「全部回复」草稿（只进草稿箱、绝不发送），自动带测试报告+修改点测试报告附件。触发词：写测试报告邮件、发测试报告、回复测试报告、报告邮件草稿、内部报告转邮件、邮件草稿、reply all 测试报告、QDM 版本测试邮件、报告附件放什么。上游是「版本系统测试报告生成」skill，本 skill 负责最后一步：报告 → 邮件。'
---

# 内部报告转邮件草稿

**输入**：已生成好的测试报告 xlsx（+ 修改点测试报告 xlsx）
**输出**：Outlook 草稿箱里一封 **reply-all 草稿**（不发送）
**核心原则**：**照着上一版（同项目、同收件人）那封邮件改，不要从零写 HTML。**

## 一、流程（5 步）

### 1. 找上一版邮件（模板源）

用 `msgraph-delegated-setup` 的 `graph_mail.py`：

```python
sys.path.insert(0, r"<workspace>\scripts\delegated-outlook-ikotek")
from graph_mail import GraphMailClient
c = GraphMailClient()
msgs = c.search_messages("QDM562", folder="sentitems", top=100)
# 按主题/日期挑出「上一版的测试报告」那封，记下 id
```

⚠️ 老版本邮件可能在 **已发送**，也可能只在**收件箱的送测 thread**里；
用主题关键词（`测试报告` / `版本` / 项目号）多搜几轮。
找到后 `get_message(mid, body_type="html")` 把 HTML 存成 `mail_src.html`——**这是唯一的格式模板**。

### 2. 在原 HTML 上改内容（不要手写）

用 BeautifulSoup 解析 `mail_src.html`，逐块替换：

| 改什么 | 怎么找 |
|---|---|
| 版本号 `_763 → _765` | 表格外的 `<p>` 里含 `_763` 的 `<span>`（**表格里的历史 Bug 版本号不要动**） |
| 测试风险 | 正文里 `<p>` 文本以 `1）/2）/3）` 开头的段落 —— 替换第一条、克隆补足条数、删掉多余 |
| 功能矩阵 | 表格里 `td` 文本等于上一版本号的整行 |
| 缺陷数量 | 表格 r1~r7 的第 2 个 `td` |
| 问题点记录 | 复制一条数据行做模板，克隆 N 份填新数据，再删掉旧行 |
| 压力表 | 复制第 1 条数据行做模板，清掉原数据行后按新数据重建 |
| 路测 | 本轮没跑就**整段删除**（标题段落 + 表格） |

**只替换 `<td>` / `<p>` 里的文本，别重建表格 DOM** —— 边框、`#92CDDC` 蓝底表头、`#92D050` 绿底、列宽、字体全在原 HTML 里。

### 3. 调表格大小和列宽（最容易翻车的一步）

| 坑 | 事实 | 做法 |
|---|---|---|
| `width:80%` / `table-layout:fixed` 没用 | **Outlook 用 Word 渲染引擎，忽略百分比宽度**，只认 `td` 的 px | 直接改每个 `td` 的 `width="<px>"`（表宽 = 单行 td 合计） |
| 只改 table 的 width | 表宽由 td 决定，改 table 白改 | 逐 `td` 改 |
| 某些列太窄 → 行特别高 | `ST评审意见/SW评估意见/备注/测试数据统计` 被压到 30~60px | **重新分配**：短内容列（项目/等级/状态/优先级/版本/测试人）压到 25~90px，把空间让给长文本列 |

实测参考（QDM562 765，总宽保持 1056px / 916px 不变）：

```
缺陷表 [85, 55, 65, 85, 330, 120, 60, 60, 196]
        Bug号 项目 等级 状态 描述 发现版本 ST  SW  备注
压力表 [18, 55, 110, 90, 24, 50, 40, 95, 55, 40, 240, 25, 74]
        序号 功能项 内容 脚本 优先级 网络 版本 设备 时长 结果 统计 测试人 备注
```

### 4. 建 reply-all 草稿 + 附件

```python
POST /me/messages/{source_id}/createReplyAll      # 收件人/抄送自动带全
PATCH /me/messages/{draft_id}  {"body": {...}}    # 换成改好的 HTML（含原引用链）
POST /me/messages/{draft_id}/attachments          # 每个附件一次，大文件 timeout≥600s
```

附件固定两个：
1. `【机密】【MOB】..._SystemTestReport_V1.0.xlsx`（测试报告）
2. `..._修改点测试报告_Report.xlsx`（修改点报告）

### 5. 回读校验（必做）

```python
GET /me/messages/{draft_id}?$select=subject,isDraft,body,hasAttachments
GET /me/messages/{draft_id}/attachments?$select=name,size
```

核对：`isDraft=True`、收件人/抄送人数与源邮件一致、附件名和大小、正文里没有残留旧版本号。

## 二、正文结构（8 段，照历史邮件）

```
Dear All:
<版本号> 版本测试已完成，附件为测试报告和修改点测试报告。
1、测试版本号: <_765>   测试结果：FAIL
2、软测判定：FAIL    原因：基础功能存在BUG
3、测试风险：
   1）…（缩进 3 个 &nbsp;，与「测试风险」的「测」字对齐）
   2）…
4、测试报告路径：<SVN 链接>
5、功能项测试情况列表：[表格]
6、缺陷列表如下 [缺陷数量统计表][缺陷链接表][问题点记录表]
7、压力测试：FAIL [压力表]
（没有路测就整段不写）
```

### 文案口径（用户拍过板的）

| 项 | 要求 |
|---|---|
| 原因 | 只写 **「基础功能存在BUG」**，不要展开 |
| 测试风险 | **不写 JIRA 编号**，只写现象 + 概率（必现/小概率/大概率） |
| 风险条数 | 与报告「测试风险」一致，一条一行，红字 |
| 风险缩进 | 3 个 `&nbsp;`（多了会被说"空格太多"） |
| 测试计划/压力备注 | 完整「Bug号 + 描述」，压力 FAIL 行备注标红 |
| 路测 | 没跑就**不写这一段**，不要写"未进行路测" |
| 主题 | reply-all 自动带 `RE:`，**不要改主题** |

## 三、脚本

```
scripts/report_draft.py     # 核心：拉源邮件 → 套 patch → 建 reply-all 草稿 → 传附件 → 回读校验
scripts/rebuild_example.py  # 本次 QDM562 763→765 的正文改造范例（表格/风险/路测处理全在里面）
```

用法：

```bat
set PYTHONIOENCODING=utf-8
python scripts/report_draft.py --source-mail-id <id> --body-html body.html ^
    --attach "D:\...\【机密】【MOB】..._SystemTestReport_V1.0.xlsx" ^
    --attach "D:\...\..._修改点测试报告_Report.xlsx"
```

先 `--dry-run` 只打印收件人/主题/附件，核对无误再去掉。

## 四、踩过的坑（血泪）

1. **手写 HTML 一定被打回**：自己写的 `<table border=1>` 跟原邮件的 Word 表格完全两个样（丢了底色、边框粗细、列宽、字体），用户一眼看出"格式不对"。**必须基于原 HTML 改。**
2. **`width:%` 在 Outlook 无效**，改 px 才行（见上表）。
3. **`createReply` 不带全部收件人**，要用 `createReplyAll`。
4. **PATCH body 会冲掉引用链**：先从 `draft.body` 取回带引用的 HTML，把新正文插在 `<body>` 标签后面，再 PATCH 回去。
5. **附件走 `/attachments` 端点**，20MB 的报告要 `timeout≥600`，否则命令行超时（草稿已建、附件只传了一半）。
6. **文件名别带 `_765`**（用户要求：报告文件名只留 A 版本串，V 版本不写进文件名）。
7. **草稿创建后如果又要改**：直接 PATCH 同一封草稿的 body，不要重新 createReplyAll（会多出重复草稿）。
8. **中文参数在 cmd 下乱码**：先 `set PYTHONIOENCODING=utf-8`，或把参数写进 JSON 配置文件读。
9. **改完必须回读校验**：看 `isDraft`、收件人数量、附件列表、正文里是否还有 `_763`。

## 五、与上游 skill 的关系

```
版本系统测试报告生成  →  产出 xlsx（报告 + 修改点报告）
        ↓
内部报告转邮件草稿  →  产出 Outlook 草稿（本 skill）
        ↓
人工检查 → 手动发送
```

报告里的「测试风险 / 缺陷 / 压力」数据直接对应邮件正文第 3、6、7 段，**两边必须一致**；
改一边记得同步另一边。
