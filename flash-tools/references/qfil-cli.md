# Qualcomm QFIL 烧录（GUI + Silent/命令行模式）

> **结论先说：QFIL.exe 有命令行模式（Silent Mode = `-MODE=3`），可以无人值守烧录。**
> 已在本机 QFIL **2.0.2.8** 上实测跑通命令行解析（见下方「实测验证」）。
> 但 QFIL 本质是 WinForms GUI 程序，**默认没有 `--help`**（不带参数/乱带参数会直接弹 GUI 窗口）。
> 只想要稳定的纯命令行流水线，优先用同目录的 **QSaharaServer.exe + fh_loader.exe**（见文末）。

## 适用芯片 / 场景

| 关键词 | 说明 |
|---|---|
| QFIL / Qualcomm Flash Image Loader | 高通信任 EDL(9008) 烧录 GUI 工具，QPST 套件成员 |
| 9008 / QDLoader / EDL | 设备进入紧急下载模式后的烧录口 |
| prog_emmc_firehose_*.mbn / prog_firehose_ddr.elf | Firehose device programmer（必须与芯片匹配） |
| rawprogram*.xml / patch*.xml | Flat build 的刷机描述文件 |
| contents.xml / meta build / flavor / storage(ufs/emmc/nand) | Meta build 打包刷机 |
| fh_loader / QSaharaServer | QFIL 底层真正执行烧录的控制台工具 |

## 工具路径（本机）

```
QFIL         = "D:/Program Files (x86)/Qualcomm/QPST/bin/QFIL.exe"          (v2.0.2.8, 141KB, .NET WinForms)
SWDL_DLL     = "D:/Program Files (x86)/Qualcomm/QPST/bin/SwDownloadDLL.dll" (参数解析 + 业务逻辑)
QSAHARA      = "D:/Program Files (x86)/Qualcomm/QPST/bin/QSaharaServer.exe" (v18.10.09, 控制台)
FH_LOADER    = "D:/Program Files (x86)/Qualcomm/QPST/bin/fh_loader.exe"     (v18.09.26.16.10, 控制台)
QFIL_CONFIG  = "%APPDATA%/Qualcomm/QFIL/QFIL.config"                        (持久化参数，silent 模式会读它)
QFIL_LOG_DIR = "%APPDATA%/Qualcomm/QFIL/COMPORT_<n>/port_trace.txt"          (每次烧录的详细 trace)
```

## 实测验证（2026-09-11，本机）

只在未接设备、未触发下载动作的前提下验证参数解析链路：

```
cd /d "D:\Program Files (x86)\Qualcomm\QPST\bin"
QFIL.exe -MODE=3 -SKIPQPSTCHECK -LOGFILEPATH="%TEMP%\qfil_cli_test.log"
```

结果（**exit code 0，无 GUI 窗口，日志同时回显到 stdout 且写入文件**）：

```
Loading parameters may takes few minutes, please wait...
2026-09-11 14:57:12.761    MODE:3
2026-09-11 14:57:12.763    LOGFILEPATH:C:\Users\...\Temp\qfil_cli_test.log
2026-09-11 14:57:12.764    Validating Application Configuration
2026-09-11 14:57:12.770    Load APP Configuration
2026-09-11 14:57:12.792    COM:56
...
2026-09-11 14:57:12.949    Load ARG Configuration
2026-09-11 14:57:12.960    Validating Download Configuration
2026-09-11 14:57:12.964    Image Search Path: D:\work\551\...\update\firehose
2026-09-11 14:57:12.969    RAWPROGRAM file path: ...\rawprogram_nand_p2K_b128K.xml
2026-09-11 14:57:12.973    PATCH file path:...\patch_p2K_b128K.xml
2026-09-11 14:57:12.977    Programmer Path:...\partition.mbn
2026-09-11 14:57:12.985    QFIL version: 2.0.2.8
```

⚠️ **注意最后几行**：这次没传 `-COM/-SEARCHPATH/-RAWPROGRAM/-PATCH/-PROGRAMMER`，
QFIL 却把 `%APPDATA%\Qualcomm\QFIL\QFIL.config` 里上次保存的参数**全部加载了进来**
（COM=56、BG95 NAND firehose 包）。也就是说：**silent 模式 = 用已保存配置 + 命令行覆盖**，
如果只补了 `-DOWNLOADFLAT` 而端口/固件没显式指定，它会**直接在旧配置的 COM 口上开烧**。
→ **每次 silent 调用都必须把关键参数显式写全**，不要依赖残留配置。

## 命令行参数（从本机 SwDownloadDLL.dll 2.0.2.8 的 `ARG_STR_*` 常量逐字提取）

