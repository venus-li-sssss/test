# 九号项目 — Ninebot IoT OTA 固件平台操作 Skill

**版本**: 1.7.5 | **一体化覆盖**: 平台 OTA 操作 + 手机端 APP UI 控制

---

## 快速开始

### 前置条件
1. **内网连接**（必须）：运行 `D:\work\QDM559\连接九号内网.bat`，手动输入 SSH 密码
2. **验证隧道**：`netstat -ano | findstr :1080` 显示 `LISTENING`
3. **自动登录**：脚本内置账号密码，首次调用自动登录并持久化 Cookie

### 常用命令速查

```bash
PY=C:/Users/venus.li/.workbuddy/binaries/python/envs/default/Scripts/python.exe
OTA=C:/Users/venus.li/.qwenpaw/workspaces/QwenPaw_QA_Agent_0.2/skills/ninebot-project/scripts/ninebot_ota.py
APP=C:/Users/venus.li/.qwenpaw/workspaces/QwenPaw_QA_Agent_0.2/skills/ninebot-project/scripts/device_control.py

# 平台操作
$PY $OTA query-device <IMEI>                    # 查询设备 + 零部件版本
$PY $OTA add --imei <IMEI> --file fw.bin --version 032E  # 新增固件包
$PY $OTA upgrade <IMEI> <VERSION>               # FOTA 升级
$PY $OTA rollback <IMEI> <VERSION>              # FOTA 回滚
$PY $OTA status <IMEI>                          # 查看版本 + 升级历史
$PY $OTA fota <IMEI> --files a.bin,b.bin --versions A,B --rollback-to C  # 一站式
$PY $OTA ble-upgrade <IMEI> <VERSION>           # 蓝牙升级指令下发
$PY $OTA commands <IMEI> --watch 30             # 平台指令链路核验

# APP 控制
$PY $APP status                                 # 设备连接状态
$PY $APP tap --text "闪灯鸣笛"                  # 点击按钮
$PY $APP get_device_info                        # 提取设备信息 + 固件版本
$PY $APP get_battery_info                       # 提取电池数据
$PY $APP go_to_page --page battery              # 页面导航
$PY $APP power_on                               # 滑动开机
$PY $APP swipe --direction up --times 3         # 滑动屏幕
$PY $APP set_slider --text "提示音音量" --value 80  # 设置滑动条到 80%
```

---

## 一、平台 OTA 操作（ninebot_ota.py）

### 1.1 设备查询

```bash
python ninebot_ota.py query-device 868105049574252
```

**输出示例**：
```json
{
  "device": {
    "sn": "48DGZ2602J0022",
    "vehicleModelCode": "K21101",
    "vehicleModelCnName": "赛格威越野电摩 Xaber 300 美洲版",
    "productKey": "kBwCVBq4",
    "onlineStatus": 1
  },
  "parts": {
    "ECU": {"part_firmware_version": "023e", "pn": "Z0DKAVN25K9D0096"},
    "DIS": {"part_firmware_version": "0115"},
    "TFT": {"part_firmware_version": "0317"}
  }
}
```

### 1.2 新增固件包

**推荐用 `--imei` 自动解析车型**（避免加错车型）：

```bash
python ninebot_ota.py add --imei 868105049574252 --file 032e.bin --version 032E
```

**显式指定**：
```bash
python ninebot_ota.py add --file 032e.bin --version 032E \
  --model kBwCVBq4,K21101 --part-code WV --type ECU
```

**⚠️ 关键规则**：
- 文件名必须为 `V<x1>.<x2>.<x3>.<x4>.bin` 格式（如 `V0.3.2.E.bin`）
- 平台从**文件名**提取固件版本，裸名 `032e.bin` 会报 `4025` 错误
- helper 自动处理命名，无需手动改

### 1.3 升级 / 回滚 / 状态

```bash
python ninebot_ota.py upgrade  868105049574252 032E    # 升级
python ninebot_ota.py rollback 868105049574252 022f    # 回滚
python ninebot_ota.py status   868105049574252         # 状态
```

**⚠️ 版本区分**：
- `otaTargetVersion` = **包标签版本**（如 `032E`，来自文件名）
- `otaCurrentVersion` = **设备真实上报版本**（如 `023e`，来自 `get-parts-version`）
- 两者可能不同，不要强等

### 1.4 一站式 FOTA

```bash
python ninebot_ota.py fota 868105049574252 \
  --files 032e.bin,032f.bin \
  --versions 032E,032F \
  --rollback-to 022f
```

**流程**：解析设备 → 注册缺失包 → 升级链路 → 回滚 → 每步校验

### 1.5 蓝牙升级

```bash
# 1) 平台下发指令
python ninebot_ota.py ble-upgrade 868105049574252 032E

# 2) APP 经 BLE 刷写（需车辆蓝牙连手机）
python device_control.py ble_upgrade_app --wait-task 30
```

