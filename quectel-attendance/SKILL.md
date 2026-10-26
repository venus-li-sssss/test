---
name: quectel-attendance
description: 查询移远 QHR 考勤系统 (hr.quectel.com) 的打卡记录并计算工时。双班次（17:30/18:00 下班，加班自 18:30/19:00 起算），前段实际7.5h也按8h标准工时，弹性迟到补偿、迟到早退统计。触发词：考勤、打卡、工时、上班时间、下班时间、加班、迟到、QHR、hr.quectel.com。
agent_created: true
---

# 移远 QHR 考勤查询与工时计算

## 快速使用

```bash
PY="C:/Users/venus.li/.workbuddy/binaries/python/versions/3.13.12/python.exe"
cd ~/.workbuddy/skills/quectel-attendance/scripts

$PY attendance.py                      # 本月全部
$PY attendance.py --month 2026-07      # 指定月份（可逗号分隔多月）
$PY attendance.py --date 2026-08-03    # 单日
$PY attendance.py --last 7             # 最近 7 个有打卡的日子
$PY attendance.py --shift a --last 3   # 强制按 A班(17:30下班/18:30起算加班) 计算
$PY attendance.py --month 2026-07 --json   # JSON 输出，便于二次分析
```

输出列：日期 / 周几 / 班次(A/B) / 首次打卡 / 末次打卡 / 工时 / 应下班时间 / 迟到 / 早退 / 加班，
末尾给出总工时、日均工时、总加班。JSON 里 `work_hours` = 前段8h规则 + 实际加班，可直接提交。

## 工时计算规则（重要）

有两个班次（上午都是 09:00 起、弹性；下午/下班不同），**前段实际哪怕只上了 7.5h 也按 8h 标准工时计**，
加班从各自起算点起按实际时长计（"后面加班多少就是多少"）：

| 班次 | 下午上班(午休结束) | 下班 | 晚餐缓冲 | 加班起算 | 满班前段 |
|---|---|---|---|---|---|
| **A班** `--shift a` | 13:00 | **17:30** | 17:30–18:30 | **18:30** | 实际7.5h → 按8h |
| **B班** `--shift b` | 13:30 | **18:00** | 18:00–19:00 | **19:00** | 实际7.5h → 按8h |

班次判定：显式 `--shift a|b` 优先；不指定时自动推断——**末次打卡早于 18:00 只可能是 A班，
否则默认 B班**。⚠️ A班但晚上加班（末次 ≥ 18:00）的日子必须显式加 `--shift a`，否则会按
B班从 19:00 起算加班、少算 0.5h。

1. **首次打卡 / 末次打卡**：取当天所有打卡记录的最早和最晚（系统里一天常有十几条重复刷卡，必须去重取首尾）。
2. **前段（标准工时）= 8h − 早退差额**：
   - 迟到 = max(0, 首次打卡 − 09:00)（早于 9:00 打卡不提前算，基准仍是 9:00）
   - **应下班 = 班次下班时间(17:30/18:00) + 迟到时长**（弹性：早上迟来多久，晚上就晚走多久）
   - 早退 = max(0, 应下班 − 末次打卡)；只要干到应下班时间就算满班，**统一按 8h**（含实际 7.5h 的日子）
   - 迟到 ≤ 60 分钟标记 `flex`（正常弹性范围），超出需关注
3. **后段（加班）= max(0, 末次打卡 − 加班起算点)**：
   - A班从 18:30 起算、B班从 19:00 起算，按实际时长，精确到分
   - 应下班 → 加班起算点之间是晚餐缓冲，不计工时（B班干到 19:00 以内加班都是 0）
4. **总工时 `work_hours` = 前段 + 加班**，提交工时系统时只传这个总数，系统自动拆标准/加班。
5. **休息日**（班次字段 SHIFT 含"休息"，即周末/节假日）：不判迟到早退、不适用 8h 规则，
   当天有效时长（扣与午休窗口的重叠；超过加班起算点才再扣晚餐窗口）全部直接计为加班。
6. 早上提前打卡不加时；单次打卡（漏刷）按早退差额算，前段通常为 0，需看 `abnormal`/`absent_hours`。

旧版（2026-10 之前）单一规则"12:00–13:00 午休、18:00 下班、19:00 起算加班、有效工时=在司-午休-晚餐"
已废弃，现在的差异：7.5h 班计 8h、A班加班从 18:30 起算。

## 认证

凭据优先级：环境变量 `QHR_USER` / `QHR_PASS` > `../.credentials.json`。
凭据文件已配置为 `Venus.Li@ikotek.com`（QHR 与 SSO 共用统一域账号密码）。

登录链路（已在 `qhr_client.py` 中实现，无需手动操作）：
1. `POST sso-web.quectel.com/api/uaa/mfa-open/check` — 校验账密（返回 `isPass`）
2. `POST sso-web.quectel.com/api/uaa/oauth/token` — 换取 bearer token
   - **必需参数**：`grant_type=password`、`username`、`password`（RSA 加密）、
     `scope=ui`、`client_id=quectel`、`client_secret=quectel`、**`auth_type=rsa_area`**
   - **必需请求头**：`terminal: web`、`devicesn: <任意32位hex>`
   - 缺少上述任一项会直接返回 401
3. `POST hr.quectel.com/?ssotoken=6DehZxYDUzhQJ9hk` 带 `tk` / `quectel_token` 换 HR 会话 Cookie
4. `GET /view/app/app!G8_TRwtFegd0QeO2BfN6kg` 激活"我的考勤"应用上下文（必须，否则 ajax 返回 HTML）

密码加密：RSA/PKCS#1 v1.5，公钥硬编码在 `qhr_client.py`（取自 SSO 前端
`js/Login~factoryLogin.*.js`）。若某天登录突然 401，先去该 JS 里核对公钥是否更换。

## 数据接口

均为 `POST https://hr.quectel.com/ajax/function/<name>`，Content-Type: application/json，
body 形如 `{"appParam":{"TERM":"2026-08-01T00:00:00.000Z"},"appFnKey":"SE03xx","formData":{}}`。
TERM 必须是该月 1 号；一次返回整月数据。

| 接口 | appFnKey | 说明 | 关键字段 |
|---|---|---|---|
| `alist!G8_TRwtFegd0QeO2BfN6kg.220302` | SE0302 | 原始打卡流水 | `CARDTIME`（打卡时刻）、`SHIFTTERM`（归属日） |
| `alist!G8_TRwtFegd0QeO2BfN6kg.220398` | SE0398 | 每日考勤汇总 | `TERM`、`SHIFT`（班次/休息）、`LATEMIN`、`EARLYLEAVE`、`ABST`(缺勤时数)、`ISEXCEPTION`、`C018`(延时餐补次数) |
| `extfields!....220398` | SE0398 | 扩展列名映射 | ABST_1=缺勤时数, LTRM_1=迟到分钟, ERLM_1=早退分钟, C018_1=延时餐费补贴次数 |

注意：HR 系统自身的 `LATEMIN` / `EARLYLEAVE` 常年为 0（弹性制下不判罚），
所以工时和迟到早退需按上面的规则**自行从打卡流水计算**，不要直接信这两个字段。

## 文件

- `scripts/qhr_client.py` — 登录与接口封装（可作为库 import：`QHR(u,p).login().punches("2026-08")`）
- `scripts/attendance.py` — 工时计算与 CLI
- `.credentials.json` — 账号密码（本地，勿外传）

依赖：`requests`、`pycryptodome`。
