---
name: log-analysis
description: 'Use this skill when the user wants to analyze large logs (tens to hundreds of MB) to find why a test round fails, times out or occasionally misbehaves, by comparing a normal round against an abnormal round. Triggers: "分析日志", "日志对比", "为什么超时", "升级超时", "偶发失败", "压测失败原因", "对比正常和异常日志", "script_log / upper_log / real_time_log / serial log 分析", root-cause analysis of stress/pressure test logs, upgrade (OTA/IAP/FOTA) timeouts, retransmission or packet-loss analysis.'
---

# 大日志对比分析 Skill

用脚本流式处理大日志，先给出"每轮结果 + 耗时"，再取一轮正常、一轮异常做对比，量化差异、找到突变点、排除假设，最后区分"已证实"和"未证实"。

经验来源：QDM559 T-BOX 上位机升级压测，三份日志共 670MB，见 [references/upgrade-timeout-case.md](references/upgrade-timeout-case.md)。

## 0. 开始前必须做的检查

1. 用户给了明确路径就直接用，不要全盘搜索。路径可能被粘贴成两段连在一起，需要拆开。
2. 先确认文件真实大小，不要凭"读出来是空的"下结论：
   ```powershell
   Get-ChildItem <path> | ForEach-Object { "$($_.Name) $([math]::Round($_.Length/1MB,1))MB" }
   ```
   - 工作区里同名文件是 0 字节，不代表用户说的文件为空；用户常把日志放在 Downloads，让用户确认路径。
   - 超过 50MB 的文件，文件读取工具会报 `Files above 50MB cannot be synchronized`，必须用脚本。
3. 同步终端有时返回空输出（`echo hello` 都没有输出）。此时改用异步模式运行命令，再读输出。
4. 不要把整份大日志读进上下文。脚本把结果写到小文件，再读小文件。

## 1. 识别日志角色

| 角色 | 典型文件名 | 用途 |
|:---|:---|:---|
| 脚本/控制日志 | `script_log_*` | 每轮步骤、判定、PASS/FAIL 统计，定位哪一轮异常 |
| 上位机/串口报文日志 | `upper_log_*`、`serial_*` | 收发帧，看协议层时序、重发、超时 |
| 设备固件日志 | `real_time_log_*`、`debug_*` | 设备端内部状态，看设备有没有收到、有没有报错 |

三份日志时间戳格式可能不同（带日期/不带日期），时钟可能有几十毫秒偏差，对齐时要留余量。

## 2. 分析流程

脚本目录：`scripts/`（下文省略路径前缀）。所有脚本都加 `python -X utf8`，用 `-o 文件` 输出到 UTF-8 文件再读取。

### 步骤 1：每轮结果与耗时

```powershell
python -X utf8 run_summary.py <script_log> -o sum.txt
```
- 看：总轮数、哪些轮耗时明显偏长、第一个失败轮、失败是否一直持续、失败原因是否都一样。
- `--marker` 指定轮次标记正则，`--poll` 指定轮询行（会被折叠成计数），`--result` 指定判定关键字。

### 步骤 2：取一轮正常、一轮异常，各读一次

```powershell
python -X utf8 run_summary.py <script_log> --detail 1  -o run1.txt    # 正常
python -X utf8 run_summary.py <script_log> --detail 34 -o run34.txt   # 异常
```
- 对比：阶段顺序、每个阶段耗时、超时发生在哪个阶段、重试次数和重试间隔。
- 用户要求"读一次正常日志再对比异常"时，只读这两份，不要逐轮读。

### 步骤 3：把超时变成可计算的预算

- 记下超时阈值（如每次等待 30 分钟、重试 2 次）。
- 估算"正常耗时 ÷ 阈值"的余量。余量只有 2~3 倍时，轻微劣化就会超时，这正是"有时候超时"的典型成因。
- 对重试型协议，建立公式：`总耗时 ≈ 丢帧次数 × 重发间隔`，再算出会超时的临界值。

### 步骤 4：全程趋势，找突变点

```powershell
python -X utf8 bucket_count.py <log> --step 600 --pat "tx=<发送行正则>" --pat "retry=<重发行正则>" --ratio tx/retry -o buckets.txt
```
- 先用 600 秒看全局，再对可疑区间用 60 秒或 10 秒细化（`--from/--to`）。
- 判断：突变还是渐变；偶发还是持续；突变点是否落在某一轮中间；突变后是否再没恢复。
- 注意区分"每分钟重发次数"（可能一直恒定，受定时器限制）和"两次重发之间成功的块数"（才反映真实丢失率）。

### 步骤 5：窗口内对比正常与异常

```powershell
python -X utf8 window_patterns.py <dev_log> --from 10:52:00 --to 11:02:30 --rate -o normal.txt
python -X utf8 window_patterns.py <dev_log> --from 17:20:30 --to 17:50:40 --rate -o bad.txt
python -X utf8 raw_window.py <dev_log> --from 17:30:00 --to 17:30:05 --exclude "IAP size|IAP write" -o w.txt
```
- 先比较各类消息的每秒速率，速率相同的类别可以排除。
- `window_patterns.py` 会把数字替换成 `#`，进度、序号这类数字会被抹掉，需要用 `raw_window.py` 看原始行。
- 看设备端"没收到"：在设备日志里搜被丢的序号，确认设备是否从未记录过，而不是记录了但回复丢了。

### 步骤 6：逐个排除假设

对每个假设写一行：假设、用什么数据验证、结论（排除/成立/无法判断）。常见假设：
- 网络/模组联网（对比 AT、MQTT、重连频率的每秒速率）
- 设备端报错（搜 `err|fail|crc|overflow|timeout|reset`）
- 数据内容问题（失败块重发后能否成功写入）
- 升级方向/版本差异（对比不同方向的轮次）
- 上位机一侧（PC 负载、串口适配器、重发间隔过长）
- 相关性假设（如丢帧与设备周期打印重合）要和随机重合比例比较，重合比例接近期望值就不能当作原因。

### 步骤 3 之后：给出结论

结论必须分三块：
1. **已证实**：有数据支撑的机制和量化结果。
2. **已排除**：做过对比且无差异的因素。
3. **未确认**：日志无法区分的部分，说明还缺什么证据，给出验证方法（抓线上数据、第二路串口、逻辑分析仪、系统事件日志等）。

再给出缓解建议（如缩短重发间隔、增加超时余量、增加丢帧计数日志）和根治方向，并标明哪些只是缓解。

## 3. 常见坑

- **输出乱码**：PowerShell 5.1 的 `>` 和 `Out-File` 会改变编码。用脚本的 `-o` 直接写 UTF-8，不要用重定向。
- **按时间过滤**：无日期的日志跨午夜时，用 `--from/--to` 的纯时间会匹配到第一个落在窗口内的区间。需要精确时带上日期，如 `--from "2026-11-06 17:00:00"`。
- **轮询行很多**：脚本日志里每 3 秒一行"等待…状态"，用 `--poll` 折叠，不要逐行读。
- **先别猜根因**：先有每轮耗时和突变点，再谈原因；不要把相关性当因果。
- **不要修改被分析的日志**，临时文件放 `%TEMP%`。

## 4. 汇报模板

```
文件：<三份日志及大小>
现象：共 N 轮，第 a~b 轮正常（约 X 分钟），第 c 轮起失败（超时 Y 分钟），持续到日志结束
机制：<协议流程 + 超时/重试规则>
对比：| 指标 | 正常 | 异常 |
突变点：<时间，是否在某一轮中间，是否恢复>
已排除：<列表>
未确认：<列表 + 验证方法>
建议：<缓解 / 根治>
```
