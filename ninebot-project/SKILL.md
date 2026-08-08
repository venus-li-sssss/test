---
name: 九号项目
description: 操作九号(Ninebot) 的一体化 skill，覆盖两条线：(1) IoT OTA 固件平台（iot-test.ninebot.com）的固件包查询/新增上传、设备查询、FOTA 升级/回滚/状态；(2) 已连接 Android 手机上九号出行 APP 的 UI 控制（点击闪灯鸣笛/鸣笛/闪灯、查 APP 状态、截图验证），基于 uiautomator2 相对定位，一条指令即可完成。触发词：九号、Ninebot、iot-test、固件、新增固件、查询固件、上传固件、OTA、升级包、FOTA、升级、回滚、查看平台下发指令、平台下发、设备指令、链路核验、指令记录、设备控制、设备APP、控制APP、手机APP、闪灯鸣笛、鸣笛、闪灯、点击、UI自动化、uiautomator2、设备端、假超时、APP超时、重试、retry、组合指令、指令组合、超时重试、自动重试、滑动屏幕、swipe、上滑、下滑、设备信息、查看设备信息、查询版本、设备版本、固件版本、页面导航、去页面、导航到、页面树、回到首页、返回上一页、开机、关机、滑动开机、点击关机、通电、车辆电源、电源按钮。
version: 1.8.0
agent_created: true
---

# 九号项目 — Ninebot IoT OTA 固件平台操作 Skill

本 skill 封装了九号 IoT OTA 控制台（测试环境 `iot-test.ninebot.com`）的平台接口与操作规范，
**一体化**覆盖：设备查询、固件包新增（含真实二进制上传）、FOTA 升级/回滚/状态。

源信息：
- 平台现有接口/升级流程参考脚本：`D:\work\QDM559\脚本\升级脚本\QDM551平台IOT升级压力_V19.py`
- 新增接口（查询/新增固件包）来自 HAR 抓包：`C:\Users\venus.li\Downloads\iot-test.ninebot.com.txt`
- 内网连接方式（两个 bat，都在 `D:\work\QDM559\`，顺序不能反）：
  - `D:\work\QDM559\脚本连接内网.bat` —— 仅设置 `HTTP(S)_PROXY` 环境变量 + `pip install requests[socks]`，**不真正建隧道**（里面 `python your_script.py` 是占位）；跑它后还要在**同一窗口**带代理环境变量跑脚本，或依赖下面那条真正建隧道。
  - `D:\work\QDM559\连接九号内网.bat` —— **真正建立 SOCKS5 隧道**：`ssh -N -D 127.0.0.1:1080 ninebot\jhdk@10.99.82.46`。运行后**在中止窗口手动输入密码**，认证成功才会监听 `127.0.0.1:1080`。平台访问（含 `ninebot_ota.py` 的 `PROXIES`）全都走这个隧道。

配套文件：
- `scripts/ninebot_ota.py` —— 平台 helper（查询/新增固件、真实上传、设备解析、FOTA 升级/回滚/状态、一站式 `fota`）。
- `scripts/device_control.py` —— 设备端 APP UI 控制 helper（uiautomator2，相对定位）：`status`/`launch`/`tap`/`tap_xy`/`swipe`/`screenshot`/`dump`/`texts`/`wait`/`retry`/`get_device_info`/`get_battery_info`/`ble_upgrade_app`/`go_to_page`/`setting`/`toggle_setting`/`run`。**控制手机上九号 APP（如点击闪灯鸣笛、滑动屏幕、查设备版本信息、查电池数据、APP侧蓝牙升级）直接用它，不要走 dump+解析+input tap 的老流程。**
- `references/api_reference.md` —— 各接口完整请求/响应示例与字段说明。

> 流程总览：平台侧 OTA 操作走 §1~§7（`ninebot_ota.py`）；**手机端 APP 点击/查看类操作走 §8（`device_control.py`）**。两者是不同场景，按需选用。

---

## 0. 总原则：做平台操作前必须先连内网

任何访问 `iot-test.ninebot.com` 的接口调用，都必须先建立内网 SOCKS5 代理隧道（`127.0.0.1:1080`）。
helper 里已固定 `PROXIES = socks5h://127.0.0.1:1080`；若请求超时/连不通，先确认本机隧道已建立。

**建立隧道的唯一可靠方式**：运行 `D:\work\QDM559\连接九号内网.bat`（内容 = `ssh -N -D 127.0.0.1:1080 ninebot\jhdk@10.99.82.46`）。注意：
1. 它启动后**不会自动完成**——弹出的窗口会停在 `password:` 提示，**必须手动输入 SSH 密码**后隧道才开始监听 1080。
2. 判定隧道就绪：**`netstat -ano | findstr :1080` 出现 `LISTENING`**（不是 `SYN_SENT`）才算通；否则 `ninebot_ota.py` 会 `ConnectionRefusedError: 127.0.0.1:1080`。
3. 若 `ssh.exe` 进程在但 1080 无 `LISTENING` → 多半是密码还没输 / 认证没过，回去把密码补上即可，不用重跑 bat。
4. ⚠️ `D:\work\QDM559\脚本连接内网.bat` **不等于**建隧道：它只 `set` 代理环境变量 + `pip install`，末尾 `python your_script.py` 是占位。**真正让 1080 监听的是「连接九号内网.bat」那条 SSH 动态转发**，两条都跑、且 SSH 密码已输入，平台查询才通。

认证方式：平台是 **Spring OAuth2 + titan SSO**，最终用 **Cookie（SESSION / titan-test-tgc / auth-test）+ 自定义请求头 `url-request-code`** 调接口。

**已内置账号密码自动登录，不用再手动复制 Cookie**（参考 `D:\work\QDM559\脚本\升级脚本\QDM551平台IOT升级压力_V21.py` 里的 `login()`）：
- 账号密码写在 `scripts/ninebot_ota.py` 顶部 `ACCOUNT`（`dehao.zhang@ninebot.com`，登录用邮箱格式）/ `PASSWORD`。
- 登录流程：`GET /service/oauth2/authorization/iot`（拿前置 SESSION）→ `POST https://auth-test.ninebot.com/login`（提交 `username/password/isRemember`，**须跟随重定向**完成 OAuth code 交换，否则 SESSION 不完整会仍报 1010）→ 收割三个 Cookie。
- **自动鉴权**：`_session()` 每次调用先跑 `ensure_authenticated()`——缓存 30 分钟内直接放行；否则用轻量接口探测，失效就自动 `login()`。登录成功后把 Cookie **持久化到 `scripts/ninebot_cookies.json`**，跨进程复用，约 30 分钟过期后再自动重登。
- 手动刷新也行：`python ninebot_ota.py login`（只登录、刷新并持久化 Cookie，不查数据）。
- ⚠️ 改账号/密码：只改 `ACCOUNT`/`PASSWORD` 两行即可，所有命令自动重新登录；别去改顶部 `COOKIES` 硬编码初值（那只是兜底默认值，会被登录结果覆盖）。

**判据**：平台接口返回 `resultCode=1010` / `resultDesc='not authenticated'` 即会话失效——正常应自动重登；若仍失败，先确认：① 内网隧道是否在 `LISTENING`（隧道问题会直接 `ConnectionRefused 127.0.0.1:1080`，不会走到平台返回码）；② `ACCOUNT`/`PASSWORD` 是否过期（密码变了就更新 `PASSWORD`）。

---

## 1. 平台与环境

- 域名：`https://iot-test.ninebot.com`
- OTA 接口前缀：`/service/iot-ota-console-api`（`BASE`）
- Console 接口前缀：`/service/iot-console-api`（`CONSOLE_BASE`，设备查询在此）
- `url-request-code` 取值：新增/编辑/上传固件 → `firmware:add`；查询固件列表 → `firmwareList:info`。
- 成功响应统一格式：`{"resultCode":"1000","resultDesc":"成功","data":...}`。

---

## 2. ⚠️ 版本号与命名规则（新增固件包最关键）

1. 包名规范：`V<X1>.<X2>.<X3>.<X4>.bin`，如 `032E` → `V0.3.2.E.bin`。
2. **平台按【上传文件名】提取固件版本**：`V0.3.2.E.bin` → `032E`。裸名 `032e.bin` 会被提取为 `null` → `add-firmware-new` 报 `4025 固件版本(X)与文件版本(null)不一致`。
   → helper 的 `add` 会自动用 `V<x1>.<x2>.<x3>.<x4>.bin` 作为上传文件名，无需手改。
3. **MD5 必填**：32 位小写 MD5 填入 `md5_verify_code`（helper 自动算）。

> 🔴 重要坑：固件**包标签版本**（如 `032E`，来自文件名）≠ 设备**真实上报版本**（如本机 N3 刷完 `032E` 后设备报 `023e`）。
> `auto-group-send` 的 `otaCurrentVersion` 必须传**设备真实上报版本**（来自 `get-parts-version`），`otaTargetVersion` 传**包标签版本**。
> 校验时**不要**用"设备版本==包标签"做强相等；应以【平台任务状态=成功】为主，设备版本是否"发生变化"为辅助判据。

---

## 3. ⚠️ 真实二进制上传流程（新增固件包最容易踩的坑）

