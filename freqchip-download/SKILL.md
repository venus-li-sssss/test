---
name: freqchip-download
description: 通过 FreqChip_Download_Consle.exe 命令行工具自动烧录固件到 FreqChip（富芮坤）芯片设备。支持选择串口号、串口速率、芯片型号，自动烧录和自动重启。当用户需要烧录 FreqChip 芯片、使用 FreqChip_Download 工具、或烧录 FR801XH/FR801XT/FR800X/FR508X/FR30XX/FR201X/FR303X/FR803X/EX-FLASH 等芯片时使用此 skill。
agent_created: true
---

# FreqChip Download

## Overview

使用 `FreqChip_Download_Consle.exe` 命令行工具通过串口自动烧录固件到 FreqChip（富芮坤）芯片设备。工具通过 `setting.ini` 配置文件读取参数，而非命令行参数。

## 工具路径

```
FREQCHIP_DIR = "D:/work/QDK007/FreqChip_Download V1.3.9/FreqChip_Download V1.3.9"
FREQCHIP_EXE = "D:/work/QDK007/FreqChip_Download V1.3.9/FreqChip_Download V1.3.9/FreqChip_Download_Consle.exe"
```

## 芯片型号对照表

每次烧录前必须让用户选择芯片型号。芯片型号决定 `Chip_Type` 和 `Flash_Select` 两个配置项：

| 序号 | 芯片型号 | Chip_Type | Flash_Select |
|------|----------|-----------|--------------|
| 1 | FR801XH | 801H | 512KB |
| 2 | FR801XT | 801T | 512KB |
| 3 | FR800X | 800X | 512KB |
| 4 | FR508X | 508X | 512KB |
| 5 | FR30XX | 509X | 2MB |
| 6 | FR201X | 201X | 2MB |
| 7 | FR303X | 101X | 1MB |
| 8 | EX-FLASH | ExternFlash | bin size |
| 9 | FR803X | 8030 | 512KB |

## 配置参数

`setting.ini` 文件包含以下配置项：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `uart_port` | 串口号（如 COM3、COM246） | 必须由用户选择 |
| `Baud_Rate` | 串口速率（如 115200、921600、460800） | 必须由用户选择 |
| `Chip_Type` | 芯片类型（见对照表） | 必须由用户选择 |
| `Flash_Select` | Flash 大小（见对照表） | 由芯片型号决定 |
| `Auto_Burn` | 自动烧录 | True（固定） |
| `Auto_Reset` | 自动重启 | True（固定） |
| `Flash_Allerase` | 整片擦除 | False（固定，不勾选） |

## 标准烧录流程

### 1. 收集参数

烧录前必须向用户确认以下三个参数，缺一不可：

- **串口号**：如 COM3、COM246 等
- **串口速率**：常用值有 115200、921600、460800
- **芯片型号**：从上述 9 个型号中选择

若用户未提供全部三个参数，必须使用 `AskUserQuestion` 询问缺少的参数，不得猜测或使用默认值。

若用户提供了芯片型号但未提供串口和速率，则一次性询问所有缺失参数。

### 2. 写入配置文件

收集到所有参数后，根据芯片型号对照表查找对应的 `Chip_Type` 和 `Flash_Select`，然后写入 `setting.ini`：

```ini
[CONFIG]
Chip_Type=<Chip_Type>
Flash_Select=<Flash_Select>
uart_port=<串口号>
Baud_Rate=<串口速率>
Auto_Burn=True
Auto_Reset=True
Flash_Allerase=False
```

使用 Write 工具写入配置文件。

### 3. 启动烧录

在 `FREQCHIP_DIR` 目录下运行 `FreqChip_Download_Consle.exe`。

由于烧录过程可能需要较长时间，使用 `run_in_background=true` 后台运行：

```bash
cd "<FREQCHIP_DIR>" && ./FreqChip_Download_Consle.exe
```

### 4. 等待系统通知

不要主动轮询 `TaskOutput`。系统会在后台任务完成后自动发送通知。

收到通知后，使用 `TaskOutput`（`block=false`）获取完整输出。

### 5. 检查烧录结果

在输出中查找以下关键信息判断烧录是否成功：

- 成功标志：输出中包含下载进度信息，最终正常退出
- 失败标志：输出中包含错误信息（如 "fail"、"error"、"timeout" 等）

### 6. 停止后台任务

烧录完成（无论成功或失败）后，必须使用 `TaskStop` 工具停止后台任务，避免 CMD 窗口残留。

### 7. 汇报结果

向用户汇报烧录结果摘要，包括：
- 串口号
- 串口速率
- 芯片型号
- 烧录是否成功
- 关键输出信息

## 注意事项

- 工具通过 `setting.ini` 读取配置，不通过命令行参数
- 烧录前必须确保 `setting.ini` 配置正确写入
- 烧录命令必须在后台运行（`run_in_background=true`）
- 烧录完成后务必调用 `TaskStop` 停止后台任务
- 不要在没有设备连接的情况下反复尝试烧录
- `Flash_Allerase` 始终为 False（不整片擦除）
- `Auto_Burn` 和 `Auto_Reset` 始终为 True
