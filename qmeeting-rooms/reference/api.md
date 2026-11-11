# qmeeting 接口参考

来源：用户浏览器导出的 `download.devtools`（HAR）+ 实测验证（2026-11-11）。
所有请求都带：
```
authorization: bearer<access_token>
content-type: application/json
```
响应统一信封：`{"success": true, "msg": null, "code": 0, "data": ...}`；`code != 0` 即失败。

## 登录 / token

```
POST https://sso-web.quectel.com/api/uaa/oauth/token
Content-Type: application/x-www-form-urlencoded

# 账号密码登录
grant_type=password&username=<邮箱或工号>&password=<RSA密文>&scope=ui
  &client_id=quectel&client_secret=quectel&auth_type=rsa_area

# 刷新（refresh_token 会轮换，务必覆盖保存）
grant_type=refresh_token&refresh_token=<原始uuid>&scope=ui&client_id=quectel&client_secret=quectel
```
响应：
```json
{"access_token":"uuid","refresh_token":"uuid","expires_in":86399,"scope":"ui","code":"0",
 "data":{"access_token":"...","expires_in":"2026-11-12 09:38:49",
         "userInfo":{"id":"<userId>","username":"<登录名>","tenantId":"1"}}}
```
> `refresh_token` 传原始 UUID，**不要**带 `bearer` 前缀（带前缀会返回
> `The current user login information has expired`）。
> 前端 Cookie：`quectel_token=bearer<uuid>`、`quectel_refresh_token=<uuid>`。

### 密码的 RSA 加密（纯 Python 复刻）

SSO 登录页（`sso-web.quectel.com`）的登录逻辑在 `js/Login.<hash>.js` + 共享块
`js/Login~factoryLogin.<hash>.js` 里，等价 JS：

```js
// sso_login_shared.js 模块 869c 的 export c
function c(text, out='base64', inp='utf8') {
  const rsa = new Encrypt();               // jsencrypt 派生
  rsa.setOptions({ encryptionScheme: 'pkcs1' });
  rsa.importKey(<硬编码 2048 位公钥 'MIIBIjANBgkq...'>, 'pkcs8-public-pem');
  return rsa.encrypt(text, out, inp);      // → base64(256 字节)
}
// sso_login.js：area 页签下
f.password = c(f.password); f.auth_type = 'rsa_area';
```

等价 Python（脚本里的 `rsa_encrypt()`，无第三方依赖）：

1. `base64.b64decode(公钥)` → 手写 DER 解析出 `SEQUENCE{n, e}`（2048 位 / e=65537）
2. `EM = 0x00 || 0x02 || PS(非零随机, 长度 k-3-len) || 0x00 || password_utf8`
3. `c = pow(int(EM), e, n)` → 256 字节 → base64（长度 344）

实测校验：自建密钥对往返（含中文密码）与 `cryptography` 解密结果一致；
对真实公钥加密结果同样是 256 B / 344 字符，与抓包里的密文长度一致。

**公钥怎么更新**（SSO 换 key 后的修法）：打开 `https://sso-web.quectel.com/`，
取 `js/app.*.js` 里的 chunk 映射找到 `Login~factoryLogin` 的 hash，下载该 js，
搜 `MII` 拿到 392 字符的新公钥，替换 `qmeeting.py` 里的 `SSO_RSA_PUBKEY` 常量。

### MFA

```
POST /api/uaa/mfa-open/check   {"username":"<账号>","password":"<RSA密文>"}
→ {"code":0,"data":{"isPass":true,"mfaConfigVo":{"webMfaConfig":{...}},"isJumpMfaStep":"?"}}
→ 账号密码错: {"success":false,"code":400,"msg":"username or password is incorrect"}
```
前端逻辑：`needMFA = 非内网 && webMfaConfig 里有 'Y'`，此时会弹短信/邮件验证码弹窗，
后续用 `auth_type=multi_acc_login` + `key=<loginKey>` 再换 token。
**开了 MFA 的账号没法只靠密码登录**，脚本遇到会提示改用 HAR/Cookie 方式。
token 接口返回 `code:102` 也代表需要 MFA。


## 我 / 组织

