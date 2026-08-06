# WorkBuddy Skills 合集

本仓库收集了若干 WorkBuddy 用户级 skill，每个 skill 放在独立的顶层目录中，可直接复制到本地 `~/.workbuddy/skills/` 使用。

## Skill 列表

| 目录 | 用途 |
| --- | --- |
| [`ninebot-project/`](./ninebot-project) | 九号(Ninebot) 一体化 skill：① IoT OTA 固件平台（iot-test.ninebot.com）的固件查询/上传、设备查询、FOTA 升级/回滚/状态；② 已连接 Android 手机上九号出行 APP 的 UI 控制（闪灯鸣笛、查状态、截图验证），基于 uiautomator2 相对定位。触发词：九号、Ninebot、固件、OTA、FOTA、升级、回滚、设备控制、UI自动化 等。 |
| [`changelist2xlsx/`](./changelist2xlsx) | 将 git changelist（修改点）txt 导入 SMOD 平台并自动新增测试用例：① 生成同名 Excel 清单 → ② 导入 SMOD → ③ 按修改点描述自动建用例并设置测试结果。所有结果直接写入 SMOD 平台。 |
| [`quectel-attendance/`](./quectel-attendance) | 查询移远 QHR 考勤系统（hr.quectel.com）的打卡记录并计算工时：首次/末次打卡、有效工时、迟到早退、弹性工作补偿、19 点后加班时长统计。触发词：考勤、打卡、工时、加班、迟到、QHR。 |
| [`qdisk-quectel/`](./qdisk-quectel) | 移远网盘（Quectel Netdisk / qdisk.quectel.com）下载工具：把网盘中的文件或整个目录下载到本地指定位置。触发词：移远网盘、qdisk、下载网盘。 |
| [`jira-data-access/`](./jira-data-access) | JIRA 数据访问与处理：通过 JQL 或搜索 URL 查询缺陷数据，过滤/排序/统计，并生成标准化 DOCX 缺陷报告。 |
| [`log-analyzer/`](./log-analyzer) | 自动化分析各类日志文件：单日志分析、设备日志与脚本日志联合分析、结合日志指南的深度问题定位；适用于故障排查、根因分析、运行结果统计。 |
| [`api-class-generator/`](./api-class-generator) | 根据 HAR 文件或接口文档 + 操作流程描述，自动生成 Python API 类（requests 库，自动维护 session/cookie，含完整方法与 main() 示例）。 |
| [`protocol-pack-unpack/`](./protocol-pack-unpack) | 通信协议组包/解包代码生成器：支持 CAN、Serial(UART)、MQTT 二进制帧的 pack_frame()/unpack_frame() 生成，含自动化双向测试与迭代自修复（偏移/大小端/校验/缩放）。 |
| [`pyinstaller-exe-packager/`](./pyinstaller-exe-packager) | 将 Python 脚本快速打包为 Windows 单文件 exe（PyInstaller onefile），内嵌版本信息文件（references/version_info.txt）。流程极简：装 pyinstaller 后直接打包。 |

## 使用方法

将对应目录整体复制到 WorkBuddy 用户级 skill 目录即可：

```
cp -r <skill目录> ~/.workbuddy/skills/
```

## 安全说明

- 各 skill 的登录凭据（账号密码、token）均由**运行时**由用户手动输入，或从本地凭据文件读取，**不会**随代码提交。
- 本仓库**已排除**以下本地凭据文件，请勿将其加入版本控制：
  - `quectel-attendance/.credentials.json`
  - `qdisk-quectel/.token_cache.json`
- 建议将本仓库保持为**私有**，并避免提交任何含明文密码或会话 token 的文件。
