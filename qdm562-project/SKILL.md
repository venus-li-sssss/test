---
name: qdm562-project
description: QDM562（云盒/中控，ASR1602S 九号平台）项目测试知识中枢。用在：QDM562 怎么认串口/哪个 COM 是什么口、**AT 口发 DUMP（`AT+QDUMPCFG=0,0` / `AT+QDUMPCFG=2,0` / `AT+LOG=19,1`）查版本**、上位机升级压测怎么搭和怎么跑、平台开关机找网装置怎么跑（继电器+COM27 debug+COM29 日志+COM25 5A A5 DUMP）、升级后怎么查 GNSS 版本号（Build19128 / Build27526）、ATI 报 764 但实际是 0765 怎么办、debug 日志抓不到/抓取工具没在跑、上位机 5A A5 发了没回帧、差分包该拿哪个、电脑不锁屏怎么设。触发词：QDM562、云盒、中控、上位机升级、查 GNSS、GNSS 版本号、认串口、COM22/COM25/COM27/COM29/COM3/COM184、debug 口、DUMP、AT+QDUMPCFG、AT+LOG、5A A5、0765、0766、Build19128、开关机找网、压测脚本、不锁屏。
---

# QDM562 项目测试知识

云盒/中控项目，模组 EG800AKCN_91LC（ASR1602S），客户九号。本文是**实测沉淀**，不是文档摘抄；每条结论都标了怎么验证。

## 1. 先认口：QDM562 五个口分别是什么

| 口 | 设备名 | 是什么 | 谁在用 | 平时有没有数据 |
|---|---|---|---|---|
| `COM3` | `USB Serial Port (COM3)` | **debug 口**（USB-232 转接） | 日志抓取（人工 debug 用） | 静默；只有**重启/升级**才打印 |
| `COM29` | `Quectel USB MI05 COM Port` | **串口日志口**（AT/LOG 混合通道） | 升级脚本独占（`gnss_com`） | 一直有：`Monitor` / `LOC` / `$NAVVEL` / `$PDTINFO` / `FWVer` |
| `COM31` | `Quectel USB DIAG Port` | **DIAG 口** | CATStudio 抓 CAT LOG | 有，但被 CATStudio 占时别的程序打不开 |
| `COM32` | `Quectel USB AT Port` | **AT 口** | 敲 AT 指令（`ATI` / `AT+QGMR` / DUMP 配置三连，见 §1.1） | 只在你查询时回 |
| `COM184` | `USB Serial Port (COM184)` | **上位机口**（5A A5 协议） | 上位机 GUI / 压测脚本 | 未升级前设备**不回 ACK**，rx 常年 0 属正常 |
| `COM30` | `Quectel USB Modem` | Modem 口 | 用不到 | — |

### 当前治具实测（2026-11-20，带回继电器的整套环境）

换机器后 COM 号会变，**这张表只是当前这台机器的实况，换机必须重新认口**：

| 口 | 是什么 | 判据（实测） |
|---|---|---|
| `COM22` | 继电器板（CH340，9600） | 不是串口日志；`A0|通道|状态|校验`，NC 接法下状态 1=断电 |
| `COM25` | **上位机口**（FTDI AB8LW2TFA，115200） | 发 `5A A5 01 3E 09 01 02 02 B2 FF`，回 `5A A5 02 09 3E 04 02 65 07 44 FF`，data `65 07`=**0765** |
| `COM27` | **debug 口**（FTDI AF25870FA，115200） | 平时全静默；断上电后打出 `[quec_uart_open][416]` / `$RESET` / `$PDTINFO` |
| `COM28` | AT 口 | 敲 AT 才回 |
| `COM29` | **串口日志口** | 一直刷 `Monitor`/`LOC`，含 `ver:0765`、`FWVer N1000R3.42.1.3269Build21450` |
| `COM30` | Modem | 用不到 |
| `COM31` | DIAG 口 | 一开就刷二进制 CAT 数据 |

**版本号确认的最快路径（不用 GUI）**：向上位机口发 `5A A5 01 3E 09 01 02 02 B2 FF`，应答帧的第 7-8 字节 `65 07` 就是 0x0765；同时串口日志口一直刷 `ver:0765`，两条可交叉验证。
**没有上位机口时别去找 5A A5**：走 AT 口发 DUMP 配置三连（§1.1），AT 口是模组自己枚举的、插上就有。
抓开机日志的通道：继电器断电 2s → 上电，同时用 115200 抓 `COM27`（debug）+ `COM29`（日志，断电会掉枚举，需重连重试）。

