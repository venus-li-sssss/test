# QFlash GUI 使用要点（Qualcomm 等平台）

> 主程序：`QFLASH_DIR\QFlash_V7.5.exe`（GUI，**无命令行烧录能力**）
> 适用：Qualcomm/QCMM（EG91/MDM 等 OCPU 模块）、以及由 GUI 统一调度的其他平台

## 典型流程

1. **固件准备**：拿到 QFlash 格式的整包/目录（一般含 `update/` 所有镜像 + `firehose/*.xml`，如
   `EG91NAFBR07A14M4G_OCPU_NCLD_BETA260907.zip` 解压后的目录结构）。
2. **设备进下载模式**：
   - Qualcomm：设备进入 **EDL/9008** 或 **QDLoader 端口**（治具按键/短接/命令触发）
   - 在设备管理器确认端口出现（QDLoader 9008 / Quectel DLoader Port）
3. **GUI 配置**：
   - 选择芯片平台/型号（Qualcomm）
   - 选择固件路径（`update/` 目录或 xml）
   - 选择 COM 口 / 下载模式（DLoader / HS_DL_MODE）
   - 勾选镜像、擦除与用户数据选项
4. **开始下载** → 等待完成 → 设备自动重启（`Reset_after_DL`）
5. **验证**：设备起来后查版本（ProducLine 工具/AT/菜单），确认目标版本

## MainConfig.ini 关键配置项（可预置，减少手点）

| 配置项 | 说明 |
|---|---|
| `Com_Main` / `BR_Main` | 主串口号 / 波特率（0=自动，8 等为索引） |
| `Scat_Cfg_File_Path` | 烧录配置/镜像索引文件路径（如 `at_command.hbinpkg`） |
| `QCN_Temp_File_Path` | QCN 文件路径（写 RF 校准用） |
| `OCPU_Name` | OCPU 名称选择（-1 默认） |
| `QFLASH_CMD` | 是否走 QFlash 命令模式 |
| `Firehose_Reset_after_DL` | 下载完成后 firehose 复位 |
| `Wirte_RF_Configure` | 是否写 RF 配置 |
| `Com_Method` | 通信方式选择 |
| `Reset_after_DL` | 下载完成后复位 |
| `Clear_User_Data` | 是否清除用户数据（**1=清**，注意会清掉 /usrdata 等） |
| `HS_DL_MODE` | 0=Quectel DLoader Port；1=HUAWEI Mobile Connect DownLoad port |
| `PCIE_DL` | PCIE 接口下载开关 |
| `Provision_Type` | Flash 供应商类型 |
| `WriteKV_V200` | KV 写入开关 |

> 其他配置文件：`Params_Main.ini`、`bootloader.ini`、`PL_Upgrade.ini`、`NvDefinition.xml`（NV 定义）

## 注意

- **GUI 无法命令行化**：如果需要自动化，Qualcomm 平台建议评估官方 `QFIL`/`QPMST` 的命令行，或由用户手动点烧、脚本只做前后处理
- 烧录前确认 `Clear_User_Data` 设置：会清除设备用户分区（**组件级升级文件、客户配置会丢**）
- 日志：`logging_output.log`、`port_trace.txt`、`log/` 目录
- 工具集里 `Tools\`（`GenerateKey.exe`/`ImageKey.exe`/`XYRSA.exe`）用于密钥/签名相关操作，`bin\filegen.exe` 生成 bin