**核验**：用 `get-upgrade-history` 查 `actual_ota_type=2` 的任务

### 1.6 平台指令核验

```bash
python ninebot_ota.py commands 868105049574252 --watch 30
```

**用途**：APP 设置后核验平台是否下发指令、设备是否回应（解决 APP 假超时）

---

## 二、APP UI 控制（device_control.py）

### 2.1 基础指令

```bash
python device_control.py status                 # 连接状态 + 前台 APP
python device_control.py tap --text "闪灯鸣笛"  # 相对定位点击
python device_control.py screenshot --out x.png # 截图
python device_control.py texts                  # 列出界面文字
python device_control.py swipe --direction up --times 3  # 滑动
```

### 2.2 页面导航

```bash
python device_control.py go_to_page --page home            # 首页
python device_control.py go_to_page --page more_functions  # 更多功能
python device_control.py go_to_page --page device_info     # 设备信息
python device_control.py go_to_page --page battery         # 电池信息
python device_control.py go_to_page --page fota_page       # 固件升级页
```

### 2.3 信息提取

```bash
python device_control.py get_device_info    # 型号/车架号/各固件版本
python device_control.py get_battery_info   # 主电池/电压/温度/应急电池
```

**返回示例**：
```json
{
  "device_info": {
    "model": "赛格威越野电摩 Xaber 300 美洲版",
    "vin": "LTUY26WL7T1000114",
    "firmware_versions": {
      "central_control": "v2.3.14",
      "display": "v3.1.7",
      "battery": "v2.0.0.8"
    },
    "platform_versions": {
      "ECU": {"app_version": "v2.3.14", "platform_tag": "023e"},
      "TFT": {"app_version": "v3.1.7", "platform_tag": "0317"}
    }
  }
}
```

### 2.4 重试机制（应对 APP 超时）

```bash
# 关闭离车自动上锁（关闭操作约 26s）
python device_control.py retry --id "com.ninebot.segway:id/switch_view" \
  --expect "checked:false" --max 5 --settle 30

# 组合指令（导航 + 重试）
python device_control.py run --json '[
  ["tap",{"text":"更多功能"}],
  ["wait",{"text":"自动锁车设置"}],
  ["tap",{"text":"自动锁车设置"}],
  ["wait",{"id":"com.ninebot.segway:id/switch_view"}],
  ["retry",{"id":"com.ninebot.segway:id/switch_view","expect":"checked:false","max":5,"settle":30}]
]'
```

### 2.5 车辆电源控制

```bash
python device_control.py power_on    # 滑动开机（→「开机中」，需按整车电源按钮通电）
python device_control.py power_off   # 点击关机（→「滑动开机」关机态）
```

### 2.6 滑动条控制（set_slider）⭐ 零误差版

用于设置 APP 内的滑动条（如音效音量、亮度等）到**精确值**。

**核心算法**：过冲回退（Overshoot & Backtrack）
1. **快速接近** - 用大步长（默认 15px）快速拖动到目标附近
2. **过冲检测** - 如果移动后超过目标值，自动反向
3. **微调回退** - 用小步长（默认 2px）往回移动
4. **超微调整** - 如果还没精确匹配，用 1px 步长微调
5. **精确停止** - 值完全匹配目标时停止

**完全自动化**，无需 AI 介入，脚本自动完成零误差控制。

```bash
# 基础用法：设置音量到精确 80%
python device_control.py set_slider --text "提示音音量" --value 80

# 自定义步长
python device_control.py set_slider --text "提示音音量" --value 80 --step-size 20 --fine-step 3

# 超精细模式（慢但精确）
python device_control.py set_slider --text "提示音音量" --value 80 --step-size 10 --fine-step 1

# 组合指令（导航 + 设置滑动条）
python device_control.py run --json '[
  ["tap",{"text":"更多功能"}],
  ["wait",{"text":"音效设置"}],
  ["tap",{"text":"音效设置"}],
  ["set_slider",{"text":"提示音音量","value":80}]
]'
```

**参数**：
| 参数 | 说明 | 默认值 |
|---|---|---|
| `--text/--desc/--id/--xpath` | 定位滑动条（或其标签文字） | 必填 |
| `--value` | 目标值（如 80 表示 80%） | 必填 |
| `--max-value` | 最大值 | 100 |
| `--step-size` | 大步长（快速接近目标） | **15** |
| `--fine-step` | 微调步长（过冲后回退） | **2** |
| `--read-delay` | 每次移动后等待读取值的秒数 | **0.3** |
| `--max-overshoot` | 最大过冲次数（防止无限循环） | **3** |