### 1.1 AT 口查 DUMP/版本（2026-11-21 实测，AT 指令口径）

`DUMP` 有两种承载：**上位机口**是 `5A A5` 帧（需要外挂 FTDI），**AT 口**是下面这三条 AT 指令（只要模组 USB 插着就可用，现场最省事）。别看到 "DUMP" 就默认去上位机口（2026-11-23 在只有 debug FTDI 的机器上误发 5A A5，两轮全无应答、白等一场）。

| 指令 | 实测回显 | 说明 |
|---|---|---|
| `AT+QDUMPCFG=0,0` | `OK` | DUMP 配置第一组 |
| `AT+QDUMPCFG=2,0` | `OK` | DUMP 配置第二组 |
| `AT+LOG=19,1` | `OK` | 打开 19 号 log 模块 |

- 发完这三条，**AT 口本身静默**（不会把版本回在 AT 口）；版本照样以串口日志口的 `ver:xxxx` / `FWVer ...BuildNNNNN` 为准（`0766` → `Build27526`）。
- 波特率 115200，8N1，无流控；每条之间留 1 s 以上。
- 反面教材（已实测，别浪费时间）：本固件 `AT+CLAC` 返回空；`AT+QDUMP` / `AT+QDUMP?` / `AT%DUMP` / `AT+QDUMPVER` / `AT+QVERSION?` / `AT+VER?` / `AT+QVER?` 全部 `ERROR`。`AT+QGMR` 只回 `LTE01R07A05_BT_C_SDK_A`，没有 `06xx` 编号。
- `ATI` 的 `CustRevision ..._764` 是历史遗留串；烧完 766 后本机实测变成 `..._766`，但仍要拿日志口 `ver:` 交叉验证，别单点采信。

### 三步认口法（换机器/换治具照做）

1. **看设备名**：`Quectel USB xxx` 是模组自身枚举出来的（AT / DIAG / MI05 / Modem）；`USB Serial Port` 是外接 USB-232 转接器（debug 口、上位机口都属这类，**长得一样，只能靠下一步区分**）。
2. **对版本串**：AT 口读 `ATI` → `EG800AKCN_91LC` + `CustRevision ... _764`；串口日志口能看到 `ver:0765`。
3. **抓一次开机日志**：给设备断电重上电，谁在打 `$PDTINFO` / `FWVer` / `Monitor` → 那就是串口日志口（`COM29`）；完全没输出但设备确实在跑 → 那是 debug 口（`COM3`）。
4. 上位机口（`COM184`）判据：往里发 `5A A5 01 3E 09 01 02 02 B2 FF`，**串口日志口立刻出现** `_5AA5 Receive 5AA5 cmd:len:1,src:3e,dst:9,cmd:1,index:2,data:2.` → 这个口就是上位机口。

> 自动自检：`python scripts/port_probe.py`，它会枚举端口、分类、写版本帧、读日志口求证，最后打印建议写进 device.yaml 的值。

## 2. 上位机升级压测怎么搭

脚本与配置已落地在本机：`D:\QDM562\脚本\上位机升级(查GNSS版本)\`
（云盘权威副本在「压测脚本网盘」→ 产品线 → QDM562 → `QDM562_主分支_上位机升级压测`）

```
QDM562上位机升级_V3.1_gnss可选.py   # 主脚本
device.yaml                          # 端口/日志/GNSS/升级包路径
启动压测.bat                          # 双击跑，屏幕+文件双写
运行日志\ / runlog\                    # bat 落盘的完整输出
检查端口.py                            # 认口自检
环境说明.md                            # 本机现状与改动记录
```

`device.yaml` 关键字段（QDM562 + 本机实测值）：

```yaml
COM: COM184                  # 上位机口（脚本通过 GUI 选口）
check_gnss: True             # 升级后校验 GNSS 版本
gnss_com: COM29              # GNSS/版本日志来源
gnss_capture_port: COM29     # 抓取工具实际抓的口（原脚本写死 com48，本机必须改）
gnss_capture_mode: exe       # exe=日志抓取.exe；python=gnss_capture.py
gnss_capture_exe: C:/QDM562/日志抓取/日志抓取.exe   # 只能放 C 盘
gnss_log_dir: C:/QDM562/gnss_log                    # 纯英文路径
des_firmware_path: D:/QDM562/脚本/上位机升级/QDM562_diff_upgrade_765_to_766.bin
soc_firmware_path: D:/QDM562/脚本/上位机升级/QDM562_diff_rollback_766_to_765.bin
0765_gnss_build_version: Build19128
0766_gnss_build_version: Build27526
```

启动：

```bat
:: 方式 A：自己的 CMD（异常/退出码最原始）
cd /d D:\QDM562\脚本\上位机升级(查GNSS版本)
"C:\Users\DELL\AppData\Local\Programs\Python\Python310\python.exe" -u "QDM562上位机升级_V3.1_gnss可选.py"

