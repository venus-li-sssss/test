# 其他平台命令行烧录速查（MTK / Rockchip / FreqChip / NB-IoT / Beken / Altair）

## MTK 平台

- 工具：`QFLASH_DIR\MTK\1\ThinModemFlashTool1.exe`（GUI，带 `plugins`/`flash.dll`）
- **命令行烧录方式**（MT2731R，官方 `MTK\1\MT2731R\命令.txt`）：
  ```bat
  flashimage.exe --productdir E:\Python\AG509MEUAAR01A01V02T4G
  ```
  即：把准备好的 product 目录（含镜像）交给 `flashimage.exe` 烧录。
- 其他辅助：`read_efuse.xml` / `write_efuse.xml`（读写 efuse）、`option.ini`、`history.ini`

## Rockchip 平台

- 工具：`QFLASH_DIR\ROCKCHIP\1\upgrade_tool1.exe`
- 文档：同目录 `命令行开发工具使用文档.pdf`（详细命令参考），`revision.txt`（版本记录）
- 典型用法（upgrade_tool，Rockchip 通用）：
  ```bat
  upgrade_tool.exe ld                                  :: 列出设备
  upgrade_tool.exe uf firmware.img                     :: 升级整包镜像
  upgrade_tool.exe wl 0x0 boot.bin                     :: 按地址写
  upgrade_tool.exe rd                                  :: 复位/重启
  ```
  > 具体子命令以该工具 `--help` / PDF 文档为准

## FreqChip（富芮坤）

- 工具：`QFLASH_DIR\FREQCHIP\1\freqchip_flash_tool1.exe`（Python 打包，v1.0.x）
- 历史变更中的可用参数/行为（readme）：
  - `-t` 握手超时参数
  - 烧录完成前有 `disconnect` 指令
  - RTS/DTR 时序控制（DTS=FALSE, RTS=FALSE → sleep 200 → RTS=TRUE）
- 另有独立 GUI 工具（见 `flash-tools` skill 的 `FreqChip_Download_Consle.exe` 流程，通过 `setting.ini` 配置）

## NB-IoT（BC95 等）

- 工具目录：`QFLASH_DIR\NB-IoT\1\UEUpdaterCLI\`（及 `UEUpdaterCLI_317\`）
- 说明文件：`info.txt`（该目录为版本信息/commit 记录）
- 用法：进入 UEUpdaterCLI 目录运行其 CLI 工具（按工具内帮助/README），配合 GUI 端 `BC95_Baud_Switch`/`BC95_Save_Log`/`BC95_Erase_Switch` 等配置项

## Beken（博通集成）

- 工具：`QFLASH_DIR\Beken\1\bk_loader1.exe`
- 独立 loader，按工具帮助使用（通常指定串口 + 固件）

## Altair（GNSS，cxd5605）

- 工具目录：`QFLASH_DIR\Altair\1\`
  - `ImageBurnTool1.exe` / `BoardInfoCreatorTool.exe` / `cxd5605_comm1.exe` / `VersionManager.exe`
  - 帮助：`ImageBurnTool_Help.pdf`、`readme.txt`
- 需要 Kermit 通信（`KermitModule.dll`）、可能需要 `WinSCP`（网络传输）

## GNSS 其他（LC76G / HI2120）

- 目录：`QFLASH_DIR\LC76G`、`QFLASH_DIR\HI2120\1`（`readme.txt` / `readme en.txt`）
- 由 QFlash GUI（GNSS 平台）驱动，或按各自 readme 使用独立工具

## 通用注意

- 这些平台多数由 **QFlash GUI** 统一调度（GUI 会自动调用子工具）；需要命令行/自动化时才直接调用上述 exe
- 使用前先 `list_com`/`-l` 确认端口，确认固件目录与镜像名
- 清理：结束后 `taskkill /IM <工具名> /F`
