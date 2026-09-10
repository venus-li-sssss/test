---
name: flash-tools
description: 'Use this skill when the user wants to flash/burn firmware to a device (烧录/刷机/下载固件/线刷). Covers FreqChip (富芮坤) chip flashing via FreqChip_Download_Consle.exe (FR801XH/FR801XT/FR800X/FR508X/FR30XX/FR201X/FR303X/FR803X/EX-FLASH) and ASR/aboot flashing via adownload.exe (ML307C 等 arom 设备、Quectel EG800AK/QDM562 等 USB 下载模式). Triggers: 烧录, 刷机, 下载固件, 线刷, FreqChip, 富芮坤, FR801XH, FR30XX, adownload, aboot, ASR, arom, ML307C, EG800AK, QDM562, AT+QDOWNLOAD, 量产烧录, 固件包烧录.'
---

# 烧录工具 Skill（flash-tools）

统一的固件烧录 skill，覆盖两类烧录工具。**先判断用户要烧录哪类芯片/设备，再跳转到对应 reference 执行。**

## 快速路由

| 用户场景关键词 | 走哪个流程 |
|---|---|
| FreqChip、富芮坤、FR801XH/FR801XT/FR800X/FR508X/FR30XX/FR201X/FR303X/FR803X、`FreqChip_Download_Consle.exe`、`setting.ini` | → [references/freqchip-download.md](references/freqchip-download.md) |
| ASR、aboot、`adownload.exe`、ML307C、EG800AK、QDM562、烧录 `.zip` 固件包、量产/升级模式 | → [references/aboot-flash.md](references/aboot-flash.md) |
| 其他 QDM/QDK 模块（EG91/OCPU、QFlash 线刷等） | 不属于本 skill，见对应产品测试 skill |

## 通用规则（两类烧录都适用）

1. **参数/固件必须先确认**：串口号、波特率（如用）、芯片型号或固件包路径——缺失时**必须向用户询问**，不得猜测或默认。
2. **烧录前确认设备已连接**：串口/设备未接不要反复重试。
3. **烧录是长耗时操作**：串口烧录可能几十秒到几分钟。在 QuecAgent 中执行时给 `execute_shell_command` 设置足够 `timeout`（建议 300–900 秒），或分段等待。
4. **烧录完成后清理进程**：不要让烧录工具的 CMD/控制台窗口残留；必要时用 `taskkill` 结束。
5. **烧录属于破坏性/设备写操作**：执行前向用户确认目标设备与参数；不要整片擦除（除非用户明确要求）。
6. **不要盲目重试**：报错先读日志定位（端口占用 / 未进下载模式 / 固件包不对），再决定下一步。
7. **烧录后必须核对版本**：不要只看“工具报成功”就收工。用设备侧手段读回版本确认（如 AT 指令
   `ATI` / `AT+QGMR` 看 `Revision`/`CustRevision`，或产品菜单里的版本查询项），与目标版本逐字比对。
8. **aboot 烧录后通常要物理断电重上电**才启动新固件（`-r` 只复位芯片，模块会再落回下载循环）——
   报成功但设备“没反应/仍在下载模式”时，先让用户拔插 USB / 断电重上电，而不是重烧。
9. **固件包可能是双层 zip**：外层含 DBG 符号 + 内层 zip；真正可烧录的是**内层**（根目录直接是
   `download.json` + 各镜像）。烧前先确认包结构。
10. **汇报结果**：串口号/设备、速率、芯片型号或固件版本、是否成功、关键输出、耗时。

## QuecAgent 环境适配说明

原工具文档中提到的 `AskUserQuestion` / `TaskOutput` / `TaskStop` / `run_in_background` 是其他 Agent 框架的工具名，在本环境对应：

| 原工具 | QuecAgent 对应做法 |
|---|---|
| `AskUserQuestion` | 直接用自然语言向用户提问，等用户回复 |
| `run_in_background=true` | `execute_shell_command` 无法真正后台常驻；改用足够大的 `timeout` 前台执行，或用 `start /b`、重定向日志到文件后轮询 |
| `TaskOutput` | 读取重定向的日志文件，或查看命令返回的 stdout |
| `TaskStop` | `taskkill /IM <exe名> /F` 结束烧录进程 |

## 子流程文档

- [references/freqchip-download.md](references/freqchip-download.md) — FreqChip（富芮坤）芯片串口烧录：芯片型号对照表、setting.ini 配置、标准流程、注意事项
- [references/aboot-flash.md](references/aboot-flash.md) — ASR 设备 aboot 烧录：adownload.exe 参数、固件包烧录流程、成功标志、注意事项

## 工具路径（用户环境，按需确认是否仍有效）

```
FREQCHIP_EXE = "D:/work/QDK007/FreqChip_Download V1.3.9/FreqChip_Download V1.3.9/FreqChip_Download_Consle.exe"
FREQCHIP_DIR = "D:/work/QDK007/FreqChip_Download V1.3.9/FreqChip_Download V1.3.9"
ADOWNLOAD    = "D:/QDM505 tool/aboot tool/aboot-tools-2020.09.10-win-x64/aboot-tools-2020.09.10-win-x64/adownload.exe"
```

> 路径变化时以用户实际环境为准；执行前建议先确认 exe 存在。