`s3-upload-by-path` **只注册元数据，不会真正上传二进制**。若只调它，`add-firmware-new` 读不到文件版本 → `4025`。
正确顺序（helper 的 `s3_upload` 已实现）：
1. `file-upload/upload/init` → 拿 `fileId`/`objectKey`
2. `file-upload-test.ninebot.com/upload/part`（GET 预检 + POST 二进制分片，multipart）
3. `file-upload/upload/complete`
4. `hardware/firmware/s3-upload-by-path` → 拿 `file_id`

---

## 4. 接口总览

| 操作 | 方法 | 路径（前缀见 §1） | url-request-code |
|---|---|---|---|
| 查询设备+零部件版本 | POST | `/service/iot-console-api/device/list` + `/api/iot/get-parts-version` | — |
| 必填属性/可用 part_code | POST | `/hardware/firmware/require-attribute` | `firmware:add` |
| 车型列表 | GET | `/basic/products-vehicle-models?partType=ECU` | `firmware:add` |
| 固件包列表 | GET | `/hardware/firmware/firmware-list` | `firmwareList:info` |
| 真实上传 init/part/complete | POST/GET | `/service/file-upload/upload/*` + `file-upload-test.ninebot.com/upload/part` | `firmware:add` |
| S3 注册 | POST | `/hardware/firmware/s3-upload-by-path` | `firmware:add` |
| 权限/关联/提交 | POST | `/hardware/firmware/permission-new`、`firmware-relate-version-new`、`add-firmware-new` | `firmware:add` |
| **下发升级/回滚任务** | POST | `/api/iot/auto-group-send` | — |
| **下发蓝牙升级指令** | POST | `/api/iot/send`（`cmdCode=c:ota` `actual_ota_type=2`） | `ble-upgrade` |
| 升级历史 | POST | `/api/iot/get-upgrade-history` | — |
| 设备当前版本 | POST | `/api/iot/get-parts-version` | — |
| 强制关闭任务 | POST | `/api/iot/fore-close-device-ota-task` | — |

> `get-upgrade-history` 偶发返回 `resultCode:1001 服务器异常`，属平台瞬态问题；helper 的轮询会在连续失败 3 次后转"设备版本回退校验"，不会卡死。

---

## 5. 操作流程（推荐：尽量走 `fota` 一站式命令）

### 5.0 先解析设备（避免加错车型——这是最大的坑）
```bash
python scripts/ninebot_ota.py query-device 869004070113552
# 输出 productKey / vehicleModelCode / 各零部件当前版本与 pn / 推荐 part_code
```

### 5.1 新增固件包（两种用法）
```bash
# A) 自动解析车型+零部件（推荐，绝不会加错车型）：
python scripts/ninebot_ota.py add --imei 869004070113552 \
  --file 032e.bin --version 032E

# B) 显式指定：
python scripts/ninebot_ota.py add --file 032e.bin --version 032E \
  --model zGjMddvd,K15804 --part-code WV --type ECU
```
`--imei` 模式下，helper 会：解析车型 → `require-attribute` 拿候选 part_code → 用设备 ECU `pn` 前缀自动选中（如 N3 选 `WV`）。

### 5.2 升级 / 回滚 / 状态
```bash
python scripts/ninebot_ota.py upgrade  869004070113552 032E        # 升级到 032E（自动读当前版本作 otaCurrentVersion）
python scripts/ninebot_ota.py rollback  869004070113552 022f        # 回滚到 022f
python scripts/ninebot_ota.py status   869004070113552              # 当前版本+最近历史
```

### 5.2.1 🔵 蓝牙升级（平台下发 `c:ota` 指令 + APP 经 BLE 刷写）
普通 `upgrade`/`rollback` 走的是**静默 FOTA**（`auto-group-send`，平台经蜂窝/T-BOX 直接推给车机）。
**蓝牙升级是另一条接口**：平台先下发一条 `c:ota` 指令（`/api/iot/send`，`actual_ota_type=2`），之后**必须靠手机 APP 经蓝牙把固件真正传下去**（APP 侧「开始升级」）。两端职责不同：

```bash
# 1) 平台下发蓝牙升级指令（脚本会自动按 actual_ota_type=2 在 get-upgrade-history 核验）：
python scripts/ninebot_ota.py ble-upgrade 869004070113552 032E   # 目标版本 032E，部件默认 ECU

# 2) 手机 APP 经 BLE 开始刷写（device_control.py 那条线）：
C:/Users/venus.li/.workbuddy/binaries/python/versions/3.13.12/python.exe scripts/device_control.py ble_upgrade_app --wait-task 30
#    -> 自动：设备信息页→检查固件更新→固件升级页(NBReactActivity)
#    -> 点「下一步」→「确认升级」→「开始升级」经 BLE 把固件刷入 ECU
#    ⚠️ 前置：平台已 ble-upgrade 下发 + 车辆经蓝牙连上手机（否则升级页只显示"已经是最新固件"，无任务可点）
# 3) 手工查 BLE 任务进度：OTA管理 → 单元升级 → 升级详情；或接口 get-upgrade-history 筛 actual_ota_type=2
```

#### ⛔ BLE 升级核验的常见误区（务必区分两条指令日志通道）
- ❌ **不要用 `commands --watch` 核验 BLE**：它查的是「平台→车机(蜂窝)指令日志」(`/service/iot-console-api/device/command`)，
  BLE 的 `c:ota` 走「平台→手机 APP」蓝牙通道，**不会落进那条日志**，永远查不到。
- ✅ **核验路径是 `get-upgrade-history`**（OTA管理→单元升级→升级详情 背后的接口）：
  - 关键字段 `actual_ota_type`：**1** = 远程/静默 FOTA，**2** = 蓝牙升级
  - 关键字段 `upgrade_status`：**-1** 待升级(等APP开始)｜**0** 升级中｜**1** 升级成功｜**2** 升级失败
  - BLE 任务刚下发时 get-upgrade-history 有 ~1 分钟异步延迟才出现；`status=-1` 即"已下发成功、等 APP 经蓝牙开始"
- ✅ `ble-upgrade` 命令内部已自动按 (actual_ota_type=2 + part_type + 最近创建) 轮询核验并打印结果

> 与静默 FOTA 关键差异：① 端点不同（`/api/iot/send` vs `auto-group-send`）；② 单部件、带 `cmdCode:c:ota`+`actual_ota_type:2`；
> ③ 平台只下发指令，**固件传输靠 APP 蓝牙**，故 BLE 任务初始 `status=-1`(待升级)，直到 APP 经蓝牙开始后才流转到 0/1/2。
> 参考实现：`D:\work\QDM559\脚本\升级脚本\QDM551平台IOT升级压力_V21.py` 的 `fota_bluetooth_download_api` / `fota_update(ota_type="app")`。

### 5.3 🚀 一站式 `fota`（把"加包+升级+回滚"一次跑完，最少对话轮次）
```bash
python scripts/ninebot_ota.py fota 869004070113552 \
  --files 032e.bin,032f.bin \
  --versions 032E,032F \
  --rollback-to 022f
```
该命令内部依次：① 解析设备车型/零部件 → ② 注册缺失的包（已存在则跳过） → ③ 升级链路 `当前→032E→032F` → ④ 回滚到 `022f` → ⑤ 每步轮询+校验并打印结果。**一次调用 = 之前 5+ 轮对话 + 多个临时脚本**。

### 5.4 设备实时数据查询（v1.7.1 新增，来自 iot-console-api）
基于 `resolve_device` 解析的 `deviceId/deviceName/productId/productKey` 自动调用平台实时/历史数据接口，无需关心参数拼装。接口清单从浏览器 HAR 导出（`/service/iot-console-api/realTimeData/*`、`historyData/*`、`ai/vehicle/*`）提取：
```bash
# 一键聚合：整车实时 + 车辆状态 + 报警 + 故障告警 + 事件 + 电池 + 电池日志 + 字段 + 天气 + 最近24h在线历史
python scripts/ninebot_ota.py device-data <SN或IMEI>

# 各数据独立查询（返回单接口原始 data 段）：
python scripts/ninebot_ota.py device-alarm  <SN>   # 报警列表（faultCode/level/remark/经纬度）
python scripts/ninebot_ota.py device-warning <SN>   # 故障/告警（ai/vehicle/warning，分页）
python scripts/ninebot_ota.py device-event  <SN>   # 事件列表（开关机/骑行等 eventCode/eventValue）
python scripts/ninebot_ota.py device-bms    <SN>   # 电池(BMS)实时数据
python scripts/ninebot_ota.py device-bmslog <SN>   # 电池日志
python scripts/ninebot_ota.py device-status <SN>   # 车辆状态（soc/速度/电压/电流/档位/在线）
python scripts/ninebot_ota.py device-dataflow <SN>  # 数据流（默认 SOC/车速/总电流/总电压，--fields '{"k":"v"}' 覆盖）
python scripts/ninebot_ota.py device-online-history <SN>  # 在线状态历史（--hours N，默认24h）
python scripts/ninebot_ota.py download-tasks          # 固件下载任务列表（与设备无关）
```
> 注意：`device-warning` 返回 `total:0` 表示当前无故障告警（正常现象）；`alarm`/`event` 才是设备实际产生的报警与事件记录。

