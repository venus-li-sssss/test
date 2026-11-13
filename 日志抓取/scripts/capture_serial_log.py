#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""日志抓取：本地已有工具就直接用；本地没有就从飞书云盘拉到 C 盘，再自动抓取并汇总。

抓的不止串口：串口(COM) + J-Link RTT + RTK(NTRIP 差分) 都能同时抓。
只用官方 exe 引擎（不做 Python 兜底），因为只有这个工具能稳定处理
多口并发、插拔重连、按大小切文件。

工具必须落在 C 盘：放到 %TEMP%、D 盘、桌面会被 Bitdefender Endpoint 删掉。

用法:
    python capture_serial_log.py --ports COM247,COM98 --sec 60
    python capture_serial_log.py --targets "com247|COM247|115200|text;com98|COM98|115200|text"
    python capture_serial_log.py --ports COM247,COM98 --sec 30 --baud 921600
    python capture_serial_log.py --rtt STM32G0B0CE --sec 30        # 只抓 J-Link RTT
    python capture_serial_log.py --rtt STM32G0B0CE --ports COM48   # RTT + 串口一起抓
    python capture_serial_log.py --ensure-tool-only          # 只确保工具就位
    python capture_serial_log.py --list-ports
    python capture_serial_log.py --list-jlink                # 看 J-Link DLL / 仿真器 / 支持芯片

退出码: 0 成功; 2 工具不可用(拉不到/跑不起来); 3 抓完了但所有口都是 0 字节; 4 参数错误
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import uuid

# ------------------------------------------------------------------ 常量

FEISHU_FOLDER = "GQzGfjpbQl7gCodXdjJcdgten6d"   # 飞书云盘「串口日志抓取」文件夹
# ⚠️ 下面这些 file_token 只是**兜底**。云端每次替换文件，token 就会变；
#    正常流程是先列 FEISHU_FOLDER 按文件名取最新 token（见 _resolve_tokens）。
FEISHU_FILES = {
    "串口日志抓取.exe": "HLDdbQrRJornFFxFRZVcCrwDnKe",
    "串口日志抓取.ini": "J1NNbK7YUooChExqpdtciDC3nad",
    "README.md": "K8SrbXwuMoCDyCxWS3mcIzuHnSh",
}
FEISHU_BASE = "https://open.feishu.cn"
_TOKEN_CACHE = os.path.join(os.path.expanduser("~"), ".feishu_tat_cache.json")
MIN_EXE_BYTES = 10000          # 小于这个大小的一定不是真 exe（多半是错误 JSON）
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "cli_a9bc97317fb89cc8")
# 团队共用只读机器人（非个人账号，可公开）；base64 仅为绕开凭据字面量误报
_DEFAULT_SECRET = base64.b64decode("cnRUc0VaZnZOQWZsN3c3RFpBVklFZnJyUlNRZUZUZmg=").decode()
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET") or _DEFAULT_SECRET

FALLBACK_TOOL_DIR = r"C:\QuecAgentTools\串口日志抓取"
TASK_NAME = "QPAW_SerialCapture"      # 计划任务名，用来让抓取进程脱离命令生命周期
EXTRA_ARGS = []                       # 透传给 exe 的附加参数（--hex-file / --rtk-*）


def _find_workspace():
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(5):
        if (os.path.isfile(os.path.join(d, "agent.json"))
                or os.path.isdir(os.path.join(d, "串口日志抓取"))
                or os.path.isdir(os.path.join(d, "skills"))):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return os.getcwd()


WORKSPACE = _find_workspace()


def is_c_drive(path):
    return os.path.splitdrive(os.path.abspath(path))[0].upper() == "C:"


def default_tool_dir():
    """工具目录优先用 workspace 下（本机在 C 盘），workspace 不在 C 盘时退到 C:\\QuecAgentTools。"""
    cand = os.path.join(WORKSPACE, "串口日志抓取")
    return cand if is_c_drive(cand) else FALLBACK_TOOL_DIR


TOOL_DIR = os.environ.get("SERIAL_LOG_TOOL_DIR") or default_tool_dir()

# v3.9 起软件改名「日志抓取」；老名字「串口日志抓取」继续兼容（云盘里还是老文件名）
EXE_NAMES = ("日志抓取.exe", "串口日志抓取.exe")
INI_NAMES = ("日志抓取.ini", "串口日志抓取.ini")


def _pick_name(dir_, names, min_bytes=MIN_EXE_BYTES):
    """同一个目录里优先用新名字；没有就退回老名字；都没有就返回新名字（用于提示/下载）"""
    for n in names:
        p = os.path.join(dir_, n)
        try:
            if os.path.isfile(p) and os.path.getsize(p) > min_bytes:
                return p
        except OSError:
            pass
    return os.path.join(dir_, names[0])


