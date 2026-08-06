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
2. **计算工时**：
   - **开始时间**：首次打卡时间
   - **结束时间**：末次打卡时间
   - **总时间**：有效工时（已扣除午休、晚餐）
   - **注意**：只传总时间给系统，让系统自动拆分标准工时和加班，不要手动拆分
3. **选择项目**：从项目列表中选择或指定项目
4. **填写内容**：
   - **工作描述（description）**：简洁描述，如"测试 QDM559 版本"
   - **工作总结（summary）**：详细列表，如"1. xxx---已完成\n2. xxx---已完成"
5. **提交**：调用 work.ikotek.com API 提交工时

## 认证

凭据优先级：环境变量 `WORK_USER` / `WORK_PASS` > `../.credentials.json`（与考勤系统共用）。

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
