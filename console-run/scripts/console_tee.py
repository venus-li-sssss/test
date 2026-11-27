#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""console_tee.py — 跑一条命令，输出同时进「窗口」和「日志文件」。

在 console_run.py 打开的那个独立 CMD 窗口里被调用。
哪怕窗口被关、命令崩了、本脚本自己都崩了，异常也一定落在日志文件里。

用法（一般不用手敲，console_run.py 会自动拼好）：
    python console_tee.py --log D:\\logs\\x_20261127_101500.log -- python run.py --fast

退出码 = 被跑命令的退出码（启动失败 126/127，被中断 130）。
"""
import argparse
import datetime
import os
import subprocess
import sys
import time
import traceback

_LOG_FP = None


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def emit(text=""):
    """同时写窗口和日志；任一侧出错都不影响另一侧。"""
    global _LOG_FP
    if _LOG_FP is not None:
        try:
            _LOG_FP.write(text)
            _LOG_FP.flush()
        except Exception:
            pass
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except Exception:
        pass


def banner(msg):
    line = "=" * 70
    emit("\n%s\n%s\n%s\n" % (line, msg, line))


def default_log_path(cmd):
    base = "D:\\logs" if os.path.isdir("D:\\") else os.path.join(os.path.expanduser("~"), "logs")
    name = "run"
    for part in cmd:
        if part.lower().endswith((".py", ".exe", ".bat", ".cmd", ".ps1")):
            name = os.path.splitext(os.path.basename(part))[0]
            break
    return os.path.join(base, "%s_%s.log" % (name, datetime.datetime.now().strftime("%Y%m%d_%H%M%S")))


def open_log(path):
    global _LOG_FP
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    _LOG_FP = open(path, "w", encoding="utf-8", errors="replace", buffering=1)


def main():
    global _LOG_FP
    ap = argparse.ArgumentParser(description="run a command, tee output to console + log file")
    ap.add_argument("--log", default=None, help="日志文件路径（默认 D:\\logs\\<脚本名>_<时间戳>.log）")
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()

    cmd = a.cmd
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("ERROR: 没有给要执行的命令")
        return 2

    log_path = os.path.abspath(a.log or default_log_path(cmd))
    try:
        open_log(log_path)
    except Exception:
        print("ERROR: 日志文件打不开: %s\n%s" % (log_path, traceback.format_exc()))
        return 3

    # 先写 boot 行：只要它出现了，就说明 tee 起来了、日志可写
    emit("# boot %s  pid=%s  py=%s\n# stdout.encoding=%s  console_cp=%s\n"
         % (now(), os.getpid(), sys.version.split()[0],
            getattr(sys.stdout, "encoding", "?"),
            os.environ.get("COMSPEC", "")))

    banner("console_tee  启动 %s" % now())
    emit("命令   : %s\n" % subprocess.list2cmdline(cmd))
    emit("日志   : %s\n" % log_path)
    emit("工作目录: %s\n\n" % os.getcwd())

    t0 = time.time()
    rc = None
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
    except FileNotFoundError as e:
        emit("[console_tee] 启动失败：找不到可执行文件 -> %s\n" % e)
        emit("# exit 127\n")
        banner("启动失败（127）")
        return 127
    except Exception:
        emit("[console_tee] 启动失败：\n%s\n" % traceback.format_exc())
        emit("# exit 126\n")
        banner("启动失败（126）")
        return 126

    try:
        while True:
            raw = p.stdout.readline()
            if not raw:
                break
            text = raw.decode("utf-8", "replace")
            if "\ufffd" in text:            # 子进程是 GBK 输出，回退一次
                text = raw.decode("gbk", "replace")
            emit(text)
        rc = p.wait()
    except KeyboardInterrupt:
        p.kill()
        rc = 130
        emit("\n[console_tee] 被 Ctrl-C 中断\n")
    except Exception:
        emit("\n[console_tee] 读输出时出错：\n%s\n" % traceback.format_exc())
        try:
            rc = p.wait(timeout=5)
        except Exception:
            rc = 125

    elapsed = time.time() - t0
    emit("# end %s  exit=%s  %.1fs\n" % (now(), rc, elapsed))
    if rc == 0:
        banner("完成：退出码 0，耗时 %.1fs" % elapsed)
    else:
        banner("！执行失败：退出码 %s，耗时 %.1fs\n日志已存：%s\n（窗口不会关，往上翻看报错）"
               % (rc, elapsed, log_path))
    emit("日志文件: %s\n\n" % log_path)
    return rc if isinstance(rc, int) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:
        tb = traceback.format_exc()
        try:
            print(tb)
        except Exception:
            pass
        if _LOG_FP is not None:
            try:
                _LOG_FP.write("\n[FATAL] console_tee 自身异常：\n" + tb + "\n")
                _LOG_FP.flush()
            except Exception:
                pass
        sys.exit(1)
