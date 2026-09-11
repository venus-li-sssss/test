# Unisoc（展锐）平台命令行烧录 — FlashToolCLI

> 工具：`QFLASH_DIR\EFlashTool\1\FlashToolCLI.exe`（实测版本 v4.1.11，2024-01-23）
> 支持芯片：EC618 / EC718 / EC217 / EC716 / EC626 / EC616 等
> 配套：`config*.ini`（如 `config_ec618_uart.ini`、`config_ec618_usb.ini`）、`cmd_demo_618.txt`、`cmd_demo_718.txt`

## 命令总览

```
FlashToolCLI [-h] [--port PORT] [--verbose VERBOSE] [--cfgfile CFGFILE]
             [--skipconnect SKIPCONNECT] [--lineid LINEID]
             {list_com,burn,burnone,burnbatch,burn_pkgflxs,probe,list_flashinfo,
              flasherase,flashread,termode,runtmcfg,rst2dldboot,sysreset,pkg2img,chkpkgimg}
```

| 参数 | 说明 |
|---|---|
| `--port/-p PORT` | 串口，如 `COM47` |
| `--cfgfile CFGFILE` | 配置文件（必须，决定芯片/镜像布局/波特率等） |
| `--skipconnect 1` | 跳过 agentboot 下载（后续步骤复用已建立连接时用） |
| `--verbose/-v N` | 详细日志级别 |
| `--lineid N` | 指定下载产线号 |

| 子命令 | 用途 |
|---|---|
| `list_com` | 列出可用串口 |
| `probe` | 下载 agentboot 并建立连接（第一步） |
| `list_flashinfo` | 列出 flash 信息 |
| `flasherase <addr> <size>` | 擦除 flash 区间（可加 `--stor_type`） |
| `burn` / `burnone` / `burnbatch` / `burn_pkgflxs` | 烧录（批量用 `--imglist`） |
| `flashread` | 读取 flash |
| `pkg2img` | 从升级包解出独立镜像 |
| `chkpkgimg` | 校验镜像与包是否匹配 |
| `sysreset` | 复位设备 |
| `rst2dldboot` | 用第二辅助串口复位进入下载 boot |
| `runtmcfg` | 运行时参数配置（下发芯片/单板参数） |
| `termode` | 终止模式设置 |

## 标准流程（来自官方 cmd_demo）

### UART 下载模式（分步烧录）
```bat
:: 1) 连接（下载 agentboot）
FlashToolCLI.exe --cfgfile config_ec618_uart.ini --port COM47 probe
:: 2) 擦除
FlashToolCLI.exe --skipconnect 1 --cfgfile config_ec618_uart.ini --port COM47 flasherase 0 0x400000
:: 3) 烧录
FlashToolCLI.exe --skipconnect 1 --cfgfile config_ec618_uart.ini --port COM47 burnbatch --imglist bootloader system cp_system
:: 4) 复位
FlashToolCLI.exe --skipconnect 1 --cfgfile config_ec618_uart.ini --port COM47 sysreset
```

### USB 下载模式
```bat
FlashToolCLI.exe --cfgfile config_ec618_usb.ini --port COM47 probe
FlashToolCLI.exe --skipconnect 1 --cfgfile config_ec618_usb.ini --port COM47 flasherase 0 0x400000
FlashToolCLI.exe --skipconnect 1 --cfgfile config_ec618_usb.ini --port COM47 burnbatch --imglist bootloader system flexfile0 flexfile1
FlashToolCLI.exe --skipconnect 1 --cfgfile config_ec618_usb.ini --port COM47 sysreset
```

### 整包（Package）烧录
```bat
:: 1) 解包检查
FlashToolCLI.exe --cfgfile config_ec618_uart.ini pkg2img
:: 2) 连接
FlashToolCLI.exe --cfgfile config_ec618_uart.ini --port COM25 probe
:: 3) 擦除（AP/CP 分别擦）
FlashToolCLI.exe --skipconnect 1 --cfgfile config_ec618_uart.ini --port COM25 flasherase 0 0x400000 --stor_type "ap_flash"
FlashToolCLI.exe --skipconnect 1 --cfgfile config_ec618_uart.ini --port COM25 flasherase 0 0x100000 --stor_type "cp_flash"
:: 4) 烧录（若 config 里配了 flexfile，imglist 里加 flexfile0）
FlashToolCLI.exe --skipconnect 1 --cfgfile config_ec618_uart.ini --verbose 1 --port COM25 burnbatch --imglist bootloader system cp_system
:: 5) 复位
FlashToolCLI.exe --skipconnect 1 --cfgfile config_ec618_uart.ini --port COM25 sysreset
```

## 注意
- `--imglist` 里的名称必须与 `config*.ini` 中定义的镜像名一致（bootloader/system/cp_system/flexfile0/…）
- 退出码/日志中不含 "error"/"fail" 且 `sysreset` 正常执行为成功判据
- 日志会写到 `EFlashTool\1\logging_output.log`（可据此排查）
