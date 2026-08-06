# 九号 IoT OTA 平台 — 接口参考（来自 HAR 抓包）

> 所有接口前缀：`https://iot-test.ninebot.com/service/iot-ota-console-api`
> 公共请求头：`content-type: application/json;charset=UTF-8`、`accept: application/json, text/plain, */*`、`origin: https://iot-test.ninebot.com`、`referer: https://iot-test.ninebot.com/`
> 认证 Cookie（会过期，需刷新）：`SESSION`、`titan-test-tgc`、`auth-test`
> 自定义权限头：`url-request-code`（新增类=`firmware:add`，查询列表=`firmwareList:info`）
> 成功：`{"resultCode":"1000",...}`；失败示例：`{"resultCode":"4025","resultDesc":"固件版本(032E)与文件版本(null)不一致","data":null}`

---

## 1. 查询固件包列表

- 方法/路径：`GET /hardware/firmware/firmware-list`
- url-request-code：`firmwareList:info`
- Query 参数：

| 参数 | 说明 | 示例 |
|---|---|---|
| page | 页码 | 1 |
| num | 每页条数 | 10 |
| firmware_level | 固件级别（可空） | 1 |
| vehicle_model_code | 车型码（可空） | K21101 |
| firmware_type | 零部件类型 | ECU |
| firmware_version | 版本号（可空） | 032E |

- 完整 URL 示例：
```
https://iot-test.ninebot.com/service/iot-ota-console-api/hardware/firmware/firmware-list?page=1&num=10&firmware_level=&vehicle_model_code=&firmware_type=&firmware_version=
```

---

## 2. 新增固件包 — 最终提交 add-firmware-new

- 方法/路径：`POST /hardware/firmware/add-firmware-new`
- url-request-code：`firmware:add`
- 请求体（示例，来自 HAR）：
```json
{
  "productVehicleModelStringList": [["kBwCVBq4","K21101"]],
  "part_code": ["Z0DK"],
  "firmware_type": "ECU",
  "firmware_version": "032E",
  "firmware_level": 1,
  "file_id": "114500",
  "md5_verify_code": "e1c6de0e6449d5687e7906d007881808",
  "descDraft": "移远内部固件，请勿升级！！！",
  "big_file_url": "",
  "status": 1,
  "description": "移远内部固件，请勿升级！！！",
  "description_en": "Improve firmware compatibility and stability",
  "relate_version": "",
  "operate_user": "dehao.zhang",
  "encrypt_1": 2,
  "is_milestone": 0,
  "open_diff": 0,
  "firmware_diff_data": [],
  "ui_extends": [],
  "skinName": "",
  "file_use_type": 0,
  "estimate_time": 60
}
```
- 关键字段：
  - `productVehicleModelStringList`：`[[产品码, 车型码]]`
  - `part_code`：零部件编码数组
  - `firmware_version`：**必须大写，且等于包版本号去掉点**（见 SKILL.md 命名规则）
  - `file_id`：来自 s3-upload-by-path 返回
  - `md5_verify_code`：文件 MD5（32 位小写）
- 响应（成功）：`{"resultCode":"1000","resultDesc":"成功","data":...}`
- 响应（版本不一致）：`{"resultCode":"4025","resultDesc":"固件版本(032E)与文件版本(null)不一致","data":null}`

---

## 3. 上传固件文件 s3-upload-by-path（S3 注册 + MD5）

- 方法/路径：`POST /hardware/firmware/s3-upload-by-path`
- url-request-code：`firmware:add`
- 请求体（示例）：
```json
{
  "region": "cn-northwest-1",
  "bucketName": "file-upload-test",
  "objectKey": "bigfile/2026-07-22/e3944b530717471ba26ce1b1c4ba796f/032e.bin",
  "url": null,
  "name": "032e.bin",
  "size": 260800,
  "md5": "e1c6de0e6449d5687e7906d007881808",
  "file_use_type": 0,
  "productVehicleModelStringList": [["kBwCVBq4","K21101"]]
}
```
- 响应（成功）：
```json
{
  "resultCode": "1000",
  "resultDesc": "成功",
  "data": {
    "size": 260800,
    "file_id": "114500",
    "original_name": "032e.bin",
    "url": "032e.bin",
    "md5": "e1c6de0e6449d5687e7906d007881808"
  }
}
```
- `data.file_id` 与 `data.md5` 用于下一步 `add-firmware-new`。

> ⚠️ **`s3-upload-by-path` 只注册元数据，不会上传二进制！** 真实上传需先走下面的 `file-upload` 分片流程把字节写到 S3，否则 `add-firmware-new` 读取文件内嵌版本会得到 `null`，报 `4025 固件版本(X)与文件版本(null)不一致`。

### 3.1 二进制实际上传流程（file-upload，必须先用）

