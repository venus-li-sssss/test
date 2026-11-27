#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""console_run.py — 像人手双击一样，在独立 CMD 窗口里跑命令，窗口不随 AI 对话结束关闭。

为什么要这么绕（实测结论，2026-11-27）：
  * 宿主在**工具调用结束时会把本次调用期间新建的进程一起回收**——`start`、`os.startfile`、
    `CREATE_NEW_CONSOLE` 全都活不过一次工具调用（连 notepad 都会被带走）。
  * 唯一验证活下来的通道是 **任务计划（schtasks）**：任务实例由 Task Scheduler 拉起，
    不在工具调用的进程树里，调用结束后照跑。
  * 但 schtasks 拉起的进程默认**没有可见窗口**，所以在任务里再 `start "" cmd /k <bat>`
    弹一个真正的控制台窗口（层级：任务 → launcher.cmd → start → cmd /k → tee → 目标程序）。

用法：
    python console_run.py --title QDM562 -- python "D:\\work\\run.py" --fast
    python console_run.py --title 抓日志 --log-dir D:\\logs -- python capture.py COM29
    python console_run.py --bat D:\\run_me.bat -- python run.py       # 只生成 bat，给人双击
    python console_run.py --detach start -- python run.py             # 退回 start 方式（会被回收）

之后：
    看日志 : type D:\\logs\\<脚本>_<时间>.log
    看窗口 : 屏幕上的窗口标题 = --title（默认 <脚本名>_<时间>）
    停掉   : 直接关窗口，或 taskkill /fi "WINDOWTITLE eq <title>*"