参数写法：`-名称=值`（键名大小写不敏感，匹配到 `=` 后取值；多条用逗号分隔）。
带 `;` 的复合值形如 `enable;value`（如 `true;49152`）。含空格/中文的路径 **必须加引号**。

### 模式与运行控制

| 参数 | 说明 |
|---|---|
| `-MODE=<0..3>` | 0=Normal(GUI) / 1=Debug(Engineer) / 2=Background / 3=**Silent** |
| `-PID=<n>` / `-WORKPATH=<dir>` | 进程序号 / 自定义工作目录（改工作目录需管理员权限） |
| `-LOGFILEPATH=<file>` | 本地日志文件，内容同 GUI 日志框（silent 模式强烈建议加） |
| `-DETECTIONLOG=True` | 输出设备插拔检测日志 |
| `-SKIPQPSTCHECK` | 跳过「QPST Server 正在运行」检查（GUI QPST/QFIL 不能与烧录同时占用端口） |
| `-RESETPARAM` | **重置所有默认参数**（会覆盖 QFIL.config，慎用。另注：老版本曾因 `AppData\Roaming\Qualcomm\QFIL` 目录不存在而抛异常） |
| `-COM=<0..255>` | 串口号（数字，不带 COM 前缀） |

### 烧录动作（silent 模式必须有其一）

| 参数 | 说明 |
|---|---|
| `-DOWNLOADFLAT` | 开始烧 **Flat build**（需配合 SEARCHPATH/RAWPROGRAM/PATCH/PROGRAMMER） |
| `-DOWNLOADMETA` | 开始烧 **Meta build**（需配合 METABUILD） |
| `-BREAKDOWNFFU` | 拆分 FFU 包 |
| `-BACKUPQCN` / `-RESTOREQCN` | 备份/恢复 QCN（配合 QCNPATH、SPCCODE，Diag 口） |
| `-GETPARTITIONINFO` | 读取分区表，输出到 `<COM端口>_PartitionsList.xml`（当前目录） |
| `-ERASESECTOR` / `-READSECTOR` / `-WRITESECTOR` | 扇区级擦除/读/写，配合 `-SECTORPARAMS=<LUNIndex>;<StartSector>;<NumSectors>` 与 `-FILEPATH=<file>` |
| `-EDMA` / `-FLATMETA` | EDMA 相关 / flat 化 meta build |

### 构建与固件参数

| 参数 | 说明 |
|---|---|
| `-SEARCHPATH=<dir>` | 镜像搜索路径（**只支持一个**），rawprogram/patch XML 也从这里找 |
| `-RAWPROGRAM=a.xml,b.xml` | rawprogram XML，可多个，逗号分隔 |
| `-PATCH=a.xml,b.xml` | patch XML，可多个，逗号分隔 |
| `-PROGRAMMER=true;"<prog_xxx.mbn/elf>"` | Firehose programmer，`启用;完整路径`（常见错误：写成 `enabled;` 会报 Programmer is not selected） |
| `-SAHARA=true;"<prog_xxx.mbn>"` | Sahara 下载：`启用;programmer 完整路径` |
| `-PBLDOWNLOADPROTOCOL=<n>` | PBL 下载协议 |
| `-DEVICETYPE=<emmc|ufs|nand|spinor>` | 存储类型（**必须与 programmer 匹配**） |
| `-PLATFORM=<8x26 等>` | 平台名（GUI 里的 Device Type/Platform 选择） |
| `-METABUILD="<contents.xml>;<flavor>"` | Meta build 的 contents.xml + flavor |
| `-METABUILDPROGRAMMER=<file>` / `-FLATBUILDPATH=<dir>` / `-FLATBUILDFORCEOVERRIDE=true` | meta→flat 展开相关 |
| `-CDTCONFIG=<file>` | CDT 配置文件 |
| `-FFUPATH=<file>` | FFU 镜像路径 |

### 行为/校验参数

