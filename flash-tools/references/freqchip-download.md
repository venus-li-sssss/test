# FreqChip（富芮坤）芯片串口烧录

> 来源：GitHub `venus-li-sssss/test` 仓库的 `freqchip-download` skill（已合并入 flash-tools）。

## Overview

使用 `FreqChip_Download_Consle.exe` 命令行工具，通过串口自动烧录固件到 FreqChip（富芮坤）芯片设备。工具通过 **`setting.ini` 配置文件**读取参数，不走命令行参数。

## 工具路径

```
FREQCHIP_DIR = "D:/work/QDK007/FreqChip_Download V1.3.9/FreqChip_Download V1.3.9"
FREQCHIP_EXE = "D:/work/QDK007/FreqChip_Download V1.3.9/FreqChip_Download V1.3.9/FreqChip_Download_Consle.exe"
```

## 芯片型号对照表

每次烧录前必须让用户选择芯片型号。型号决定 `Chip_Type` 与 `Flash_Select`：

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

## setting.ini 配置项

| 参数 | 说明 | 默认/取值 |
|------|------|-----------|
| `uart_port` | 串口号（如 COM3、COM246） | 必须由用户指定 |
| `Baud_Rate` | 串口速率（115200 / 460800 / 921600 等） | 必须由用户指定 |
| `Chip_Type` | 芯片类型（见对照表） | 必须由用户指定 |
| `Flash_Select` | Flash 大小（见对照表） | 由芯片型号决定 |
| `Auto_Burn` | 自动烧录 | True（固定） |
| `Auto_Reset` | 自动重启 | True（固定） |
| `Flash_Allerase` | 整片擦除 | False（固定，不勾选） |

## 标准流程

1. **收集参数**（缺一不可，不得猜测）：
   - 串口号
   - 串口速率
   - 芯片型号（9 选 1）
   - 若用户只给了一部分 → 一次性问清所有缺失项
2. **写入 `setting.ini`**（先备份/读取原文件再改）：
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
3. **启动烧录**：在 `FREQCHIP_DIR` 下运行 exe。烧录耗时较长 → QuecAgent 中用足够大的 `timeout`（建议 600s+）前台执行，并把输出重定向到日志文件便于查看：
   ```
   cd /d "<FREQCHIP_DIR>" && FreqChip_Download_Consle.exe > flash_log.txt 2>&1
   ```
4. **查看输出**：读取日志/标准输出。
5. **判断结果**：
   - 成功：有下载进度信息，最终正常退出
   - 失败：出现 "fail"/"error"/"timeout" 等
6. **清理**：结束后确认控制台进程退出（必要时 `taskkill /IM FreqChip_Download_Consle.exe /F`）。
7. **汇报**：串口号、速率、芯片型号、是否成功、关键输出。

## 注意事项

- 工具只从 `setting.ini` 读配置，**不认命令行参数**
- 烧录前务必确认 `setting.ini` 已正确写入
- 不要在没有设备连接时反复尝试烧录
- `Flash_Allerase` 恒为 False（不整片擦除）；`Auto_Burn`/`Auto_Reset` 恒为 True
