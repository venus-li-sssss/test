---
name: qmeeting-rooms
description: 查/订/取消移远会议室（qmeeting.quectel.com）时用本 skill。触发词：会议室、查会议室、有没有空会议室、订会议室、预订会议室、开会订房、取消会议、退订会议室、我的会议、会议详情、qmeeting、会议室空闲、会议室占用、约个会议室。
metadata:
  qwenpaw:
    emoji: "🏢"
    requires:
      bins: ["python"]
---

# 移远会议室（qmeeting）

一条命令搞定：查空闲会议室 / 看某会议室当天占用 / 查我的会议 / 预订 / 取消。
所有能力都在 `scripts/qmeeting.py`（只用 `requests`，没有浏览器依赖）。

- 站点：`https://qmeeting.quectel.com`
- 登录：SSO（`sso-web.quectel.com`），token 有效期 24h，**refresh token 会自动续期**
- token 存放：`%USERPROFILE%\.qmeeting\token.json`（不在 skill 目录里，不会被同步出去）

## 0. 先确认登录状态

```bash
python scripts/qmeeting.py whoami
```

失败（提示未登录 / 登录过期）就按下面重新登录：

| 方式 | 命令 | 场景 |
|---|---|---|
| HAR/DevTools 文件 | `qmeeting.py login --devtools download.devtools` | 用户刚从浏览器导出了网络日志（最省事） |
| Cookie | `qmeeting.py login --cookie "quectel_token=bearerXXXX; quectel_refresh_token=YYYY"` | 用户从 DevTools → Application → Cookie 复制的整串 |
| Token | `qmeeting.py login --token "bearerXXXX" [--refresh-token YYYY]` | 只有 access token |

> 登录不需要密码：SSO 登录页的密码是 RSA 加密后提交的，脚本不做密码登录。
> 需要新 token 时：让用户浏览器登录 qmeeting → 导出 HAR → `login --devtools`。

## 1. 命令速查

```bash
# 我在哪 / 我的 userId
python scripts/qmeeting.py whoami

# 我可用的办公区域（拿 areaId / 看楼层路径）
python scripts/qmeeting.py areas

# 某时段空闲会议室（默认只看我本园区；--area 换区域）
python scripts/qmeeting.py rooms --date 2026-11-12 --start 14:00 --end 15:00 \
    [--area FoShan-B10] [--room Malaga] [--min-capacity 8] [--facility 飞书] \
    [--platform 飞书] [--all] [--sites] [--limit 40]

# 会议室当天日程（谁占了哪段时间）
python scripts/qmeeting.py calendar --date 2026-11-12 [--area FoShan] [--room Leeds] [--sites]

# 我的会议（默认我发起的未结束会议）
python scripts/qmeeting.py mine [--status MY_BOOKING|MY_INVITED|WEEK|DAY|MONTHLY|ALL_MEETING] [--include-finished]

# 会议详情（含会议号/线上会议链接/参会人/状态）
python scripts/qmeeting.py detail 599349

# 预订（先 --dry-run 看 payload，再真下单）
python scripts/qmeeting.py book --room Malaga --date 2026-11-12 --start 14:00 --end 15:00 \
    --theme "QDM562 周会" --participant "Harrison Zheng" --participant someone@quectel.com \
    --explain "议程..." [--reminder 15] [--platform LARK] [--dry-run]

# 取消（必须带 --yes 才真的提交；不带只做预览）
python scripts/qmeeting.py cancel 645864 --remark "不需要了" --yes

# 平台预订规则（时间步长/开放时段/可订天数）
python scripts/qmeeting.py config
```

`--json` 加在任何位置都能拿到原始 JSON（`qmeeting.py --json mine` / `qmeeting.py mine --json`）。

## 2. 典型工作流

**「明天下午 2 点找个 8 人会议室，主题 XX，叫上 A 和 B」**
1. `rooms --date tomorrow --start 14:00 --end 15:00 --min-capacity 8` → 选一间
2. 把 roomId/名称 + 时间 + 参会人复述给用户确认（**预订是外部操作，必须先确认**）
3. `book --room <roomId> --date ... --start ... --end ... --theme ... --participant ...`
4. 报回 bookingId、会议室、线上会议链接（如有）

**「我这周还有什么会」** → `mine --status WEEK`；**「我订的会都在哪」** → `mine --status MY_BOOKING`

**「那个会不开了」** → `mine` 找到 bookingId → 先 `cancel <id>`（无 `--yes`，只预览主题/时间/会议室）→ 用户确认后 `cancel <id> --yes`

**「3F 还有哪间空着」** → `calendar --date 今天 --area FoShan-B10-3F`，看「全天空闲」的；再 `rooms` 复核时段。

## 3. 必须知道的坑（都实测过）

1. **`recommend/listByUser` 不按办公区域过滤**，会把全公司 200+ 会议室都返回。
   脚本里用 `calendarView` 先反查「本区域有哪些 roomId」再做交集，所以默认输出已收敛到我所在园区；
   `--area` 换区域、`--sites` 查全部园区。
2. **`appointed/create` 的 `error` 字段不可信**：实测常常返回「xxx 冲突」但会议**已经建成功**，
   房间也确实被占用。判断成败以 `bookingId` + `detail` 查到的会议室为准，脚本已自动核实。
   看到「注意：平台返回提示…冲突」时告诉用户「已建成功，但平台标了冲突，要不要我取消」。
3. **时间片**：步长 5 分钟（`config` 可查），开放时段 07:00–23:59，最多订未来 90 天。
   不在 5 分钟刻度上会告警（不阻断）。
4. **取消是必杀操作**：脚本不带 `--yes` 只预览；`cancelBooking` 会真的删除会议并通知参会人。
   循环会议（`isRecurrenceMeeting=Y`）取消的是单个 bookingId 那一次。
5. **参会人**：`--participant` 支持 姓名 / 邮箱 / userId，会自动去重并**自动包含自己**；
   同名多人会报错并列出候选，用邮箱或 userId 再试。
6. **平台类型**：默认按会议室 `teleconferenceType` 推断（飞书→LARK、Teams→TEAMS、Zoom→ZOOM、
   腾讯会议→TENCENT），推断错了用 `--platform` 覆盖；会议室没有线上会议设施时不要传 `--platform`。
7. **中文乱码**：脚本在 GBK 控制台自动用 GBK 输出；把输出重定向到文件或用 `--json` 落盘时，
   先 `set QMEETING_OUTPUT_ENCODING=utf-8`（PowerShell：`$env:QMEETING_OUTPUT_ENCODING="utf-8"`）。
8. `--date` 支持 `today` / `tomorrow` / `YYYY-MM-DD`；日期时间统一按 **GMT+8** 计算。

## 4. 安全约定

- **查**（whoami / areas / rooms / calendar / mine / detail / config）随便跑。
- **写**（book / cancel）—— 先向用户复述「会议室 + 日期时间 + 主题 + 参会人」，得到确认再执行；
  执行后用 `detail` 或 `calendar` 复核并回报 bookingId。
- 不要把 token 打印到公开场合；token.json 不要提交、不要上传到任何仓库。

## 5. 接口参考

字段级细节见 [`reference/api.md`](reference/api.md)（抓包 + 实测整理，含请求/响应样例）。
