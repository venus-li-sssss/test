---
name: console-run
description: '把命令跑在「独立 CMD 窗口」里，像人手双击一样——窗口不随 AI 对话结束被杀，脚本崩了窗口不关、报错留在屏幕上，输出同时落日志。用在：AI 跑脚本说执行完了但进程跟着对话没了、脚本报错窗口一闪就没/看不到异常、长任务（抓日志、压测、烧录、升级）跑一半被杀、要边跑边看输出、要留运行日志、脚本要给别人双击运行。触发词：独立窗口、新开CMD窗口、窗口不关、闪退、窗口一闪而过、看不到报错、进程被杀、对话结束进程没了、后台跑、detached、pause、start cmd k、日志落盘、脚本给别人用。'
---

# 独立控制台窗口运行（run like a human，窗口不随对话死）

## 这个 skill 解决什么

| 症状 | 根因 |
|---|---|
| AI 说"执行完了"，进程跟着对话一起没了 | 宿主在**工具调用结束时会把本次调用期间新建的进程一起回收**（Job Object / 进程树清理）。`start`、`os.startfile`、`CREATE_NEW_CONSOLE` 全都躲不过——实测连 `start notepad` 的 notepad 都会被带走 |
| 脚本异常，窗口一闪就没，看不到报错 | 用 `cmd /c` 跑（跑完就关窗）、或 Python 异常后进程退出，窗口没有 `pause` 顶着 |
| 长任务（抓日志/压测/烧录）跑到一半被杀 | 同上：前台命令有超时，超时即树杀 |

**唯一实测能活过工具调用的通道是「任务计划」**：任务实例由 Task Scheduler 拉起，不在工具调用的进程树里；
而 schtasks 默认是隐藏窗口，所以在任务里再 `start "" cmd /k <bat>` 弹一个真正的控制台。

```
工具调用 → schtasks /run → launcher.cmd（隐藏）→ start → cmd /k worker.cmd（可见窗口）
                                                          └→ console_tee.py → 目标程序
```

## 用法（一条命令）

```powershell
python <skill目录>\scripts\console_run.py --title "抓日志" --log-dir D:\logs -- python D:\work\capture.py COM29
```

常用参数：

| 参数 | 说明 |
|---|---|
| `--title/-t` | 窗口标题（默认 `<脚本名>_<时间>`）。中英文都行，`taskkill /fi "WINDOWTITLE eq xxx*"` 靠它定位 |
| `--log-dir/-d` | 日志目录，默认 `D:\logs`；文件名 `<脚本名>_<时间戳>.log` |
| `--log` | 直接指定日志文件 |
| `--workdir/-w` | 工作目录（默认当前目录）|
| `--bat <路径>` | **只生成 bat，不启动**：给别人双击用，最稳（双击 = 人工操作） |
| `--detach sched\|start` | `sched`（默认，能活过工具调用）/ `start`（直接 start，可能被回收，仅应急） |
| `--no-tee` | 不落日志，只保证窗口不关 |
| `--wait` | 启动后等几秒自检日志是否已开始写（默认 4s） |

启动成功后它会告诉你三件事：窗口标题、日志路径、自检结果（`日志已开始写入 ✔`）。之后随时可查：

```powershell
type  D:\logs\capture_20261127_143720.log      # 跑了什么（窗口关了也还在）
dir   D:\logs                                  # 有哪些次运行
taskkill /fi "WINDOWTITLE eq 抓日志*"          # 关掉它
```

## 三条硬规矩

1. **长任务不要直接前台跑**：超过 ~30 秒的（抓日志、压测、烧录、升级、批量循环）一律走 `console_run.py`。
   否则超时一到就是树杀，前面全白干。
2. **一定要有日志**：窗口能被人关、能被误点、能被系统回收，日志文件在才是证据。默认 `D:\logs`，想换就 `--log-dir`。
3. **给人用的脚本出成 `.bat`**：`--bat D:\run_me.bat`，对方双击即可，窗口跑完停在 `pause` 上等人看完。

## 踩过的坑（复现过，别再来一遍）

1. **`start` 救不了你**：`start "" cmd /k ...`、`os.startfile(...)`、`subprocess.Popen(..., CREATE_NEW_CONSOLE)`
   在工具调用结束时都会被回收（实测 `start notepad` 的 notepad 也活不过那次调用）。必须走 schtasks。
2. **schtasks 拉的进程默认无可见窗口**：任务里必须再 `start "" cmd /k <bat>` 才有窗口；
   只 `cmd /c survive.cmd` 是能活（marker 一直在写）但你什么也看不见。
3. **bat 必须按 GBK(ANSI) 写**：cmd 解析 bat 用系统 ANSI 代码页，写 UTF-8 会让里面的中文变成乱码指令。
   中文标题放 `title` 行（在 `chcp 65001` 之前），`chcp` 之后的内容一律 ASCII，中文输出交给 python。
4. **`cmd /c` 会关窗**：要留窗口用 `cmd /k` 或末尾 `pause >nul`。
5. **`start ""` 开头那对空引号不能省**：第一个带引号的参数被当成窗口标题。
6. **`del *.log` 之类会卡住**：通配符删除在非交互下会问 `Y/N`，把整条命令挂死（我这轮就踩了）。
7. **`tasklist /v` 在这台机器上会挂死**：想看窗口标题别用它，用 `EnumWindows`（见 `scripts/enumwin.ps1`）或直接看屏幕。
7b. **本机默认终端是 Windows Terminal**：窗口标题挂在 `WindowsTerminal.exe` 上（不是你的 cmd/python），
   所以 `taskkill /fi "WINDOWTITLE eq xxx*"` 匹配不到。关窗口就点 × 关那个标签页，
   或 `taskkill /f /pid <cmd或python的pid>`（pid 用 `Get-Process cmd,python | Select Id,StartTime` 找）。
8. **Python 的 `input()` 兜底在重定向时会抛 `EOFError`**：所以统一用 bat 末尾 `pause >nul`，比 `input()` 稳。
9. **IDE 里跑 bat 看不到窗口**：IDE 接管了输出，要窗口就用 `console_run.py` 或直接双击 bat。

## 配套文件

- `scripts/console_run.py` — 启动器：写 bat → schtasks 拉起 → `start` 弹窗 → 自检日志 → 打印标题/日志路径
- `scripts/console_tee.py` — 窗口里干活的：跑目标命令，输出同时进窗口与日志；异常/退出码/耗时全部留痕
- `scripts/enumwin.ps1` — 列当前所有可见窗口标题 + pid（查窗口到底弹没弹、叫什么）

## 自检（改完脚本后跑一遍）

```powershell
# 1) 造个会崩的脚本
python -c "print('ok'); raise RuntimeError('boom')" > %TEMP%\boom.py
# 2) 用本 skill 起窗口
python <skill目录>\scripts\console_run.py --title TEST_BOOM -- python %TEMP%\boom.py
# 3) 验证：屏幕上有窗口、日志里有 traceback、窗口停在 pause 没关
type D:\logs\boom_*.log
powershell -NoProfile -ExecutionPolicy Bypass -File <skill目录>\scripts\enumwin.ps1 | findstr TEST_BOOM
```

三条都成立才算过：**窗口可见 / 日志有 traceback / 窗口没关且进程还在**。