:: 方式 B：双击 启动压测.bat（屏幕+runlog 双写，Ctrl+C 后窗口不关）
```

参数：`--no-gnss` 关掉版本校验；`--gnss-com COM29` 临时换口；`--gnss-build Build27526` 覆盖对照值。

## 3. 升级后怎么查 GNSS 版本号（本项目的核心校验）

- 原理：升级完设备重启，串口日志口会打
  `$PDTINFO,CC0058Q-01,G1B1,V2.0,R2001R3.3.3.0Build19128,N/A,N/A*0A` 和 `FWVer R2001R3.3.3.0Build19128`，芯片 `CC0058Q-01`。
- 对照口径：**0765 → Build19128**，**0766 → Build27526**（脚本按当前 `des/soc` 版本自动取对照项）。
- 脚本行为：升级前先 `日志抓取.exe /killall:qdm562cap` 清残留 → 自己拉起抓取抓 `COM29` → 升级 → 读抓下来的 `comNN_*.log` 找 Build 号 → 比对 → 结束后 kill。
- 坑：V3.1 原脚本把文件名写死 `com48_*.log`（作者机器上的口）。本机是 `com29_*.log`，不改就永远读不到版本。修法：匹配改成按配置生成 `comNN_*.log` + 兜底 `com*_*.log`；时间戳正则改 `com\d+_(\d{8})_(\d{6})`。

## 4. 版本号对不上：ATI 报 764，实际是 0765

- `ATI` 回 `CustRevision ... SDK_QDM562CNAK_01.001.001_764`，但设备真实版本要**以串口日志里的 `ver:0765` 为准**。
- 所以：不要按 ATI 的数字去挑差分包/对照 GNSS Build，否则包和对照表全错。
- 现场口径（客户/项目确认过）：ATI 这个 764 是历史遗留串，本轮**不升版本、不烧录**，只做环境与脚本验证。

## 5. 抓 debug 日志：怎么判断"真的在抓"

- **别看文件大小**。debug 口（COM3）平时完全静默，`com3_*.log` 长时间 0 字节是正常的；
  判活在跑看状态文件 `C:\QDM562\debug_log\st.json`：`state=running`、`pid`、`targets[].state=● 已连接`、`updated_at` 在刷新。
- 实例名必须分开：脚本用 `qdm562cap`，人工抓用 `qdm562debug`（或 `ai1`）。
  `/killall:X` 只清**同名**实例，清不掉别人的。
- 同一串口独占：脚本和 GUI 抢同一个口，必然有一方打不开（打不开的表现是"一直红字重试"）。
  QDM562 的分工：`COM29` 永远给脚本；`COM3` 给 debug 抓取；`COM184` 给上位机。
- 弹窗：`/run` 抓取不弹窗，`/auto` 才会把窗口显示出来给人看。要"看得见"就用 `/auto`。
- `exe` 只能放 C 盘，放 D 盘/桌面会被 Bitdefender 删掉。

## 6. bat 启动脚本的两个硬坑（含中文括号路径必看）

1. **路径里有括号**（如 `上位机升级(查GNSS版本)`）时，**不能**写
   `if not exist "%SCRIPT%" ( ... )` —— cmd 会把路径里的 `)` 当成代码块结束，直接
   `\xxx.py was unexpected at this time`。改用 `if not exist ... goto :errxxx`。
2. **bat 里写中文提示 + `chcp 65001`** 会被拆成一堆 `'xxx' is not recognized`。
   提示文字写英文，中文只让 python 输出（屏幕和落盘都正常）。
3. 想"屏幕看得见 + 文件留档"：`python -u "x.py" %* 2>&1 | powershell -NoProfile -Command "$input | Tee-Object -FilePath 'runlog\run.log'"`。
   实测是流式双写（日志每秒增长），异常栈两处都有。
4. Ctrl+C：控制台把中断发给同控制台的进程，python 打 `KeyboardInterrupt` 后退出，bat 继续收尾并 `pause`，窗口不关；收尾里顺手 `/killall:qdm562cap`，避免残留抓取实例占着 COM29。

## 7. 烧录铁律（QDM562 专属，其他项目照常全烧）

- 设备上**只要有版本**就不烧客户信息区 `customer_fs`（256KB @0x395000）和 `ext_flash`（3MB @0x100000）；只有全新裸板/整片擦除/换过 flash 才全量。
- 分区清单一律以**包内 `download.json`** 为准（每个固件不同），跳过实现见 `flash-tools` 的 `scripts/aboot_skip.py`。
- 优先 `AT+QDOWNLOAD=1` + `adownload.exe -u -a -q -s 921600 -r <zip>`；**烧完必须物理断电重上电**。

## 8. 免锁屏（跑长压测必备）

已验证的组合（缺一项都可能被锁）：

```powershell
powercfg /change monitor-timeout-ac 0 ; powercfg /change monitor-timeout-dc 0
powercfg /change standby-timeout-ac 0 ; powercfg /change standby-timeout-dc 0
powercfg /change hibernate-timeout-ac 0; powercfg /change hibernate-timeout-dc 0
# 再关掉 VIDEOIDLE / VIDEOCONLOCK / STANDBYIDLE / HIBERNATEIDLE
# 注册表 HKCU\Control Panel\Desktop: ScreenSaveActive=0 / ScreenSaveTimeOut=0 / ScreenSaverIsSecure=0
# 工具 C:\QDM562\防锁屏\防锁屏F15.exe 放 HKCU\...\CurrentVersion\Run 开机自启（每 30s 发 F15）
```

## 9. 差分包

云盘「升级包」→ QDM562 → 差分包：`QDM562_diff_upgrade_765_to_766.bin`（约 126,976 B）、`QDM562_diff_rollback_766_to_765.bin`（约 125,952 B）。
搜不到时注意：云盘搜索会**把 query 截断到 30 字符**，长文件名要用短关键词（如 `rollback_766`）。

## 10. 详细资料

- `references/串口辨识.md` —— 每个口的实测证据、判据、换机流程
- `references/上位机升级压测.md` —— 5A A5 帧、GUI 操作、脚本流程、日志三件套
- `references/环境与踩坑.md` —— 本次从零搭环境踩过的全部坑与验证方法
- `references/平台开关机找网装置.md` —— 开关机找网装置（`D:\QDM562\平台开关机找网`）：双日志抓取、DUMP 版本帧、继电器 NC 指令、掉枚举重连等踩坑
- `scripts/port_probe.py` —— 认口自检脚本

## 11. 平台开关机找网装置（D:\QDM562\平台开关机找网）

继电器断上电 + 双日志（COM27 debug + COM29 日志）+ 上位机 DUMP 版本，装置已落地在本机 D 盘。

**抓日志只用官方带界面工具（用户明确要求"要界面的"，别再自写 python 抓串口）**

- 工具实体：`C:\QuecAgentTools\串口日志抓取\串口日志抓取.exe`（v3.8，窗口标题「串口日志抓取 v3.8 —— 多串口 + RTT(J-Link) / 16进制 / 命令行」）。**exe 只能放 C 盘**，放 D 盘/桌面/`%TEMP%` 会被 Bitdefender 执行瞬间删除。
- 官方脚手架：`C:\QuecAgentTools\日志抓取\scripts\capture_serial_log.py`（源 `https://raw.githubusercontent.com/venus-li-sssss/test/main/日志抓取/scripts/capture_serial_log.py`，匿名可下）。`--ensure-tool-only` 先查本机、没有才从云盘拉；`--refresh-tool` 强更。
- **一条命令常驻双口抓**（不给 `--sec` 就是常驻，禁止短抓试探）：
  `python capture_serial_log.py --targets "debug|COM27|115200|text;serial|COM29|115200|text" --instance qdm562 --live-dir "D:\QDM562\平台开关机找网\日志\live" --launch`
  `--status` 查状态、`--stop` 停（只杀这一路，不动用户手开的窗口）。换波特率/换口 = 重开这一异常驻，不是短抓。
