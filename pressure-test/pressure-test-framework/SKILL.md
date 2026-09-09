# pressure-test-framework — 压力测试核心框架

提供压力测试脚本的运行时框架组件：超类组合、流程模板、主循环、重试机制、日志统计等。

## 核心架构

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

## 超类组合 (Layer 2)

- 用组合模式把多个基础类组装成一个设备对象
- 可以用工厂类或直接手动组合

## 流程模板 (Layer 3)

具体业务逻辑，包含三个核心方法：

- `run()` — 核心执行逻辑，返回 `{"statuscode": 200/201/404/500, "duration": 耗时秒数, ...}`
- `handle_by_result()` — 根据状态码做错误处理
- `stop_by_result()` — 根据状态码决定是否停止测试

## 主循环 (Layer 4)

`example` 主循环类标准方法：

- `__init__()` — 初始化参数、日志、统计、设备对象、`self.start_time`
- `run()` — 核心业务方法
- `handle_by_result()` — 错误处理
- `stop_by_result()` — 停止判断
- `statistics()` — 统计并输出结果，**必须遵循「statistics() 输出格式标准」**
- `one_operation()` — 单次完整操作：run → handle → stop → statistics

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
- 记录：运行次数、PASS、FAIL、流程异常、脚本异常、成功率
- 支持场景特有统计项扩展（如平均耗时、最长耗时等）

## 日志输出格式标准

### 日志文件命名规则

**每次运行创建时间戳子目录，确保不同运行实例日志隔离，避免混乱：**
```
log/
└── <timestamp>/                    # 每次运行的时间戳子目录
    ├── script_log_<timestamp>.txt  # 脚本运行日志
    ├── fail_record_<timestamp>.txt # 失败记录
    └── statistic_log_<timestamp>.xlsx  # Excel统计
```

**实现方式（参考 SOC 脚本 `_init_log` 方法）：**
```python
def _init_log(self):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = os.path.join(os.path.dirname(__file__), "log", timestamp)
    os.makedirs(log_dir, exist_ok=True)
    self.log_dir = log_dir
    self.log_file = os.path.join(log_dir, f"script_log_{timestamp}.txt")
    self.fail_file = os.path.join(log_dir, f"fail_record_{timestamp}.txt")
```

**关键点：**
- `self.log_dir` 保存为 `log/<时间戳>/` 子目录路径
- 所有日志文件（运行日志、失败记录、App日志拉取）统一输出到 `self.log_dir`
- 禁止将日志直接输出到 `log_save_path` 根目录，必须经过时间戳子目录

### 状态码标准

| 状态码 | 含义 | 处理 |
|--------|------|------|
| 200 | PASS | 统计PASS，继续 |
| 201 | FAIL | 统计FAIL，按配置决定是否停止 |
| 404 | 流程异常 | 统计流程ERR，等待后继续 |
| 500 | 脚本异常 | 统计脚本ERR，等待后继续 |

### statistics() 输出格式标准

每轮统计必须通过 `printf_script()` 输出以下**固定格式**：

```
============================================================
统计信息
============================================================
运行时间：{开始时间}---{结束时间}
累计时长：{X.XXX}H
运行次数：{N}
成功次数：{N}
失败次数：{N}
流程异常：{N}
脚本异常：{N}
成功率：{XX.XX}%
{场景特有统计项（每行一个）}
============================================================
```

**通用参数（所有场景固定，框架自动生成）：**

| 参数 | 统计来源 | 说明 |
|------|----------|------|
| 运行时间 | `self.start_time` → 当前时间 | 脚本启动时间到当前时间 |
| 累计时长 | 时间差 | 格式化为小时（H），保留3位小数 |
| 运行次数 | `self._list_statistics['运行次数']` | 累计总轮次 |
| 成功次数 | `self._list_statistics['PASS']` | statuscode=200 |
| 失败次数 | `self._list_statistics['FAIL']` | statuscode=201 |
| 流程异常 | `self._list_statistics['流程异常']` | statuscode=404 |
| 脚本异常 | `self._list_statistics['脚本异常']` | statuscode=500 |
| 成功率 | `成功次数 / 运行次数 * 100` | 格式化为百分比（保留2位小数） |

**场景特有参数（根据流程类型分析确定）：**

| 流程类型 | 典型特有参数 |
|----------|-------------|
| 开关机流程 | 平均上线耗时、最长上线耗时、最短上线耗时 |
| OTA升级流程 | 平均升级耗时、最长升级耗时、最短升级耗时 |
| 通信流程 | 平均通信耗时、最长/最短通信耗时、通信成功率 |
| 自定义流程 | 根据 `run()` 返回值中的具体字段分析确定 |

**实现要求：**
- `example.__init__()` 中初始化 `self.start_time = datetime.datetime.now()`
- `example.statistics()` 中先输出分隔线和"统计信息"标题，再逐行输出通用参数，最后输出场景特有参数
- 场景特有参数需根据 `run()` 的实际返回值（如 `duration`）分析确定，由 agent 在生成脚本时具体分析并写入 `statistics()` 方法
- Excel 统计（`xl_log.printf()`）同步更新所有参数

## 注意事项

1. 配置文件固定命名为 `device.yaml`，脚本自动加载
2. 所有代码（基础类 + 超类 + 流程 + 主循环）在同一个 .py 文件中
3. 用户提供的超类文件内容直接嵌入脚本，不需要额外 import
4. 基础类应该独立可测试，每个类负责一个硬件/协议领域
5. 超类通过组合模式组装基础类，不继承不融合
6. YAML 中 `_` 前缀字段是框架元数据
7. 所有依赖库通过 `import_or_install()` 自动安装
8. 生成的脚本可直接 `python xxx.py` 运行