---

## 6. 安全与注意

- Cookie 是会话凭据，不要外泄；过期后从浏览器刷新 `COOKIES`。
- 升级/回滚是真实 OTA 任务，会写设备；下发前确认 IMEI/版本无误。
- 升级前确认设备**不在升级中**（`get-parts-version` 的 `part_in_upgrade` 应为 0），否则新任务可能冲突。
- 固件包“标签版本”与设备“真实版本”可能不一致（见 §2），不要以标签相等作为唯一成功判据。
- `get-upgrade-history` 偶发“服务器异常”，属正常瞬态，helper 已做容错。

---

## 7. 本次提速/避坑总结（给后续会话）

之前踩过的弯路，现已固化进 skill，避免重蹈：
1. **加错车型**：之前把 032E/032F 加到了 Xaber(K21101) 而非设备实际的 N3(K15804)，导致升级报错。→ 现在 `add --imei` 自动按设备解析车型/零部件，杜绝手填错误。
2. **二进制未真上传** → `4025`。→ `s3_upload` 已含 init/part/complete 完整流程。
3. **文件名决定版本**：裸名 `032e.bin` → null。→ `add` 自动用 `V0.3.2.E.bin` 命名。
4. **没有 FOTA 命令**：之前现写 `fota_upgrade.py` 反复调试（JSON 解析错、partTypes 格式错）。→ 现已内置 `upgrade`/`rollback`/`status`/`fota`。
5. **校验逻辑错**：用"设备版本==包标签"判等，而两者本就不同（032E→023e）。→ 改为"平台任务状态为主 + 设备版本变化为辅"。
6. **历史接口瞬态报错**卡死轮询。→ 连续失败转版本回退校验。
7. **散落多个临时脚本 + 多轮对话**。→ 全部收敛进一个 `ninebot_ota.py`，`fota` 一条命令完成全链路。

---

## 8. 设备端 APP UI 控制（手机上九号出行 App 自动化）

当用户要「控制设备 APP / 点击某个按钮（如闪灯鸣笛、鸣笛、闪灯）/ 查看 APP 是否已启动 / 截屏看效果 / 列出界面文字」时，**走本机已连接的 Android 设备**，用 `scripts/device_control.py`（uiautomator2，相对定位）。

⚠️ **优先用 `device_control.py` 的 helper 命令（一条指令完成、坐标由框架动态算）。只有当某功能没有现成 helper 能一条指令完成时，才走兜底方案 `adb shell uiautomator dump` → 解析 XML → 算中心 → `input tap`（详见 §8.13）。** helper 已覆盖的功能（tap/swipe/screenshot/go_to_page/get_*/retry/run/组合指令）一律走 helper，不要手敲 adb 重走老路——除非真的没有对应 helper。

### 8.1 环境（一次性，已配好可跳过）
- Python 用隔离 venv：`C:\Users\venus.li\.workbuddy\binaries\python\envs\default\Scripts\python.exe`
- 已装 `uiautomator2`；已对设备执行 `python -m uiautomator2 init`（atx-agent 跑在 9008 端口）
- 已连设备序列号：`A2TBVB2C27014459`（已写死在脚本 `DEFAULT_SERIAL`）
- 九号出行 APP 包名：`com.ninebot.segway`

若报 `uiautomator2 未安装` 或连接失败，先重跑上面两条安装/初始化命令。

### 8.2 直接发指令（最少步骤）

```bash
PY=C:/Users/venus.li/.workbuddy/binaries/python/envs/default/Scripts/python.exe
SK=C:/Users/venus.li/.workbuddy/skills/ninebot-project/scripts/device_control.py

$PY $SK status                              # 设备是否连上 + 当前前台 APP
$PY $SK tap --text "闪灯鸣笛"               # 相对定位点击（自动上溯可点击祖先）
$PY $SK screenshot --out shot.png          # 截图看效果
$PY $SK launch --package com.ninebot.segway  # APP 已运行则不重启，直接调前台
$PY $SK texts                               # 列出当前界面所有文字（定位前先探一下）
$PY $SK swipe --direction up --distance 0.8 --times 3   # 向上滑动3次（页面向下滚）
$PY $SK get_device_info                     # 一键进「设备信息」页并提取型号/车架号/各固件版本号
$PY $SK get_battery_info                    # 一键进「电池信息」页并提取 主电池/电压/温度/应急电池 等数据
$PY $SK go_to_page --page battery           # 导航到指定设备页(见 §8.8 页面树)：home/more_functions/device_info/battery/safety/throttle/lab/fota_page
$PY $SK ble_upgrade_app --wait-task 30      # APP侧蓝牙升级刷写(需 ninebot_ota.py ble-upgrade 先下发+车辆蓝牙已连手机)
$PY $SK setting --name "灯光设置"           # 一键打开「更多功能」里任意设置项(19项均可，见 §8.12)
$PY $SK toggle_setting --name "驻车感应" --expect checked:true   # 行内开关：自动定位并 retry 到期望状态(关闭类确认框自动点确定)
$PY $SK cmd --target "驻车感应" --action toggle --evidence ./ev   # ⭐ v1.9.0 主推：通用执行（dump XML+截图），不写死任何指令，新任务一律用这个
# 批量一步到位（JSON 指令列表，每条=[命令,{选项}]）：
$PY $SK run --json '[["status",{}],["tap",{"text":"闪灯鸣笛"}],["screenshot",{"out":"shot.png"}]]'
```

### 8.2.5 ⭐ 通用指令执行 `cmd`（v1.9.0 主推：dump XML + 截图，一套方法执行所有指令）

**为什么要有它**：之前每条指令都写死成独立命令（`toggle_setting` / `setting` + 页面树 `PAGE_TREE`），一旦 APP 元素变化、或新增指令没录入，执行就失败。本命令改用**通用方法**——`dump UI 层级 XML` 按文字通用定位 + `截图取证`，**所有指令（开关 / 按钮 / 进子页 / 弹窗确认）都走这一条路径**，脚本里**不再存任何"指令清单"**。

**核心原则（v1.9.0 铁律）**：脚本只保留【不怎么变】的稳定基元（dump / 截图标注 / 按文字点按或翻转 / 导航到 hub / 平台核验）；"执行哪条指令、点哪个文字"在**运行时由调用方（Agent 读屏）以参数传入**。这样 APP 元素怎么变、新增多少指令都**无需改脚本**。

```bash
PY=C:/Users/venus.li/.workbuddy/binaries/python/envs/default/Scripts/python.exe
SK=C:/Users/venus.li/.workbuddy/skills/ninebot-project/scripts/device_control.py

# 通用开关：自动 dump XML 找「驻车感应」行内开关并翻转，同时存 3 张分步截图到 ./ev
$PY $SK cmd --target "驻车感应" --action toggle --evidence ./ev
# 想开/想关明确指定（不写则自动翻到相反态）
$PY $SK cmd --target "自动驻车" --action on  --evidence ./ev
$PY $SK cmd --target "自动驻车" --action off --evidence ./ev

# 进入子页再操作其中开关（--path 逗号分隔，最后一个是操作目标）
$PY $SK cmd --path "更多功能,音效设置,提示音" --action on --evidence ./ev

# 首页控件（起点 hub 用 --start home）
$PY $SK cmd --target "闪灯鸣笛" --action tap --start home

# 只读当前状态（不点击），同样出取证截图
$PY $SK cmd --target "驻车感应" --action state --evidence ./ev
```

**工作机制（`do_cmd`，脚本内单一实现）**：
1. **确保 APP 在前台**并进入起点 hub（`--start`：默认 `more_functions`；首页控件用 `home`；`current` 不导航）。
2. **逐级下钻**：`--path` 的中间层级按文字 `tap` 进入子页（通用，无需预录页面结构）。
3. **dump XML 通用定位**：`d.dump_hierarchy()` 解析全部 `text/content-desc`，按「包含」匹配目标文字；找不到就自动滚动重找。再据控件类型自动判定：行内开关（可勾选后代）→ 翻转；可点按钮/整行 → 点击（导航或激活）。
4. **截图取证（3 张）**：操作前 / 点击后 / 结果，自动加**橙色标题条（用例+步骤+时间）+ 红框标控件**，存入 `--evidence` 目录。**图即证据，文字仅辅助**。
5. **失败不重试、先归因**：开关未达期望 → 自动 `_diagnose_toggle` 输出 `diagnosis` + 诊断截图（`dialog_pending` / 确认框文案 / 过渡态 / APP 报错 / 开关禁用 …），按 §8.5.3 处置；确认框按钮按词库或 `--confirm-text` 指定点击。
6. 返回 JSON：`{ok, target, action, before_state, after_state, evidence[], diagnosis?}`，可直接贴回测试用例 Excel 的 P/Q/R 列。

> 与 §9 联动：开关类失败先跑 `ninebot_ota.py commands <SN> --watch 30` 用平台下发页定责（无下发=脚本问题 / 有下发无响应=设备无响应 / 有下发有响应但 APP 不变=APP 问题），再写用例结论。