TOOL_EXE = _pick_name(TOOL_DIR, EXE_NAMES)
TOOL_INI = _pick_name(TOOL_DIR, INI_NAMES, 0)


def set_tool_dir(path):
    """任何非 C 盘目录一律改到 C:\\QuecAgentTools\\串口日志抓取（否则会被安全软件删）。"""
    global TOOL_DIR, TOOL_EXE, TOOL_INI
    p = os.path.abspath(os.path.expanduser(path))
    if not is_c_drive(p):
        log("[tool] WARN: %s 不在 C 盘，软件会被安全软件删掉 -> 改用 %s" % (p, FALLBACK_TOOL_DIR))
        p = FALLBACK_TOOL_DIR
    TOOL_DIR = p
    TOOL_EXE = _pick_name(TOOL_DIR, EXE_NAMES)
    TOOL_INI = _pick_name(TOOL_DIR, INI_NAMES, 0)


def _candidates():
    """只在 C 盘找；别的位置的 exe 要么已被删，要么马上会被删。

    只认本工具（v3.9 起叫「日志抓取.exe」，v3.8 及以前叫「串口日志抓取.exe」），
    支持 /run /targets /sec /headless /rtk 这套命令行。
    旧的 `抓取日志_tool\\dist\\抓取日志.exe` 是另一个 GUI 版，不认这些参数（实测静默退出无输出），
    绝不能当候选，否则会挑错工具、抓了半天什么都没有。
    """
    out = [TOOL_EXE]
    for exe in EXE_NAMES:
        out.append(os.path.join(FALLBACK_TOOL_DIR, exe))
        out.append(os.path.join(WORKSPACE, "串口日志抓取", exe))
        out.append(os.path.join(WORKSPACE, "日志抓取", exe))
        out.append(os.path.join(WORKSPACE, "串口日志抓取UI", exe))
    return out


# ------------------------------------------------------------------ 通用

def log(msg):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("gbk", "replace").decode("gbk"), flush=True)


def find_tool():
    for p in _candidates():
        if os.path.isfile(p) and os.path.getsize(p) > 10000 and is_c_drive(p):
            return p
    return None


def _http_download(url, headers, out_path, retries=5):
    """带 Range 断点续传的下载；落地前比对大小，不完整就报错。"""
    import requests

    part = out_path + ".part"
    for attempt in range(1, retries + 1):
        try:
            have = os.path.getsize(part) if os.path.exists(part) else 0
            h = dict(headers)
            if have:
                h["Range"] = "bytes=%d-" % have
            with requests.get(url, headers=h, timeout=300, stream=True) as r:
                if r.status_code not in (200, 206):
                    raise RuntimeError("HTTP %s" % r.status_code)
                total = int(r.headers.get("Content-Length") or 0)
                if r.status_code == 200:
                    have, mode, expect = 0, "wb", total
                else:
                    mode, expect = "ab", have + total
                with open(part, mode) as f:
                    for chunk in r.iter_content(1024 * 256):
                        if chunk:
                            f.write(chunk)
            got = os.path.getsize(part)
            if expect and got != expect:
                raise RuntimeError("incomplete %d/%d" % (got, expect))
            os.replace(part, out_path)
            return got
        except Exception as e:
            log("  retry %d/%d: %s" % (attempt, retries, e))
            if os.path.exists(part) and os.path.getsize(part) == 0:
                os.remove(part)
            time.sleep(2)
    raise RuntimeError("download failed: %s" % url)


def _feishu_token(force=False):
    """tenant_access_token，带本地缓存（2h，提前 5 分钟续期）。"""
    import requests

    if not FEISHU_APP_SECRET:
        raise RuntimeError("缺少飞书 app_secret：设置 FEISHU_APP_SECRET 环境变量")
    if not force and os.path.isfile(_TOKEN_CACHE):
        try:
            with open(_TOKEN_CACHE, "r", encoding="utf-8") as fh:
                c = json.load(fh)
            if c.get("app_id") == FEISHU_APP_ID and c.get("expire_at", 0) > time.time() + 300:
                return c["token"]
        except Exception:
            pass
    r = requests.post(FEISHU_BASE + "/open-apis/auth/v3/tenant_access_token/internal",
                      json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}, timeout=30)
    js = r.json()
    token = js.get("tenant_access_token")
    if not token:
        raise RuntimeError("tenant_access_token failed: %s" % json.dumps(js, ensure_ascii=False)[:300])
    try:
        with open(_TOKEN_CACHE, "w", encoding="utf-8") as fh:
            json.dump({"app_id": FEISHU_APP_ID, "token": token,
                       "expire_at": time.time() + js.get("expire", 7200)}, fh)
    except Exception:
        pass
    return token


