---
description: Use this skill when 用户要抓取/录制串口日志：抓 COM247 和 COM98 的日志、开始抓串口、跑起来抓日志、常驻抓日志、串口日志抓取、抓log、监听某个 COM 口、dump 串口输出、同时抓多路串口、hex 模式抓二进制、看抓取状态、停止抓日志。本地没工具时会自动从飞书云盘下载抓取工具再跑。
name: 抓取串口日志
---

# 抓取串口日志

默认场景：**COM247 + COM98，115200，text 模式**。

工具来源只有两条路：

1. **本地已有工具** → 直接用
2. **本地没有** → 从飞书云盘拉到 **C 盘**，拉完直接跑

拉不到 or 跑不起来就**报错停下**（退出码 2），不做 Python 兜底 —— 抓日志的能力全靠这个工具，降级抓到的东西和它不对等，容易给出错误结论。

> ⚠️ **软件只能放在 C 盘。** 放 `%TEMP%`、D 盘、桌面，Bitdefender Endpoint 会在执行那一瞬间删掉 exe（报「拒绝访问 / 系统找不到指定的文件」）。非 C 盘的 `--tool-dir` 会被强制改到 `C:\QuecAgentTools\串口日志抓取\`。

## 软件名（v3.9 起）

工具改名 **串口日志抓取 → 日志抓取**：`日志抓取.exe` / `日志抓取.ini`。
脚本两个名字都认（同目录优先 `日志抓取.exe`，没有就退回 `串口日志抓取.exe`），
云盘里还是老文件名也能照常拉取，不用手动改名。

## RTK 差分（v3.9 新增）

给某个串口登录 NTRIP 差分账号：设备自己的 GGA 发给 caster，caster 回的 RTCM **注回同一个串口**。

```bat
python scripts\capture_serial_log.py --ports COM100 --sec 60 ^
    --rtk-host 106.13.146.74 --rtk-port 8102 --rtk-mount RTCM_CC ^
    --rtk-user xyw0040 --rtk-pass ****** --rtk-target com100
```

- `--rtk-target`：给哪个目标开（别名 / COM 号 / `all`，默认 all）
- RTCM 默认**不开**；只有带 `--rtk-host`/`--rtk-mount` 才会开
- 成没成看 `status.json` 里每个 target 的 `rtk`：`state=connected` 是登录成功，
  `fix=RTK Fixed` 才是真进了固定解

查 caster 上有哪些挂载点（不抓日志）：

```bat
"<工具目录>\日志抓取.exe" /rtksourcetable /rtkhost:106.13.146.74 /rtkport:8102 /quiet
```

账号**默认就从多维表格取**：

```bat
rem 一个开关：自动取第一个可用账号，并顺手刷新工具目录下的 rtk_accounts.tsv
python scripts\capture_serial_log.py --ports COM100 --sec 60 --rtk-auto

rem 只想看看表里有哪些账号
python scripts\rtk_accounts.py
python scripts\rtk_accounts.py --json --out rtk_accounts.json
```

- `--rtk-auto`：账号从飞书位表「资源 → GNSS的RTK账号信息」取（第一个 `账号状态=可用`）
- 显式给了 `--rtk-user` 就以你给的为准
- 跑完会把缓存写到 `<工具目录>\rtk_accounts.tsv`，**GUI 打开 RTK 对话框会直接读它**

## HEX 日志后缀（v3.9 新增，默认已改回 .log）

HEX 模式**默认存 `.log`**（内容就是带时间戳的 16 进制转录，本质还是日志）；
要裸数据流才用 `--hex-file bin`，要 `.hex` 用 `--hex-file hex`。文本模式固定 `.log`。

为什么默认是 `.log`：实际用 16 进制的场景基本都是**协议交互** —— 发一条 16 进制指令、
看 16 进制返回；这种内容本来就不是裸码流，存成 `.bin` / `.hex` 反而不好读也不好发。

```bat
rem 默认：HEX 模式存 .log
python scripts\capture_serial_log.py --ports COM100 --mode hex --sec 30

