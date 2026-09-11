---
name: qflash
description: 'Use this skill when the user wants to flash/burn Quectel module or OCPU firmware using QFlash tool (QFlash 烧录/线刷/下载固件/EDL/9008/QDLoader/firehose/整包烧录/升级底包). Tool at D:\work\551\QFlash_V7.5_EN\QFlash_V7.5. Covers: QFlash GUI (Qualcomm QCMM/firehose), and platform CLI tools bundled inside (Unisoc FlashToolCLI, STM32_Programmer_CLI, MTK ThinModemFlashTool/flashimage, Rockchip upgrade_tool, FreqChip freqchip_flash_tool, NB-IoT UEUpdaterCLI). Triggers: QFlash, 烧录, 线刷, 下载固件, OCPU, firehose, 9008, EDL, QDLoader, 底包, 整包, EC618/EC718/EC217/EC716, STM32, MT2731R, upgrade_tool, UEUpdaterCLI.'
---

# QFlash 烧录 Skill（QFlash_V7.5）

Quectel **QFlash V7.5** 是移远的多平台固件烧录工具集。**主程序 `QFlash_V7.5.exe` 是 GUI（无命令行烧录能力），但工具集内各平台子工具提供完整命令行烧录**。本 skill 覆盖 GUI 与各平台 CLI 两种方式。

## 工具位置

```
QFLASH_DIR = "D:\work\551\QFlash_V7.5_EN\QFlash_V7.5"
QFLASH_EXE = "D:\work\551\QFlash_V7.5_EN\QFlash_V7.5\QFlash_V7.5.exe"
```

> 工具支持平台：Qualcomm(QCMM)、Unisoc 展锐(Decode/EFlashTool)、MTK、STM32、Rockchip、Beken、FreqChip、ASR(aboot)、Altair、ESWIN、GNSS(LC76G/HI2120)、NB-IoT、XY1100/XY4100 等。

## 快速判断：GUI 还是 CLI？（先确认目标芯片平台）

| 平台/芯片 | 烧录方式 | 工具/说明 |
|---|---|---|
| **Qualcomm**（EG91/MDM/QCMM、firehose、9008/EDL/QDLoader） | ✅ **CLI**（EDL 命令行烧录） | `QCMM\CH1\QSaharaServer.exe` + `QCMM\CH1\fh_loader.exe` → [references/cli-qualcomm-edl.md](references/cli-qualcomm-edl.md)；也可用主程序 GUI 手点 |
| **Unisoc 展锐**（EC618/EC718/EC217/EC716/EC626/616） | ✅ CLI | `EFlashTool\1\FlashToolCLI.exe` → [references/cli-unisoc.md](references/cli-unisoc.md) |
| **STM32**（ST-LINK SWD/JTAG、UART/USB DFU） | ✅ CLI | `STM32\1\bin\STM32_Programmer_CLI1.exe` → [references/cli-stm32.md](references/cli-stm32.md) |
| **MTK**（MT2731R 等） | ✅ CLI | `MTK\1\ThinModemFlashTool1.exe`；`flashimage.exe --productdir <dir>` → [references/cli-others.md](references/cli-others.md) |
| **Rockchip** | ✅ CLI | `ROCKCHIP\1\upgrade_tool1.exe`（文档：`命令行开发工具使用文档.pdf`）→ [references/cli-others.md](references/cli-others.md) |
| **FreqChip 富芮坤** | ✅ CLI | `FREQCHIP\1\freqchip_flash_tool1.exe`（`-t` 握手超时；GUI 见已有 `flash-tools` skill） |
| **NB-IoT** | ✅ CLI | `NB-IoT\1\UEUpdaterCLI\` |
| **Beken / Altair / GNSS / XY 系列** | 专用工具 | `Beken\1\bk_loader1.exe`、`Altair\1\ImageBurnTool1.exe` 等，按需使用 |

**GUI 通用流程**（Qualcomm 及未列平台）：设备进下载模式（EDL/9008 或 QDLoader 端口）→ QFlash 选择芯片平台与镜像目录（`update/`）→ 勾选镜像/擦除选项 → 下载 → 自动重启。GUI 配置可部分通过 `MainConfig.ini` 预设（见 [references/gui-usage.md](references/gui-usage.md)）。

## 通用规则

1. **先确认平台/芯片与固件包**：不同的芯片走不同的子工具/命令，不得用错工具。
2. **确认设备在下载模式**：Qualcomm 需 9008/EDL 或 QDLoader 端口；Unisoc/STM32 需对应下载端口或 ST-LINK；未接设备不要反复重试。
3. **烧录是破坏性写操作**：执行前确认目标设备、镜像、擦除范围（`Flash_Allerase`/`flasherase` 范围）；不要误清数据分区（除非需要）。
4. **长耗时**：给 `execute_shell_command` 足够 `timeout`（建议 300–900s），或把输出重定向到日志后轮询。
5. **完成后清理进程/窗口**：必要时 `taskkill /IM <工具名> /F`。
6. **汇报结果**：平台、端口/COM、镜像、耗时、是否成功、关键日志。

## QuecAgent 环境适配

原工具文档/其他框架的 `run_in_background`/`TaskOutput`/`TaskStop` 对应本环境：
- 前台执行 + 大 `timeout`；或 `... > flash_log.txt 2>&1` 重定向后分次读取日志
- 结束进程用 `taskkill /IM <exe名> /F`
- 询问用户直接用自然语言

## 文档索引

- [references/cli-qualcomm-edl.md](references/cli-qualcomm-edl.md) — **Qualcomm EDL(9008) 命令行烧录**：QSaharaServer + fh_loader 流程、参数、xml/镜像配套
- [references/cli-unisoc.md](references/cli-unisoc.md) — Unisoc FlashToolCLI：probe/flasherase/burnbatch/sysreset 完整流程（UART & USB）
- [references/cli-stm32.md](references/cli-stm32.md) — STM32_Programmer_CLI：SWD/UART 连接、下载、擦除、校验、复位
- [references/cli-others.md](references/cli-others.md) — MTK / Rockchip / FreqChip / NB-IoT / Beken / Altair 命令行速查
- [references/gui-usage.md](references/gui-usage.md) — QFlash GUI 操作要点 + MainConfig.ini 关键配置

## 注意

- 实际路径/平台以用户为准，执行前确认 exe 与本机 COM 口。
- **Qualcomm 平台两种方式都可用**：命令行（`QCMM\CH1\QSaharaServer.exe` + `fh_loader.exe`，走 EDL/9008 + firehose xml，推荐用于自动化）或 QFlash GUI 手点。命令行细节见 [references/cli-qualcomm-edl.md](references/cli-qualcomm-edl.md)。
- Qualcomm 命令行烧录前提：设备能进 **EDL(9008)**，且 `update/` 里有配套的 `rawprogram_*.xml` + firehose programmer（`prog_*_firehose_*.mbn`）。