⚠️ **`setting` / `toggle_setting` 自 v1.9.0 起降为兼容兜底**：它们是按指令写死的旧实现，仅在没有 `cmd` 覆盖的极端场景使用；**新任务一律用 `cmd`**。

### 8.3 关键设计（为何更快/更稳）
- **相对定位**：用 `text` / `content-desc` / `resource-id` / `xpath` 做锚点，对元素对象 `.click()`，坐标由框架动态算，**绝不要写死像素坐标**。
- 文字控件本身常 `clickable=false` → 自动用 `//*[@text="..."]/ancestor-or-self::*[@clickable="true"][1]` 上溯到最近可点击祖先。
- `--up N` 可显式点第 N 层祖先（0=自身）。
- APP 已运行时**不重启**：`launch` 用 `app_start(..., stop=False)` 直接调前台。

### 8.4 ⚠️ 踩坑（已固化，勿重蹈）
- **uiautomator2 v3.7.0 的 `UiObject.parent()` 会抛异常** → 一律改用 xpath 相对轴（`ancestor::*`）做层级定位，禁止调用 `d(text=...).parent()`。
- 不要再用 `adb shell uiautomator dump` + 解析 + `input tap` 那套。
- 若 `tap` 没反应：先 `status` 确认 APP 在前台且屏幕亮，再用 `screenshot` 看按钮是否有高亮反馈，或 `texts` 确认按钮文字没变。
- 设备「已连接」但 `app_start` 失败：确认包名正确、APP 已安装；非 exported 的 Activity 不要用 `am start`（会 SecurityException）。
- **uiautomator2 选择器返回的 `Iter` 对象只能用 `for` 循环遍历**：`[e.info for e in d(className=...)]` 这种 list comprehension 会报 `'Iter' object is not iterable`，必须用 `for e in d(...): ...` 逐条 append。
- **`d.swipe()` 的 `duration` 参数是「秒」不是毫秒**：传 `500` 会卡 500 秒被超时杀掉；CLI 层的 `--duration` 按毫秒语义，脚本内部已 `÷1000` 转换。
- **判定"当前在哪个页面"= activity 名 + uiautomator2 完整 XML dump 双重判别**：先按 `d.app_current()` 的 activity 名粗判（九号各页 activity 不同且稳定：首页=`MainOversea`、更多功能根页=其二级子页=`DynamicListActivity`/`DynamicList2Activity`、设备信息=`DynamicDeviceInfoActivity`、电池/安心守护/固件=`NBReactActivity`）。遇到「一个 activity 承载多个页面」的情况（见下条），再用 `d.dump_hierarchy()`（等价于 `adb shell uiautomator dump`，但由 uiautomator2 直接取）解析出**全部 `text`/`content-desc`**（含标题栏、自定义控件，比只看 TextView 稳），按页面特征文字区分。长列表页（如更多功能）的"设备信息"入口在折叠区、当前屏文字看不到，光靠当前屏文字会误判 → 所以 activity 优先、完整 XML 文字兜底。统一走 `detect_current_page`，**不要自己手写判定**。
- **设备信息页的「固件详情」只是区块标题、不可点击**：`tap --text "固件详情"` 会报 `target element not found (nearest clickable ancestor-or-self)`——它没有任何可点击祖先。各模块固件版本（仪表控制器/中控/彩屏仪表/电池/电机控制器/充电器）**直接显示在设备信息页内、"固件详情"标题下方滚动可见**，提取固件版本时**只需滚动页面收集文字，不要去 tap「固件详情」**。

### 8.5 读开关/勾选状态以元素为准（判定闭环）
- 验证「是否开启」**必须读元素属性，不要看截图**：开关是 `android.widget.CompoundButton`（`resourceId=com.ninebot.segway:id/switch_view`，通用），用 `d(resourceId=SW).info['checked']` 取布尔值；开启后 `checked=True` 并可能多出配置行（如"自动上锁时间"）。
- **⚠️ 点开关会进入"正在设置..."进度态，`switch_view` 被隐藏（`exists=false`）**：读 `checked` 前必须先轮询等它重新出现并稳定，否则会误判成失败。时长因操作而异：**开启(ON)约 5 秒；关闭(OFF)约 26 秒**（实测）。OFF 远长于 APP 自身短超时 → 这就是"APP 显示超时/失败但实际已生效"的根因。
- 「自动锁车设置」是导航行（`tv_title`，不可点），点开子页"离车自动上锁"才是真正开关。
- 元素级判定模板见工作区 `test_autolock_v2.py`（读 checked + 轮询等"正在设置..."结束 + 平台链路核验）。

#### 8.5.1 ⚠️ 蓝牙不是设置类功能的前置条件（勿再写错）
首页横幅「请先连接蓝牙」**只针对感应解锁 / NFC / APP侧BLE刷写**这类必须 BLE 直连的功能。
**更多功能里的绝大部分设置（灯光设置、音效设置、驻车感应、低电量延长续航、电子刹车、安防设置、自动锁车设置…）走 4G 云通道，不需要蓝牙**——已实机验证：首页持续显示「请先连接蓝牙」时，`go_to_page --page more_functions` 仍 `verified:true`，`toggle_setting` 照常翻转成功。
- 不要因为看到该横幅就判 BLOCKED，也不要把它写成设置类的前置条件。
- 真正需要 BLE 的只有：感应解锁、NFC 钥匙、`ble_upgrade_app`（APP 侧固件刷写）。
- 若导航失败，先怀疑 **uiautomator2 服务端残态**（报 `AccessibilityService already registered` / `Remote end closed connection`），而不是蓝牙。恢复方式：
  ```bash
  adb shell am force-stop com.github.uiautomator
  adb shell am force-stop com.github.uiautomator.test
  # 切勿 pm clear com.github.uiautomator（会把服务端彻底清掉，更难恢复）
  ```

#### 8.5.2 开关操作失败的四段归因（必须用平台指令下发页定责）
**开关点了没生效 ≠ 脚本 bug。** 九号这类设置有大概率出现「开启后设备无响应」。判定顺序固定为：

| 现象（APP 侧） | 平台侧（`commands`） | 结论 | 该记的用例结果 |
|---|---|---|---|
| 点击后**页面毫无反应** | **无下发记录** | 脚本没点到 → 定位/坐标问题 | 修脚本，不算缺陷 |
| 点击后 APP 停在**「正在设置…」** | **无下发记录** | APP 收到点击但**指令没发出平台** → APP 侧缺陷 | FAIL（APP 未下发） |
| 点击后 APP 转圈/超时 | **有下发、无响应** | **设备无响应**（设备侧问题，非脚本） | FAIL（设备无响应） |
| 点击后 APP 无变化 | **有下发、有响应** | 指令链路正常 → **APP 显示问题** | FAIL（APP 未刷新） |
| APP 状态正确翻转 | 有下发、有响应 | 正常 | PASS |

> 第 2 行为 2026-08-08 新增实证分支：驻车感应「开启」点击后 APP 停在「正在设置…」，
> 但平台 8 分钟窗口内**零下发**（最后一条 `1786174505` 早于点击时刻 `1786174535`）。
> 说明「APP 有反应」≠「指令已发出」，必须查平台才能区分脚本问题与 APP 问题。

操作方法（对应平台「原始数据 → 指令下发」页，接口 `GET /service/iot-console-api/device/command`）：
```bash
# 在 APP 点开关的同时/紧随其后执行，实时等平台下发与设备回应
python scripts/ninebot_ota.py commands <IMEI或SN> --watch 30
# 事后复盘拉长时间窗
python scripts/ninebot_ota.py commands <IMEI或SN> --minutes 30
```
> **规则**：`toggle_setting` 报 `switch-gone-after-toggle` / 未达期望状态时，**不要直接下"脚本失败"结论**，必须先跑一次 `commands --watch` 按上表定责，再写用例结果与缺陷归属。

**当前测试设备（默认，勿用旧值）**
- IMEI：`868105049574252`
- SN：`48DGZ2602J0022`
- deviceId：`1001232`，productKey：`kBwCVBq4`
- ⚠️ 旧设备 `869004070113552 / 2HDEZ2447J0001` 已作废，不要再用。

**实证记录（2026-08-07）**：连续 6 条下发中 4 条设备已回应（时延 1.0s~3.7s，波动大）、2 条超时无响应；开关指令为 `g:cmd`，`data=00010001` 开 / `00010000` 关。据此确认 `switch-gone-after-toggle` 属**设备侧无响应**（FAIL-设备侧），非脚本 bug；`--settle` 建议给 25~30s。

#### 8.5.3 ⛔ 铁律：开关失败**不许重试**，必须先归因
> 反复点同一个开关是**有害**的：会叠加重复指令、把弹窗越堆越多、污染平台下发记录，
> 而且掩盖真实原因。`toggle_setting` 自 **v1.8.0** 起默认 `--max 1`（只点一次）。

失败时命令会自动输出 `diagnosis` 字段 + 诊断截图（`diag_<名称>_<ts>.png`），**先读它再决定下一步**：

