# STM32 平台命令行烧录 — STM32_Programmer_CLI

> 工具：`QFLASH_DIR\STM32\1\bin\STM32_Programmer_CLI1.exe`（实测 STM32CubeProgrammer v2.11.0）
> 接口：ST-LINK（JTAG/SWD）、UART bootloader、USB DFU、SPI/CAN/I2C
> 支持烧录格式：bin / hex / srec / s19 / elf / stm32 / tsv

## 常用命令

```bat
:: 列出可用接口
STM32_Programmer_CLI1.exe -l uart
STM32_Programmer_CLI1.exe -l usb
STM32_Programmer_CLI1.exe -l st-link

:: 擦除 + 下载 + 校验 + 复位（最常用组合，ST-LINK SWD）
STM32_Programmer_CLI1.exe -c port=SWD -e all -w firmware.bin 0x08000000 -v -rst

:: 仅下载（不擦除；配合 --skipErase 预防擦除）
STM32_Programmer_CLI1.exe -c port=SWD -w app.bin 0x08000000 -v

:: UART 下载（指定串口与波特率）
STM32_Programmer_CLI1.exe -c port=COM5 br=115200 P=EVEN -e all -w firmware.hex -v -rst

:: USB DFU 下载
STM32_Programmer_CLI1.exe -c port=usb1 -w firmware.bin 0x08000000 -v -rst

:: 读回上传
STM32_Programmer_CLI1.exe -c port=SWD -u 0x08000000 0x10000 dump.bin

:: 仅擦除 / 选项字节操作 / 读保护解除
STM32_Programmer_CLI1.exe -c port=SWD -e all
STM32_Programmer_CLI1.exe -c port=SWD -ob displ
STM32_Programmer_CLI1.exe -c port=SWD -rdu
```

## 关键参数速查

| 参数 | 说明 |
|---|---|
| `-c/--connect port=<PortName>` | 连接：`JTAG` / `SWD` / `COMx` / `usb1`… |
| SWD/JTAG 可选 | `freq=`、`index=`、`sn=`、`mode=NORMAL/HOTPLUG/UR/POWERDOWN`、`reset=SWrst/HWrst/Crst`、`shared` |
| UART 可选 | `br=<波特率>`、`P=NONE/ODD/EVEN`、`db=8`、`sb=1`、`fc=OFF` |
| `-e/--erase` | `all` / 扇区 `0,1,2` / 区间 `[5 10]` |
| `-w/--download <file> [address]` | 下载（bin 必须给地址；hex/elf 自带地址） |
| `--skipErase` | 编程前跳过擦除 |
| `-v/--verify` | 校验 |
| `-u/--upload <addr> <size> <file>` | 上传到文件 |
| `-rst` / `-hardRst` | 软复位 / 硬件复位（SWD） |
| `-g/--go <addr>` | 从指定地址运行 |
| `-ob displ/...` | 选项字节显示/修改 |
| `-rdu` | 解除读保护（RDP1→0） |
| `-q` 静默、`-log file.log` 日志、`-y` 忽略确认 | 辅助参数 |

## 注意
- **bin 文件必须给烧录地址**；hex/srec/elf 自带地址可不给
- SWD 下 `-w` 会先做解析不擦除，需要整片重烧时显式加 `-e all`
- 产物校验用 `-v`；复位用 `-rst`
- 其余高级能力（SFI 安全编程、OTP、SWV 日志、密钥管理、HSM）见工具 `--help` 输出