- **`status.json` 在 `--live-dir` 里，不在工具目录**（本机实测：`工具目录\status.json` 不存在会误判"没在跑"）。每秒刷新，判活看 `totals.bytes`/每 target 的 `bytes`、`connected`、`reconnects`；磁盘 `.log` 和 `current_size` 为 0 是**带缓冲写**，别当死。
- 工具自带掉枚举重连：断电瞬间 COM29 掉枚举，工具自己找回，实测 `serial reconnects=1` 后照常抓到 132KB，无需人工干预。
- 启动后确认有窗口：`Get-Process 串口日志抓取 | Select MainWindowTitle`，应回「串口日志抓取 v3.8 …」，空标题=headless（用户看不到界面）。

- **四个口的分工**：`COM22` 继电器（9600，`A0|通道|状态|校验`，NC 下 1=断电）；`COM25` 上位机（115200，5A A5）；`COM27` debug（115200，静默/开机才打）；`COM29` 日志（一直刷 `ver:0765`）。
- **DUMP 帧**：发 `5A A5 01 3E 09 01 02 02 B2 FF`，应答 `5A A5 02 09 3E 04 02 65 07 44 FF`，版本 = data 两字节**反序**（`65 07` → **0765**）。心跳 `5A A5 00 09 01 7B 00 7A FF` 不是应答。
  **没有上位机口别发这帧**（发了必定无应答，别误判成设备故障），改发 AT 口三连：`AT+QDUMPCFG=0,0` / `AT+QDUMPCFG=2,0` / `AT+LOG=19,1`，口径见 §1.1。