| `reason` | 含义 | 正确处置（禁止盲目重试） |
|---|---|---|
| `dialog_pending` | 弹了确认框但没点中确认按钮 | 看 `confirm_candidates`，用 `--confirm-text "<按钮文字>"` 重跑一次 |
| `dialog_unknown_buttons` | 有弹窗但按钮文案不在词库 | 从 `all_clickable_labels` 挑出确认按钮，用 `--confirm-text` 指定，并把新文案补进词库 |
| `still_pending` | 页面停在「正在设置…」 | **禁止再点**。查平台下发：无下发=APP未发出(FAIL-APP侧)；有下发无回应=FAIL(设备侧) |
| `app_error_hint` | APP 已明确报错/提前置条件 | 先满足前置条件（开机/在线），重试无意义 |
| `switch_disabled` | 开关 `enabled=false` | 前置条件不满足，重试无意义 |
| `switch_missing` | 开关从页面消失 | 检查 activity 是否被推到子页，页面稳定后再单次重试 |
| `confirmed_but_unchanged` | 确认框点了但状态没变 | 按 §8.5.2 查平台定责 |
| `state_unchanged_no_dialog` | 无弹窗无报错但状态没变 | 按 §8.5.2 查平台定责 |

**确认框按钮文案不统一（v1.8.0 关键修复）**
之前 `toggle_setting` 只认「确定」+「取消」组合，而九号 APP 的确认框按钮实际是
**「关闭」/「开启」** 这类语义化文案 → 永远点不中确认 → 弹窗挂着 → 脚本无脑重试到失败。
现已内置词库并按【可点击节点】匹配（只匹配页面文字会把普通文案误判成按钮）：

```
确认类：确定 确认 继续 同意 我知道了 知道了 好的 是 开启 关闭 OK Confirm Yes
取消类：取消 再想想 暂不 不了 否 Cancel No
```

实证（2026-08-08，设备 48DGZ2602J0022）：
- `自动驻车 → OFF`：确认框按钮为**「关闭」**，命中词库，**1 次成功**（旧版重试 3 次全败）
- `自动驻车 → ON`：无确认框，**1 次成功**
- `驻车感应 → ON`：`reason=still_pending`，平台零下发 → 判 **FAIL（APP 未下发）**

```bash
# 标准用法：单次执行，失败自动归因
$PY $SK toggle_setting --name "自动驻车" --expect checked:false --settle 25
# 诊断报 dialog_pending 后，指定确认按钮再跑一次
$PY $SK toggle_setting --name "自动驻车" --expect checked:false --confirm-text "关闭"
```

### 8.6 retry 指令：应对 APP 短超时（自动重试直到响应，最多 5 次）
针对「APP 设置的超时时间太短 → 显示超时/失败，但实际已生效」这类问题：用 `retry` 指令反复下发同一操作，直到 APP 在超时(`settle`)内达到期望状态，最多 `max` 次（默认 5），最后只统计结果（`summary` / `final_state`）。

```bash
PY=C:/Users/venus.li/.workbuddy/binaries/python/envs/default/Scripts/python.exe
SK=C:/Users/venus.li/.workbuddy/skills/ninebot-project/scripts/device_control.py

# 把『离车自动上锁』开关切到关闭态（关闭操作约26s，故 settle 给 30）
$PY $SK retry --id "com.ninebot.segway:id/switch_view" --expect "checked:false" --max 5 --settle 30
# 切到开启态（开启约5s）
$PY $SK retry --id "com.ninebot.segway:id/switch_view" --expect "checked:true"  --max 5 --settle 12
```

参数：
- `--text/--desc/--id/--xpath`：点按目标（相对定位，同 tap）
- `--expect`（必填）：`checked:true` | `checked:false` | `exists` | `gone` | `text:<值>`
- `--check-id/--check-text/--check-desc/--check-xpath`：校验元素（默认=被点元素本身；点开关即校验开关）
- `--max`：最多重试次数（默认 **5**）
- `--settle`：每次操作后**轮询期望状态**的秒数（默认 12）

返回 JSON：`{ok, expect, attempts, max_retries, final_state, summary, history[]}`。看 `summary` 与 `final_state` 即可。

⚠️ **`settle` 必须大于真实操作耗时**，否则会在长操作途中误重Tap、指令互相打架永远卡在"正在设置..."。机制：发出一次点击后，在 `settle` 时长内**持续轮询期望状态**（不是等完再点），命中即成功；只有整段 `settle` 都没命中才进入下一次重试。

组合执行（导航+重试一步到位，**不用写脚本**）：
```bash
$PY $SK run --json '[["tap",{"text":"更多功能"}],["wait",{"text":"自动锁车设置"}],["tap",{"text":"自动锁车设置"}],["wait",{"id":"com.ninebot.segway:id/switch_view"}],["retry",{"id":"com.ninebot.segway:id/switch_view","expect":"checked:false","max":5,"settle":30}]]'
```
`wait`（等某元素出现，或 `--gone` 等消失）用于组合指令里的页面跳转同步。

### 8.7 设计原则：脚本通用、只发指令；导航与操作严格分离
- `device_control.py` 是**通用指令集**：底层稳定基元（status / launch / tap / tap_xy / swipe / screenshot / dump / texts / wait / retry / go_to_page / get_device_info / get_battery_info / ble_upgrade_app / power_on / power_off）+ 通用执行器 `cmd` + `run` 组合。**所有业务指令统一走 `cmd`**（dump XML 通用定位 + 截图取证，见 §8.2.5），不要在脚本里为每个按钮新写 Python、也不要依赖写死的指令清单。
- 旧写法 `setting` / `toggle_setting` 是按指令写死的兼容兜底，仅在没有 `cmd` 覆盖的极端场景使用；**新任务一律用 `cmd`**，避免"指令没录入就执行不了"的问题。
- **导航与操作分离（v1.6.0 核心）**：
  - **去哪个页面**统一由「页面导航引擎」负责——`go_to_page --page <id>` 或业务命令内部调用 `navigate_to(d, target)`。它先看当前在哪（`detect_current_page`，按 activity 名优先判定，文字兜底），再在 `PAGE_TREE` 上 BFS 求最短路径并逐边执行（tap / scroll_tap / back / launch），与目标页无关、与具体操作无关。
  - **到了页面干什么**由各业务的 `extract_*` 负责（如 `extract_device_info`），假设"已在目标页"，只做提取/点击，不负责怎么过去。
  - 这条边界是所有九号 APP 自动化命令的硬性约定：**任何"查/点"类功能，都先 `navigate_to` 到位，再在页面上操作**。新增目标页只需在 `PAGE_TREE` 加边，业务代码零改动。
- 单步不够就 `run --json` 把多步串起来；需要"等 APP 响应"就包一层 `retry`。
- 判定一律以元素属性（`checked` 等）为准，截图仅供调试。

### 8.8 APP 页面导航树（已实探 v1.7.4，仅设备相关页）
本 skill 只纳入「设备相关」页面（控车 / 查看数据）。**已显式排除**「发现 / 服务器 / 我的」等无关页。各页均经真机遍历确认，`go_to_page --page <id>` 或业务命令内部 `navigate_to` 即可到达。

**页面树（PAGE_TREE）与真实 activity 对照：**

| 页面 id | 入口 / 路径 | 真实 activity | 关键内容 |
|---|---|---|---|
| `outside` | 桌面/其他APP | （非九号包） | — |
| `home` | 启动APP | `MainOversea` | 控车：闪灯鸣笛/感应解锁/安防设置/仪表盘；数据：电量/续航/最近骑行/总里程 |
| `more_functions` | home→「更多功能」 | `DynamicListActivity` | 设备设置列表（2026-08-07 实机全量 **19 项**）：安防设置/灯光设置/音效设置/NFC和密码设置/快捷功能定义/驻车感应/自动锁车设置/低电量延长续航/电子刹车/能量回收强度/骑行模式设置/公英制切换/转把设置/安心守护/实验室/电池信息与设置/设备信息/解绑车辆（含二级子页，见 §8.12） |
| `device_info` | more_functions→「设备信息」(底部) | `DynamicDeviceInfoActivity` | 型号/车架号/总里程 + 各固件版本 + 「检查固件更新」入口 |
| `battery` | more_functions→「电池信息与设置」 | `NBReactActivity` | 主电池/应急电池电量、电压、温度、充电上限（数据提取见 `get_battery_info`） |
| `safety` | more_functions→「安心守护」 | `NBReactActivity` | 电子围栏（添加电子围栏） |
| `throttle` | more_functions→「转把设置」 | `DynamicList2Activity` | 转把校准 |
| `lab` | more_functions→「实验室」 | `DynamicList2Activity` | 智能后仰抑制等实验功能 |
| `fota_page` | device_info→「检查固件更新」(底部) | `NBReactActivity` | 固件升级：检测更新/下一步/确认升级/开始升级（蓝牙升级刷写页） |

⚠️ **activity 同名必须按文字区分**：`NBReactActivity` 同时承载 `battery`/`safety`/`fota_page`，`DynamicList2Activity` 同时承载 `throttle`/`lab` 根页 + 多个「更多功能」二级子页（灯光设置/音效设置/NFC和密码设置/快捷功能定义/安防设置/骑行模式设置 等也都是 `DynamicList2Activity`）。`detect_current_page` 已用 `d.dump_hierarchy()` 取完整 XML 文字做二次判定：`_detect_nbreact` / `_detect_list2` 命中根页特征词才返回对应根页 id，**任何不匹配的子页统一返回 `more_functions_sub`**（见 §8.8 下方），**不要只看 activity**。

