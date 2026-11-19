---
description: 'Use this skill when the user wants to run/审核/归档 a real-device FCT(产测) 自动化测试：FCT 自动化测试流程、产测脚本实机跑、FCT 口、5AA5 帧、单口跑批、写后还原(write-restore)、结果归档到版本目录、产测报告。Triggers: FCT 自动化测试, 产测脚本, FCT 产测, 5AA5, FCT 口, 实机跑产测, 写后还原, write-restore, 写PN, 写蓝牙MAC, 产测结果归档, 版本目录归档, 产测 allure 报告. NOT for 循环压测(用 pressure-test-generator) / Excel 用例转 pytest 壳(用 pressure-test-pytest).'
name: pressure-test-fct
---

# FCT 自动化测试流程（实机产测跑批 + 结果归档）

> 本 skill 管的是**"已经在跑的 FCT 产测项目怎么跑、怎么判、怎么归档"**；
> 从零生成项目骨架用 `pressure-test-pytest`（Excel→pytest 壳）或框架的 spec 生成器，
> 基础类（串口/CAN/CMD/继电器）用 `pressure-test-bases`。
> 循环压测不在这里 —— 那是 `pressure-test-generator` / `pressure-test-framework`。

## 流程总览

```
① 确认固件形态(FCT版) + 找对 FCT 口
        ↓
② 链路体检（脏链路直接断电重上电，别硬跑）
        ↓
③ 跑批（选择写操作档位：不跑 / --write / --write-restore）
        ↓
④ 核对结果（汇总表 + 版本三项 + 跳过项是否有理由）
        ↓
⑤ 归档（scripts/archive_results.py → 版本目录，自动生成 说明.md）
```

## ① 开跑前：固件形态与串口

| 检查 | 做法 |
|:---|:---|
| 是不是 FCT 版固件 | 读版本串确认（QDM562 这类看 `ATI` 的 `CustRevision`；AT 型产测固件看版本串含不含 `_FCT_`） |
| 哪个口是 FCT 口 | 桌面枚举里找 FTDI `USB Serial Port`（夹具口）；**模组自己的 AT/DIAG/Modem/Dump 口不是 FCT 口** |
| 哪些口绝对不能碰 | 继电器控制口（CH340 / `A0+路号+状态位+校验和`）：误发 5AA5 帧可能让被测设备掉电 |

> 端口**每次动态检测**，不要写死：`python -c "import serial.tools.list_ports as p;[print(x.device,x.description) for x in p.comports()]"`

## ② 链路体检（最重要的一步）

FCT 口有两种"脏状态"，跑起来就是满屏超时，不是脚本坏：

1. **重启指令之后**：设备会在 FCT 口持续输出内部总线帧（方向字节 `09 01` / `09 13` / `09 20`），
   且**不会自愈** —— 必须**断电重上电**；
2. **上一轮进程没退**：串口句柄没释放，表现为"打不开 / 跑几次就不正常"。

体检方式：开串口静默 1~2s，统计收到的帧里"非 `09 3E` 方向"的比例。
实测一次脏链路：3 分钟 49 条指令只回 12 条合法应答，却夹了 1164 个内部总线帧。
体检不过 → 让用户断电重上电，**不要加 `--force` 硬跑**。

## ③ 跑批：写操作三档（关键设计）

产测里有两种写操作：**写 PN**（文档常误写"写SN"）、**写蓝牙 MAC**。它们会**永久改写设备身份数据**，
所以分三档，默认最保守：

| 档位 | 行为 | 什么时候用 |
|:---|:---|:---|
| 默认（不加参数） | 两条写用例 **SKIP** | 日常回归：不碰设备身份 |
| `--write` | 写两次不同值 + 回读校验，**不还原** | 产线首次写号（设备本来就是空的） |
| `--write-restore` | **备份原值 → 写测试值 → 回读确认写入成功 → 写回原值 → 再回读确认已还原** | **已有身份数据的设备要验证写功能**（送样机、在测机） |

`--write-restore` 的判定链（缺一不可，别只判"写回了 OK"）：

```
原始值(读) → 写入测试值 → 回读 == 测试值    （证明"写指令真的生效"，不是碰巧和原值相同）
           → 写回原始值 → 回读 == 原始值    （证明"设备没被留在测试值上"）
```

实现要点：
- 写用例内部用 `try/finally` **兜底还原**（写失败也要还原，别让设备停在半路）；
- 回读校验用**独立读指令**（PN 用 `01 28 0E` 读索引 0x28 的 14 字节再 7bit 解压；
  MAC 用读 MAC 指令），不要拿写指令的回显当证据；
- 还原后**再跑一条独立的读用例**（如"读蓝牙MAC"）做最终确认，报告里一条链看全。

实测（QDM562 / 766）：
```
072 写PN     原值 Z0E7CVN26L2D0046 → 写 Z09BAVN25C5C0117/0118 各回读一致 → 还原 回读一致 ✅
128 写MAC    原值 20:29:B9:F0:BF:2D → 写 A0EDFB99F5DC/DD 各回读一致 → 还原 回读一致 ✅
131 读MAC    读回 20:29:B9:F0:BF:2D（已还原）✅
```

## ④ 结果核对清单

| 看什么 | 合格标准 |
|:---|:---|
| 汇总行 | `PASS + FAIL + SKIP = 用例总数`，FAIL 必须为 0 才算过（SKIP 不算失败但要逐条有理由） |
| 版本三项 | ECU APP 版本 = 本次烧录版本；底包版本合理；GNSS 版本读得到 |
| 跳过项 | 只允许三类：指令已废弃（文档写明产线不用）/ 研发专用射频（需 `--rf`）/ 需人工或仪器判定 |
| 写操作 | 见 ③ 的判定链，报告里要有 `原始值 → 写入值 → 还原值` 三段 |
| 数据合理性 | 关键量在量程内：RSRP -140~-40dBm、ADC 0~5V、CSAT/星数合理、NMEA 校验和全对 |
| 异常提示 | `PASS(提示)` 类（如 flash id 只回 1 字节、与文档不符）要单独记，别混进正常项 |

