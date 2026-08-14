---
description: 'Use this skill when the user wants to create, manage, or run pressure/stress
  test scripts. Triggers: "压力测试", "压测脚本", "stress test", "pressure test", "生成压力脚本",
  "生成yaml配置", "管理压力测试", "压力框架", or any request involving generating test scripts with
  retry, logging, statistics, and YAML config management.'
name: pressure-test
---

# 压力测试脚本管理 Skill

根据用户的业务场景，自动生成完整的压力测试 Python 脚本和 YAML 配置文件。

## 核心架构：基础类 → 超类 → 流程 → 日志

```
┌─────────────────────────────────────────────────────────────────┐
│ Layer 4: 主循环 (Main Loop)                                     │
│   while True: one_operation() → run → handle → statistics → wait │
├─────────────────────────────────────────────────────────────────┤
│ Layer 3: 流程 (Flow)                                            │
│   升级流程 / 开关机流程 / 通信流程 / 自定义流程                    │
│   包含: 重试、错误处理、状态码判断                                 │
├─────────────────────────────────────────────────────────────────┤
│ Layer 2: 超类 (Super Class / 组合模式)                           │
│   组合多个基础类为一个设备对象                                     │
│   例: device = Platform + CAN + AT + Debug                       │
├─────────────────────────────────────────────────────────────────┤
│ Layer 1: 基础类 (Base Classes)                                   │
│   Serial / CAN / Relay / Platform API / AT / Jlink / File        │
│   每个类独立，负责一个硬件或协议领域                                │
└─────────────────────────────────────────────────────────────────┘
```

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

## 触发场景

- 用户要创建新的压力/压测脚本（任何类型）
- 用户要生成或修改 device.yaml 配置
- 用户提供了业务类/方法，需要包装成可循环执行的压力脚本
- 用户提到 OTA升级压力、开关机压力、通信压力、接口压力等场景

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
- 串口类 (Serial)、CAN类、继电器类 (Relay)、AT指令类、平台API类等
- 每个类独立，有自己的 open/close/read/write 方法

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

### 5. 输出文件

生成两个文件到同一目录：
- `device.yaml` — 配置文件（固定名称）
- `<场景名>.py` — 完整可运行的压力脚本（单文件，包含所有代码）

## 日志输出格式标准

### 日志文件命名规则
```
log/
├── script_log_<timestamp>.txt      # 脚本运行日志
├── fail_record_<timestamp>.txt     # 失败记录
└── statistic_log_<timestamp>.xlsx  # Excel统计
```

### 状态码标准

| 状态码 | 含义 | 处理 |
|--------|------|------|
| 200 | PASS | 统计PASS，继续 |
| 201 | FAIL | 统计FAIL，按配置决定是否停止 |
| 404 | 流程异常 | 统计流程ERR，等待后继续 |
| 500 | 脚本异常 | 统计脚本ERR，等待后继续 |

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

## 框架内置组件

### ReTry 重试类
- `check_in_time()` — 按时间重试，超时返回 404
- `check_in_times()` — 按次数重试
- 支持 pass/fail/err 三种条件判断表达式

### retry_on_failure 装饰器
- 指数退避重试装饰器
- 可配置重试次数、延迟、退避倍数
- 只重试指定异常类型

### Make_File 日志类
- 支持 txt 和 bin 模式
- 自动添加时间戳前缀

### xl_log Excel统计类
- 自动创建统计 Excel
- 记录：运行次数、PASS/FAIL/ERR 次数、PASS RATE

### example 主循环类
标准方法：
- `__init__()` — 初始化参数、日志、统计、设备对象
- `run()` — **核心业务方法**
- `handle_by_result()` — 根据状态码做错误处理
- `stop_by_result()` — 根据状态码决定是否停止
- `statistics()` — 统计并输出结果
- `one_operation()` — 单次完整操作

## 注意事项

1. 配置文件固定命名为 `device.yaml`，脚本自动加载
2. 所有代码（基础类 + 超类 + 流程 + 主循环）在同一个 .py 文件中
3. 用户提供的超类文件内容直接嵌入脚本，不需要额外 import
4. 基础类应该独立可测试，每个类负责一个硬件/协议领域
5. 超类通过组合模式组装基础类，不继承不融合
6. YAML 中 `_` 前缀字段是框架元数据
7. 所有依赖库通过 `import_or_install()` 自动安装
8. 生成的脚本可直接 `python xxx.py` 运行
