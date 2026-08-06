---
name: quectel-attendance
description: 查询移远 QHR 考勤系统 (hr.quectel.com) 的打卡记录并计算工时。支持首次/末次打卡时间、有效工时、迟到早退、弹性工作补偿、19 点后加班时长统计。触发词：考勤、打卡、工时、上班时间、下班时间、加班、迟到、QHR、hr.quectel.com。
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
$PY attendance.py --month 2026-07 --json   # JSON 输出，便于二次分析
```

输出列：日期 / 周几 / 首次打卡 / 末次打卡 / 有效工时 / 应下班时间 / 迟到 / 早退 / 加班，
末尾给出总工时、日均工时、总加班。

## 工时计算规则（重要）

标准班：**09:00 上班，18:00 下班，12:00–13:00 午休 1h，标准工时 8h**。

1. **首次打卡 / 末次打卡**：取当天所有打卡记录的最早和最晚（系统里一天常有十几条重复刷卡，必须去重取首尾）。
2. **有效工时** = 末次 − 首次 − 午休 − 晚餐
   - 午休：与 12:00–13:00 的重叠部分（最多 1h）
   - 晚餐：仅当末次打卡晚于 19:00 时，扣除与 18:00–19:00 的重叠（1h）
3. **弹性工作制**：早上迟来多久，晚上就要晚下班多久。
   - 迟到时长 = 首次打卡 − 09:00（早于 9:00 打卡不提前算，基准仍是 9:00）
   - **应下班时间 = 18:00 + 迟到时长**
   - 早退 = 应下班 − 末次打卡（为正才算）
   - 迟到 ≤ 60 分钟标记为 `flex`（正常弹性范围），超出需关注
4. **加班**：**从 19:00 开始计算**，18:00–19:00 是缓冲/晚餐时间不计。
   - 加班时长 = 末次打卡 − 19:00（为正才算）
5. **休息日**（班次字段 SHIFT 含"休息"，即周末/节假日）：不判迟到早退，
   当天全部有效工时直接计为加班。

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