**返回示例**：
```json
{
  "ok": true,
  "target_value": 80,
  "final_value": 80,
  "error": 0,
  "total_steps": 18,
  "overshoot_count": 1,
  "history": [
    {"phase": "coarse", "direction": "left", "from_x": 874, "to_x": 859, "value_before": 96, "value_after": 94},
    {"phase": "coarse", "direction": "left", "from_x": 859, "to_x": 844, "value_before": 94, "value_after": 92},
    ...
    {"phase": "fine", "direction": "right", "from_x": 814, "to_x": 816, "value_before": 79, "value_after": 80},
    {"phase": "micro", "direction": "left", "from_x": 820, "to_x": 819, "value_before": 81, "value_after": 80}
  ]
}
```

**工作原理**：
```
阶段 1（快速接近）：
  当前 96% → 目标 80%
  大步长 15px 向左拖
  96% → 94% → 92% → ... → 82% → 79%（过冲！）
  
阶段 2（微调回退）：
  检测到过冲（79% < 80%），切换方向
  小步长 2px 向右拖
  79% → 81%（又过冲！）
  
阶段 3（超微调整）：
  在目标值附近 3 以内，用 1px 微调
  81% → 80% ✅ 精确匹配！
```

**优势**：
- ✅ **零误差** - 过冲回退算法确保精确匹配目标值
- ✅ **快速** - 大步长快速接近，小步长精确调整
- ✅ **完全自动** - 无需 AI 介入，脚本自动完成
- ✅ **防无限循环** - `--max-overshoot` 限制过冲次数
- ✅ **详细日志** - 返回每步的 phase/direction/value

**注意事项**：
- 拖动过程中 APP 会显示"正在设置..."，这是正常的
- 如果滑动条响应慢，可增大 `--read-delay`（如 0.5）
- 如果滑动条吸附严重，可减小 `--fine-step`（如 1）
- 返回 `ok: true` 表示精确匹配，`ok: false` 表示接近但有误差

---

## 三、关键注意事项

### 3.1 内网连接
- **唯一可靠方式**：`D:\work\QDM559\连接九号内网.bat`（SSH 动态转发）
- **判定就绪**：`netstat -ano | findstr :1080` 显示 `LISTENING`
- `脚本连接内网.bat` **不等于**建隧道（只设环境变量）

### 3.2 认证
- 自动登录：`ACCOUNT`/`PASSWORD` 写在 `ninebot_ota.py` 顶部
- Cookie 持久化：`ninebot_cookies.json`（约 30 分钟过期）
- 手动刷新：`python ninebot_ota.py login`

### 3.3 版本命名
- 包标签版本（`032E`） 设备真实版本（`023e`）
- `add` 命令自动用 `V0.3.2.E.bin` 命名，避免 `4025` 错误

### 3.4 真实上传流程
`s3-upload-by-path` **只注册元数据**，真实上传需走：
1. `file-upload/upload/init`
2. `file-upload-test.ninebot.com/upload/part`（GET 预检 + POST 二进制）
3. `file-upload/upload/complete`
4. `s3-upload-by-path`

helper 的 `add` 命令已自动处理完整流程。

### 3.5 APP 假超时
- APP 显示超时 ≠ 实际失败
- **权威判据**：`commands --watch` 查平台指令记录
- `status=3` + `resp_code=01` = 设备已执行成功

---

## 四、模块对照表

| APP 设备信息页 | 平台代码 | 用途 |
|---|---|---|
| 仪表控制器 | DIS | 主仪表 |
| 中控 | ECU | T-BOX（车载通信/中控） |
| 彩屏仪表 | TFT | TFT 彩屏显示器 |
| 电池 | BMS | 电池管理系统 |
| 电机控制器 | MCU | 电机控制器 |
| 充电器 | CHG | 充电器 |

**版本转换**：
- APP `vX.Y.Z` → 平台 `"0" + X + Y + Z`（hex）
- APP `vX.Y.Z.W` → 平台 `X + Y + Z + W`（hex）
- 例：`v2.3.14` → `023e`，`v3.1.7` → `0317`

---

## 五、完整 API 参考

详见 [references/api_reference.md](./references/api_reference.md)

---

## 六、历史踩坑记录

### 已固化到脚本的坑
1. **加错车型** → `add --imei` 自动解析
2. **二进制未真上传** → `s3_upload` 含完整流程
3. **文件名决定版本** → `add` 自动命名
4. **校验逻辑错** → 平台任务状态为主 + 设备版本变化为辅
5. **历史接口瞬态报错** → 连续失败转版本回退校验
6. **uiautomator2 v3.7.0 的 `parent()` 异常** → 改用 xpath 相对轴
7. **`d.swipe()` 的 `duration` 是秒不是毫秒** → CLI 已转换
8. **滑动开机滑块 uiautomator2 无效** → 改用 `adb input swipe`

### 详细踩坑历史
见工作区 `memory/` 目录或 GitHub 提交历史。

---

**配套文件**：
- `scripts/ninebot_ota.py` — 平台 helper
- `scripts/device_control.py` — APP UI 控制 helper
- `scripts/ninebot_cookies.json` — Cookie 持久化
- `config.json` — 统一配置
- `references/api_reference.md` — API 完整文档