| 参数 | 说明 |
|---|---|
| `-ACKRAWDATAEVERYNUMPACKETS=true;100` | 每 N 个包回 ACK |
| `-MAXPAYLOADSIZETOTARGETINBYTES=true;49152` | 单包大小（false 则由 host/target 协商；须为 512 倍数、>0） |
| `-VALIDATIONMODE=<0..5>` | 回读校验方式：0 不回读 / 1,3,5 外部回读（data/SHA256 等）/ 4 外部回读数据 / 5 跟随 rawprogram |
| `-RESETAFTERDOWNLOAD=true` | 下载完复位设备 |
| `-SWITCHTOFIREHOSETIMEOUT=<sec>` / `-RESETTIMEOUT=<sec>` / `-RESETDELAYTIME=<sec>` | 切 Firehose 超时 / 复位超时 / 复位前延时 |
| `-RESETSAHARASTATEMACHINE=true` / `-SAHARAREADSERIALNO=true` | Sahara 状态机复位 / Sahara 阶段读序列号 |
| `-MAXDIGESTTABLESIZE` / `-CHAINEDDIGEST` / `-SIGNEDDIGEST` / `-DRYRUN` | VIP/摘要表与 dry-run 相关 |
| `-ACTIVEBOOTPARTITION=<0|1>` | 活动启动分区 |
| `-ERASEALL=true` | **擦除整片 flash**（会连校准 QCN 一起清掉，**先备份再用**） |
| `-AUTOPRESERVEPARTITIONS=true` / `-PARTITIONPRESERVEMODE=<n>` / `-PRESERVEDPARTITIONS=fsg,0;modemst1,0` | 保留分区（fsg/efs/modemst1/modemst2…） |
| `-QCNAUTOBACKUPRESTORE=true` / `-QCNPATH="<x.qcn>"` / `-SPCCODE="000000"` / `-ENABLEMULTISIM=true` | QCN 自动备份恢复 / 路径 / SPC / 多卡 |
| `-PROVISIONPROGRAMMER` / `-PROVISIONXMLPATH=<file>` | Provision 相关（社区反馈：仅传这两个**不会**触发 provision，需靠 DOWNLOAD* 动作） |

> 该版本**没有** `-CONSOLELOG`（早期 QFIL 2.0.2.6 文档里有，其他版本可能有差异；
> 本机实测 stdout 本来就会回显日志，无需该参数）。

## 标准流程（Flat build，silent 烧录）

1. **准备 Firehose 包**（典型 Quectel BG95/BG77 等 `update/firehose/` 目录）：应有
   `prog_firehose_*.mbn` 或 `partition.mbn`（programmer）、`rawprogram*.xml`、`patch*.xml`、各 `.bin/.mbn`。
2. **确认 EDL 口 + 编号**：设备上电进 9008（EDL），设备管理器出现 `Qualcomm HS-USB QDLoader 9008 (COMx)`。
   - 查口：`powershell -c "Get-PnpDevice -Class Ports | ? {$_.FriendlyName -match 'QDLoader|9008'}"`
   - ⚠️ 此时**关掉 QPST / QFIL GUI**（端口独占），或加 `-SKIPQPSTCHECK`。
3. **执行 silent 烧录**（关键参数全部显式给全）：
   ```
   cd /d "D:\Program Files (x86)\Qualcomm\QPST\bin"
   QFIL.exe -MODE=3 -SKIPQPSTCHECK -COM=56 ^
     -SEARCHPATH="D:\work\551\DTU_version\module\BG95M3LAR02A03_01.202.01.202\update\firehose" ^
     -PROGRAMMER=true;"D:\...\update\firehose\partition.mbn" ^
     -RAWPROGRAM=rawprogram_nand_p2K_b128K.xml -PATCH=patch_p2K_b128K.xml ^
     -DEVICETYPE=nand -RESETAFTERDOWNLOAD=true ^
     -LOGFILEPATH="D:\temp\qfil_burn.log" -DOWNLOADFLAT
   ```
   QuecAgent 里用 `execute_shell_command` 执行时给足 `timeout`（建议 600–900s），并把日志重定向：
   `... > burn_out.txt 2>&1`
   > `^` 是 cmd 续行符，实际执行建议**拼成一行**，避免转义问题。
4. **判断结果**：看 stdout/日志 + `%APPDATA%\Qualcomm\QFIL\COMPORT_<n>\port_trace.txt`。
   - 成功：日志出现下载完成/`Finish Download`、进度 100%、进程退出码 0；
   - 失败：`Sahara Fail` / `Download Fail:` / `Programmer is not selected` / `Invalid working folder root` 等，按日志定位。
5. **清理**：`powershell -c "Get-Process QFIL -ErrorAction SilentlyContinue | Stop-Process -Force"`，
   确保没有残留 QFIL 进程占着端口。
6. **核对版本**：设备起来后读版本（AT 口 `ATI` / `AT+QGMR`，或产品菜单），**不要只信工具报成功**。
7. **汇报**：COM 口、programmer 与固件版本、存储类型、是否成功、退出码、耗时、日志路径。

## 更推荐的纯命令行方案：QSaharaServer.exe + fh_loader.exe

QFIL silent 模式本质上是**把参数塞进 `SwDownloadDLL.dll`，由它再调这两个控制台工具**。
如果要做自动化/量产，直接调这两个更可控（真正的 console 程序、参数稳定、能重定向输出）：

```
:: ① 用 Sahara 把 Firehose programmer 打进目标（image_id 13 = device programmer）
QSaharaServer.exe -p \\.\COM56 -s 13:"D:\...\partition.mbn"

:: ② 用 Firehose 按 rawprogram 刷写
fh_loader.exe --port=\\.\COM56 --sendxml=rawprogram_nand_p2K_b128K.xml ^
              --search_path="D:\...\firehose" --noprompt --zlpawarehost=1 --nop
```

