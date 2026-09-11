# QFlash V7.5 多平台烧录（Qualcomm / Unisoc / STM32 / MTK / Rockchip / NB-IoT 等）

> 源：原独立 skill `qflash`，已并入统一烧录 skill **flash-tools**（本目录）。
> 移远 **QFlash V7.5** 是多平台固件烧录工具集。**主程序 `QFlash_V7.5.exe` 是 GUI（无命令行烧录能力），但工具集内各平台子工具提供完整命令行烧录。** 本文覆盖 GUI 与各平台 CLI 两种方式。

## 工具位置

```
QFLASH_DIR = "D:\work\551\QFlash_V7.5_EN\QFlash_V7.5"
QFLASH_EXE = "D:\work\551\QFlash_V7.5_EN\QFlash_V7.5\QFlash_V7.5.exe"
```

> 工具支持平台：Qualcomm(QCMM)、Unisoc 展锐(Decode/EFlashTool)、MTK、STM32、Rockchip、Beken、FreqChip、ASR(aboot)、Altair、ESWIN、GNSS(LC76G/HI2120)、NB-IoT、XY1100/XY4100 等。

## 快速判断：GUI 还是 CLI？（先确认目标芯片平台）

| 平台/芯片 | 烧录方式 | 工具/说明 |
|---|---|---|
| **Qualcomm**（EG91/MDM/QCMM、firehose、9008/EDL/QDLoader） | ✅ **CLI**（EDL 命令行烧录） | `QCMM\CH1\QSaharaServer.exe` + `QCMM\CH1\fh_loader.exe` → [cli-qualcomm-edl.md](cli-qualcomm-edl.md)；也可用主程序 GUI 手点。另有 QFIL 路线见 [../qfil-cli.md](../qfil-cli.md) |
| **Unisoc 展锐**（EC618/EC718/EC217/EC716/EC626/616） | ✅ CLI | `EFlashTool\1\FlashToolCLI.exe` → [cli-unisoc.md](cli-unisoc.md) |
| **STM32**（ST-LINK SWD/JTAG、UART/USB DFU） | ✅ CLI | `STM32\1\bin\STM32_Programmer_CLI1.exe` → [cli-stm32.md](cli-stm32.md) |
| **MTK**（MT2731R 等） | ✅ CLI | `MTK\1\ThinModemFlashTool1.exe`；`flashimage.exe --productdir <dir>` → [cli-others.md](cli-others.md) |
| **Rockchip** | ✅ CLI | `ROCKCHIP\1\upgrade_tool1.exe`（文档：`命令行开发工具使用文档.pdf`）→ [cli-others.md](cli-others.md) |
| **FreqChip 富芮坤** | ✅ CLI | `FREQCHIP\1\freqchip_flash_tool1.exe`（`-t` 握手超时；GUI 流程见 [../freqchip-download.md](../freqchip-download.md)） |
| **NB-IoT** | ✅ CLI | `NB-IoT\1\UEUpdaterCLI\` → [cli-others.md](cli-others.md) |
| **Beken / Altair / GNSS / XY 系列** | 专用工具 | `Beken\1\bk_loader1.exe`、`Altair\1\ImageBurnTool1.exe` 等，按需使用 → [cli-others.md](cli-others.md) |
| **ASR / aboot**（ML307C、EG800AK、QDM562 等） | ✅ CLI | 用 `adownload.exe`，见 [../aboot-flash.md](../aboot-flash.md) |

**GUI 通用流程**（Qualcomm 及未列平台）：设备进下载模式（EDL/9008 或 QDLoader 端口）→ QFlash 选择芯片平台与镜像目录（`update/`）→ 勾选镜像/擦除选项 → 下载 → 自动重启。GUI 配置可部分通过 `MainConfig.ini` 预设（见 [gui-usage.md](gui-usage.md)）。

## 通用规则

1. **先确认平台/芯片与固件包**：不同的芯片走不同的子工具/命令，不得用错工具。
2. **确认设备在下载模式**：Qualcomm 需 9008/EDL 或 QDLoader 端口；Unisoc/STM32 需对应下载端口或 ST-LINK；未接设备不要反复重试。
3. **烧录是破坏性写操作**：执行前确认目标设备、镜像、擦除范围（`Flash_Allerase`/`flasherase` 范围）；不要误清数据分区（除非需要）。
4. **长耗时**：给 `execute_shell_command` 足够 `timeout`（建议 300–900s），或把输出重定向到日志后轮询。
5. **完成后清理进程/窗口**：必要时 `taskkill /IM <工具名> /F`。
6. **烧录后核对版本**：不要只看"工具报成功"，用设备侧手段（AT 指令 / 菜单 / `uname` 等）读回版本逐字比对。
7. **汇报结果**：平台、端口/COM、镜像、耗时、是否成功、关键日志。

## 文档索引

- [cli-qualcomm-edl.md](cli-qualcomm-edl.md) — **Qualcomm EDL(9008) 命令行烧录**：QSaharaServer + fh_loader 流程、参数、xml/镜像配套
- [cli-unisoc.md](cli-unisoc.md) — Unisoc FlashToolCLI：probe/flasherase/burnbatch/sysreset 完整流程（UART & USB）
- [cli-stm32.md](cli-stm32.md) — STM32_Programmer_CLI：SWD/UART 连接、下载、擦除、校验、复位
- [cli-others.md](cli-others.md) — MTK / Rockchip / FreqChip / NB-IoT / Beken / Altair 命令行速查
- [gui-usage.md](gui-usage.md) — QFlash GUI 操作要点 + MainConfig.ini 关键配置

## 注意

- 实际路径/平台以用户为准，执行前确认 exe 与本机 COM 口。
- **Qualcomm 平台两种方式都可用**：命令行（`QCMM\CH1\QSaharaServer.exe` + `fh_loader.exe`，走 EDL/9008 + firehose xml，推荐用于自动化）或 QFlash GUI 手点。命令行细节见 [cli-qualcomm-edl.md](cli-qualcomm-edl.md)。
- Qualcomm 命令行烧录前提：设备能进 **EDL(9008)**，且 `update/` 里有配套的 `rawprogram_*.xml` + firehose programmer（`prog_*_firehose_*.mbn`）。
- QFIL/QPST 是另一条 Qualcomm 路线（silent 命令行 + 同目录 QSaharaServer/fh_loader），见 [../qfil-cli.md](../qfil-cli.md)。
