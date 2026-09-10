# ASR 设备 aboot 烧录（adownload.exe）

> 来源：GitHub `venus-li-sssss/test` 仓库的 `aboot-flash` skill（已合并入 flash-tools）。

## Overview

使用 `adownload.exe` 命令行工具自动烧录固件包到 ASR 设备（如 **ML307C**）：支持 USB 自动检测、自动重启、烧录完成后清理后台任务。

## 工具路径

```
ADOWNLOAD = "D:/QDM505 tool/aboot tool/aboot-tools-2020.09.10-win-x64/aboot-tools-2020.09.10-win-x64/adownload.exe"
```

## 命令参数

| 参数 | 说明 |
|------|------|
| `-a, --auto-enable` | 自动启用 arom USB 设备 |
| `-u, --usb-only` | 仅使用 arom USB 端口 |
| `-s, --speed` | 波特率（常用 921600） |
| `-r, --reboot` | 烧录完成后自动重启设备 |
| `-m, --production` | 量产模式（默认是升级模式） |
| `-p, --port=COMx` | 指定串口（替代 `-a -u`） |

## 标准流程

1. **确认固件包存在**：检查 `.zip` 固件文件存在且大小合理。
2. **启动烧录**：
   ```
   "<ADOWNLOAD>" -a -u -s 921600 -r "<firmware.zip>"
   ```
   用户指定串口时用 `-p COMx` 替代 `-a -u`。
   - QuecAgent：给 `execute_shell_command` 设大 `timeout`（建议 600s），或重定向日志到文件后轮询：
     ```
     "<ADOWNLOAD>" -a -u -s 921600 -r "<firmware.zip>" > aboot_log.txt 2>&1
     ```
3. **通知用户重启设备**：命令会等待设备连接，需提示用户重启/上电设备。
4. **查看输出**（日志文件或 stdout）。
5. **判断结果**：
   - 成功标志：`all finished. total time:` 行；`progress: 100`；`processing command [reboot]`（确认自动重启）
6. **清理**：烧录成功或失败后立即结束后台进程，避免 CMD 窗口残留（`taskkill /IM adownload.exe /F`）。
7. **汇报**：设备端口（COMx）、固件版本、总耗时、是否自动重启、是否成功。

## 注意事项

- 烧录通常需要 10–30 秒，务必留足超时时间
- 结束时必须清理进程，防止 CMD 窗口残留
- 用户要求停止烧录时，立即结束进程
- 不要在没有设备连接时反复尝试烧录