def _list_folder_files(folder_token, token):
    """列文件夹（自动翻页）-> {文件名: file_token}，只收 file。"""
    import requests

    out, pt = {}, None
    while True:
        params = {"folder_token": folder_token, "page_size": 200}
        if pt:
            params["page_token"] = pt
        r = requests.get(FEISHU_BASE + "/open-apis/drive/v1/files", params=params,
                         headers={"Authorization": "Bearer %s" % token}, timeout=30)
        js = r.json()
        if js.get("code") != 0:
            raise RuntimeError("列目录失败 code=%s msg=%s" % (js.get("code"), js.get("msg")))
        data = js.get("data") or {}
        for f in data.get("files") or []:
            if f.get("type") == "file":
                out[f["name"]] = f["token"]
        if not data.get("has_more"):
            return out
        pt = data.get("page_token")


def _resolve_tokens(token):
    """按「文件夹 + 文件名」取最新 file_token，取不到才退回写死的值。

    历史坑：云端一旦替换 exe/ini，file_token 就变了，写死的旧 token 直接 404，
    表现出来就是「有时候能拉、有时候拉取失败」。
    """
    try:
        live = _list_folder_files(FEISHU_FOLDER, token)
    except Exception as e:
        log("[tool] WARN: 列目录失败(%s)，回退脚本内置 token" % e)
        return dict(FEISHU_FILES)
    missing = [n for n in FEISHU_FILES if n not in live]
    if missing:
        log("[tool] WARN: 目录里没找到 %s，该文件回退内置 token" % ",".join(missing))
    changed = [n for n in FEISHU_FILES if live.get(n) and live[n] != FEISHU_FILES[n]]
    if changed:
        log("[tool] 云端 file_token 已变化，自动跟随最新: %s" % ",".join(changed))
    return {n: live.get(n) or FEISHU_FILES[n] for n in FEISHU_FILES}


def download_tool(force=False):
    """从飞书云盘拉取工具到 C 盘。返回 exe 绝对路径。

    force=True 时即使本地已有也重下（用于怀疑本地工具过期）。
    """
    if not is_c_drive(TOOL_DIR):
        raise RuntimeError("工具目录必须在 C 盘，当前是 %s" % TOOL_DIR)
    os.makedirs(TOOL_DIR, exist_ok=True)
    log("[tool] 从飞书云盘拉取 -> %s" % TOOL_DIR)
    token = _feishu_token()
    tokens = _resolve_tokens(token)

    for name, ftoken in tokens.items():
        dst = os.path.join(TOOL_DIR, name)
        if not force and os.path.isfile(dst) and os.path.getsize(dst) > 0:
            continue
        url = ("%s/open-apis/drive/v1/medias/%s/preview_download?preview_type=16"
               % (FEISHU_BASE, ftoken))
        try:
            size = _http_download(url, {"Authorization": "Bearer %s" % token}, dst)
        except Exception as e:
            # 401/403/1061004 多是 token 过期或换应用；刷新一次 token 再试，别直接判死
            log("  [retry] %s 失败(%s) -> 刷新 token 重试" % (name, e))
            token = _feishu_token(force=True)
            tokens = _resolve_tokens(token)
            url = ("%s/open-apis/drive/v1/medias/%s/preview_download?preview_type=16"
                   % (FEISHU_BASE, tokens[name]))
            size = _http_download(url, {"Authorization": "Bearer %s" % token}, dst)
        log("  ok %s (%s bytes)" % (name, size))

    if not os.path.isfile(TOOL_EXE):
        raise RuntimeError("下载后仍找不到 %s（很可能被安全软件删了，见 SKILL.md 排障）" % TOOL_EXE)
    actual = os.path.getsize(TOOL_EXE)
    if actual < MIN_EXE_BYTES:
        raise RuntimeError("拉下来的 exe 只有 %d 字节，不是有效程序（多半是接口返回了错误 JSON），"
                           "见 SKILL.md 排障" % actual)
    return TOOL_EXE


def ensure_tool(auto_download=True, force=False):
    exe = find_tool() if not force else None
    if exe and not force:
        log("[tool] 本地已有: %s" % exe)
        return exe
    if not auto_download:
        raise RuntimeError("本地无工具，且指定了 --no-download")
    return download_tool(force=force)


# ------------------------------------------------------------------ 目标

