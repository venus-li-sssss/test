---
description: 'Use this skill when the user wants to export DUMP logs via YMODEM protocol.
  Triggers: 导出DUMP日志, YMODEM接收dump, 串口dump导出, 接收dump文件, Dump Debug Port, 抓取dump, 拉取dump'
name: 导出DUMP日志
---

# 导出 DUMP 日志

通过 YMODEM 协议从设备 `Quectel USB Dump Debug Port` 自动接收 DUMP 日志文件。

## 工作原理

1. 设备触发 DUMP 后，会通过 USB 枚举出 `Quectel USB Dump Debug Port` 串口
2. 该 COM 口号每次可能不同（设备重启后 USB 重新枚举），但名称固定
3. 脚本自动扫描注册表找到该 COM 口，通过 YMODEM CRC 模式接收所有 dump 文件

## 执行

本 skill 提供 batch JSON 文件 `scripts/dump_log.json`。

**调用 `run_tool_batch` 时，使用 `file_path` 加载文件。不要自己构造 `actions` 列表。**

`run_tool_batch` 需要 **绝对路径** 的 `file_path`。使用你看到 SKILL.md 所在目录的绝对路径来构造完整路径。

```
run_tool_batch(
  file_path="<this skill dir>/scripts/dump_log.json",
  args={
    "com_port": "COM53",
    "output_dir": "D:\\QDM505 tool\\dump_logs",
    "skill_dir": "<this skill dir>"
  }
)
```

### Batch 参数

* `com_port`: COM 口号。可以留空让脚本自动识别 `Dump Debug Port`，也可以手动指定。示例：`COM53`
* `output_dir`: DUMP 文件保存目录。默认 `D:\QDM505 tool\dump_logs`
* `skill_dir`: skill 目录的绝对路径（从系统提示中获取）

### Batch 失败处理

如果 `run_tool_batch` 失败：
1. 先检查 `com_port` 是否正确（运行 `reg query HKLM\SYSTEM\CurrentControlSet\Enum\USB /s /f "Dump Debug Port"` 确认）
2. 如果自动识别失败，手动指定 `com_port` 重试
3. 如果仍然失败，使用下方"手动执行参考"逐步执行

### 手动执行参考

1. **识别 COM 口**（可选，脚本会自动识别）：
   ```
   reg query HKLM\SYSTEM\CurrentControlSet\Enum\USB /s /f "Dump Debug Port"
   ```
   找到类似 `Quectel USB Dump Debug Port (COM53)` 的行，提取 COM 口号

2. **创建保存目录**：
   ```
   mkdir "D:\QDM505 tool\dump_logs"
   ```

3. **运行接收脚本**：
   ```
   python <skill_dir>/scripts/ymodem_recv.py --com COM53 --output "D:\QDM505 tool\dump_logs"
   ```
   或自动识别 COM 口：
   ```
   python <skill_dir>/scripts/ymodem_recv.py --output "D:\QDM505 tool\dump_logs"
   ```

4. **等待传输完成**：脚本会显示接收进度，完成后列出所有文件

## QDM562 实测口径（DUMP 导出经验，2026-11）

| 项 | 实测值 |
|---|---|
| 接收端口 | `Quectel USB Dump Debug Port`（本机 COM53；**每次重启 USB 重新枚举，COM 号会变，只认名字**） |
| 波特率 | 115200 8N1，无流控 |
| 文件数 / 大小 | 约 15 个 `.bin` / 合计 ~4.6 MB |
| 耗时 | 6-7 分钟，有效吞吐 10-11 KB/s |
| 主镜像 | `com_DDR_RW.bin` ≈ 3,930,112 B（最大文件，里面能捞到 ICCID / IMEI / NB-4GECU 串，报告要 IMEI 从这里取，别拿别的样机顶替） |

其余常见：`com_PS_DAT.bin` / `com_DSP_DDR.bin` / `com_DSPdtcm.bin` / `com_ITCM.bin` / `com_DTCM.bin` …

### 抓之前必须先「让设备吐 dump」

脚本只是接收端，设备不发就一直等。QDM562 两种触发方式：

- **AT 口三连**（推荐，只要模组 USB 插着就能用）：`AT+QDUMPCFG=0,0` → `AT+QDUMPCFG=2,0` → `AT+LOG=19,1`，每条都要回 `OK`（关自动重启 + 打开 19 号 log 模块）；
- **上位机口 `5A A5` 帧**（需外挂 FTDI，没有上位机口时别发，发了必定无应答，别误判成设备故障）。

> AT 口和 Dump 口是两个不同的 COM：AT 口发配置，Dump 口收日志。

### 顺序（别搞反）

1. 先跑接收脚本，它在发 `C` 等 YMODEM 握手；
2. 再触发 dump（或断电重上电让设备自己 dump）；
3. 等 `Transfer complete!`，脚本自动列出收到的文件。

### 踩坑

- **COM 号会变**：脚本按名字扫注册表自动识别；识别不到再
  `reg query HKLM\SYSTEM\CurrentControlSet\Enum\USB /s /f "Dump Debug Port"` 手取。
- **结尾报 `PermissionError` 不影响文件**：设备发完就掉 USB、串口被系统回收，文件已落盘，**别重抓**。
- **串口打不开 = 有残留进程占口**：先 `Get-Process python | Stop-Process`（或关掉占口的串口工具）再重试。
- **传输中别断线、别关脚本**：YMODEM 无断点续传，断了从头发。
- DUMP 类 JIRA 单：严重等级 `A-Critical`、功能类别只填父级、备注走评论（口径见 `qdm562-project` skill）。

## 注意事项

- **设备必须先触发 DUMP**：脚本只是接收端，需要设备先开始发送（通常通过 AT 命令或固件自动触发）
- **COM 口会变**：设备重启后 USB 重新枚举，COM 口号可能变化，但 `Dump Debug Port` 名称不变
- **传输时间**：DUMP 文件可能很大（几 MB），传输需要几十秒到几分钟
- **不要中断**：传输过程中不要断开串口或关闭脚本

## 输出示例

```
YMODEM Receiver
COM Port: COM53
Baud Rate: 115200
Save Directory: D:\QDM505 tool\dump_logs

Waiting for device to send files...
Make sure the device has started the dump process.

Opened COM53 at 115200
Sending 'C' to start YMODEM CRC mode...
Receiving file: com_DDR_RW.bin
Saved: D:\QDM505 tool\dump_logs\com_DDR_RW.bin (3930112 bytes)
...
Transfer complete!

Total files received: 19
  - D:\QDM505 tool\dump_logs\com_DDR_RW.bin
  ...

✓ Transfer completed successfully!
```