1. **init**：`POST /service/file-upload/upload/init`
   请求体：`{"md5":"<md5>","name":"<Vx.y.z.W.bin>","size":<bytes>,"totalBlock":1,"clientKey":"iot-console-api"}`
   响应 data：`fileId` / `uploadId` / `bucketName` / `objectKey` / `pass`（`pass=true` 表示同 md5 文件已存在，可跳过第 2 步直接 complete）。
2. **上传分片**（仅当 `pass=false`）：
   - `GET  https://file-upload-test.ninebot.com/upload/part?bucketName=&objectKey=&uploadId=&fileId=&chunkNumber=1&totalChunks=1&size=5242880&md5=`（预检）
   - `POST https://file-upload-test.ninebot.com/upload/part`（multipart/form-data，字段：`bucketName,objectKey,uploadId,fileId,chunkNumber=1,totalChunks=1,size=5242880,md5`，最后 `file` 字段放二进制 `application/octet-stream`）
3. **complete**：`POST /service/file-upload/upload/complete` 请求体 `{"fileId":<fileId>}` → 返回最终 `objectKey/size/md5`。
4. 再调上面的 `s3-upload-by-path` 拿到 `file_id`。

### 3.2 文件名决定固件版本（关键坑）

**平台从【文件名】提取固件版本号**，文件名必须是规范命名 `V<x1>.<x2>.<x3>.<x4>.bin`：
- `032F` → 文件名 `V0.3.2.F.bin` ✅（提取到 `032F`，与 `firmware_version` 一致 → 新增成功）
- 裸名 `032f.bin` / `032e.bin` ❌（提取为 `null` → `4025`）

对应 helper 已修复：`add` 命令自动用 `package_name + ".bin"`（如 `V0.3.2.F.bin`）作为上传文件名。

---


## 4. 权限校验 permission-new

- 方法/路径：`POST /hardware/firmware/permission-new`
- url-request-code：`firmware:add`
- 请求体：
```json
{
  "productVehicleModelStringList": [["kBwCVBq4","K21101"]],
  "firmware_type": "ECU",
  "part_code": ["Z0DK"]
}
```

---

## 5. 关联版本 firmware-relate-version-new

- 方法/路径：`POST /hardware/firmware/firmware-relate-version-new`
- url-request-code：`firmware:add`
- 请求体：
```json
{
  "productKeys": [],
  "vehicle_model_codes": [],
  "productVehicleModelStringList": [["kBwCVBq4","K21101"]],
  "firmware_type": "ECU",
  "firmware_version": "032E",
  "firmware_level": 1,
  "pageSize": 10,
  "pageNumber": 1
}
```

---

## 6. 获取必填属性 require-attribute

- 方法/路径：`POST /hardware/firmware/require-attribute`
- url-request-code：`firmware:add`
- 请求体：
```json
{
  "productVehicleModelList": [["kBwCVBq4","K21101"]],
  "partType": "ECU"
}
```

---

## 7. 获取零部件类型 get-part-type-list

- 方法/路径：`POST /api/iot/get-part-type-list`
- url-request-code：`firmware:add`
- 请求体：`{}`
- 响应 data 为数组，每项含 `part_type` 与 `part_name`，例如：
  `XDP, WLOCK, WIFI, WEIGHT, VCU, VBOX, USB-S, UPC, TPS, TFT, TCU, T-BOX, SW, SPL, MCU, LRA, LIGHT, LIDAR, LCD-RES, ... , ECU, BMS, ...`

---

## 8. 获取车型列表 products-vehicle-models

- 方法/路径：`GET /basic/products-vehicle-models?partType=ECU`
- url-request-code：`firmware:add`
- 响应 data 为树形：每项有 `label`/`value`（产品码，如 `kBwCVBq4`），其 `children` 有 `label`/`value`（车型码，如 `K21101`）。
- `productVehicleModelStringList` 即取 `[[产品码, 车型码]]`。

---

## 9. 按 IMEI/SN 查询设备信息 device/list（iot-console-api）

> 与固件接口不同，此接口走 **`/service/iot-console-api`** 前缀，**不需要 `url-request-code` 头**，仅需 SSO Cookie（SESSION / titan-test-tgc / auth-test）+ SOCKS5 内网代理。参考脚本：`D:\work\QDM559\脚本\升级脚本\QDM551平台IOT升级压力_V19.py` 的 `device_info()`。