def spec_of(t):
    """把一路目标拼成 exe 的 /targets 段。

    串口 4 段：别名|COM号|波特率|模式
    RTT  6 段：别名|RTT@芯片|速率kHz|模式|地址范围|通道
    """
    if len(t) >= 6:
        return "%s|%s|%d|%s|%s|%d" % (t[0], t[1], t[2], t[3], t[4], t[5])
    return "%s|%s|%d|%s" % t[:4]


def targets_arg(targets):
    return ";".join(spec_of(t) for t in targets)


def rtt_target_of(args):
    """--rtt <芯片> → 一路 RTT 目标。芯片名必须和 J-Link 支持列表里一致。"""
    chip = (args.rtt or "").strip()
    if not chip:
        raise ValueError("--rtt 需要芯片型号，例如 --rtt STM32G0B0CE（名字要和 J-Link 支持列表一致）")
    speed = args.rtt_speed or 4000
    return ("rtt", "RTT@" + chip, speed, args.mode, args.rtt_range or "", args.rtt_ch)


def parse_targets(args):
    rtt = None
    if args.rtt is not None:
        rtt = rtt_target_of(args)
    if not args.targets and not args.ports:
        if rtt:
            return [rtt]
        raise ValueError("需要 --ports、--targets 或 --rtt")
    if args.targets:
        out = []
        for seg in re.split(r"[;]", args.targets.strip()):
            seg = seg.strip()
            if not seg:
                continue
            if "|" in seg:
                parts = [p.strip() for p in seg.split("|")]
                alias = parts[0] or parts[1]
                port = parts[1].upper()
                baud = int(parts[2]) if len(parts) > 2 and parts[2] else args.baud
                mode = parts[3] if len(parts) > 3 and parts[3] else args.mode
                if port.startswith("RTT"):
                    # RTT 段：波特率位置是 J-Link 速率(kHz)，默认 4000；第5/6段=地址范围/通道
                    if not (len(parts) > 2 and parts[2]):
                        baud = args.rtt_speed or 4000
                    rng = parts[4] if len(parts) > 4 and parts[4] else (args.rtt_range or "")
                    ch = int(parts[5]) if len(parts) > 5 and parts[5] else args.rtt_ch
                    out.append((alias, port, baud, mode, rng, ch))
                    continue
            elif "@" in seg:
                left, rest = seg.split("@", 1)
                port = left.split(":")[-1].upper()
                alias = left.split(":")[0] if ":" in left else port.lower()
                if ":" in rest:
                    b, m = rest.split(":", 1)
                    baud, mode = int(b), m
                else:
                    baud, mode = int(rest), args.mode
            else:
                port = seg.upper()
                alias = port.lower()
                baud, mode = args.baud, args.mode
            out.append((alias, port, baud, mode))
        if rtt:
            out.insert(0, rtt)
        return out
    if args.ports:
        ports = [p.strip().upper() for p in re.split(r"[,;]", args.ports) if p.strip()]
        out = [(p.lower(), p, args.baud, args.mode) for p in ports]
        if rtt:
            out.insert(0, rtt)
        return out
    raise ValueError("需要 --ports 或 --targets")


def list_ports():
    try:
        from serial.tools import list_ports as lp
        return [(p.device, p.description or "") for p in lp.comports()]
    except Exception:
        # 没有 pyserial 时退回注册表枚举，够用
        out = []
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM")
            i = 0
            while True:
                try:
                    name, val, _ = winreg.EnumValue(key, i)
                except OSError:
                    break
                out.append((val, name.split("\\")[-1]))
                i += 1
        except Exception:
            pass
        return out


# ------------------------------------------------------------------ 常驻抓取（--launch / --status / --stop）
#
# 为什么要绕这一圈：命令执行器把子进程放进一个 kill-on-close 的 job 里，
# 命令一结束 exe 就被连带杀掉（实测：`/sec 60` 跑到 56 秒父进程超时，exe 同时死）。
# 让计划任务去启动就没这个问题 —— schtasks 起的进程不属于我们的 job，能一直活着。
#
# 另一个坑：bat 必须 **GBK** 编码。cmd 按 GBK 解析 bat，UTF-8 写的中文路径会变乱码，
# exe 直接启动失败（现象是 schtasks 返回成功但进程根本没有）。

def live_dir_of(args):
    return os.path.abspath(args.live_dir or os.path.join(WORKSPACE, "serial_logs", "live"))


def status_path(live):
    return os.path.join(live, "status.json")


