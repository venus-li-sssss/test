---
name: quectel-workhours
description: 自动填写移远工时系统 (work.ikotek.com) 的工时记录。支持从考勤系统获取打卡数据，自动计算工时并提交。触发词：工时、填写工时、提交工时、work.ikotek.com、workhours。
agent_created: true
---

# 移远工时自动填写

## 快速使用

```bash
PY="C:/Users/venus.li/.workbuddy/binaries/python/versions/3.13.12/python.exe"
cd ~/.qwenpaw/workspaces/QwenPaw_QA_Agent_0.2/skills/quectel-workhours/scripts

# 查看本月工时列表
$PY workhours.py --list

# 查看某月工时
$PY workhours.py --list --month 2026-07

# 提交工时（交互式）
$PY workhours.py --submit

# 提交指定日期的工时
$PY workhours.py --submit --date 2026-08-06

# 撤销已提交的工时
$PY workhours.py --withdraw

# 撤销指定日期的工时
$PY workhours.py --withdraw --date 2026-08-05

# 重新提交已撤销的工时
$PY workhours.py --resubmit

# 重新提交指定日期的工时
$PY workhours.py --resubmit --date 2026-08-05

# 批量提交本月所有未提交工时
$PY workhours.py --submit --month 2026-08 --auto

# JSON 输出
$PY workhours.py --list --json
```

## 工作流程

1. **获取考勤数据**：调用 quectel-attendance skill 获取指定日期的打卡记录
2. **计算工时**（`workhours.py` 内置 `calc_work_hours(first, last, is_rest_day, shift)` / `calc_from_attendance_json()`，规则与 quectel-attendance 一致，双班次）：
   - **A班** 13:00–17:30，加班 **18:30** 起算；**B班** 13:30–18:00，加班 **19:00** 起算；
     `shift=None` 自动推断（末次打卡 <18:00 → A，否则 B）。A班但晚上加班的日子必须显式传 `shift="A"`，否则少算 0.5h
   - **工作日**：前段满班按 **8h** 计（实际只上 7.5h 也算 8h；弹性迟到=晚下班同量，早退按差额扣），
     加班从班次起算点按实际时长加。例 B班 09:20–21:32 → 8 + 2.53 = 10.53h；A班 09:00–20:00（shift="A"）→ 8 + 1.5 = 9.5h
   - **休息日**：实际在司时间（扣午休 12:00→班次下午上班点；超过加班起算点才再扣晚餐窗口）
   - **总时间 = 前段 + 加班**
   - **注意**：只传总时间给系统，让系统自动拆分标准工时和加班，不要手动拆分
3. **选择项目**：从项目列表中选择或指定项目
4. **填写内容**：
   - **工作描述（description）**：简洁描述，如"测试 QDM559 版本"
   - **工作总结（summary）**：详细列表，如"1. xxx---已完成\n2. xxx---已完成"
5. **提交**：调用 work.ikotek.com API 提交工时

## 认证

凭据优先级：环境变量 `WORK_USER` / `WORK_PASS` > `../.credentials.json`（与考勤系统共用）。
本仓库不含任何账号：使用时自己在 `../.credentials.json` 填入账号和密码，形如
`{"username": "<你的账号>", "password": "<你的密码>", "userId": "<你在工时系统的userId>"}`。
其中 `userId` 是提交工时 payload 必需的本人 ID（可从 `/api/mh/work-info/list` 返回记录里查到），
也可用环境变量 `WORK_USERID` 提供；缺了脚本会报错提示。

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

## 文件

- `scripts/work_client.py` — work.ikotek.com API 客户端
- `scripts/workhours.py` — 工时填写 CLI
- `../.credentials.json` — 账号密码（与考勤系统共用）

依赖：`requests`