- **必须两个日志都抓**：debug 口只有断上电/升级才打印（判活看 `CHIP_ID`/`$RESET`/`PlatInfo`，不看字节数）；日志口一直刷但**断电瞬间会掉枚举**，`read()` 会抛 `ClearCommError PermissionError(13)`，必须 catch 后按 hwid `2C7C` 找回（排除 AT/DIAG/Modem），否则线程静默死掉、日志只有半截。
- **DUMP 时机**：上电后等 6s，再每 1.5s 重发，窗口 14s；太早发（3s 内）一定没应答。
- **跑法分工**：日志 = 上面官方 exe 双口常驻；继电器断上电 + DUMP 取版本用 `D:\QDM562\平台开关机找网\一轮_继电器与DUMP.py`（一轮：断电2s→上电→等6s→COM25 发 DUMP，实测 17:27 断电 `A0 01 01 A2` / 上电 `A0 01 00 A1`，DUMP 应答 `5A A5 02 09 3E 04 02 65 07 44 FF` → **0765**）。平台判定由 `qdm562_平台开关机脚本_V01.py` 负责（需内网代理）。
- 自写 `开关机找网抓取.py` 仅作**无界面批量轮次**的备用手段（继电器+双口+DUMP 一体、`--cycles 0` 无限轮）；默认不要用它替代官方工具抓日志。
- **启动三铁律**：① python 必须用绝对路径 `C:\Users\DELL\AppData\Local\Programs\Python\Python39\python.exe`（PATH 首个 `python` 是 LarkShell 沙箱运行时，cmd/bat 里会找不到或没装 pyserial，表现就是"工具没在运行"）；② **只开一个抓取实例**，COM27/COM29 独占，多开会互抢；③ 判活看 `status.json` 的 `bytes` 是否持续涨，别按秒判死。
- **业务失败即停 / 运行异常重试不停**（2026-11-20 已改代码并实测，用户两次明确要求）：
  - 两类失败要分开：**业务判定失败**（201 上线超时、平台明确回非 200）= 真失败，`fail_continue: 0` 时**立刻停**；**运行异常**（登录失败、token 失效、代理掉线、平台查询抛错、脚本自身抛异常）= 环境问题，**重试、继续跑，绝不停脚本**。
  - `device.yaml` 三个旋钮：`login_retry: 3`（登录失败重试次数，间隔 `login_retry_interval: 5` 秒）；`max_consecutive_errors: 0`（**0 = 连续异常永不停**，推荐；填 N 则连续 N 轮异常才兜底停，用于无人值守防刷日志）。
  - 实现要点：`PlatformClient.login` = 带重试包装 → `_login_once`；`run_cycle` 平台查询抛错返回 `404 + abortable: False`（不当业务失败）；`Device.run()` 里 `AuthenticationError` / `PlatformError` / 通用 `Exception` 全部 `abortable: False` + `consecutive_errors += 1`（200 时清零），只有超 `max_consecutive_errors` 才 `fatal`；**break 只剩三种**：`fatal` / `abortable 且非 200 且 fail_continue=0` / 跑满 `cycles`。
  - **启动阶段也不许一失败就退**：`resolve_with_retry()` 把首次登录/设备解析包进重试（`max_consecutive_errors` 次，0 则兜底 20 次≈100 秒），代理瞬时掉线能自愈；`--check-platform` 只重试 `login_retry` 次（人工查询要快失败）。
  - 证据（`log\2026_11_20_19_23_13_526194\`）：`异常不停_控制流测试.txt`（登录失效×3 轮不停 / 脚本异常×3 轮不停 / `max_consecutive_errors: 2` 时第 2 轮兜底停 / 业务 201 在 `fail_continue: 0` 下仍只跑 1 轮，4 项全 PASS）；`回归_正常1轮_200.txt`（真机 1 轮 200、成功率 100%）。回归脚本 `test_异常不停.py`（纯 stub，不碰继电器，改完代码先跑它）。
- **失败即停（业务侧，当前配置）**：`fail_continue: 0` = 真业务失败（201 超时 / 平台明确非 200）立刻停止整个跑测；退出前继电器保持"上电"态，现场日志留在 `log\<时间戳>\`。实测：`cycles: 3` + `check_timeout: 6` → 第 1 轮 201 后结束，`运行次数=1`、失败 1、成功率 0%，没跑第 2/3 轮。要改"失败继续"写 `1`。
- 基线（2026-11-20 实测）：DUMP=0765、`ver:0765`、debug≈12.9KB/轮、日志≈50.8KB/轮、IMEI `866462081737442`。

## 12. 连九号平台（SOCKS5 1080 隧道）——平台判 PASS 的前提（已跑通）

平台 `iot-test.ninebot.com`（解析到内网 10.67.240.19）只有走这条隧道才通。

**认准导航卡片里的官方 bat，别自己造**（用户原话："导航页面拉一下 bat"）：
- 导航「客户网址 → 九号平台」卡片的 `skill:` 里写着云盘目录 `FJmxfeR5PlTaZxdawlKc0ukpnuf`（「资源·九号内网代理」），里面就两个文件：
  - `连接九号内网_V01.bat` token `YVdObkwyMoKqSHxEYgicGlkAnEh` —— **正式隧道脚本**
  - `脚本连接内网.bat` token `FNuHbOjZco5zULxMScsc6aG9nne` —— 设 `HTTP(S)_PROXY=socks5://127.0.0.1:1080` 再跑脚本的模板