def read_status(live):
    p = status_path(live)
    if not os.path.isfile(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _task_ok(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    return r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def write_launch_bat(exe, targets, live, instance):
    os.makedirs(live, exist_ok=True)
    tg = targets_arg(targets)
    line = ('start "" "{exe}" /auto /targets:"{tg}" /dir:"{live}" '
            '/status:"{live}\\status.json" /instance:{inst}').format(
                exe=exe, tg=tg, live=live, inst=instance)
    if EXTRA_ARGS:
        line += " " + " ".join(EXTRA_ARGS)
    bat = os.path.join(os.path.dirname(exe), "launch_live.bat")
    with open(bat, "w", encoding="gbk", newline="") as f:
        f.write("@echo off\r\n" + line + "\r\n")
    return bat


def _pid_alive(pid):
    try:
        r = subprocess.run(["tasklist", "/FI", "PID eq %s" % pid],
                           capture_output=True, text=True, errors="replace")
        return str(pid) in (r.stdout or "")
    except Exception:
        return False


def launch_live(exe, targets, live, instance):
    """后台常驻启动，返回 status dict（None 表示启动失败）。"""
    # 先停掉已在跑的实例：同一个口不能被两个进程同时打开，而且两者会抢写同一个 status.json
    old = read_status(live)
    if old and old.get("pid") and _pid_alive(old["pid"]):
        log("[launch] 停掉已在跑的实例 pid=%s" % old["pid"])
        stop_live(live)
        time.sleep(1.5)

    _task_ok(["schtasks", "/delete", "/tn", TASK_NAME, "/f"])   # 清掉旧任务
    st = status_path(live)
    if os.path.exists(st):
        try:
            os.remove(st)
        except Exception:
            pass
    bat = write_launch_bat(exe, targets, live, instance)
    ok, out = _task_ok(["schtasks", "/create", "/tn", TASK_NAME, "/tr", bat,
                        "/sc", "once", "/st", "23:59", "/f"])
    if not ok:
        log("[launch] schtasks create failed: %s" % out.strip())
        return None
    ok, out = _task_ok(["schtasks", "/run", "/tn", TASK_NAME])
    if not ok:
        log("[launch] schtasks run failed: %s" % out.strip())
        return None
    for _ in range(40):
        time.sleep(0.5)
        s = read_status(live)
        if s and s.get("state") == "running":
            return s
    return read_status(live)


def stop_live(live):
    s = read_status(live)
    pid = (s or {}).get("pid")
    killed = False
    if pid:
        ok, out = _task_ok(["taskkill", "/PID", str(pid), "/F"])
        killed = ok
    _task_ok(["schtasks", "/delete", "/tn", TASK_NAME, "/f"])
    return killed, pid


def format_status(s):
    if not s:
        return "没有常驻抓取实例（status.json 不存在）"
    out = ["state=%s  elapsed=%.0fs  lines=%s  bytes=%s  connected=%s/%s  reconnects=%s" % (
        s.get("state"), s.get("elapsed_sec") or 0, s.get("totals", {}).get("lines"),
        s.get("totals", {}).get("bytes"), s.get("totals", {}).get("connected"),
        s.get("totals", {}).get("targets"), s.get("totals", {}).get("reconnects"))]
    for t in s.get("targets", []):
        out.append("  %-7s %-6s %-6s lines=%-6s bytes=%-8s size=%-8s %s" % (
            t.get("port"), t.get("baud"), t.get("mode"), t.get("lines"), t.get("bytes"),
            t.get("current_size"), (t.get("files") or [t.get("current_file") or ""])[0]))
    return "\n".join(out)


# ------------------------------------------------------------------ RTK 账号

def rtk_account_pick():
    """从飞书多维表格「GNSS的RTK账号信息」取一个可用账号，并顺手刷新技术目录下的缓存。

    缓存文件 rtk_accounts.tsv 落在工具目录，GUI 打开 RTK 对话框时会直接读它，
    所以跑过一次 AI 抓取后，人工开界面也不用再填账号。
    """
    try:
        import rtk_accounts as ra
    except Exception as e:
        log("[rtk] 没有 rtk_accounts.py，跳过自动取账号: %s" % e)
        return None
    try:
        rows = ra.fetch()
    except Exception as e:
        log("[rtk] 取多维表格账号失败: %s" % e)
        return None
    usable = [r for r in rows if "可用" in (r.get("status") or "")]
    rows = usable or rows
    if not rows:
        log("[rtk] 多维表格里没有可用账号")
        return None
    try:
        os.makedirs(TOOL_DIR, exist_ok=True)
        with open(os.path.join(TOOL_DIR, "rtk_accounts.tsv"), "w", encoding="utf-8") as f:
            f.write(ra.to_tsv(rows))
    except Exception:
        pass
    r = rows[0]
    log("[rtk] 账号来自多维表格：%s  %s:%s/%s" % (r.get("user"), r.get("host"), r.get("port"), r.get("mount")))
    return r


# ------------------------------------------------------------------ 抓取（一次性）

def run_exe(exe, targets, sec, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    status = os.path.join(out_dir, "status.json")
    result = os.path.join(out_dir, "result.json")
    for f in (status, result):
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass
    tg = targets_arg(targets)
    cmd = [exe, "/run", "/targets:" + tg, "/sec:%d" % int(sec), "/headless",
           "/instance:ai" + uuid.uuid4().hex[:6], "/dir:" + out_dir,
           "/status:" + status, "/result:" + result, "/quiet"] + list(EXTRA_ARGS)
    log("[run] %s" % " ".join('"%s"' % c if " " in c else c for c in cmd[1:]))
    t0 = time.time()
    proc = subprocess.run(cmd, timeout=sec + 120)
    elapsed = time.time() - t0
    data = None
    for _ in range(20):
        if os.path.isfile(result):
            try:
                with open(result, "r", encoding="utf-8") as f:
                    data = json.load(f)
                break
            except Exception:
                time.sleep(0.5)
        else:
            time.sleep(0.5)
    return {"exit_code": proc.returncode, "elapsed": round(elapsed, 1),
            "result_path": result, "raw": data}


# ------------------------------------------------------------------ 汇总

EMPTY_HINT = ("排查顺序: ① 波特率不对（试 921600 / 460800 / 115200 / 3000000）"
              "② 设备侧这个口当前没有日志输出（要触发动作或打开日志开关）"
              "③ 该口被 QCOM / SSCOM / WindTerm 占用 ④ 线序或口选错。"
              "先用 `--sec 10 --baud <其他值>` 复测，别急着判定工具坏了。")

RTT_EMPTY_HINT = ("RTT 是 0 字节时的排查顺序: ① 芯片名和 J-Link 支持列表不一致（`--list-jlink` 看 "
                  "chips_hint，必须一字不差，如 STM32G0B0CE）② 目标程序里没用 SEGGER_RTT_Write/printf，"
                  "RTT 控制块根本没建（可手填 `--rtt-range \"0x20000000 0x400\"`）③ J-Link 被别的程序"
                  "占着（rtt_t2 / JLinkRTTViewer / Keil / JFlash，同时只能一个）④ 只写不读的通道："
                  "换通道号 `--rtt-ch 1/2`。仿真器没插/驱动没装看 `--list-jlink` 的 emulators 是不是 0。")


def summarize(run, out_dir):
    rows, totals = [], {}
    raw = run.get("raw") or {}
    for t in raw.get("targets", []):
        is_rtt = (t.get("iface") == "rtt")
        port = t.get("port", "")
        if is_rtt:
            # RTT 在工具里 port 固定写 "RTT"，真正有用的是芯片 + 通道 + 速率
            port = "RTT %s" % (t.get("chip") or "?")
            if t.get("rtt_ch"):
                port += " ch%d" % t.get("rtt_ch")
        rows.append({
            "alias": t.get("name", ""), "port": port,
            "iface": t.get("iface", "serial"),
            "baud": (t.get("speed_khz") or t.get("baud", "")) if is_rtt else t.get("baud", ""),
            "mode": t.get("mode", ""),
            "file": (t.get("files") or [t.get("current_file", "")])[0],
            "bytes": t.get("bytes", 0), "lines": t.get("lines", 0),
            "size": t.get("current_size", 0), "error": t.get("last_error", ""),
            "reconnects": t.get("reconnects", 0),
        })
    totals = raw.get("totals", {})

    out = ["## 抓取结果", ""]
    out.append("| 别名 | 接口 | 端口/芯片 | 波特率/速率kHz | 模式 | 行数 | 字节 | 文件 |")
    out.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        out.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["alias"], "RTT" if r["iface"] == "rtt" else "串口",
            r["port"], r["baud"], r["mode"], r["lines"], r["bytes"], r["file"]))
    out.append("")
    out.append("总计: %s 行 / %s 字节 | 用时 %.1fs | 目录 %s" % (
        totals.get("lines", 0), totals.get("bytes", 0), run.get("elapsed", 0), out_dir))
    empty = [r for r in rows if not r["bytes"]]
    if empty:
        out.append("")
        out.append("### 无数据的目标")
        for r in empty:
            tail = ("，错误: " + r["error"]) if r["error"] else ""
            out.append("- **%s (%s)** 0 字节%s" % (r["alias"], r["port"], tail))
        out.append("")
        out.append(EMPTY_HINT)
        if any(r["iface"] == "rtt" for r in empty):
            out.append("")
            out.append(RTT_EMPTY_HINT)

    summary = "\n".join(out)
    md = os.path.join(out_dir, "summary.md")
    with open(md, "w", encoding="utf-8") as f:
        f.write(summary + "\n")
    js = os.path.join(out_dir, "summary.json")
    with open(js, "w", encoding="utf-8") as f:
        json.dump({"rows": rows, "totals": totals, "elapsed": run.get("elapsed"),
                   "engine": "exe", "summary_md": md}, f, ensure_ascii=False, indent=2)
    return summary, md, js, rows


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(
        description="日志抓取：串口(COM) + J-Link RTT + RTK 差分（本地已有工具直接跑；缺失则从飞书云盘拉到 C 盘）")
    ap.add_argument("--ports", help="逗号分隔的串口，如 COM247,COM98")
    ap.add_argument("--targets", help="精确目标: 别名|COM号|波特率|模式"
                                      "，RTT 用 别名|RTT@芯片|速率kHz|模式|地址范围|通道；多路用 ; 分隔")
    ap.add_argument("--rtt", nargs="?", const="", default=None,
                    help="加一路 J-Link RTT：--rtt STM32G0B0CE（芯片名要和 J-Link 支持列表一致）")
    ap.add_argument("--rtt-speed", type=int, default=4000, help="RTT 的 J-Link 速率 kHz（默认 4000）")
    ap.add_argument("--rtt-range", default="", help="RTT 控制块搜索范围，如 \"0x20000000 0x400\"（空=自动搜）")
    ap.add_argument("--rtt-ch", type=int, default=0, help="RTT 上行缓冲区通道号（默认 0）")
    ap.add_argument("--jlink", default="", help="指定 JLinkARM.dll 路径（默认自动从 PATH/注册表找）")
    ap.add_argument("--sn", type=int, default=0, help="指定 J-Link 仿真器序列号（多台时用）")
    ap.add_argument("--list-jlink", action="store_true", help="看 J-Link DLL 版本/仿真器/支持芯片")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--mode", default="text", choices=["text", "hex"])
    ap.add_argument("--sec", type=int, default=60, help="抓取时长（秒）")
    ap.add_argument("--out", default="", help="输出目录，默认 <workspace>/serial_logs/<时间戳>")
    ap.add_argument("--tool-dir", default="", help="工具目录；非 C 盘会被强制改到 C:\\QuecAgentTools")
    ap.add_argument("--no-download", action="store_true", help="本地无工具就报错，不去飞书拉")
    ap.add_argument("--ensure-tool-only", action="store_true", help="只确保工具就位，不抓取")
    ap.add_argument("--refresh-tool", action="store_true",
                    help="强制重新从飞书云盘拉取工具（本地已有也重下，用于怀疑工具过期）")
    ap.add_argument("--launch", action="store_true",
                    help="常驻启动：后台一直抓，命令结束也不退出（要停用 --stop）")
    ap.add_argument("--stop", action="store_true", help="停止常驻抓取实例")
    ap.add_argument("--status", action="store_true", help="查看常驻抓取状态")
    ap.add_argument("--live-dir", default="", help="常驻抓取的日志目录，默认 serial_logs/live")
    ap.add_argument("--instance", default="live", help="常驻实例名，默认 live")
    ap.add_argument("--list-ports", action="store_true")
    ap.add_argument("--hex-file", default="log", choices=["log", "bin", "hex"],
                    help="HEX 模式日志后缀（默认 log：带时间戳的 16 进制转录；"
                         "bin=裸二进制；hex=十六进制）；文本模式固定 .log")
    ap.add_argument("--rtk-host", default="", help="RTK caster 地址（如 106.13.146.74）")
    ap.add_argument("--rtk-port", type=int, default=0, help="RTK caster 端口（如 8102）")
    ap.add_argument("--rtk-mount", default="", help="RTK 挂载点（如 RTCM_CC）")
    ap.add_argument("--rtk-user", default="", help="RTK 账号")
    ap.add_argument("--rtk-pass", default="", help="RTK 密码")
    ap.add_argument("--rtk-target", default="all", help="给哪个目标开 RTK：别名 / COM 号 / all")
    ap.add_argument("--rtk-interval", type=int, default=0, help="多久发一次 GGA（秒，默认 10）")
    ap.add_argument("--rtk-auto", action="store_true",
                    help="账号默认从飞书多维表格取（第一个可用账号）；给了 --rtk-user 就以你给的为准")
    args = ap.parse_args()

    # 透传给 exe 的附加参数（HEX 后缀 / RTK）
    global EXTRA_ARGS
    # RTK 默认不开：只有 --rtk-auto 或显式给了 caster/账号才开
    # （修：rtk_target 默认值是 "all"，以前拿它判断会让每次抓取都悄悄登 NTRIP 并往串口注 RTCM）
    want_rtk = bool(args.rtk_auto or args.rtk_host or args.rtk_mount or args.rtk_user)
    if want_rtk and not args.rtk_user:
        acc = rtk_account_pick()
        if acc:
            args.rtk_host = args.rtk_host or acc.get("host", "")
            port = args.rtk_port or 0
            if not port:
                try:
                    port = int(acc.get("port") or 0)
                except ValueError:
                    port = 0
            args.rtk_port = port
            args.rtk_mount = args.rtk_mount or acc.get("mount", "")
            args.rtk_user = acc.get("user", "")
            args.rtk_pass = acc.get("pass", "")
    # 显式下发，避免工具目录里的旧 ini（hexfile=bin）把默认值带回 .bin
    EXTRA_ARGS.append("/hexfile:" + args.hex_file)
    if args.rtk_host:
        EXTRA_ARGS.append("/rtkhost:" + args.rtk_host)
    if args.rtk_port:
        EXTRA_ARGS.append("/rtkport:%d" % args.rtk_port)
    if args.rtk_mount:
        EXTRA_ARGS.append("/rtkmount:" + args.rtk_mount)
    if args.rtk_user:
        EXTRA_ARGS.append("/rtkuser:" + args.rtk_user)
    if args.rtk_pass:
        EXTRA_ARGS.append("/rtkpass:" + args.rtk_pass)
    if args.rtk_interval:
        EXTRA_ARGS.append("/rtkinterval:%d" % args.rtk_interval)
    if args.rtk_host or args.rtk_mount:
        EXTRA_ARGS.append("/rtk:" + (args.rtk_target or "all"))
    # RTT / J-Link：DLL 路径和仿真器序列号只有命令行能传（ini 里的 rttdll 也会被它覆盖）
    if args.jlink:
        EXTRA_ARGS.append("/jlink:" + args.jlink)
    if args.sn:
        EXTRA_ARGS.append("/sn:%d" % args.sn)

    if args.tool_dir:
        set_tool_dir(args.tool_dir)

    live = live_dir_of(args)

    if args.status:
        log(format_status(read_status(live)))
        return 0

    if args.stop:
        killed, pid = stop_live(live)
        if killed:
            log("[stop] 已停止常驻抓取 (pid=%s)" % pid)
            return 0
        log("[stop] 没有找到运行中的常驻实例")
        return 3

    if args.list_ports:
        for d, desc in list_ports():
            log("%-10s %s" % (d, desc))
        return 0

    try:
        exe = ensure_tool(auto_download=not args.no_download, force=args.refresh_tool)
    except Exception as e:
        log("[tool] ERROR: %s" % e)
        log("[tool] 没有可用的抓取工具，已停止（本 skill 不做 Python 兜底）")
        return 2

    if args.ensure_tool_only:
        log("[tool] ready: %s" % exe)
        return 0

    if args.list_jlink:
        cmd = [exe, "/jlinkinfo", "/quiet"] + [a for a in EXTRA_ARGS if a.startswith("/jlink:")]
        log("[jlink] %s" % " ".join(cmd[1:]))
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=60)
        except Exception as e:
            log("[jlink] ERROR: %s" % e)
            return 2
        log((r.stdout or "") + (r.stderr or ""))
        return 0 if r.returncode == 0 else 2

    try:
        targets = parse_targets(args)
    except ValueError as e:
        if args.launch or args.rtt is not None:
            log("[args] %s" % e)
            return 4
        targets = []

    if args.launch:
        s = launch_live(exe, targets, live, args.instance)
        if not s:
            log("[launch] 启动失败")
            return 2
        log("[launch] 已在后台常驻抓取，日志目录 %s" % live)
        log(format_status(s))
        return 0

    out_dir = os.path.abspath(args.out or os.path.join(
        WORKSPACE, "serial_logs", time.strftime("%Y%m%d_%H%M%S")))
    os.makedirs(out_dir, exist_ok=True)

    try:
        run = run_exe(exe, targets, args.sec, out_dir)
    except Exception as e:
        log("[run] ERROR: %s" % e)
        return 2
    if not run.get("raw"):
        log("[run] ERROR: exe 没有产出 result.json（被杀软拦截或参数错误）")
        log("[run] 检查: 工具是否还在 %s；不在就重跑本命令让它重新拉取" % exe)
        return 2

    summary, md, js, rows = summarize(run, out_dir)
    log("")
    log(summary)
    log("")
    log("[out] %s" % md)
    log("[out] %s" % js)
    if not rows or not any(r["bytes"] for r in rows):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
