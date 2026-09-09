---
name: aboot-flash
description: 通过命令行使用 adownload.exe 自动烧录固件包到 ASR 设备，支持自动检测 USB 设备、自动重启、烧录完成后自动停止后台任务。当用户需要烧录固件包（.zip）到设备、执行 aboot 烧录、或使用 adownload.exe 命令行烧录时使用此 skill。
agent_created: true
---

# Aboot Flash

## Overview

使用 `adownload.exe` 命令行工具自动烧录固件包到 ASR 设备（如 ML307C），支持 USB 自动检测、自动重启、烧录完成后自动停止后台任务。

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

## 标准烧录流程

### 1. 确认固件包存在

使用 `ls -la` 检查固件包 .zip 文件存在且大小合理。

### 2. 启动后台烧录

后台运行烧录命令，使用 `run_in_background=true`，设置 `timeout=600000`（10 分钟）：

```bash
"<ADOWNLOAD>" -a -u -s 921600 -r "<firmware.zip>"
```

若用户指定了串口，则用 `-p COMx` 替代 `-a -u`。

### 3. 通知用户重启设备

烧录命令启动后，会在后台等待设备连接。通知用户重启设备。

### 4. 等待系统通知

不要主动轮询 `TaskOutput`。系统会在后台任务完成后自动发送 `<task-notification>` 通知。

收到通知后，使用 `TaskOutput`（`block=false`）获取完整输出。

### 5. 检查烧录结果

在输出中查找以下关键信息：

- **成功标志**：`all finished. total time:` 行
- **进度**：`progress: 100` 表示完成
- **重启**：`processing command [reboot]` 行确认自动重启已执行

### 6. 停止后台任务

**烧录成功或失败后，必须立即停止后台任务**，避免 CMD 窗口残留。

使用 `TaskStop` 工具停止所有相关后台任务：

```json
{"task_id": "<task_id>"}
```

### 7. 汇报结果

向用户汇报烧录进度摘要，包括：
- 设备端口（COMx）
- 固件版本
- 总耗时
- 是否自动重启
- 烧录是否成功

## 注意事项

- 烧录命令必须在后台运行（`run_in_background=true`），因为烧录通常需要 10-30 秒
- 烧录完成后务必调用 `TaskStop` 停止后台任务，防止 CMD 窗口残留
- 如果用户要求先停止当前烧录，立即使用 `TaskStop` 停止
- 不要在没有设备连接的情况下反复尝试烧录