rem 只有真要裸二进制 / .hex 时才显式指定
python scripts\capture_serial_log.py --ports COM100 --mode hex --hex-file bin --sec 30
python scripts\capture_serial_log.py --ports COM100 --mode hex --hex-file hex --sec 30
```

GUI 里对应「HEX 存」下拉框：`.log`（默认）/ `.bin` / `.hex`，ini 里是 `hexfile=log|bin|hex`。

## 两种模式

**模式 A：常驻抓取（默认用这个）** —— 工具在后台一直跑着抓，命令返回后进程还活着。

```bat
python "<此 SKILL.md 所在目录>\scripts\capture_serial_log.py" --ports COM247,COM98 --launch
python "<此 SKILL.md 所在目录>\scripts\capture_serial_log.py" --status
python "<此 SKILL.md 所在目录>\scripts\capture_serial_log.py" --stop
```

用户说"你运行""跑起来抓""开始抓日志""抓一下"时，用 `--launch`。说完就把状态表回给他，并给出日志目录。

**模式 B：定时抓取（定长）** —— 抓 N 秒后自己停，产出 `summary.md`/`summary.json`。

```bat
python "<此 SKILL.md 所在目录>\scripts\capture_serial_log.py" --ports COM247,COM98 --sec 40
```

> ⚠️ `--sec` **不要超过 45**。命令执行器单次上限约 60 秒，超了父进程被掐、exe 被连带杀掉（会抓到一半数据但没有 `result.json`）。要抓更久 → 用模式 A，或者拆多次 `--sec 40`。

退出码：`0` 成功 · `2` 工具不可用 / 启动失败 · `3` 全 0 字节或没有实例 · `4` 参数错误。

## 参数

| 参数 | 说明 | 默认 |
|---|---|---|
| `--launch` | 常驻启动（后台一直抓，命令结束不退出） | — |
| `--status` | 查看常驻实例状态 | — |
| `--stop` | 停止常驻实例 | — |
| `--ports` | 逗号分隔的串口，如 `COM247,COM98` | — |
| `--targets` | 精确指定每一路：`别名\|COM号\|波特率\|模式`，用 `;` 分隔 | — |
| `--baud` | 统一波特率 | `115200` |
| `--mode` | `text` / `hex` | `text` |
| `--sec` | 定时抓多久（秒），**≤45** | `60` |
| `--out` | 定时模式的输出目录 | `<workspace>\serial_logs\<时间戳>` |
| `--live-dir` | 常驻模式的日志目录 | `<workspace>\serial_logs\live` |
| `--instance` | 常驻实例名 | `live` |
| `--tool-dir` | 工具目录（非 C 盘会被强制重定向） | `<workspace>\串口日志抓取` |
| `--no-download` | 本地没工具就报错 | 关 |
| `--ensure-tool-only` | 只准备工具，不抓 | 关 |
| `--list-ports` | 列出本机串口 | — |
| `--hex-file` | HEX 模式日志后缀：`log`（默认，16 进制转录）/ `bin`（裸二进制）/ `hex` | `log` |
| `--rtk-host` `--rtk-port` `--rtk-mount` | RTK caster 地址/端口/挂载点 | — |
| `--rtk-user` `--rtk-pass` `--rtk-target` | RTK 账号/密码/给哪个目标开（别名或 COM，默认 all） | — |
| `--rtk-auto` | 账号从飞书多维表格自动取（第一个可用），并刷新 `rtk_accounts.tsv` | 关 |

## 常驻模式是怎么实现的（别改回去）

命令执行器把子进程放进 **kill-on-close 的 job**，命令一结束 exe 就被连带杀掉。所以 `--launch` 走的是：

1. 生成 **GBK 编码**的 `launch_live.bat`（放在工具目录）—— cmd 按 GBK 解析 bat，**用 UTF-8 写的中文路径会变乱码，exe 静默启动失败**，现象是 schtasks 返回成功但进程根本不存在；
2. `schtasks /create + /run` 由计划任务启动 exe —— 它不属于我们的 job，能跨命令存活；
3. 轮询 `status.json` 等到 `state=running` 再返回。

停止走 `taskkill /PID <status.json 里的 pid>`，只杀这一路，不动用户手动开的窗口。实例名不同（`--instance`）就能并存多份。

## 结果怎么读

- 日志：`<别名>_<YYYYmmdd_HHMMSS>.log`，text 模式每行前带毫秒时间戳，**原始字节原样保留**（GBK 中文不会坏）。
- `status.json` 每秒刷新：`state`、`elapsed_sec`、`totals.{lines,bytes,connected,targets,reconnects}`、每个 target 的 `current_file` / `current_size` / `last_error`。
- **常驻模式刚启动的那几十秒 `current_size` / 文件大小可能还是 0** —— 工具是带缓冲写的，缓冲攒够了才落盘。别据此说"没抓到"，看 `status.json` 的 `bytes` 才准。
- 某一路 `bytes=0` 时脚本会单独列出并给排查顺序，**不要说"工具坏了"**：先换波特率复测，再确认设备这个口当前到底有没有在打日志。

## 踩过的坑（实测）

1. **exe 不能乱放**：`%TEMP%`、D 盘、桌面会被执行瞬间删除。能稳定跑的位置：`<workspace>\串口日志抓取\`、`C:\QuecAgentTools\串口日志抓取\`（都在 C 盘）。
2. **exe 被删了重跑同一条命令**：本地找不到会自动从飞书重新拉。
3. **只认 `串口日志抓取.exe`**（v2.x，支持 `/auto /run /targets /sec /headless`）。工作区里旧的 `抓取日志_tool\dist\抓取日志.exe` 是另一个 GUI 版，**不认这些参数**（实测静默退出无输出），已从候选里剔除，别捡回来。
4. **串口被占用**（QCOM / SSCOM / WindTerm / 上位机）：工具一直重试，`last_error` 写「访问被拒绝」，`bytes=0`。先关掉占用工具。
5. **COM247 长期 0 字节**：2026-11-10 实测 57600 / 115200 / 230400 / 460800 / 921600 / 1500000 / 3000000 **全部无输出**、口能正常打开 → 设备侧这个口当前没有日志流，不是波特率也不是工具问题。如实告诉用户，别反复换波特率耗时间。
6. **用 `subprocess` 直接拉 exe**，不要 `start /wait`（`/headless` 下中文路径会报「拒绝访问」）。

## 工具从哪来

**本地优先**，按顺序找第一个能用（>10KB 且在 C 盘）的：

1. `<tool-dir>\串口日志抓取.exe`（默认 `<workspace>\串口日志抓取\`）
2. `C:\QuecAgentTools\串口日志抓取\串口日志抓取.exe`
3. `<workspace>\串口日志抓取UI\串口日志抓取.exe`

**本地没有就去飞书云盘拉**（免扫码，应用身份 `tenant_access_token`）：

- 云盘文件夹：`GQzGfjpbQl7gCodXdjJcdgten6d`（「测试环境搭建 → 串口日志抓取」）
- 团队只读机器人凭据内置在脚本里（`cli_a9bc97317fb89cc8`，可公开）；
  token 缓存在 `~/.feishu_tat_cache.json`（2h，提前 5 分钟续期）
- 下载走 `preview_download?preview_type=16`（`/medias/xxx/download` 对 bot 会 403）

### 拉取流程（2026-11-10 重构，别再改回写死 token）

```
取 tenant_access_token（有缓存）
  → 列 FEISHU_FOLDER，按文件名取**当前** file_token
  → 逐个 preview_download（Range 断点续传，最多 5 次）
  → 校验 exe > 10KB 才算成功