| 用途 | 请求 |
|---|---|
| 我的信息 | `GET /api/org/employee/getMyInfo?fileId=` → `data.employeeVo{userId,enName,legalName,deptName,workEmail}` |
| 我所在园区 | `GET /api/meet/system/area` → `data{id:"12",name:"FoShan"}` |
| 员工搜索 | `POST /api/org/employee/page` `{"workStatus":"IN_SERVICE","pageNumber":1,"pageSize":20,"name":"<关键词>","key":"<关键词>"}` → `data.records[]{userId,enName,legalName,workEmail,deptName}` |
| 按 userId 查员工 | `POST /api/org/employee/selectEmpBaseInfoByUserIds` `["<userId>"]` |

## 办公区域

| 用途 | 请求 |
|---|---|
| 我的区域树 | `POST /api/meet/office-area/list-treeByUser` `{}` → 树 `{id,name,parentId,level,leaf,children[]}` |
| 全部区域树 | `POST /api/meet/office-area/list-tree` |
| 保存我的常用区域 | `POST /api/meet/appointed/officeIds` `["61","62"]`（**必须是 Long 数组**，传对象报 500） |

树里用路径拼：`FoShan` → `B10` → `3F`（`id=12 / 61 / 62`）。订会议室时把这些 id 一起传。

## 系统配置

| 用途 | 请求 | 关键字段 |
|---|---|---|
| 配置 | `GET /api/meet/system/config` | `bookingTimeSlotConfig{step:5,cell:15}`、`openBookingConfig{startTime:"07:00",endTime:"23:59"}`、`dateRangeConfig.restrictFutureBookingDay:90`、`conflictConfig{enableMeetingRoomConflict,meetingRoomConflictHandlingMethod:"NOT_ALLOW_COMMIT"}`、`checkInConfig` |
| 提示语 | `GET /api/meet/system/hint` | 「最多支持预订未来90天以内的会议室」 |
| 设施字典 | `GET /api/meet/room-facility/all` | `[{id,name,enName}]`（飞书/TV/Projector/Zoom/Teams/腾讯会议/手持麦克风/客户接待…） |
| 维度 | `POST /api/meet/common/all` `{"type":["ROOM_FACILITY_DIMENSION"]}` | 同上 |

## 查会议室

### 1) 某时段的可用/占用（推荐）

```
POST /api/meet/recommend/listByUser
{"officeAreaIds":["61","62"],"startStamp":1794463200000,"endStamp":1794466800000}
→ data{ableRooms:[...],unableRooms:[...]}
```
> ⚠️ **`officeAreaIds` 实际不生效**：会返回全公司会议室（实测 219+）。
> 需要区域级收敛时先用 `room/calendarView` 取该区域的 roomId 集合再求交集。

room 对象（挑常用字段）：
```
roomId, name, cnName, seatingCapacity, facilities[], teleconferenceType(飞书/Teams/…),
officeName(楼层，如 "3F"), officeId, step, enableHideWhenNotOpen,
availableTimeSlots[], unAvailableTimeSlots[], using[]{start,end,bookingId,bookingName,bookingTheme,state}
```

### 2) 会议室日历（区域级，唯一按区域过滤的接口）

```
POST /api/meet/room/calendarView
{"officeAreaIds":["61","62"],"facilityIds":[],"periodOfTimeStart":"","periodOfTimeEnd":"",
 "roomName":"","dateStr":"2026-11-12","fountTimeStart":"07:00","fountTimeEnd":"23:59"}
→ data[ room{... , using:[{start:"14:00",end:"16:00",bookingName:"<预订人>",bookingTheme,state:"BOOKED"}]} ]
```
`using` 为空 = 全天空闲。**只有这个接口会按 officeAreaIds 过滤**（FoShan 3F 返回 9 间、FoShan 全园区 20 间）。

### 3) 我的空闲/占用（按人）

```
POST /api/meet/recommend/checkAvailability  {"userIds":["<userId>"],"bookingId":"","dateStr":"2026-11-12"}
→ data[{userId,userName,periods:[]}]
```

### 4) 日历页辅助

```
POST /api/meet/appointed/timePeriod  {"officeAreaIds":["61","62"],"source":"USER"} → {start:"07:00",end:"23:59",step:5}
POST /api/meet/appointed/daysPeriod  {"officeAreaIds":["61","62"]} → {startDay,endDay}
POST /api/meet/appointed/period      {"startDay","endDay","bookingCriteria":{...}} → [{date,exist}]
POST /api/meet/recommend/numberOfDays ["148"] → 90
POST /api/meet/system/whetherToShowBusy ["148"] → true
```