- 拉取：`lark-cli drive +download --file-token <token> --output "D:\QDM562\平台开关机找网\<name>.bat" --overwrite`
- **跳板机 IP 是 `10.99.80.246`（不是文档里的 10.99.82.46！）**，用户/密码 `ninebot\jhdk` / `ninebot-9`；官方 bat 里用 `SSH_ASKPASS` 自动喂密码（免手输）、`RETRY=5` 掉线 5 秒自动重连、`chcp 936`，参数带 `PreferredAuthentications=password`、`ExitOnForwardFailure`、`ServerAliveInterval=15`。
- **实测（2026-11-20）**：`10.99.80.246:22` TCP 通 → 起 bat 后 `127.0.0.1:1080 LISTENING`（ssh 进程在）→ `curl --socks5-hostname 127.0.0.1:1080 https://iot-test.ninebot.com/` 返回 **200 / 1.38s**。
- **平台判定随之跑通**：`--check-platform` 出 `SN=NFDBF2420J0080, 产品标识=9YB5Vyi8, 平台设备ID=1005539, 设备标识=866462081737442`；`--cycles 1` → 断电→上电→等上线记录，**状态码 200，上线耗时 10.5 秒，成功率 100%**（405→只有 200）。
- 论文档里那条 `ssh -D 1080 ninebot\jhdk@10.99.82.46`（「九号平台代理环境搭建」docx `FnmRd6o34oJ2X5xrsXnchx3cn3s` / 「代理环境搭建」docx `EZJFd8Uvfoyj4RxxzbZcqeaWnEc`）是旧 G3 机器的写法，**旧 IP 本机 ping 全超时、22 不通**，别照抄。
- 隧道通了之后：`device.yaml` 里 `platform.use_proxy: true` 走 `socks5://127.0.0.1:1080`；浏览器侧用 Proxy SwitchyOmega 3 填 SOCKS5 `127.0.0.1:1080`。
- **bat 落地铁律（本机实测）**：用 Write 直接写的 bat 是 **LF 换行**，cmd 会断行误解析，报 `'ayedexpansion' 不是内部或外部命令` 这种怪错 → 自造 bat 必须存成 **CRLF + ASCII**（`Get-Content -Raw` 替换 `` `n `` 为 `` `r`n `` 后 `Set-Content -Encoding ascii -NoNewline`）。官方 bat 是 GBK+CRLF，读的时候按 GBK 读否则全是乱码。


