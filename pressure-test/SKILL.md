---
description: 'Use this skill when the user wants to create, manage, or run pressure/stress test scripts. Triggers: "压力测试", "压测脚本", "stress test", "pressure test", "生成压力脚本", "生成yaml配置", "管理压力测试", "压力框架", or any request involving generating test scripts with retry, logging, statistics, and YAML config management.'
name: pressure-test
---

# 压力测试脚本管理 Skill（入口）

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

## 子 Skill 路由

本 skill 是一个 skill 集入口，按需加载对应子 skill：

| 子 skill | 内容 | 加载时机 |
|:---|:---|:---|
| **pressure-test-framework** | 超类组合、流程模板、主循环、ReTry/Make_File/xl_log/example、statistics格式、状态码标准 | 需要理解框架运行时行为、编写流程代码 |
| **pressure-test-generator** | generate_script.py/generate_yaml.py 用法、YAML 字段定义、输出文件规范、工作流 | 需要生成脚本或配置文件 |
| **pressure-test-bases** | Serial/CAN/Relay/Platform API/AT/Jlink/File 基础类模板和示例 | 需要编写/理解基础类代码 |
| **pressure-test-api-analyzer** | 从 HAR 文件或接口文档自动分析接口，生成适配 pressure-test 框架的 Platform API 基础类代码 | 接口自动化场景，用户提供了 HAR 文件或接口文档 |
| **pressure-test-uiautomation** | 基于 Python uiautomation 库，通过【规划→编码→测试→修复】迭代循环生成 Windows UI 自动化压力测试脚本，强制使用相对定位 | Windows 界面自动化场景，需要为 EPAT 等应用生成 UI 压力脚本 |
| **pressure-test-uiautomator** | 基于 uiautomator2 库，生成 Android UI 自动化压力测试脚本，支持相对定位、自动上溯可点击祖先、组合指令(run --json)、retry重试机制 | Android APP 自动化场景，需要为台铃APP、九号APP等生成 UI 压力脚本 |
| **pressure-test-webui** | 基于 Selenium WebDriver/Playwright 生成 Web UI 自动化压力测试脚本，支持多定位策略（CSS/XPath/text）、显式等待、截图取证、多标签页管理 | Web 界面自动化场景，需要为网页应用生成 UI 压力脚本 |

**使用方式**：当用户触发 pressure-test 时，先加载本入口 skill 了解架构，然后根据具体需求加载对应的子 skill。

## 触发场景

- 用户要创建新的压力/压测脚本（任何类型）
- 用户要生成或修改 device.yaml 配置
- 用户提供了业务类/方法，需要包装成可循环执行的压力脚本
- 用户提到 OTA升级压力、开关机压力、通信压力、接口压力等场景

## 覆盖的自动化类型

| 自动化类型 | 对应子 skill | 说明 |
|:---|:---|:---|
| 串口 | pressure-test-bases (Serial) | 串口通信基础类 |
| CAN | pressure-test-bases (CAN) | CAN 总线通信基础类 |
| CMD串口/子进程 | pressure-test-bases (CMD) | CMD 子进程逐字节读取基础类 |
| 接口自动化 | pressure-test-bases (Platform API) | 平台 API 调用基础类 |
| 继电器控制 | pressure-test-bases (Relay) | 电源控制基础类 |
| Jlink调试 | pressure-test-bases (Jlink) | 固件烧录/调试基础类 |
| web自动化 | pressure-test-webui | 基于 Selenium/Playwright 的 Web UI 自动化压力测试 |
| Windows界面自动化 | pressure-test-uiautomation | 基于 uiautomation 的 Windows UI 自动化压力测试 |
| uiautomator自动化 | pressure-test-uiautomator | 基于 uiautomator2 的 Android UI 自动化压力测试 |

## 注意事项

1. 配置文件固定命名为 `device.yaml`，脚本自动加载
2. 所有代码（基础类 + 超类 + 流程 + 主循环）在同一个 .py 文件中
3. 基础类代码由用户提供，子 skill 提供模板和设计规范
4. 生成的脚本可直接 `python xxx.py` 运行
