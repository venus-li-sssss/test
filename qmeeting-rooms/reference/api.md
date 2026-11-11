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

# 密码登录（前端用 RSA 加密 password，脚本不实现）
grant_type=password&username=<邮箱>&password=<RSA密文>&scope=ui&client_id=quectel&client_secret=quectel&auth_type=rsa_area

# 刷新（refresh_token 会轮换，务必覆盖保存）
grant_type=refresh_token&refresh_token=<原始uuid>&scope=ui&client_id=quectel&client_secret=quectel
```
响应：
```json
{"access_token":"uuid","refresh_token":"uuid","expires_in":86399,"scope":"ui","code":"0",
 "data":{"access_token":"...","expires_in":"2026-11-12 09:38:49",
         "userInfo":{"id":"18178","username":"venus.li","workEmail"? :"...","tenantId":"1"}}}
```
> `refresh_token` 传原始 UUID，**不要**带 `bearer` 前缀（带前缀会返回
> `The current user login information has expired`）。
> 前端 Cookie：`quectel_token=bearer<uuid>`、`quectel_refresh_token=<uuid>`。

## 我 / 组织

| 用途 | 请求 |
|---|---|
| 我的信息 | `GET /api/org/employee/getMyInfo?fileId=` → `data.employeeVo{userId,enName,legalName,deptName,workEmail}` |
| 我所在园区 | `GET /api/meet/system/area` → `data{id:"12",name:"FoShan"}` |
| 员工搜索 | `POST /api/org/employee/page` `{"workStatus":"IN_SERVICE","pageNumber":1,"pageSize":20,"name":"<关键词>","key":"<关键词>"}` → `data.records[]{userId,enName,legalName,workEmail,deptName}` |
| 按 userId 查员工 | `POST /api/org/employee/selectEmpBaseInfoByUserIds` `["18178"]` |

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
→ data[ room{... , using:[{start:"14:00",end:"16:00",bookingName:"Jorf Li",bookingTheme,state:"BOOKED"}]} ]
```
`using` 为空 = 全天空闲。**只有这个接口会按 officeAreaIds 过滤**（FoShan 3F 返回 9 间、FoShan 全园区 20 间）。

### 3) 我的空闲/占用（按人）

```
POST /api/meet/recommend/checkAvailability  {"userIds":["18178"],"bookingId":"","dateStr":"2026-11-12"}
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
  "bookingUser":{"userId":"18178","userFullName":"Venus Li 黎卓明","deptNameList":null},
  "bookingUserId":"18178",
  "isPublicConference":"N", "enableParticipantManagement":"N",
  "enableCheckInNoAuthWithExhibitionPanel":"Y", "enableEndInAdvanceNoAuthWithExhibitionPanel":"Y",
  "cancellationReason":"", "participantsNum":1, "participants":["18178"], "roomIds":["148"],
  "meetingPassword":"", "muteEnableJoin":"Y", "autoCloudRecord":"N", "useRoomMeetingCode":false,
  "platformType":"LARK",                        // LARK|TEAMS|ZOOM|TENCENT
  "enablePassword":"N", "visibleToParticipants":"N", "roomRequired":"Y",
  "bookingSource":"USER", "hasRoom":"Y", "useOnlineMeeting":"Y", "simplerBooking":"N"
}
→ data{bookingId:"645864", error:["306-FS-B10-3F-Male黎卓明 冲突"]}
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
