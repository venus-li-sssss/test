---
name: qdm562-project
description: QDM562（云盒/中控，ASR1602S 九号平台）项目测试知识中枢。用在：QDM562 怎么认串口/哪个 COM 是什么口、上位机升级压测怎么搭和怎么跑、升级后怎么查 GNSS 版本号（Build19128 / Build27526）、ATI 报 764 但实际是 0765 怎么办、debug 日志抓不到/抓取工具没在跑、上位机 5A A5 发了没回帧、差分包该拿哪个、电脑不锁屏怎么设。触发词：QDM562、云盒、中控、上位机升级、查 GNSS、GNSS 版本号、认串口、COM29/COM184/COM3、debug 口、5A A5、0765、0766、Build19128、压测脚本、不锁屏。
---

# QDM562 项目测试知识

云盒/中控项目，模组 EG800AKCN_91LC（ASR1602S），客户九号。本文是**实测沉淀**，不是文档摘抄；每条结论都标了怎么验证。

## 1. 先认口：QDM562 五个口分别是什么

| 口 | 设备名 | 是什么 | 谁在用 | 平时有没有数据 |
|---|---|---|---|---|
| `COM3` | `USB Serial Port (COM3)` | **debug 口**（USB-232 转接） | 日志抓取（人工 debug 用） | 静默；只有**重启/升级**才打印 |
| `COM29` | `Quectel USB MI05 COM Port` | **串口日志口**（AT/LOG 混合通道） | 升级脚本独占（`gnss_com`） | 一直有：`Monitor` / `LOC` / `$NAVVEL` / `$PDTINFO` / `FWVer` |
| `COM31` | `Quectel USB DIAG Port` | **DIAG 口** | CATStudio 抓 CAT LOG | 有，但被 CATStudio 占时别的程序打不开 |
| `COM32` | `Quectel USB AT Port` | **AT 口** | 敲 AT 指令 | 只在你查询时回 |
| `COM184` | `USB Serial Port (COM184)` | **上位机口**（5A A5 协议） | 上位机 GUI / 压测脚本 | 未升级前设备**不回 ACK**，rx 常年 0 属正常 |
| `COM30` | `Quectel USB Modem` | Modem 口 | 用不到 | — |

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
- `scripts/port_probe.py` —— 认口自检脚本
