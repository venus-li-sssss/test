# 错误码对照表

分析时先在这里查已知错误码，没有的再按日志上下文推断；新确认的错误码补充到本表。

## 设备端 MQTT / OTA

| 日志关键字 | 含义 |
|:---|:---|
| `-8,206` | 升级包断点续传失败 |
| `check fail 8` | 升级包完整性校验失败 |
| `request region url failed -8` | 升级服务器地址请求失败 |
| `ota timeout ack reset` | OTA 超时触发重置 |
| `http post error code = 0` | 网络请求失败 |
| `download failed` | 设备下载升级包失败（常与 `check fail 8` 同时出现） |

## 脚本侧

| 关键字 | 含义 |
|:---|:---|
| `statuscode: 201` | 升级指令下发成功，但状态检查失败 |
| `statuscode: 404` + `升级成功状态检测超时` | 在等待时间内没有进入升级成功状态 |
| `FOTA升级状态检查失败` | 多模块升级未全部完成 |
| `返回数据无RX` | 上位机发送后没有收到回包 |

## 设备 IAP（串口升级）

| 日志关键字 | 含义 |
|:---|:---|
| `IAP begin! file size: N` | 开始升级，固件大小 N 字节 |
| `IAP write: <总大小> <已写> - <百分比>` | 已写入进度 |
| `CMD: 8, index: xx, IAP result: 0` | 数据块 xx 写入成功 |
| `uart_reSend_iapData` | 设备侧重发处理，周期约 3 秒 |
| `IAP crc ok!` / `IAP reset` | 校验通过 / 升级完成后复位 |

## 常见联合分析链路示例

指令下发成功 → 设备下载升级包失败（`download failed`）→ 校验失败（`check fail 8`）→ 状态检查不通过（`statuscode: 201`）。