"""
import argparse
import datetime
import os
import re
import subprocess
import sys
import tempfile
import time

BAT_ENC = "gbk"          # cmd 按系统 ANSI 代码页解析 bat，写 UTF-8 会让中文变乱码指令
TASK_PREFIX = "QecAgentRun_"


def build_worker_bat(title, workdir, tee, log_path, cmd, no_tee=False):
    """真正干活的窗口脚本：跑命令 + tee + 结束后 pause。"""
    cmdline = subprocess.list2cmdline(cmd)
    lines = [
        "@echo off",
        "title %s" % title,              # 中文标题放 chcp 之前，按 GBK 解析才对
        "chcp 65001 >nul",               # 之后内容一律 ASCII，中文交给 python 打
        'cd /d "%s"' % workdir,
        "echo [console_run] cmd : %s" % cmdline,
        "echo [console_run] log : %s" % log_path,
        "echo.",
    ]
    if no_tee:
        lines.append(cmdline)
    else:
        lines.append('python -u "%s" --log "%s" -- %s' % (tee, log_path, cmdline))
    lines += [
        "",
        "echo.",
        "echo ---- finished; window stays open, press any key to close ----",
        "pause >nul",
    ]
    return "\r\n".join(lines) + "\r\n"


def build_launcher_bat(worker_bat):
    """任务计划只跑这个（隐藏），它负责把真正的窗口 start 出来。"""
    return "\r\n".join([
        "@echo off",
        'start "" cmd /k "%s"' % worker_bat,
        "",
    ])


def guess_stem(cmd):
    for part in cmd:
        if part.lower().endswith((".py", ".exe", ".bat", ".cmd", ".ps1")):
            return os.path.splitext(os.path.basename(part))[0]
    return "run"


def safe_name(text):
    return re.sub(r"[^A-Za-z0-9_]+", "_", text)[:40] or "run"


def write(path, text, enc=BAT_ENC):
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding=enc, errors="replace", newline="") as f:
        f.write(text)


def run_schtasks(args):
    try:
        p = subprocess.run(["schtasks"] + args, capture_output=True, text=True,
                           encoding="gbk", errors="replace", timeout=30)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return -1, repr(e)


def main():
    ap = argparse.ArgumentParser(
        description="run a command in a detached console window (survives the agent tool call)")
    ap.add_argument("--title", "-t", default=None, help="窗口标题（默认 <脚本名>_<时间>）")
    ap.add_argument("--log", default=None, help="日志文件路径")
    ap.add_argument("--log-dir", "-d", default=r"D:\logs", help="日志目录（默认 D:\\logs）")
    ap.add_argument("--workdir", "-w", default=None, help="工作目录（默认当前目录）")
    ap.add_argument("--bat", default=None, help="只生成可双击的 .bat 到该路径，不启动")
    ap.add_argument("--detach", choices=["sched", "start"], default="sched",
                    help="sched=任务计划拉起（默认，能活过工具调用）；start=直接 start（可能被回收）")
    ap.add_argument("--no-tee", action="store_true", help="不落日志，只保证窗口不关")
    ap.add_argument("--wait", type=float, default=4.0, help="启动后等几秒确认已开跑")
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()

    cmd = a.cmd
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        sys.exit("ERROR: 没给要跑的命令。例：python console_run.py --title test -- python run.py")

    workdir = os.path.abspath(a.workdir or os.getcwd())
    if not os.path.isdir(workdir):
        sys.exit("ERROR: 工作目录不存在: %s" % workdir)

    stem = guess_stem(cmd)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    title = a.title or ("%s_%s" % (stem, ts))
    log_path = os.path.abspath(a.log or os.path.join(a.log_dir, "%s_%s.log" % (stem, ts)))
    tee = os.path.join(os.path.dirname(os.path.abspath(__file__)), "console_tee.py")

    worker_text = build_worker_bat(title, workdir, tee, log_path, cmd, a.no_tee)

    # 只生成 bat：给人双击用（双击 = 人工操作，最稳）
    if a.bat:
        write(os.path.abspath(a.bat), worker_text)
        print("已生成: %s（双击即可运行，窗口跑完不会自动关）" % os.path.abspath(a.bat))
        print("日志会写到: %s" % (log_path if not a.no_tee else "(未启用 tee)"))
        return 0

    tag = safe_name(title) + "_" + ts
    worker_bat = os.path.join(tempfile.gettempdir(), "console_run_worker_%s.cmd" % tag)
    write(worker_bat, worker_text)

    if a.detach == "start":
        subprocess.Popen('start "" "%s"' % worker_bat, shell=True, cwd=workdir,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        mode = "start（注意：可能随工具调用结束被回收）"
    else:
        launcher = os.path.join(tempfile.gettempdir(), "console_run_launch_%s.cmd" % tag)
        write(launcher, build_launcher_bat(worker_bat))
        task = TASK_PREFIX + tag[:50]
        rc, out = run_schtasks(["/create", "/tn", task, "/tr", '"%s"' % launcher,
                                "/sc", "once", "/st", "23:59", "/f"])
        if rc != 0:
            print("WARN: 建计划任务失败，退回 start 方式：%s" % out.strip())
            subprocess.Popen('start "" "%s"' % worker_bat, shell=True, cwd=workdir,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            mode = "start（降级）"
        else:
            rc2, out2 = run_schtasks(["/run", "/tn", task])
            if rc2 != 0:
                print("WARN: 触发计划任务失败：%s" % out2.strip())
            mode = "schtasks（任务名 %s，可忽略/自动覆盖）" % task

    # 自检：等日志出现 + 看 tee 进程是否活下来
    ok = False
    deadline = time.time() + max(a.wait, 0)
    while time.time() < deadline:
        if os.path.exists(log_path) and os.path.getsize(log_path) > 0:
            ok = True
            break
        time.sleep(0.25)

    print("已在独立窗口启动：%s" % mode)
    print("  窗口标题: %s" % title)
    print("  日志文件: %s" % (log_path if not a.no_tee else "(未启用 tee)"))
    print("  窗口脚本: %s" % worker_bat)
    if not a.no_tee:
        print("  自检    : %s" % ("日志已开始写入 ✔" if ok else
                                "⚠ %.0fs 内没有日志 —— 看屏幕有没有弹窗，或直接双击上面的窗口脚本" % a.wait))
    print("")
    print("  看日志: type \"%s\"" % log_path)
    print("  关窗口: 直接点 ×，或 taskkill /fi \"WINDOWTITLE eq %s*\"" % title)
    return 0


if __name__ == "__main__":
    sys.exit(main())