## 会议室详情 / 图片 / 位置导航图

```
GET /api/meet/room/detail/<roomId>
```
返回（节选）：
```json
{
  "id": "148",
  "roomHeard": {"name": "306-FS-B10-3F-Male", "cnName": ""},
  "roomBase": {
    "seatingCapacity": 6,
    "typeDimensionDto": {"name": "VTC Room"},
    "officeAreaDto": {"name": "3F"},
    "areaDto": {"name": ""},
    "imageFileIdList": ["2532089", "2532090"],
    "imageFiles": [{
      "link": "https://qos.quectel.com/tenant-1-quectel/upload/2023-09-25/4da63a95-....jpg",
      "originalName": "Male会议室-前.jpg",
      "fileSize": "221625", "attachId": "2532089"
    }],
    "locationGuideImageFile": {
      "link": "https://qos.quectel.com/tenant-1-quectel/upload/2023-11-10/11d3bd51-....jpg",
      "originalName": "FS-B10-3F（Male).jpg"
    }
  },
  "roomFacility": {
    "facilityList": [{"id": "2", "name": "TV"}, {"id": "6", "name": "飞书"}],
    "zoomAccount": "8139611807",
    "zoomLink": "https://meeting.tencent.com/p/8139611807",
    "teleconferenceType": "腾讯会议",
    "panelInfoList": [{"exhibitionPanelCode": "1280495993",
                       "templateInfo": {"name": "check in app"}}],
    "meetingRoomResourceReserveVo": {"platformType": "LARK", "platformTypeName": "飞书"}
  }
}
```

要点：

- **图片是公网 URL**：`https://qos.quectel.com/...` 直接 GET 就 200，不需要 token（想存本地直接下）。
- **没有"按房间取图"的专用接口**：`/api/meet/room/detail`、`/room/info`、`/room/images`、
  `/app-book/room/detail` 全部 404；图片是会议室对象的字段。**唯一带 roomId 的是
  `GET /api/meet/room/detail/<roomId>`**。
- 图片字段在多处出现，按场景选：
  | 场景 | 字段位置 |
  |---|---|
  | 单间会议室详情 | `room/detail/{id}` → `roomBase.imageFiles` / `roomBase.locationGuideImageFile` |
  | 某区域当天所有会议室 | `room/calendarView` → 每间房 `imageFiles` / `locationGuideImageFile` / `areaLocationGuideImageFile` |
  | 已预订会议的房间 | `appointed/detail/{bookingId}` 或 `app-book/detail/{bookingId}` → `roomBaseInfoVos[].guideMap` + `imageFiles` |
  | 推荐列表 | `recommend/listByUser` 里这几项**恒为 null**（不返回图片），别指望它 |
- `roomFacility` 里三处平台信息可能互相矛盾（`facilityList` 有飞书、`teleconferenceType` 写腾讯会议、
  `meetingRoomResourceReserveVo.platformType` 是 LARK）—— 显示时三个都标出来，不要只取一个下结论。
- `panelInfoList[].exhibitionPanelCode` 是门口屏/签到屏编号，可用于签到场景。

## 我的会议

```
POST /api/meet/booking-user/list
{"meetingBookingTimeStatus":"MY_BOOKING","isFilterEnd":"Y"}
```
`meetingBookingTimeStatus` 枚举（服务端报错信息里给出的全集）：
`DEFAULT_MONTH | WEEK | MY_BOOKING | MY_INVITED | DAY | MONTHLY | ALL_MEETING`
（`MY_BOOKING`=我发起的，`MY_INVITED`=我受邀的，`WEEK`=本周，`MONTHLY`=本月）

返回数组，元素关键字段：
```
id(=bookingId), theme, startTime/endTime(ms 字符串), roomBaseInfoVos[]{roomId,roomName,capacity,facility},
hasRoom, platformName(飞书), state, responseStateName, cancelButton("Y"/"N"), editButton, signInButton
```

其他：
```
GET  /api/meet/booking-user/getNum        → {weekCount,bookingCount,invitedCount,allBookingCount}
GET  /api/meet/booking-user/often         → 常用会议室
POST /api/meet/booking-user/month-list    {"meetingBookingTimeStatus":"MONTHLY","userMonth":"2026-11"}
POST /api/meet/booking-user/listView-user {"pageNumber","pageSize","deptIds","officeAreaIds",
                                           "bookingOperateStart","bookingOperateEnd","bookingStart",
                                           "bookingEnd","orderBy","orderDirection","userKey"}
```

