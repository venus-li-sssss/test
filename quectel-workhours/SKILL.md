---
name: quectel-workhours
description: 自动填写移远工时系统 (work.ikotek.com) 的工时记录。支持从考勤系统获取打卡数据，自动计算工时并提交。触发词：工时、填写工时、提交工时、work.ikotek.com、workhours。
agent_created: true
---

# 移远工时自动填写

## 快速使用

```bash
cd C:\Users\venus.li\.qwenpaw\workspaces\default\skills\quectel-workhours\scripts

# 查看本月工时列表
python workhours.py --list

# 查看某月工时
python workhours.py --list --month 2026-07

# 提交工时（交互式）
python workhours.py --submit

# 提交指定日期的工时
python workhours.py --submit --date 2026-08-06

# 撤销已提交的工时
python workhours.py --withdraw

# 撤销指定日期的工时
python workhours.py --withdraw --date 2026-08-05

# 重新提交已撤销的工时
python workhours.py --resubmit

# 重新提交指定日期的工时
python workhours.py --resubmit --date 2026-08-05

# 批量提交本月所有未提交工时
python workhours.py --submit --month 2026-08 --auto

# JSON 输出
python workhours.py --list --json
```

## 工作流程

1. **获取考勤数据**：调用 quectel-attendance skill 获取指定日期的打卡记录
2. **计算工时**（规则在 quectel-attendance 的 `attendance.py`，双班次）：
   - **开始时间**：首次打卡时间；**结束时间**：末次打卡时间
   - **前段**：满班按 **8h** 计（A班 17:30 / B班 18:00 下班，实际哪怕只上了 7.5h 也算 8h）；
     早退按差额扣，弹性迟到=晚下班同样时长
   - **加班**：A班从 **18:30**、B班从 **19:00** 起按实际时长计（下班后 1h 晚餐缓冲不算）
   - **班次**：**必须显式问用户**（`--shift a|b`，首次问选班+是否设本地默认；有默认每次仍要确认"用默认X吗"）。
     平台副本**无默认班次、不按打卡推断**；agent 不带 --shift 跑会直接报错。一个月混班时按班次分批跑
   - **总时间 `work_hours` = 前段 + 加班**
   - **注意**：只传总时间给系统，让系统自动拆分标准工时和加班，不要手动拆分
3. **选择项目**：从项目列表中选择或指定项目
4. **填写内容**：
   - **工作描述（description）**：简洁描述，如"测试 QDM559 版本"
   - **工作总结（summary）**：详细列表，如"1. xxx---已完成\n2. xxx---已完成"
5. **提交**：调用 work.ikotek.com API 提交工时

## 认证

凭据优先级：环境变量 `WORK_USER` / `WORK_PASS` > `.credentials.json`
（位于 skills 根目录，与考勤系统共用）。
本仓库不含任何账号：使用时自己在 `.credentials.json` 填入账号和密码，形如
`{"username": "<你的账号>", "password": "<你的密码>"}`。
**userId 不需要填**：提交时脚本用登录后的账号自动调 `/api/mh/work-info/list`，
从返回记录里取本人 `userId`（`WorkClient.get_userid()`），任何情况下都不写死。

登录链路（已在 `work_client.py` 中实现）：
1. SSO 登录获取 token
2. 用 token 访问 work.ikotek.com

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/mh/work-info/list` | POST | 获取工时列表 |
| `/api/mh/project-info/project-name` | GET | 获取项目列表 |
| `/api/mh/work-info/submit` | PUT | 提交/重新提交工时 |
| `/api/mh/work-info/withdraw/{id}` | POST | 撤销已提交的工时 |
| `/api/mh/work-info/update/{id}` | GET | 获取工时编辑详情 |

## 批量补填（推荐用法，非交互 + 并发）

`scripts/batch_fill_by_attendance.py` —— 按考勤自动补填指定日期，默认 dry-run，加 `--commit` 才写。

```bash
cd C:\Users\venus.li\.qwenpaw\workspaces\default\skills\quectel-workhours\scripts

# 多天同一份内容
python batch_fill_by_attendance.py --dates 2026-09-28,2026-09-29 --commit ^
  --desc "测试 QDM562 版本" --items "测试xxx版本---进行中" "协助客户产线---已完成"