## ⑤ 结果归档（别手抄，用脚本）

跑完把 `report/ + result/xml/ + log/ + 控制台输出` 归到版本目录，并自动生成 `说明.md`：

```bash
python scripts/archive_results.py ^
    --src "D:\\work\\<产品>\\脚本\\自动化测试\\<项目目录>" ^
    --dst "D:\\work\\<产品>\\版本测试\\<版本>\\FCT测试" ^
    --version 766 ^
    --device "IMEI 864897087029223" ^
    --firmware "ECU APP V0766 / 底包 0705" ^
    --console-log "_fct_run3.txt" ^
    --doc "D:\\...\\4G-ECU FCT指令说明20260914_05BT.xlsx"
```

脚本做的事：
1. `report/`（allure HTML）、`result/xml/`（原始数据）整目录复制；
2. **自动挑本轮**的 `script_log / serial_log / summary`（以最新 summary 的 mtime 为锚取最接近的那份，
   同轮会有多个时间戳只差几秒的小文件，按体积二次排除）—— 也可 `--script-log/--serial-log` 指定；
3. 控制台完整输出 → `log/运行日志_<日期>.txt`；
4. 指令文档（`--doc`）复制到目标根目录；
5. **生成 `说明.md`**：版本/设备/固件/运行参数 + 结论汇总行 + 跳过项 + 数据汇总表 + 目录说明；
6. 自检并打印：`index.html` 是否存在、allure json 数量、文件数与总大小。

`--dry-run` 只打印计划。源目录只读，目标目录增量覆盖（不删旧文件）。

**目录规范**（与历史版本保持一致）：

```
<产品>\版本测试\<版本>\FCT测试\
├── report\           allure HTML（必须 HTTP 打开）
├── result\xml\       allure 原始数据
├── log\              script_log / serial_log / summary / 运行日志
├── 说明.md           结论摘要（自动生成）
└── <指令说明>.xlsx    用例依据文档
```

## 工程约束（Windows / 本环境实测踩过）

1. **命令行工具常有 60s 上限**：FCT 全量跑 2~3 分钟，前台跑会被中途杀掉（还停在"重启指令"那一步，
   设备留成脏链路）。正确做法：写成 `.bat` 后交给**计划任务**拉出当前会话：
   ```bat
   schtasks /create /tn "XXX_FCT_RUN" /tr "\"<bat 绝对路径>\"" /sc once /st 23:59 /f
   schtasks /run  /tn "XXX_FCT_RUN"
   :: 跑完 schtasks /delete /tn "XXX_FCT_RUN" /f
   ```
   `.bat` 里用 `cd /d "%~dp0"`（不要写中文字面路径，cmd 按 GBK 读会乱），python 加 `-u` 让日志实时落盘。
2. **别用 Python `DETACHED_PROCESS` 硬脱离**：日志会被块缓冲吞掉，进程也常被父进程的 job object 回收。
3. **`allure open` 会挂一个常驻 java 服务**：跑完记得收掉，否则下次 `generate --clean` 会被占用。
   ```powershell
   Get-CimInstance Win32_Process -Filter "name='java.exe'" |
     Where-Object { $_.CommandLine -match 'allure.*open' } |
     ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
   ```
4. **allure 报告必须走 HTTP**：`allure open <dir>`，双击 `index.html` 一定白屏。
5. **别 kill 名字叫 python.exe 的进程**：本机跑 agent 的进程也是 python；按 PID 或命令行匹配再动手。
6. **`cd /d X & copy` 这类一行命令**：`cmd` 的 `set VAR=.. &` 会带尾随空格，路径全错 —— 复制/归档一律用脚本，别用行内 set。

## 常见问题

| 现象 | 原因 | 处理 |
|:---|:---|:---|
| 满屏"超时未收到响应" | 脏链路 / 口选错 / 上一轮进程占口 | 断电重上电 → 体检 → 确认是 FTDI 那个口 |
| 只有部分用例 FAIL，重跑又过 | 串口被反复开关、指令间隔太短 | 会话级共享串口、指令间隔 ≥0.4s、失败用例内重发而不是靠 pytest rerun |
| 写用例 PASS 但设备数据变了 | 只做了"写+回读"，没做还原 | 用 `--write-restore`，并检查还原后独立读用例 |
| 报告里 SKIP 特别多 | 写操作没开 / 射频默认跳过 | 正常；按 ③ 选档，射频要跑加 `--rf` |
| 归档后日志不是本轮那份 | 同轮有多个时间戳只差几秒的日志 | 用 `archive_results.py`（按 summary mtime 锚定 + 体积排除），或显式 `--script-log` |
| 归档目录里 report 打不开 | file:// 打开 | `allure open <dst>\report` |

## 实测样例（QDM562 / 766 / 2026-11-19）

| 项 | 值 |
|:---|:---|
| 命令 | `4G_ECU_FCT_TEST_V04.py --port COM246 --baud 115200 --write-restore` |
| 结果 | 41 项 / 执行 37 / **PASS 37** / FAIL 0 / SKIP 4，161.35s |
| 固件 | ECU APP V0766、底包 0705 |
| 关键读数 | RSRP -82dBm、ADC 3.92V、NMEA 115 条校验全对、蓝牙 MAC 20:29:B9:F0:BF:2D |
| 归档 | `D:\work\QDM562\版本测试\766\FCT测试`（report 194 文件 + result 197 + log 4，3.8MB） |