## 会议详情

```
GET /api/meet/appointed/detail/<bookingId>       → 详情（含 recurrenceRule、roomBaseInfoVos、participantInfo、state）
GET /api/meet/app-book/detail/<bookingId>        → App/预订页用的详情（字段基本一致）
GET /api/meet/appointed/participant/<bookingId>  → [{memberUserId,partUserName,participantType,status}]
GET /api/meet/appointed/log/<bookingId>          → 操作日志
```

## 预订

```
POST /api/meet/appointed/create
{
  "id":"", "isSingle":false, "theme":"<主题>", "meetingDate":"2026-11-12",
  "startTime":1794376800000, "endTime":1794377700000,
  "enableMeetingRoomZoom":"Y", "zoomMeetingRoomId":"", "zoomLink":"",
  "chooseZoomMeetingRoomId":"148",              // = 会议室 roomId
  "ruleType":"SINGLE", "isRecurrenceMeeting":"N", "recurrenceRule":null, "recurrenceMeetingCode":"",
  "reminderTimeBeforeStart":15, "explanation":"<备注>", "fileIdList":[],
  "bookingUser":{"userId":"<userId>","userFullName":"<你的姓名>","deptNameList":null},
  "bookingUserId":"<userId>",
  "isPublicConference":"N", "enableParticipantManagement":"N",
  "enableCheckInNoAuthWithExhibitionPanel":"Y", "enableEndInAdvanceNoAuthWithExhibitionPanel":"Y",
  "cancellationReason":"", "participantsNum":1, "participants":["<userId>"], "roomIds":["148"],
  "meetingPassword":"", "muteEnableJoin":"Y", "autoCloudRecord":"N", "useRoomMeetingCode":false,
  "platformType":"LARK",                        // LARK|TEAMS|ZOOM|TENCENT
  "enablePassword":"N", "visibleToParticipants":"N", "roomRequired":"Y",
  "bookingSource":"USER", "hasRoom":"Y", "useOnlineMeeting":"Y", "simplerBooking":"N"
}
→ data{bookingId:"645864", error:["306-FS-B10-3F-Male<你的姓名> 冲突"]}
```
**注意**：`error` 非空时会议其实**已经创建**（实测房间被占用、detail 可查）。
是否成功以 `bookingId` + `GET appointed/detail/<id>` 为准。

其他写接口：
```
POST /api/meet/appointed/bookingModification   # 改会议（同 create 结构，带 id）
POST /api/meet/appointed/bookingReviews        # 审批
POST /api/meet/booking-user/update-status      {"id":"<bookingId>","partState":"ACCEPT"}
GET  /api/meet/app-book/bookingSign/<id>       # 签到
GET  /api/meet/app-book/bookingEnd/<id>        # 提前结束
POST /api/meet/app-book/delayed                # 延时
```

## 取消

```
POST /api/meet/appointed/cancelBooking
{"bookingId":"645864","remark":"测试","flag":false}
→ data:true
```

## 消息（非必须）

```
POST /api/message/v1/stationMsg/qry/findUnreadCount {"groupCode":"103","appId":"1677938311020859392","level":"4","terminalType":"WEB"}
POST /api/message/v1/stationMsg/qry/pageStationMsg  {"searchKey":"","read":null,"groupCode":"103","pageSize":30,"pageNumber":1,"appId":"1677938311020859392","terminalType":"WEB"}
```
`params` 里带 `bookingId / theme / roomName / startTime / zoomLink / type`，可用于「我的会议提醒」。

## 实测结论

| 结论 | 依据 |
|---|---|
| refresh_token 可无限续期（每次轮换） | 2026-11-11 连续两次 refresh 成功 |
| refresh 必须传裸 UUID | 带 `bearer` 前缀被拒 |
| `recommend/listByUser` 忽略 officeAreaIds | 传 `["61","62"]` 仍返回 BG/GL/B10 全量 |
| `room/calendarView` 按 officeAreaIds 过滤 | 同一参数返回 9 / 20 间 |
| `create` 的 `error` 不代表失败 | 返回「冲突」但 bookingId 有效、房间被占 |
| 步长 5 分钟、可订 90 天、07:00–23:59 | `system/config` |