# 每天内容不同：写 plan 文件（放在 ../plan/），一条命令并发提交
python batch_fill_by_attendance.py --plan ..\plan\plan_2026-10-08_12.json --commit
```

plan JSON 字段：`date` / `desc`（多项目用 `" | "` 分隔）/ `items`（不带序号，自带 `---状态`）/
`split`（`"792=4.1,611=4.1"` 一天拆多项目，合计与考勤不符时自动按比例归一）/ `force`。

提速：考勤与项目列表落盘缓存在 `.cache/`（`--refresh` 强制重拉）；SSO 只登一次，token 发给
线程池里各 worker 的独立 session；多天并发 `--workers`（默认 5）。考勤缓存按
**规则版本+班次** 分桶（`RULE_VERSION`），换算法/换 `--shift a|b` 不会互相污染，旧格式缓存自动作废重拉。
班次用考勤同一套：`--shift a`=5点半班(18:30起算加班)、`--shift b`=6点班(19:00起算加班)，
**`--shift` 必填**（先问用户/确认默认；无默认不推断，缺了 argparse 直接报错）。
实测 4 次只读请求 串行 6.2s → 并发 1.7s。

## ⚠️ 判断"哪天该填"的正确口径（踩过）

- **不要看工时列表的 `type` 字段**：它把国庆（10-01~10-03）、中秋（09-25）也标成 `0`（"工作日"），
  照它统计会把休息日当成漏填。
- **正确做法 = 查 QHR 每日汇总 `SHIFT` 字段**（quectel-attendance skill，`appFnKey=SE0398`）：
  `SHIFT` 含"休息" **且当天零打卡** → 休息日，不用填；有打卡 → 按考勤 `work_hours` 填。
- `attendance.py` 默认只输出**有打卡**的日子，所以"某天不在输出里"= 那天没打卡，别当成脚本漏了。
- **工时列表 `status` 有三个值，别只认 `2`**：`1`=未提交、`2`=已提交、`4`=**已审批/归档**。
  1~3 月这类早已归档的月份全是 `4`，写 `status=="2"` 判"已提交"会把整个归档月误报成漏交。
  正确判据：`status in {"2","4"}` 才算交过。
- **考勤缓存里的当月数据一定会过期**（打卡当天还在累积）。`cached_attendance()` 已改为
  **当月永远强制重拉**，且**拉回 0 行的月份不落盘**（下次还会重试）。踩过：拿 10-22 建的缓存
  核对 10-26，把 10-23（实际 09:22–20:29、有效 9.5h、工时 0 未提交）误判成"没打卡不用填"。
- **QHR 接口只回溯最近 3 个自然月**（SE0302/SE0398 对更早月份返回 0 行，实测 2025-09 ~ 当年 7 月全空）。
  所以"有考勤但没填工时"这类核对**最多只能回看两个月前**；更早的月份只能做工时侧自查
  （工作日 0 工时 + 无法证实是否上班），要坐实得换数据源（邮件/JIRA/SVN 当天活动）。

## ⚠️ 提交接口的硬事实（实测）

- 提交 = `PUT /api/mh/work-info/submit`，**补历史日期必须在 payload 里带该记录的 `id` 和 `reportTime`**
  （`id` 从 `/api/mh/work-info/list` 拿，形如 `724987`；`reportTime` 形如 `2026年09月28日`）。
  只有日期没有 id 的 payload 是 `workhours.py --submit` 的"提交今天"路径。
- **已提交的天重提会被拒**：返回 `You have already submitted data, no need to submit again`
  —— 幂等保护，误重提不会改数据；要改必须先 `--withdraw` 再提。
- 一天可挂多项目（`detailVos` 多条，各自 `workTime`），总 `workTime` = 各条之和；
  加班不要手工拆，`overTime`/`overtime` 传 0，系统按 19:00 起自拆。
- `summary` 是主记录级 HTML：`<p>1. xxx---已完成</p><p>2. yyy---进行中</p>`；
  `description` 在 `detailVos` 里按项目各写一句简洁描述。

### 常用项目 ID（venus.li 实际在用的）

| ID | 项目 | 阶段 | 负责人 | productNameId | productLine |
|---|---|---|---|---|---|
| 792 | QDM562-EA-MCN | EVT | Seamus Yan 闫会杰 | 15581 | Embedded(Not FWA) |
| 611 | QDM559-EA-NA | DVT | Sank Qin 覃胜广 | 15554 | Embedded(Not FWA) |

其它候选：795 QDM562-EA-KCN / 1295 QDM568-EA-CNC / 1139 QDM568-EA-CN。共 819 个项目，
完整列表在 `.cache/projects.json`（跑一次脚本自动生成）。

## 文件

- `scripts/work_client.py` — work.ikotek.com API 客户端
- `scripts/workhours.py` — 工时填写 CLI（交互式，只能填今天）
- `scripts/batch_fill_by_attendance.py` — **批量补填**（非交互、考勤取数、多项目拆分、并发提交）
- `../plan/*.json` — 补填计划文件（每天一条：date/desc/items/split）
- `../.cache/{attendance,projects}.json` — 提速缓存，可随手删，`--refresh` 重建
- `../.credentials.json` — 账号密码（与考勤系统共用）

依赖：`requests`
