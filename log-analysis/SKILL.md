---
name: log-analysis
description: 'Use this skill to analyze log files of any size (small files up to hundreds of MB): single-log error analysis, device log + script log joint analysis, guide-based deep analysis, fault troubleshooting, and comparing a normal round against an abnormal round to find why a test fails, times out or occasionally misbehaves. Triggers: "分析日志", "日志分析", "日志对比", "故障排查", "根因分析", "运行结果统计", "为什么超时", "升级超时", "偶发失败", "压测失败原因", "设备日志和脚本日志联合分析", "对比正常和异常日志", "script_log / upper_log / real_time_log / serial log 分析", upgrade (OTA/IAP/FOTA) timeouts, retransmission or packet-loss analysis.'
---

# 日志分析 Skill

用脚本流式处理日志（不依赖文件大小），先给出"每轮结果 + 耗时"，再取一轮正常、一轮异常做对比，量化差异、找到突变点、排除假设，最后区分"已证实"和"未证实"。

经验来源：QDM559 T-BOX 上位机升级压测，三份日志共 670MB，见 [references/upgrade-timeout-case.md](references/upgrade-timeout-case.md)。已知错误码见 [references/error-codes.md](references/error-codes.md)。

## 分析模式

| 用户提供 | 做法 |
|:---|:---|
| 1 份日志，要求统计/找错误 | 步骤 1 汇总每轮结果，再用错误扫描（步骤 1b）分类统计，按 §2 的流程定位 |
| 设备日志 + 脚本日志（+ 上位机/串口日志） | 联合分析：见"联合分析"一节 |
| 设备日志 + 日志指南 + 脚本日志 | 先读指南，把指南里的状态、错误码、时序要求当作判定依据，再按联合分析走 |
| 只有现象（如"偶发超时"） | 先向用户要日志路径，不要猜；拿到后按上面三种之一处理 |

## 联合分析

1. **分别分析**：先各自独立汇总（脚本日志看每轮结果，设备日志看错误分类），不要一开始就混在一起。
2. **时间对齐**：用失败轮的起止时间截取设备日志窗口；不同日志时钟可能有几十毫秒偏差，匹配时留余量。
3. **关联匹配**：脚本侧的指令下发、状态查询，对应设备侧的响应、执行结果。
4. **链路还原**：还原从指令下发到设备执行的完整链路，找到第一个与正常轮不同的环节。
5. **归因到层**：明确故障发生在云端 / 网络 / 设备 / 上位机 / 脚本哪一层。

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

### 步骤 1b：错误扫描与分类统计

```powershell
python -X utf8 window_patterns.py <log> --grep "ERROR|FAIL|Exception|Traceback|failed|timeout|超时|失败|错误" --top 40 -o errors.txt
```
- 数字被归一化后，相同类型的错误合并成一行，给出次数、首末时间和样例。
- 对照 [references/error-codes.md](references/error-codes.md) 解释已知错误码。
- 失败原因是否单一、是否随时间集中出现，决定后面是找一个突变点，还是逐类分析。

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
文件：<各日志及大小>
整体概况：共 N 轮，成功 a、失败 b、成功率 x%，运行时长 T
现象：第 a~b 轮正常（约 X 分钟），第 c 轮起失败（超时 Y 分钟），持续到日志结束
失败原因分类：| 类别 | 次数 | 轮次 | 样例 |
逐次失败详情：<时间、具体错误、根因；失败很多时只列有代表性的，其余按类别汇总>
成功案例汇总：<正常轮的耗时分布>
机制：<协议流程 + 超时/重试规则>
对比：| 指标 | 正常 | 异常 |
突变点：<时间，是否在某一轮中间，是否恢复>
故障所在层：云端 / 网络 / 设备 / 上位机 / 脚本
共性根因：<已证实部分>
已排除：<列表>
未确认：<列表 + 验证方法>
建议：<缓解 / 根治>
```