- 方法/路径：`POST /service/iot-console-api/device/list`
- 请求体（JSON）：
```json
{
  "pageNumber": 1, "pageSize": 10,
  "snVin": "<IMEI或SN>",
  "activeStatus": "", "onlineStatus": "",
  "sort": "desc", "productIds": [], "modelCodes": []
}
```
- 成功响应：`{"resultCode":"1000","data":{"total":1,"list":[ {...} ]}}`；`list[0]` 含 `sn / deviceName(IMEI) / vin / productKey / productName / tboxPn / iccid / vehicleModelCode / vehicleModelCnName / onlineStatus / activeStatus / totalMileage / carNo / lastOnlineTime / remark` 等字段。
- 关联接口（同前缀，按 `sn` 查各零部件版本）：
  - `POST /service/iot-ota-console-api/api/iot/get-parts-version` 请求体 `{"sn":"<sn>"}` → `data[]` 每项含 `part_type` 与 `part_firmware_version`。
  - `GET  /service/iot-console-api/device/dataFlow?deviceName=<imei>&productKey=<pk>&startTime=&endTime=&dataFlowCode=&pageNum=1&pageSize=100`（设备数据流）。
  - `GET  /service/iot-console-api/device/connectLog?productKey=<pk>&deviceName=<imei>&startTime=&endTime=`（连接日志）。

---

## 10. FOTA 升级 / 回滚 / 状态（iot-ota-console-api）

> 参考脚本：`D:/work/QDM559/脚本/升级脚本/QDM551平台IOT升级压力_V19.py` 的 `auto_group_send()`。
> 这些接口走 **`/service/iot-ota-console-api`** 前缀，**不需要 `url-request-code` 头**，仅需 SSO Cookie + SOCKS5 代理。
> ⚠️ 平台**没有专门的"回滚"接口**：回滚 = 再下发一次更低版本的升级任务（`auto-group-send`）。

### 10.1 下发升级/回滚任务 auto-group-send
- 方法/路径：`POST /service/iot-ota-console-api/api/iot/auto-group-send`
- 请求体（JSON 字符串）：
```json
{
  "sn": "<设备SN>",
  "product_key": "<产品码,如 zGjMddvd>",
  "partTypes": [
    {"partType": "ECU", "otaTargetVersion": "032E", "otaCurrentVersion": "022f", "buttonDisplay": false}
  ],
  "vehicle_model_code": "K15804",
  "encrypt_2": 2,
  "times": "1",
  "intervalTime": 15,
  "verification": false
}
```
- 关键：`otaCurrentVersion` = **设备真实上报版本**（来自 get-parts-version，如 `022f`）；`otaTargetVersion` = **包标签版本**（如 `032E`）。`partTypes` 是**对象数组**（不是字符串数组）。
- 响应：`{"resultCode":"1000","resultDesc":"成功",...}` 表示任务已创建。

### 10.2 查询升级历史 get-upgrade-history
- 方法/路径：`POST /service/iot-ota-console-api/api/iot/get-upgrade-history`
- 请求体：`{"page":1,"size":20,"product_key":"<pk>","sn":"<sn>","part_type":"","upgrade_status":"null","ota_target_version":""}`
- 响应 `data.list[]`：`part_type / ota_target_version / ota_current_version / upgrade_status / status_reason / progress / ota_task_result_id`。
  - `upgrade_status`：`0`=处理中/初始，`1`=成功，`2`=失败。
- ⚠️ 该接口偶发 `resultCode:1001 服务器异常`（平台瞬态），helper 轮询在连续失败 3 次后转"设备版本回退校验"，不会卡死。

### 10.3 设备当前版本 get-parts-version
- 方法/路径：`POST /service/iot-ota-console-api/api/iot/get-parts-version`
- 请求体：`{"sn":"<sn>"}`
- 响应 `data[]`：`part_type / part_firmware_version(真实上报版本) / part_remark / part_name / pn(零部件PN) / part_in_upgrade(是否升级中) / active_status / online_status`。
- 用途：① 取 `otaCurrentVersion`；② 升级后二次校验；③ `pn` 前缀用于自动选 part_code。

### 10.4 强制关闭任务 fore-close-device-ota-task
- 方法/路径：`POST /service/iot-ota-console-api/api/iot/fore-close-device-ota-task`
- 请求体：`{"user_name":"<账号>","sn":"<sn>","product_key":"<pk>","cmdCode":"c:ota","qos":0,"timeout":0,"part_type":"ECU","part_firmware_version":"<版本>","vehicle_model_code":"<vmc>","actual_ota_type":2,"verification":false}`
- 用途：取消一个**尚未完成/卡住**的升级任务（不是回滚）。

### 10.5 必填属性/可用 part_code require-attribute（新增固件包用）
- 方法/路径：`POST /service/iot-ota-console-api/hardware/firmware/require-attribute`
- 请求体：`{"productVehicleModelList":[["<产品码>","<车型码>"]],"partType":"ECU"}`
- 响应 `data.partCodes`：`[{"code":"4G"},{"code":"WV"},{"code":"XV"}]`（该车型该零部件的可用 part_code 候选）。
- 用法：用设备 ECU `pn` 前缀从这些候选里选最匹配者（如 N3 的 ECU pn 前缀 `WV` → 选 `WV`）。helper 的 `resolve_part_code` 已实现此逻辑。
