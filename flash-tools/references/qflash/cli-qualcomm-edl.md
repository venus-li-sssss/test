# Qualcomm（EDL / 9008）命令行烧录 — QSaharaServer + fh_loader

> 工具（QFlash 自带，非 GUI）：
> `QFLASH_DIR\QCMM\CH1\QSaharaServer.exe`、`QFLASH_DIR\QCMM\CH1\fh_loader.exe`
> 辅助：`QModeSwitch.exe`、`fastboot.exe`（同目录）、`SDX7X\fh_loader.exe`
> 适用：Qualcomm 平台（MDM9607/EG91 OCPU、SDX 系列等），走 EDL(9008) + firehose
> 实测工具版本：QSaharaServer / fh_loader build 2019-06-25

## 原理与流程

```
① 设备进 EDL(9008) → ② QSaharaServer 载入 firehose programmer（prog_nand_firehose_9x07.mbn）
→ ③ fh_loader 按 rawprogram xml 烧写 update/ 镜像 → ④ reset 重启
```

### ① 让设备进入 EDL（9008）
方式（按设备支持选择）：
- `adb reboot edl`（设备正常时最简单）
- `fastboot oem edl`（QCMM\CH1\fastboot.exe）
- `QModeSwitch.exe`（GUI/工具切换模式）
- 硬件：EDL 测试点短接 / 治具按键，上电进 9008
- 成功标志：设备管理器出现 **Qualcomm HS-USB QDLoader 9008 (COMx)**

### ② Sahara 引导（载入 firehose programmer）
```bat
QSaharaServer.exe -p \\.\COM19 -s 13:prog_nand_firehose_9x07.mbn -b <update目录>
```
| 参数 | 说明 |
|---|---|
| `-p \\.\COMx` | 目标端口（EDL 端口） |
| `-s 13:<file>` | image id 13（= programmer/prog firehose）映射文件名 |
| `-b <path>` | 文件搜索路径 |
| `-v 1` | 详细日志 |

### ③ firehose 烧录（按 xml 烧镜像）
```bat
fh_loader.exe --port=\\.\COM19 --sendxml=rawprogram_nand_p4K_b256K_update.xml ^
              --search_path=<update目录> --noprompt --reset
```
如平台需要 patch：
```bat
fh_loader.exe --port=\\.\COM19 --sendxml=patch_p4K_b256K.xml --search_path=<update目录> --noprompt
```
常用参数：
| 参数 | 说明 |
|---|---|
| `--port=\\.\COMx` | 端口（注意 `\\.\COM` 前缀写法） |
| `--sendxml=<file>` | 要执行的 firehose xml（rawprogram / patch / contents） |
| `--search_path=<dir>` | 镜像搜索目录（指到 `update/`） |
| `--noprompt` | 不交互（自动化必须） |
| `--reset` | 烧完复位设备 |
| `--loglevel=`, `--verbose` | 日志 |
| `--showpercentagecomplete` | 进度百分比 |
| `--zlpawarehost=1` | ZLP aware host（部分平台需要） |
| `--memoryname=nand` | 存储类型（NAND 平台可显式指定） |
| `--erase=all` | 全擦（慎用） |
| `--setactivepartition=<n>` | 切换活动分区（A/B 平台） |
| `--verify_programming` | 烧写校验（按需） |

### ④ 完成
- 设备自动重启（`--reset`）
- 校验版本（见 qdm002-test / 版本查询文档）

## 注意事项

- **镜像与 xml 必须配套**：`rawprogram_nand_p4K_b256K_update.xml` 里的分区/文件名要与 `update/` 目录实际文件一致（本包：appsboot.mbn、sbl1.mbn、tz.mbn、rpm.mbn、NON-HLOS.ubi、mdm9607-boot.img、mdm9607-recovery.ubi、mdm9607-sysfs.ubi、data.ubi、usrdata.ubi、partition.mbn、QDM002_MCU_*.bin）
- **端口是 EDL(9008) 端口**，不是普通 AT/ADB 端口
- `QSaharaServer` 执行后设备进入 firehose 模式，端口通常保持；若端口变化需重新确认
- 错误日志：`fh_loader` 会在当前目录写 `port_trace.txt`（超长截断）
- 设备需先能进 EDL；若 USB 枚举异常（如"未知 USB 设备 端口重置失败"），先排查线缆/供电/驱动
- **破坏性**：整包烧录会重写分区（可能清用户数据），执行前确认