```

- **写死的 `FEISHU_FILES` 只是兜底**：列目录失败时才用
- **云端替换文件后 token 会变**，脚本会自动跟随并在日志里说
  `[tool] 云端 file_token 已变化，自动跟随最新: xxx`
- **下载失败会自动刷新 token 重试一次**（401/403/1061004 多半是 token 过期或换应用）
- 怀疑本地工具是旧版：加 `--refresh-tool` 强制重下

```bat
python scripts\capture_serial_log.py --ensure-tool-only              :: 只确保工具就位
python scripts\capture_serial_log.py --ensure-tool-only --refresh-tool  :: 强制重拉最新版
```

### 拉取失败怎么排（按顺序看日志）

| 日志/现象 | 原因 | 处理 |
|---|---|---|
| `WARN: 列目录失败(...) 回退脚本内置 token` 后仍成功 | 列目录接口抖动，内置 token 还能用 | 正常，可忽略；持续出现再查权限 |
| `列目录失败 code=1061004` | 文件夹没共享给这个应用 | 让目录所有者把应用加为**可阅读**协作者（搜应用名，不是人名） |
| `HTTP 403` / `code=1061004` 下载时 | token 过期或应用被移出协作者 | 脚本已自动刷新重试；仍失败看权限 |
| `HTTP 404` | file_token 失效（云端替换过文件，且列目录也失败） | 网络恢复后重跑；或 `--refresh-tool` |
| `拉下来的 exe 只有 N 字节` | 接口返回了错误 JSON，被当成文件写盘 | 看上面错误码；清掉 `%TOOL_DIR%\串口日志抓取.exe` 后重跑 |
| `下载后仍找不到 ...exe` | 被安全软件/EDR 删了 | 工具目录必须在 **C 盘**（`C:\QuecAgentTools\串口日志抓取\`），见下方"踩过的坑" |
| `retry 1/5 ... retry 5/5` 全失败 | 网络断流 | 已带 Range 续传 + 5 次重试；仍失败就稍后重跑（会从 `.part` 续上） |

云端更新后想核对目录里有哪些、token 是什么：

```bat
python <feishu-software-download skill>\scripts\feishu_dl.py find 串口日志抓取
```

## 依赖

只需 `requests`（拉工具用）。`--list-ports` 优先用 pyserial，没装就走注册表枚举，pyserial 不是必须的。