**QSaharaServer.exe 参数**（本机 v18.10.09 实测 `--help` 输出）：

| 参数 | 说明 |
|---|---|
| `-p, --port <\\.\COMx>` | 串口（Windows 必须写成 `\\.\COMx`） |
| `-u, --portnumber <n>` | 用数字端口号代替完整名（自动补 `\\.\COM`） |
| `-s, --sahara <id:file>` | Sahara 镜像映射，可多个；`13:` 固定是 device programmer |
| `-b, --addsearchpath <dir>` | 找文件的搜索路径，可多个 |
| `-c, --command <id>` / `-m, --memdump` / `-i, --image` | 强制命令模式 / 内存 dump / 镜像传输 |
| `-r, --ramdumpimage <id>` / `-l, --efssyncloop` / `-w, --where <dir>` / `-g, --prefix <p>` | 内存 dump 相关 |
| `-t, --rxtimeout <t>` / `-j, --maxwrite <n>` / `-v, --verbose <n>` | 超时 / 最大写长度 / 详细级别 |
| `-k, --sendclearstate` / `-x, --switchimagetx` / `-o, --nomodereset` | 复位 Sahara 状态机 / 完成后强制转 image tx / dump 后不切模式 |
| `-a, --cmdrespfilepath <id:path>` | 保存命令响应到文件 |

**fh_loader.exe 主要参数**（本机 v18.09.26.16.10 `--help` 输出节选）：

```
port=                 sendxml=             sendimage=          search_path=
contentsxml=          rawprogram 相关:      skippatch           noprompt
noreset               nop                  zlpawarehost=       verbose
erase / erasefirst / wipefirst             reset               setactivepartition=
memoryname=           lun=                 num_sectors=        sectorsizeinbytes=
maxpayloadsizeinbytes=  maxdigesttablesizeinbytes=
createdigests / chaineddigests= / signeddigests= / createcommandtrace / showdigestperpacket
verify_programming    verify_build(=contentsxml)   simulate   convertprogram2read
notfiles= notlabels= files= labels=        dontsorttags        forceoverwrite
skipstorageinit       fixgpt               getstorageinfo=     flattenbuildto=
json_in=(meta_cli.py get_partition_files 生成的 json)     loglevel=(0..3)
porttracename=        readbogusdata        benchmarkreads/writes/digestperformance
stresstest            trials=              getgptmainbackup=
```

示例（官方 help 原文）：
```
fh_loader.exe --port=\\.\COM19 --sendxml=rawprogram0.xml --search_path=c:\builds\...\ --loglevel=2
fh_loader.exe --port=\\.\COM19 --sendimage=AnyFile.bin --search_path=c:\...\ --noreset --noprompt
```
注意：**必须先 `QSaharaServer -s 13:<programmer>`**，否则 fh_loader 会报
「you forgot to send DeviceProgrammer first」。

## 注意事项 / 踩坑

- **没有 `--help`**：QFIL.exe 是 GUI 程序，不带参数或参数不认识会**直接弹窗口**；查参数只能看本文档或 `SwDownloadDLL.dll`。已弹窗的用 `Get-Process QFIL | Stop-Process -Force` 关掉。
- **silent 模式会继承旧配置**：务必显式传 `-COM/-SEARCHPATH/-RAWPROGRAM/-PATCH/-PROGRAMMER/-DEVICETYPE`，否则可能**在错误端口上烧错包**。
- **端口独占**：QPST Server / QFIL GUI 与命令行烧录不能同时用同一 COM 口；先关掉，或 `-SKIPQPSTCHECK`。
- **programmer 不匹配 = Sahara Fail**：`prog_emmc_firehose_*` / `prog_ufs_firehose_*` / `prog_firehose_*_nand` 要与芯片和存储类型一致。
- **`-ERASEALL` / 擦整片**：会清掉校准数据（QCN），先 `-BACKUPQCN` 备份。
- **`-RESETPARAM`** 会重置 QFIL 配置，别误用。
- **退出码 0 不代表烧成功**（本地实测无动作时也是 0）：必须看日志关键字 + port_trace.txt 核对。
- **路径含空格/中文**要加引号；`-PROGRAMMER=true;"路径"` 里引号是必须的。
- 烧录后建议物理断电重上电再验版本（部分模块 `-RESETAFTERDOWNLOAD` 后仍停在下载态）。
- 本机 QFIL 为 **2.0.2.8**（QPST 2.7.486，2019 版）；不同 QFIL 版本参数集略有差异，换版本请重新确认。
