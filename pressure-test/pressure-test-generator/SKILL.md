# pressure-test-generator — 压力测试脚本生成器

根据用户提供的业务场景和代码，自动生成完整的压力测试 Python 脚本和 YAML 配置文件。

## 输出文件规范

每次压力测试生成 **两个文件**，放在同一目录下：

| 文件 | 固定名称 | 说明 |
|------|---------|------|
| 配置文件 | `device.yaml` | YAML 配置，脚本运行时自动加载 |
| 压力脚本 | `<场景名>.py` | 包含 基础类 + 超类 + 流程 + 主循环，单文件可运行 |

**重要**：
- 配置文件固定命名为 `device.yaml`，脚本中 `yaml_import()` 默认加载该文件
- 超类和压力脚本合并在 **同一个 .py 文件** 中，不拆分多个文件
- 用户提供的超类代码（如 `super_client.py`）直接嵌入到生成的脚本中

## 工作流程

### 1. 收集信息

向用户确认（已有的跳过）：

**必填：**
- **压力场景名称**：如 "QDM551平台IOT升级压力"、"开关机压力"
- **流程类型**：升级流程 / 开关机流程 / 通信流程 / 自定义
- **业务代码**：用户提供的基础类或超类（Python 代码、文件路径、或描述让 agent 生成）
- **YAML 配置项**：场景特有的配置参数

**可选（有默认值）：**
- 循环等待时间 `wait_time`（默认 60s）
- 失败后是否停止 `fail_stop_flag`（默认 False）
- 是否需要 Excel 统计日志（默认 True）

### 2. 确定架构层次

根据用户提供的信息，确定每层的内容：

**Layer 1 — 基础类**：用户提供的硬件/协议类
- 串口类 (Serial)、CAN类、继电器类 (Relay)、AT指令类、CMD窗口类、平台API类等
- 每个类独立，有自己的 open/close/read/write 方法
- **CMD窗口场景**：需要启动子进程（如SWDownloader、adb、fbfdownloader等）并监控其输出时，可加载子 skill `pressure-test-bases` 获取 CMD 基础类代码（逐字节读取，规避 readline 阻塞问题）
- **接口自动化场景**：如果用户提供了 HAR 文件或接口文档，可加载子 skill `pressure-test-api-analyzer` 自动分析接口并生成 Platform API 基础类代码（适配 pressure-test 状态码体系）

**Layer 2 — 超类**：组合基础类
- 用组合模式把多个基础类组装成一个设备对象
- 可以用工厂类或直接手动组合

**Layer 3 — 流程**：具体业务逻辑
- `run()` 方法：核心执行逻辑
- `handle_by_result()` 方法：错误处理
- `stop_by_result()` 方法：是否停止测试

**Layer 4 — 主循环**：循环执行 + 统计
- `one_operation()` 方法：单次完整操作
- `statistics()` 方法：统计输出

### 3. 生成 YAML 配置

使用 `${skill_dir}/scripts/generate_yaml.py` 生成 `device.yaml`。

```bash
python ${skill_dir}/scripts/generate_yaml.py \
  --output <输出目录>/device.yaml \
  --common '<JSON通用配置>' \
  --extra '<JSON场景配置>'
```

### 4. 生成压力脚本（单文件）

使用 `${skill_dir}/scripts/generate_script.py` 组装完整压力脚本。

**所有代码（基础类 + 超类 + 流程 + 主循环）合并到一个 .py 文件。**

如果用户提供了独立的超类文件（如 `super_client.py`），将其内容直接嵌入脚本中。

```bash
python ${skill_dir}/scripts/generate_script.py \
  --output <输出目录>/<场景名>.py \
  --yaml <yaml路径> \
  --business <业务代码文件路径> \
  --scenario <场景名称> \
  --version <版本号>
```

如果用户提供了超类文件需要嵌入：
```bash
python ${skill_dir}/scripts/generate_script.py \
  --output <输出目录>/<场景名>.py \
  --yaml <yaml路径> \
  --business <业务代码文件路径> \
  --embed <超类文件路径> \
  --embed-name <超类模块名> \
  --scenario <场景名称> \
  --version <版本号>
```

## YAML 配置字段说明

### 通用字段（所有场景）

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `wait_time` | int | 60 | 每次循环等待时间(秒) |
| `fail_stop_flag` | bool | False | 失败后是否停止脚本 |
| `_device_version` | str | "" | 设备版本号(可空) |
| `_pressure_name` | str | "" | 压力名称 |
| `_pressure_version` | int | 1 | 压力脚本版本号 |

### 场景特有字段示例

**OTA升级场景：**
```yaml
is_vpn: False
is_can: False
ota_type: Plateform
device_imei: "868105049574252"
fota_scope: ['T-BOX','BMS']
fota_combination: 1
fota_version_dict:
    ECU:
        version_a: "023e"
        version_b: "022e"
```

**开关机场景：**
```yaml
relay_com: "COM13"
relay_type: "NC"
device_key: "868471088459890"
platform_base_url: "https://hwbustest.tailgvip.com"
platform_username: "<your_username>"
platform_password: "<your_password>"
power_off_duration: 5
boot_wait_time: 60
online_check_timeout: 300
online_check_interval: 10
```

## 脚本文件

生成脚本所需的核心 Python 工具位于 `${skill_dir}/scripts/` 目录：
- `generate_yaml.py` — YAML 配置文件生成器
- `generate_script.py` — 压力脚本组装器

使用前请确保脚本文件存在，agent 调用时请使用 `${skill_dir}` 变量引用脚本路径。