⚠️ **`more_functions` 根页与全部二级子页共用 `DynamicListActivity`/`DynamicList2Activity`**：但 `detect_current_page` 现在能区分——根页含「更多功能」标题或命中的已知设置项 ≥5 个 → `more_functions`；否则 → `more_functions_sub`。`navigate_to` 在起始页为 `more_functions_sub`（或任何非页面树节点）时会**自动先按返回退回根页再导航**，所以 `setting`/`toggle_setting` 即使从某子设置页发起也能正确工作，**无需手动回退**。（旧版曾踩坑：子页被误判为根页导致不回退、点到错误控件，已修复。）

**更多功能里的「对话框/原地开关」（非独立页）：**
- `能量回收强度`：底部弹窗，选项「标准/弱/关闭」
- `骑行模式设置`：进入二级设置（自定义档位）
- `驻车感应` / `低电量延长续航` / `电子刹车` / `倒车断电`：行内开关（用 `toggle_setting --name` 直达，关闭类弹确认框自动点确定）
- `公英制切换`：公制/英制切换
- 其余（`安防设置`/`灯光设置`/`音效设置`/`NFC和密码设置`/`快捷功能定义`/`安心守护`/`实验室`/`电池信息与设置`/`设备信息`）：打开即进入二级页
- 完整 19 项清单与直达方式见 **§8.12**。

**新增命令：**
```bash
$PY $SK get_battery_info        # 导航到电池信息页并提取 主电池/电压/温度/应急电池 等数据
$PY $SK ble_upgrade_app --wait-task 30   # APP侧蓝牙升级刷写（需平台先 ble-upgrade 下发 + 车辆蓝牙已连手机）
$PY $SK go_to_page --page battery|safety|throttle|lab|fota_page|device_info|more_functions|home
$PY $SK power_on                          # 滑动开机：adb input swipe 把首页「滑动开机」滑块滑过去→「开机中」(真正通电需按整车电源按钮)
$PY $SK power_off                         # 点击关机：点击首页「点击关机」红色按钮→「滑动开机」关机态
```

### 8.9 swipe 滑动屏幕（v1.5.0 新增）
用于长页面滚动（如「更多功能」页到底部找「设备信息」）。**优先用本命令**（坐标由框架按屏幕比例动态算，且已修正 `duration` 单位坑：uiautomator2 的 `swipe` 的 `duration` 是**秒**，早期一度误传毫秒导致卡死）；只有 helper 滚动不够用时，才回退到 `adb shell input swipe`（属 §8.13 兜底原则）。

```bash
PY=C:/Users/venus.li/.workbuddy/binaries/python/envs/default/Scripts/python.exe
SK=C:/Users/venus.li/.workbuddy/skills/ninebot-project/scripts/device_control.py

$PY $SK swipe --direction up   --distance 0.8 --times 3   # 上滑3次（页面向下滚）
$PY $SK swipe --direction down --distance 0.8 --times 2   # 下滑2次（页面向上滚）
$PY $SK swipe --direction left --times 1                  # 左滑（页面右滚）
```
参数：
- `--direction`：`up`(上滑/页下滚) / `down`(下滑/页上滚) / `left` / `right`，默认 `up`
- `--distance`：滑动距离占屏比例 0~1，默认 0.8
- `--times`：滑动次数，默认 1
- `--duration`：滑动时长（毫秒，CLI 语义；脚本内部已 ÷1000 转秒），默认 500
- 与 `run` 组合：`run --json '[["swipe",{"direction":"up","times":3}],["texts",{}]]'`

### 8.9 get_device_info 一键查设备版本信息（v1.6.2 含 APP↔平台双向映射）
**九号 APP 专用**：内部 = `navigate_to("device_info")` 走到页面 + `extract_device_info()` 在页面上提取，返回结构化 JSON，**无需人工逐步点击、无需关心当前在哪**。

```bash
$PY $SK get_device_info
```
- 自适应所有入口（已在设备信息页 / 在更多功能页 / 在首页 / APP 未前台会自动拉起），全靠页面导航引擎统一处理。
- 到达后**滚回顶部再向下完整收集**所有文字（合并去重），避免滚动位置导致字段漏抓；固件版本仅当下一字段形如 `vX.Y.Z` 才赋值（电机控制器本行后无独立版本号，标记为 `null`）。
- ⚠️ **「固件详情」是区块标题、不可点击**（无 clickable 祖先，`tap` 会失败）：各模块固件版本直接显示在设备信息页内、"固件详情"下方，提取时**只滚动页面收集文字，绝不要 tap「固件详情」**。

#### APP ↔ 平台（iot-test.ninebot.com）模块名对照表（v1.6.2 新增）
排查固件问题时不必猜测，直接用此表对照（截图验证，2026-08-05）：

| APP 设备信息页模块名 | 平台零部件代码 | 用途 |
|---|---|---|
| 仪表控制器 | `DIS` | 主仪表 |
| 中控 | `ECU` | **T-BOX**（车载通信/中控一体模块） |
| 彩屏仪表 | `TFT` | TFT 彩屏显示器 |
| 电池 | `BMS` | 电池管理系统 |
| 电机控制器 | `MCU` | 电机控制器（APP 不显示独立版本号） |
| 充电器 | `CHG` | 充电器 |

→ T-BOX = `中控` = `ECU`；APP 设备信息页**没有独立的"T-BOX"条目**，但 T-BOX 就是中控模块。

#### APP 版本号 ↔ 平台 hex 编码 转换（v1.6.2 新增）
平台版本号是 4 位小写 hex 编码（截图"零部件名称"右侧"固件版本"列），与 APP 的 `vX.Y[.Z][.W]` 互转：

| APP 版本 | 平台 hex | 对应模块 |
|---|---|---|
| `v3.1.7` | `0317` | TFT |
| `v2.3.14` | `023e` | ECU |
| `v2.0.0.8` | `2008` | BMS |
| `v5.0.13` | `050d` | CHG |
| `v1.1.5` | `0115` | DIS |

转换规则（脚本内 `_format_platform_version()` 实现）：
- APP 3 段 `vX.Y.Z`     → 平台 `"0" + X + Y + Z`（hex；10-15 → a-f）
- APP 4 段 `vX.Y.Z.W`   → 平台 `X + Y + Z + W`（hex）
- 单段必须 ≤ 15（hex 一位），否则原样返回（防御性）

#### 返回示例（含 APP 视角 + 平台视角双版本）
```json
{
  "ok": true,
  "device_info": {
    "model": "赛格威越野电摩Xaber 300美洲版",
    "activate_time": "2026.01.21",
    "vin": "LTUY26WL7T1000114",
    "sn": "48DGZ2602J0022",
    "total_mileage": "28.3KM",
    "firmware_versions": {                       // APP 视角（内部英文 key）
      "instrument_controller": "v1.1.5",
      "central_control":       "v2.3.14",
      "display":               "v3.1.7",
      "battery":               "v2.0.0.8",
      "motor_controller":      "未单独显示",
      "charger":               "v5.0.13"
    },
    "platform_versions": {                       // 平台视角（v1.6.2 新增，按平台"零部件"列顺序）
      "DIS": { "app_label": "仪表控制器", "app_version": "v1.1.5",   "platform_tag": "0115" },
      "ECU": { "app_label": "中控",       "app_version": "v2.3.14",  "platform_tag": "023e" },
      "TFT": { "app_label": "彩屏仪表",   "app_version": "v3.1.7",   "platform_tag": "0317" },
      "CHG": { "app_label": "充电器",     "app_version": "v5.0.13",  "platform_tag": "050d" },
      "MCU": { "app_label": "电机控制器", "app_version": null,       "platform_tag": null },
      "BMS": { "app_label": "电池",       "app_version": "v2.0.0.8", "platform_tag": "2008" }
    },
    "module_map_app_to_platform": {              // v1.6.2 新增：APP 模块名 → 平台代码速查表
      "仪表控制器": "DIS", "彩屏仪表": "TFT", "中控": "ECU",
      "电池": "BMS", "电机控制器": "MCU", "充电器": "CHG"
    },
    "tbox_equivalent": "中控 (ECU) — 九号电摩 T-BOX 即中控模块"
  }
}
```

> 完整定义在 `device_control.py` 模块顶部：`APP_TO_PLATFORM` / `PLATFORM_TO_APP` / `FIRMWARE_KEY_TO_APP` 常量 + `_format_platform_version()` 版本转换函数，可直接 import 复用。

### 8.11 车辆电源控制：滑动开机 / 点击关机（v1.7.5 新增）

```bash
$PY $SK power_on     # 滑动开机：把首页「滑动开机」滑块从最左滑到最右(thumb转右)，界面进入「开机中」
$PY $SK power_off    # 点击关机：点击首页「点击关机」红色电源按钮，回到「滑动开机」关机态
```

⚠️ **这两个动作的底层机制完全不同，且都踩过坑，已固化进 `device_control.py`，不要手敲 `adb`/`input` 重走老路：**

