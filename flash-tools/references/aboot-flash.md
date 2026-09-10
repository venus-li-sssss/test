# ASR 设备 aboot 烧录（adownload.exe）

> 来源：GitHub `venus-li-sssss/test` 仓库的 `aboot-flash` skill（已合并入 flash-tools）。

## Overview

使用 `adownload.exe`（Asrmicro aboot download console）自动烧录固件包到 **ASR / arom** 平台设备。
支持 arom USB 自动检测、串口下载、AT 命令回落下载、自动重启。

**两类场景，先对号入座：**

| 场景 | 特征 | 走哪节 |
|---|---|---|
| **A. 串口/USB 下载模式可达**（EVB、ML307C 等有下载键或已知串口） | 设备能被按键/复位进入下载模式，或明确指定 COM 口 | [标准流程](#标准流程场景-a) |
| **B. Quectel ASR 模块 USB 在线但无下载键**（如 EG800AK / QDM562） | 只枚举 Quectel USB 复合口（AT/DIAG/Modem），没有下载键 | [Quectel 模块变体](#变体场景-bquectel-asr-模块如-eg800ak--qdm562) |

> **怎么判断“是不是下载模式”**：下载模式下设备枚举为 `ASR Serial Download Device (COMx)`
> （VID_2ECC PID_3004，arom usb boot port）；正常跑应用时 Quectel 模块枚举为
> `Quectel USB AT Port / DIAG Port / Modem`（VID_2C7C PID_6002），**不是**下载模式。

## 工具路径

```
ADOWNLOAD = "D:/QDM505 tool/aboot tool/aboot-tools-2020.09.10-win-x64/aboot-tools-2020.09.10-win-x64/adownload.exe"
```

## 命令参数

| 参数 | 说明 |
|------|------|
| `-p, --port=COMx` | 指定串口（多个用逗号分隔）；也可用于 `-f` 发送 AT 的串口 |
| `-a, --auto-enable` | 自动启用 arom USB 端口设备 |
| `-u, --usb-only` | 仅使用 arom USB 端口 |
| `-f, --at-fallback` | 向 `-p` 指定串口发 AT 命令，使模块回落到下载模式 |
| `-q, --quit` | 任一端口完成后即退出（**强烈建议加**） |
| `-s, --speed` | 波特率（常用 921600；支持 115200/230400/460800/921600/1842000/3686400） |
| `-r, --reboot` | 烧录完成后自动重启设备 |
| `-m, --production` | 量产模式（默认是升级模式；`productionOnly` 命令仅量产模式执行） |
| `-d, --dump-enable` | 打印下载协议包（排障用） |

## 标准流程（场景 A）

1. **确认固件包**：`.zip` 存在且大小合理；根目录应有 `download.json` + 各镜像。
   *双层 zip 时用内层那个。*
2. **确认工具可运行**：必须在 adownload.exe **自身目录**下执行（依赖同目录 `config/`、`drivers/`），
   否则会秒退且无输出。
3. **启动烧录**（建议加 `-q`，输出重定向到日志）：
   ```
   cd /d "<工具目录>"
   adownload.exe -u -a -q -s 921600 -r "<firmware.zip>" > aboot_log.txt 2>&1
   ```
   用户指定串口时用 `-p COMx` 替代 `-a -u`。
4. **等待设备**：命令会等设备进入下载模式，需提示用户上电/复位/进入下载模式。
   - QuecAgent：`execute_shell_command` 给足 `timeout`（建议 300–600s）。
5. **看输出判断结果**（日志或 stdout）：
   - 成功：`all finished. total time: <n>s`；`"status" : "SUCCEEDED"`；`progress : 100`；
     `processing command [reboot]`（确认自动重启）；进程退出码 0。
   - 失败：卡在某进度（如 96%）后无输出 → 多为工具未退出被超时杀掉 / 设备掉线。
6. **清理**：确认无残留进程（必要时 `taskkill /IM adownload.exe /F`）。
7. **核对版本 + 汇报**：设备起来后读回版本确认；汇报端口（COMx）、固件版本、总耗时、是否重启、成功与否。

## 变体（场景 B：Quectel ASR 模块，如 EG800AK / QDM562）

模块正常跑应用时**不**处于下载模式，也没有下载键，用 `-f` 让工具发 AT 命令把它切进下载模式。

1. **找 AT 口**：设备管理器里 `Quectel USB AT Port (COMx)`。
2. **进下载模式 + 烧录**（工具会依次发 `AT$MYDOWNLOAD=1` 和 `AT+QDOWNLOAD=1`，Quectel 认后者）：
   ```
   cd /d "<工具目录>"
   adownload.exe -p COM22 -a -f -q -s 921600 -r "<内层zip>" > aboot_log.txt 2>&1
   ```
   AT 口会消失、枚举出 `ASR Serial Download Device (COM12)`，工具自动接管。
3. **重刷**（设备已在下载模式时）不需要 `-p/-f`：
   ```
   adownload.exe -u -a -q -s 921600 -r "<内层zip>"
   ```
3b. **⚠️ 若 `-p COMx -a -f` 一启动就崩**（退出码 `3221225477` / `-1073741819` = `0xC0000005` 访问违例，
   连 `parsing command line paramters ...` 都不打印，而 `adownload.exe --help` 正常）——
   这是 AT-fallback 代码路径在部分环境下的偶发崩溃。**改用两步法绕开**（更稳，推荐直接用这个）：
   ```
   :: ① 自己用串口发 AT 命令切下载模式（pyserial 等）
   python -c "import serial,time; s=serial.Serial('COMx',115200,timeout=1.5); s.write(b'AT+QDOWNLOAD=1\r\n'); time.sleep(1); s.close()"
   :: ② 等设备枚举出 ASR Serial Download Device 后，纯 USB 模式烧录
   cd /d "<工具目录>" && adownload.exe -u -a -q -s 921600 -r "<内层zip>"
   ```
   （`AT+QDOWNLOAD=1` 发出后模块立即复位，AT 口的返回读不到属正常，看设备管理器是否出现下载口即可。）
4. **⚠️ 烧完必须物理断电重上电**：`-r` 只复位芯片，模块会再次落回 Rom 下载循环（下载标志未清），
   拔插 USB / 断电重上电后才启动新固件。
   - 软件复位**无效**：`Disable-PnpDevice`（常规故障）、`pnputil /restart-device`（拒绝访问，需管理员）、
     COM 口 DTR/RTS 脉冲（对 Rom 无影响）——`pnputil` 需管理员，别指望它。
5. **核对版本**：对 AT 口（115200）发 `ATI`，看 `CustRevision`，例如：
   ```
   ATI
   -> Quectel
      EG800AKCN_91LC
      Revision: LTE01R07A13_C_SDK_A
      CustRevision:LTE01R07A13_C_SDK_A_SDK_QDM562_NINEBOT_01.001.01.004_BETA260903
   ```
   （`AT+QGMR` 在该固件返回 ERROR，别用它判断。）

## 注意事项

- 烧录通常 10–40 秒（USB 下载），串口下载更慢；务必留足超时时间
- **加 `-q`**：不带时工具烧完不退出（一直等新设备），会被外层命令超时杀掉 → 可能中断在收尾阶段
- 结束时必须清理进程，避免 CMD 窗口残留
- 用户要求停止烧录时，立即结束进程
- 不要在没有设备连接时反复尝试烧录；报错先读日志定位
- **不要只看“工具报成功”**：场景 B 一定要核对 `CustRevision` 并确认已断电重启

## 实战记录（2026-09-10，EG800AK / QDM562，两台设备）

- 目标：`LTE01R07A13_C_SDK_A_SDK_QDM562_NINEBOT_01.001.01.004_BETA260903`（网盘 → 本地双层 zip）

**设备 1**（AT=COM22，原固件 `EG800AKCN91LCR97A02M04`，IMEI 865964082011124）
- 命令：`adownload.exe -p COM22 -a -f -q -s 921600 -r "<内层zip>"`
- 结果：`all finished. total time: 34.383s` / `SUCCEEDED` / 退出码 0 → 断电重上电 → `ATI` 确认
  `CustRevision` 与目标一致 ✅
- 踩坑：首次未加 `-q`，工具烧完不退出被超时杀掉，中断在 96%；重刷即成功。

**设备 2**（AT=COM25，原固件 `LTE01R07A03_BT_C_SDK_A` / `..._QDM562CNAK_01.001.01.001_V03`，IMEI 864107084093341）
- `-p COM25 -a -f -q` **直接崩**（`0xC0000005`），重试仍崩 → 改用两步法：
  先 pyserial 发 `AT+QDOWNLOAD=1` 切下载模式，再 `adownload.exe -u -a -q -s 921600 -r "<内层zip>"`
- 结果：`all finished. total time: 37.058s` / `SUCCEEDED` ✅ → 断电重上电后验证版本

**结论：优先用「先发 AT+QDOWNLOAD=1，再 `-u -a -q` 纯 USB 烧录」的两步法，比 `-p -a -f` 稳。**