#### 滑动开机（`power_on`）— 必须用 `adb input swipe`，`uiautomator2` 通道无效
- 首页「滑动开机」滑块是自定义 `svgaView` 控件，**uiautomator2 的 `d.touch`/`d.swipe` 被它完全忽略**（pill 红色中心死死不动，0 反应）；
- 只有系统 `adb shell input swipe` 通道（带真实手指类型）能驱动它。命令内部已自动用 `adb -s <serial> shell input swipe` 执行。
- 这正是「helper 通道无效、无现成一条指令可用 → 必须走 adb 兜底」的真实案例：脚本已把 adb 调用封装进 `power_on`，对外仍是一条指令（与 §8.13 兜底原则一致）。
- 滑过去只到 **「开机中」过渡态**；**真正通电还需物理按整车电源按钮**（按后界面才显示「点击关机」）。自动化只能完成"滑过去"这一步 —— 这是设计如此，不是失败。
- 成功判据：`滑动开机` 文字消失、`开机中` 出现（命令返回 `ok:true` 即代表滑块已滑过去）。
- 坐标用**屏幕比例换算**（基准 1080×2400 实测）：起点 = 红色按钮(thumb)中心(最左) ≈ `w*0.4343, h*0.4783`；终点 = 拖到滑块右界之外使 thumb 被 clamp 到底 ≈ `w*0.7037`。不要改成像素写死。

#### 点击关机（`power_off`）— 用 `uiautomator2` click 即可
- 开机态下「点击关机」是常规可点 tile，`d.click` 在 dump XML 中 `svgaView` 视觉中心（≈ `w*0.5, h*0.4783`）即可触发，无需 `adb`。

#### 完整开机链路（自动化 + 人工）
1. `power_on` → 滑块滑过去，APP 显示「开机中」（自动化完成）；
2. 人工按**整车物理电源按钮** → 通电，APP 显示「点击关机」（真正开机）；
3. 需要关机时 `power_off` → 回到「滑动开机」。

> ⚠️ 历史坑回顾（已写入记忆，勿重蹈）：曾误以为"滑块滑不动、必须手动"——根因是①错用 `u2.bounds()` 拿坐标（该控件报的是错误坐标系，偏左 236px）、②错把"出现点击关机"当成功标准（那要等整车按钮）、③用了 `d.swipe` 通道（被忽略）。正确路径就是 `adb input swipe` + 以「开机中」为滑过去判据。

---

### 8.12 APP 功能速查（按功能直达，优先用 helper）

下表覆盖九号出行 APP **已实机核实**的全部主要功能（首页 + 更多功能 19 项）。**新任务一律用通用执行器 `cmd`（见 §8.2.5）**，不再逐条写死指令；表中 `setting`/`toggle_setting` 仅作兼容参考：
- `setting --name "<设置项名>"`：自动 `go_to_page more_functions` + 点开任意设置项（打开二级列表/对话框/开关行）。
- `toggle_setting --name "<开关名>" --expect checked:true|false`：自动定位该行内 `CompoundButton` 并 retry 到期望状态，**关闭类开关弹出的确认框（确定/取消）会自动点「确定」**（如 驻车感应关闭时弹"关闭后，会禁用自动锁车功能"）。

任何"去页面"动作都先 `go_to_page`/`navigate_to`（见 §8.10），到了页面再操作；helper 匹配不到的控件才走兜底（§8.13）。

#### 一、首页（home / `MainOversea`）
| 功能 | 直达方式 |
|---|---|
| 闪灯鸣笛 / 鸣笛 / 闪灯 | `$PY $SK tap --text "闪灯鸣笛"` |
| 感应解锁（开关） | `go_to_page home` → `retry --text "感应解锁" --expect checked:true/false` |
| 安防设置 | `setting --name "安防设置"` |
| 仪表盘数据（电量% / 续航 km / 最近骑行 / 总里程） | `texts` 或 `screenshot` 读文字；结构化整车数据走平台 `device-status`（§5.4） |
| 滑动开机 / 点击关机 | `power_on` / `power_off`（见 §8.11） |

#### 二、更多功能（more_functions）— 共 19 项（2026-08-07 实机全量抓取）

**① 打开即进入二级页/列表（用 `setting --name` 直达）：**
| 设置项 | 备注 / 二级页内容 |
|---|---|
| 安防设置 | 二级安全设置页 |
| 灯光设置 | 含「延迟关闭大灯（关闭/开启）」等 |
| 音效设置 | 音效/彩蛋皮肤开关 |
| NFC和密码设置 | NFC 卡 / 密码管理 |
| 快捷功能定义 | 自定义快捷按键 |
| 骑行模式设置 | 自定义档位模式 |
| 转把设置 | 油门与转把相关（同 `go_to_page throttle`） |
| 安心守护 | 安全区域/电子围栏（同 `go_to_page safety`） |
| 实验室 | 智能后仰抑制等实验功能（同 `go_to_page lab`） |
| 电池信息与设置 | 主/应急电池电量、电压、温度、充电上限（同 `get_battery_info`） |
| 设备信息 | 型号/车架号/各固件版本（同 `get_device_info`） |
| 解绑车辆 | ⚠️ **危险操作**，仅确认需要时执行 |

**② 行内开关（用 `toggle_setting --name` 直达，自动处理确认框）：**
| 开关 | 说明 |
|---|---|
| 驻车感应 | 监测边撑是否收起；**关闭会弹确认框"关闭后，会禁用自动锁车功能"**（命令已自动点确定） |
| 自动锁车设置 | 进入子页后有「离车自动上锁」开关，见 §8.5 / §8.6（`retry --id switch_view --expect`） |
| 低电量延长续航 | 电量<20% 时自动调低车速上限 |
| 电子刹车 | 行内开关 |

**③ 弹窗/选项类（先 `setting --name` 打开，再 `tap` 选项）：**
| 设置项 | 说明 |
|---|---|
| 能量回收强度 | 标准 / 弱 / 关闭（打开后弹窗选「标准」等） |
| 公英制切换 | 公制 / 英制 |

> 说明：②/③ 里的开关与选项名（如「延迟关闭大灯」「能量回收强度」）同样可用 `setting --name` 或 `toggle_setting --name` 直达；`toggle_setting` 专用于行内 `CompoundButton` 且需判定 `checked` 状态。凡"直达方式"是 `tap --text/--id` 的都可包进 `run --json` 组合；涉及开关状态判定的包一层 `retry`（§8.6）。

#### 三、组合与判定
- 多步串联：`run --json '[["setting",{"name":"灯光设置"}],["tap",{"text":"延迟关闭大灯"}],["retry",{"name":"延迟关闭大灯","expect":"checked:true"}]]'`（先打开设置页，再操作其中开关）。
- 读开关状态一律以元素属性（`checked`）为准，截图仅供调试；APP 偶发"假超时/未刷新"时以平台下发指令（`commands --watch`，§9）为权威判据，按 §8.5.2 三段归因定责（无下发=脚本问题 / 有下发无响应=设备无响应 / 有下发有响应但APP无变化=APP问题）。
- helper 选择器（`--text/--id/--xpath`）匹配不到目标控件时，走 §8.13 兜底。

### 8.13 兜底方案（三级，逐级降级）

**使用原则**：helper 已覆盖的功能一律走 helper（`tap --text/--id/--xpath`、`setting`、`toggle_setting`）；**只有某功能没有现成 helper 能一条指令完成时**，才按下面三级顺序降级。dump/图像兜底都慢、依赖界面不变、坐标易错，仅作兜底、**不能作为首选**。

**Tier 1 — 相对定位（首选兜底）**：`device_control.py` 的 `tap --text/--id/--xpath`（自动上溯可点击祖先），不受列表滚动位移影响。

**Tier 2 — `uiautomator dump` → 解析 XML → 算中心 → `input tap`**：
```bash
SERIAL=A2TBV2C27014459
# 1) 抓当前布局 XML 到设备，再拉回本机
adb -s $SERIAL shell uiautomator dump /sdcard/ui.xml
adb -s $SERIAL pull /sdcard/ui.xml ./ui.xml
# 2) 解析目标节点 bounds（示例：找 text="某按钮" 的节点）
#    bounds="[x1,y1][x2,y2]" → 中心 cx=((x1+x2)//2), cy=((y1+y2)//2)
# 3) 用设备像素坐标点击
adb -s $SERIAL shell input tap <cx> <cy>
```
- 坐标来自**设备真实像素**（`input tap` 吃设备像素，与 density 无关）；界面位移/列表滚动会使坐标失效，故用完即弃。
- 优先用 `device_control.py` 的 `dump`/`texts` 看元素，`tap --text/--id/--xpath` 相对定位（不受位移影响）；只有相对定位也匹配不到时，才手算坐标兜底。
- 典型真实案例：首页「滑动开机」`svgaView` 控件 uiautomator2 完全忽略，必须用 `adb shell input swipe`（已封装进 `power_on`），见 §8.11。

**Tier 3 — 图像兜底：截图 → 图像理解 → 像素点击（dump 抓不到控件时）**：
当目标控件是 **canvas / SVGA / 游戏化视图 / 自定义绘制**（uiautomator2 的 dump 里根本没有对应节点，Tier 2 无从解析）时，改用图像方式：
1. 截图：`$PY $SK screenshot --out shot.png`（输出**设备像素**图）。
2. **用图像理解在截图里定位目标元素，得到它在图像上的像素坐标 (px, py)**（即「屏幕像素坐标」）。
3. 像素点击（两条等价路径，坐标系一致）：
   - helper：`$PY $SK tap_xy --x <px> --y <py>`（u2 `d.click`，吃设备像素）
   - 原生：`adb -s $SERIAL shell input tap <px> <py>`
- ⚠️ **分辨率映射**：`screenshot` 输出的是**设备像素**（与 `input tap` / `tap_xy` 同坐标系，1:1 直接可用）；若截图被缩放查看或用了非 1:1 的采样，需先把图像理解得到的坐标按「原图宽高 ÷ 显示宽高」缩放回设备像素再点。
- ⚠️ 与 Tier 2 同样：坐标依赖界面不变，列表滚动/动画会改变位置，用完即弃；能回到 Tier 1/2 相对定位时优先回去。

---

### 8.10 统一页面导航引擎（v1.6.0 新增）⭐ 所有"去目标页面"的唯一入口
把"去页面"从各业务里抽出来集中管理，彻底与"在页面操作"解耦。任何九号 APP 命令要换页，都只走这一层。

**页面树 `PAGE_TREE`（脚本内常量，单一事实来源）**：
```python
PAGE_TREE = {
    "outside":        { "edges": { "home": {"action": "launch", "package": NINEBOT_PKG} } },
    "home":           { "edges": { "more_functions": {"action": "tap_text", "text": "更多功能"} } },
    "more_functions": { "edges": { "home": {"action": "back"},
                                   "device_info": {"action": "scroll_tap_text", "text": "设备信息", "max_scroll": 6} } },
    "device_info":    { "edges": { "more_functions": {"action": "back"} } },
}
```
- 每个节点 = 一个 APP 页面；`edges` = 从本页到邻居页的**导航边**（一条动作描述）。
- 新增目标页（如 `固件详情`、`安防设置`）：只在 `PAGE_TREE` 加节点和边即可，业务代码零改。

**导航四件套（脚本内函数）**：
| 函数 | 作用 |
|---|---|
| `detect_current_page(d)` | **查询当前页面**：先按 `d.app_current()` 的 activity 名粗判；遇到「一个 activity 承载多页」时，用 `d.dump_hierarchy()`（完整 XML，等价于 adb uiautomator dump）解析全部 text/content-desc 做二次区分。根页返回 `home/more_functions/device_info/battery/safety/throttle/lab/fota_page`；「更多功能」的任意二级子页（灯光/音效/NFC/安防…）返回 `more_functions_sub`；不在九号APP返回 `outside`；前台但无法识别返回 `unknown` |
| `_bfs_path(start, target)` | 在 `PAGE_TREE` 上 BFS 求"当前页→目标页"最短路径（含两端） |
| `_exec_nav_action(d, action)` | 执行单条导航边（launch / tap_text / scroll_tap_text / back） |
| `navigate_to(d, target)` | **统一导航**：查当前页→求路径→逐边执行并校验到达（tap 类失败自动重试）→返回 `{ok, from, path, steps, final_page}` |

**直接调用（只去不操作）**：
```bash
$PY $SK go_to_page --page device_info     # 直接走到设备信息页（不提取）
$PY $SK go_to_page --page home           # 一路 back 回到首页
$PY $SK go_to_page --page more_functions
```
`--page` 取值即 `PAGE_TREE` 的节点：`outside / home / more_functions / device_info`（传其它值会报"未知目标页面"并列出可用页）。

**业务命令的正确写法（导航与操作分离）**：
```python
def do_xxx(d, opts):
    nav = navigate_to(d, "device_info")      # 1) 先统一去目标页（与具体操作无关）
    if not nav["ok"]:
        return {"ok": False, "navigation": nav}
    return extract_xxx(d)                    # 2) 到了页面再做具体操作（假设已在页上）
```
> 实测覆盖的入口场景：已在设备信息页 / 在更多功能页 / 在首页 / APP 未前台（自动 `launch`）。全部走同一条 `navigate_to`，判定以 activity 为准（之前用"可见文字"判定会因长列表"设备信息"被折叠而误判为 unknown，已改为 activity 优先）。

---

## 9. 查看平台下发指令（设备链路核验）⭐ APP 假超时的权威判据

### 9.1 背景与链路
设备控制的真实链路是：
**APP 设置 → 平台下发指令到设备 → 设备接收并执行 → 返回结果到平台 → APP 的值才改变**。

已知问题：APP 偶发「假超时」——设备其实已控制、平台也下发了指令且有设备回应（`resp_code=01`、`status=3`），但 APP 仍显示超时、数据也没刷新（实际已改变）。此时**不能只信 APP 显示**，要以平台的下发/回应记录为权威判据。

### 9.2 接口（来自抓包验证可用）
- `GET /service/iot-console-api/device/command`
- 参数：`productKey`、`sn`、`deviceId`、`startTime`、`endTime`（epoch 秒）
- 返回 `data[]`，每条即一条平台下发指令，关键字段：
  - `req_time` 平台下发时间；`resp_time` 设备回应时间（空=未回应/超时）
  - `resp_code` 设备回应码（`01`=已回应；空=未回应）；`status` 状态字符串（`3`=设备已回应完成）
  - `cmd_body` 平台下发的指令体（sourceId/tragetId/cmdId/data/index…）；`resp_data` 设备回执体
- 已在 `ninebot_ota.py` 实现为 `commands` 子命令（含字段兼容：设备列表返回 camelCase，脚本内部归一化为 snake_case）。

### 9.3 用法
```bash
# 列表模式：查看近 N 分钟平台下发的指令，并给出链路核验结论
python ninebot_ota.py commands <IMEI或SN> --minutes 10

# watch 模式：APP 在手机上点完设置后，立刻在本机跑这条，
# 它会轮询等待平台下发的新指令并跟踪到设备回应，直接判定"下发+回应"是否成功
python ninebot_ota.py commands <IMEI或SN> --watch 30
```
输出结论：
- `✅ 设备已回应` + `status=3` + `resp_code=01` → 平台已下发且设备已执行 → **即便 APP 显示超时，实际链路成功**。
- `⏳ 未回应/超时`（status=2 已送达但无 resp）→ 可能真超时/设备离线，需结合 APP 判断。

### 9.4 标准工作流（APP 设置 → 平台核验）
1. 用 §8 的 `device_control.py` 在手机 APP 上点设置（如"闪灯鸣笛""离车自动上锁"）。
2. **立刻**在本机跑 `commands <SN> --watch 30`：等待平台下发该指令并确认设备回应。
3. 以命令记录的 `status`/`resp_code` 为最终判定，**不依赖 APP 的超时提示**。
   - 若 `resp_code=01` 但 APP 仍显示旧值 → 报告"平台链路成功，APP 显示异常（已知假超时）"。
4. 历史排查：`commands <SN> --minutes 120` 拉长时间窗看完整下发记录。

### 9.5 会话 Cookie / 鉴权
- **自动登录已内置**：`ninebot_ota.py` 顶部 `ACCOUNT`/`PASSWORD`（`dehao.zhang@ninebot.com` / 当前密码）即登录凭据；`_session()` 每次自动 `ensure_authenticated()`，失效即自动 `login()`，登录结果持久化到 `scripts/ninebot_cookies.json` 跨进程复用（约 30min 过期）。
- 手动：`python ninebot_ota.py login` 刷新 Cookie；改密码只改 `PASSWORD` 一行。
- 别再手动从浏览器复制 Cookie 覆盖顶部 `COOKIES` 初值——那是兜底默认值，登录会覆盖它。

### 9.6 ⚠️ 实测踩坑（已固化）
- **`status` / `req_time` 在 JSON 里是字符串**：比对/排序前必须 `int()` 转换（如 `int(c.get("req_time") or 0) >= t`），否则会 `TypeError` 或漏判。
- **APP 显示与平台结论冲突的真实案例（离车自动上锁 / 自动锁车设置）**：
  - APP 元素 `checked` 稳定显示 `True`（ON），即使退出页面重进也保持不变；
  - 但平台记录该「关闭」指令 `cmd_body.data="04000000"`、`status=3`、`resp_code=01` → **平台已下发且设备已回应成功**。
  - 结论：这就是 §9.1 的「APP 假超时」变体——**APP 开关显示未随指令更新，但指令在平台/设备侧已成功**。此时一律以平台指令为准，并提示「APP 显示异常，实际已生效」。
- **协议特征（离车自动上锁）**：`cmd_body.data` `04000400`≈开启、`04000000`≈关闭；`resp_data "7D"`=设备 ACK。可按 `cmd_body` 含 `"04000000"` 过滤关闭类指令。
- 车辆 SN 与当前手机 APP 配对：`48DGZ2602J0022`（deviceId `1001232`，productKey `kBwCVBq4`）；脚本 `test_autolock_v2.py` 为元素级+平台级双判定模板。


