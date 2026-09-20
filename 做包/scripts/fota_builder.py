#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FOTA 升级包制作脚本
支持全量包、差分包、最小系统包三种模式
"""

import os
import sys
import re
import hashlib
import struct
import zipfile
import subprocess
import tempfile
import shutil
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

# 工具目录（必须全 ASCII 路径！FBFMake_CF_V1.6-150.exe 不认中文路径，会弹
# "Unable to open file: ...\????\..." 的模态框并永久卡住等点击）
TOOL_DIR = r"D:\work\package\fota_tool"
# 默认配置文件（仅作交叉校验用；config 现在依据版本包 ZIP 生成）
DEFAULT_CONFIG = os.path.join(TOOL_DIR, "config_app")
# 单个外部工具命令的最长等待秒数（超时会被终止并抛出，附工具弹窗文本）
TOOL_TIMEOUT = 180

# 全局日志列表
_log_lines = []
# 日志文件路径
_log_file_path = None
# GUI 关键日志回调（由 FOTABuilderGUI 设置，仅用于关键流程信息）
_gui_log_callback = None


def set_gui_log_callback(callback):
    """设置 GUI 关键日志回调函数"""
    global _gui_log_callback
    _gui_log_callback = callback


def set_log_file_path(path):
    """设置日志文件路径"""
    global _log_file_path
    _log_file_path = path


def log(msg, level="INFO"):
    """统一日志输出：打印到控制台、追加到列表、写入日志文件。不再直接推送 GUI"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {msg}"
    print(line)
    _log_lines.append(line)
    # 写入日志文件
    if _log_file_path:
        try:
            with open(_log_file_path, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except Exception:
            pass


def gui_key_log(msg):
    """仅向 GUI 推送关键流程信息（线程安全）"""
    if _gui_log_callback:
        try:
            _gui_log_callback(msg)
        except Exception:
            pass


def write_log_to_file(output_dir):
    """将日志保存到文件"""
    log_file = os.path.join(output_dir, f"build_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    with open(log_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(_log_lines))
    return log_file


def read_tool_dialogs(pid):
    """读某个进程弹出的对话框文本。
    FBFMake 出错时会弹模态框（如 "Unable to open file: ..."）并一直等人点确定，
    脚本里必须靠这个把它的"卡住原因"读出来，否则只能看到一个不动的进程。"""
    out = []
    try:
        import ctypes
        import ctypes.wintypes as wt
        u = ctypes.windll.user32
        Proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
        tops = []

        def cb(hwnd, _):
            w = wt.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(w))
            if w.value == pid:
                tops.append(hwnd)
            return True

        u.EnumWindows(Proc(cb), 0)
        for h in tops:
            buf = ctypes.create_unicode_buffer(512)
            u.GetWindowTextW(h, buf, 512)
            cls = ctypes.create_unicode_buffer(64)
            u.GetClassNameW(h, cls, 64)
            if cls.value != '#32770':          # 只要对话框
                continue
            texts = []

            def cb2(ch, _):
                t = ctypes.create_unicode_buffer(1024)
                u.GetWindowTextW(ch, t, 1024)
                if t.value.strip():
                    texts.append(t.value.strip())
                return True

            u.EnumChildWindows(h, Proc(cb2), 0)
            if texts:
                out.append(' / '.join(texts))
    except Exception:
        pass
    return out


def run_tool(cmd, tag="tool", timeout=None):
    """统一执行外部工具（adiff / FBFMake）：
      - 用 GBK 解码输出（这两个工具是 ANSI 程序，用 utf-8 解会把读取线程搞崩，
        大输出时管道写满 → 死锁，这正是之前"卡 10 分钟"的元凶之一）
      - 超时即终止，并把它弹的对话框文本一起抛出来
    """
    timeout = timeout or TOOL_TIMEOUT
    log(f"  执行: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, cwd=TOOL_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        raw, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        dlgs = read_tool_dialogs(proc.pid)
        proc.kill()
        raw, _ = proc.communicate()
        msg = f"{tag} 超过 {timeout}s 未结束，已终止: {os.path.basename(cmd[0])}"
        if dlgs:
            msg += "\n  工具弹窗内容: " + " | ".join(dlgs)
            msg += "\n  （弹窗=工具在等人点确定；若提示 Unable to open file 且路径含中文，请把工具目录/工作目录换成纯 ASCII 路径）"
        tail = (raw or b'').decode('gbk', 'replace').strip().splitlines()[-5:]
        if tail:
            msg += "\n  最后输出: " + " / ".join(tail)
        log(msg, "ERROR")
        raise RuntimeError(msg)
    text = (raw or b'').decode('gbk', 'replace')
    # adiff/FBFMake 会刷几百行，日志只留头尾（完整输出仍返回给调用方做校验）
    lines = [l for l in text.splitlines() if l.strip()]
    for line in lines[:5]:
        log(f"  [{tag}] {line}")
    if len(lines) > 14:
        log(f"  [{tag}] ...（省略 {len(lines) - 14} 行）...")
    for line in lines[-9:]:
        log(f"  [{tag}] {line}")
    # FBFMake 失败时也可能走正常退出路径，用弹窗兜底
    dlgs = read_tool_dialogs(proc.pid)
    if dlgs:
        log(f"  [{tag}] 检测到弹窗: {' | '.join(dlgs)}", "WARN")
        proc.kill()
        raise RuntimeError(f"{tag} 弹出对话框（通常是错误提示）: {' | '.join(dlgs)}")
    if proc.returncode != 0:
        log(f"  [{tag}] 退出码 {proc.returncode}", "WARN")
    return proc.returncode, text


def check_adiff_output(adiff_text, output_file):
    """校验 adiff 输出：文件必须存在且非空；stdout 里的 error 仅作警告"""
    if not os.path.exists(output_file):
        raise RuntimeError(f"adiff 输出文件未生成: {output_file}")
    if os.path.getsize(output_file) == 0:
        raise RuntimeError(f"adiff 输出文件为空: {output_file}")
    low = (adiff_text or "").lower()
    if "error" in low and "the diff file size" not in (adiff_text or "").lower():
        log(f"adiff 输出含 error 关键词，但文件已生成，请手动确认: {output_file}", "WARN")
    log(f"adiff 输出校验通过: {output_file} ({os.path.getsize(output_file):,} bytes)")


def check_fbfmake_output(output_file):
    """校验 FBFMake 输出：文件必须存在且非空"""
    if not os.path.exists(output_file):
        raise RuntimeError(f"FBFMake 输出文件未生成: {output_file}")
    if os.path.getsize(output_file) == 0:
        raise RuntimeError(f"FBFMake 输出文件为空: {output_file}")
    log(f"FBFMake 输出校验通过: {output_file} ({os.path.getsize(output_file):,} bytes)")


def extract_version_from_filename(zip_path):
    """取"用来区分新旧版本"的短标签。
    优先取文件名尾部的版本标记（__V04 / _BETA260820 之类），它才是真正的版本号：
      QDM568_ML307CR02_01.001.01.006_V02.zip -> V02
      QDM568_ML307CR02_01.006_BETA0819.zip   -> BETA0819

    !! 不要只取中间那一段 01.001.01.006 —— V02 和 V04 两个包会取出同一个标签，
    导致 A→B 与 B→A 两个输出文件同名互相覆盖（老版本就踩过这个坑）。
    """
    basename = os.path.splitext(os.path.basename(zip_path))[0]
    m = re.search(r'[_-](V\d+(?:[._]\d+)*|BETA\w*)$', basename, re.IGNORECASE)
    if m:
        tag = m.group(1)
        return tag.upper() if tag.lower().startswith('beta') else tag
    # 退路：文件名里的 V1.2.3 / 1.2.3 形式
    m = re.search(r'[Vv]?(\d+\.\d+\.\d+(?:\.\d+)?)', basename)
    if m:
        return m.group(0) if m.group(0).startswith(('V', 'v')) else 'V' + m.group(0)
    fallback = re.sub(r'[^a-zA-Z0-9._-]', '', basename)
    return fallback if fallback else "unknown"


def distinct_labels(old_zip, new_zip):
    """两个包的版本标签；标签相同就强制区分，避免输出文件重名互相覆盖"""
    a = extract_version_from_filename(old_zip)
    b = extract_version_from_filename(new_zip)
    if a == b:
        log(f"注意: 两个包的版本标签相同({a})，输出名将加 _OLD/_NEW 区分以防覆盖", "WARN")
        a, b = a + '_OLD', b + '_NEW'
    return a, b


def extract_zip(zip_path, extract_to):
    """解压 zip 文件"""
    if not os.path.exists(zip_path):
        raise FileNotFoundError(f"ZIP 包不存在: {zip_path}")
    log(f"解压: {zip_path} -> {extract_to}")
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(extract_to)
    log("解压完成。")


def extract_nested_app_zip(extract_dir):
    """查找并解压嵌套的ML307C_APP.zip"""
    app_zip = find_file(extract_dir, "ML307C_APP.zip")
    if app_zip:
        log(f"发现嵌套ZIP: {app_zip}，正在解压...")
        extract_zip(app_zip, extract_dir)
        log("嵌套ZIP解压完成。")
    return extract_dir


def find_file(directory, filename):
    """在目录中递归查找文件"""
    for root, dirs, files in os.walk(directory):
        if filename in files:
            return os.path.join(root, filename)
    return None


# ============================================================================
# 分区表解析：config 依据「版本包 ZIP」生成，不再依赖工具目录里写死的 config_app
#
# 版本包结构（QDM568 / ML307C / ASR1605 4M）：
#   <版本号>.zip
#   ├─ ML307C_APP.zip         <- 装载包：内含 partition.bin / system.img / user_app.bin
#   ├─ ML307C_APP.bin         <- 客户 app 镜像（与装载包里的 user_app.bin 同一份）
#   ├─ ML307C_APP_Source.zip  <- 源码包（不参与做包，跳过）
#   └─ DBG/config/partition/ASR1605_SINGLE_SIM_FLASH_LAYOUT_4M.json  <- 布局（可交叉校验）
#
# 关键点：app 整包 config 里的 1_Image_Flash_Entry_Address 必须等于客户 app 分区
#        （partition.bin 里 type=cust 的那条）的 Start，否则差分会写到错误地址。
# ============================================================================
PT_ENTRY_SIZE = 68          # BTPA 分区表：8 字节头 + N*68 字节记录
PT_NAME_LEN = 32
PT_TYPE_LEN = 16
APP_PART_CANDIDATES = ("user_app", "customer_app", "cusapp", "app")   # 客户 app 分区名候选
APP_IMAGE_CANDIDATES = ("user_app.bin", "ML307C_APP.bin", "customer_app.bin")


def find_nested_payload_zips(extract_dir):
    """找出目录下「含 partition.bin 的嵌套 zip」（如 ML307C_APP.zip），跳过 Source 包"""
    found = []
    for root, dirs, files in os.walk(extract_dir):
        for name in files:
            if not name.lower().endswith('.zip') or 'source' in name.lower():
                continue
            path = os.path.join(root, name)
            try:
                with zipfile.ZipFile(path) as zf:
                    if any(n.endswith('partition.bin') for n in zf.namelist()):
                        found.append(path)
            except Exception:
                pass
    return found


def extract_payload_zips(extract_dir):
    """解压所有装载包（含 partition.bin 的嵌套 zip），平铺到 zip 所在目录"""
    for z in find_nested_payload_zips(extract_dir):
        log(f"发现装载包(含 partition.bin): {z}，解压...")
        with zipfile.ZipFile(z) as zf:
            zf.extractall(os.path.dirname(z))
    return extract_dir


def find_partition_bin(extract_dir):
    """递归找 partition.bin（含嵌套 zip 内），返回 (bytes, 来源说明)"""
    for root, dirs, files in os.walk(extract_dir):
        if 'partition.bin' in files:
            p = os.path.join(root, 'partition.bin')
            return open(p, 'rb').read(), p
    for root, dirs, files in os.walk(extract_dir):
        for name in files:
            if not name.lower().endswith('.zip') or 'source' in name.lower():
                continue
            path = os.path.join(root, name)
            try:
                with zipfile.ZipFile(path) as zf:
                    for n in zf.namelist():
                        if n.endswith('partition.bin'):
                            return zf.read(n), '%s::%s' % (path, n)
            except Exception:
                pass
    raise FileNotFoundError("未找到 partition.bin（版本包结构异常），无法依据包生成 config")


def parse_partition_table(data):
    """解析 BTPA 分区表 -> [{name,type,start,size,vstart,vsize}]"""
    if data[:4] != b'BTPA':
        raise ValueError("不是 BTPA 分区表: %r" % data[:4])
    entries, off = [], 8
    while off + PT_ENTRY_SIZE <= len(data):
        rec = data[off:off + PT_ENTRY_SIZE]
        name = rec[0:PT_NAME_LEN].split(b'\x00')[0].decode('ascii', 'replace')
        ptype = rec[PT_NAME_LEN:PT_NAME_LEN + PT_TYPE_LEN].split(b'\x00')[0].decode('ascii', 'replace')
        start, size, vstart, vsize = struct.unpack('<IIII', rec[48:64])
        if name:
            entries.append(dict(name=name, type=ptype, start=start, size=size,
                                vstart=vstart, vsize=vsize))
        off += PT_ENTRY_SIZE
    return entries


def pick_app_partition(entries):
    """挑出客户 app 分区：优先 type=cust，其次按分区名候选"""
    for e in entries:
        if e['type'] == 'cust':
            return e
    for cand in APP_PART_CANDIDATES:
        for e in entries:
            if e['name'] == cand:
                return e
    return None


def find_app_image(extract_dir):
    """找客户 app 镜像：优先 user_app.bin，其次 ML307C_APP.bin，返回 (路径, 文件名)"""
    for cand in APP_IMAGE_CANDIDATES:
        p = find_file(extract_dir, cand)
        if p:
            return p, cand
    return None, None


def parse_and_log_table(extract_dir, tag=""):
    """解析并打印分区表，返回客户 app 分区条目（找不到返回 None）"""
    data, src = find_partition_bin(extract_dir)
    entries = parse_partition_table(data)
    log(f"{tag}分区表来源: {src}")
    app = pick_app_partition(entries)
    if app:
        log("%s客户 app 分区: %s  start=0x%08X size=0x%08X (vstart=0x%08X)" %
            (tag, app['name'], app['start'], app['size'], app['vstart']))
    else:
        log(f"{tag}分区表里没找到客户 app 分区(cust/user_app/customer_app)", "WARN")
    return app, entries


def dump_layout_file(entries, pkg_dir, tag=""):
    """把分区表落到输出目录，便于追溯（config 是依据它生成的）"""
    path = os.path.join(pkg_dir, f"分区表_layout{('_' + tag) if tag else ''}.txt")
    lines = ["Name                 Type   Start        Size         vStart",
             "-" * 72]
    for e in entries:
        lines.append("%-20s %-6s 0x%08X   0x%08X   0x%08X" %
                     (e['name'], e['type'], e['start'], e['size'], e['vstart']))
    open(path, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    log(f"分区表已导出: {path}")
    return path


def write_image_config(path, images):
    """写 FBFMake 用的 config；images = [(镜像文件名, 分区 start), ...]"""
    lines = ['[Image_List]', 'Number_of_Images = %d' % len(images)]
    for i, (img, start) in enumerate(images, 1):
        lines += ['%d_Image_Enable = 1' % i,
                  '%d_Image_Image_ID = 0x%02X' % (i, 0x2F + i),
                  '%d_Image_Path = %s' % (i, img),
                  '%d_Image_Flash_Entry_Address = 0x%08X' % (i, start),
                  '%d_Image_ID_Name = %d' % (i, i)]
    open(path, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    log(f"已依据版本包生成 config: {path}")
    log("--- config 内容 ---")
    for l in lines:
        log("    " + l)
    log("-------------------")
    return path


def build_config_from_zip(extract_dir, out_path, app_image_name="user_app.bin"):
    """依据版本包 ZIP 生成 app 整包用的 config（1 个镜像：客户 app -> 其分区 Start）"""
    data, src = find_partition_bin(extract_dir)
    entries = parse_partition_table(data)
    log(f"分区表来源: {src}")
    app = pick_app_partition(entries)
    if not app:
        raise RuntimeError("分区表里找不到客户 app 分区（cust / user_app / customer_app）")
    log("客户 app 分区: %s  start=0x%08X size=0x%08X" % (app['name'], app['start'], app['size']))
    return write_image_config(out_path, [(app_image_name, app['start'])]), app, entries


def read_config_address(config_path):
    """读一个 config 里的 (镜像名, 地址)，用于交叉校验"""
    try:
        txt = open(config_path, encoding='utf-8-sig', errors='replace').read()
    except Exception:
        return None
    img = addr = None
    for line in txt.splitlines():
        line = line.strip()
        if '=' not in line:
            continue
        k, v = line.split('=', 1)
        k, v = k.strip(), v.strip()
        if k.endswith('_Image_Path'):
            img = v
        elif k.endswith('_Image_Flash_Entry_Address'):
            addr = v
            break
    if addr is None:
        return None
    try:
        return img, int(addr, 16)
    except ValueError:
        return None


def cleanup_app_workdir():
    """清理 FBFMake 工作目录 a\ 里本次拷贝进去的客户 app 镜像（a\ 下次运行会整体重建）"""
    a_dir = os.path.join(TOOL_DIR, "a")
    for name in APP_IMAGE_CANDIDATES:
        p = os.path.join(a_dir, name)
        if os.path.exists(p):
            try:
                os.remove(p)
                log(f"  已清理工作目录文件: {p}")
            except Exception as e:
                log(f"  清理 {p} 失败: {e}", "WARN")


def make_diff_package_full(old_zip, new_zip, output_dir):
    """制作差分包（全量差分升级）：对应说明文档第1节，生成 system 差分包"""
    log("=" * 50)
    log("模式: 差分包-全量差分升级 (Diff Package - Full)")
    log("=" * 50)

    old_version, new_version = distinct_labels(old_zip, new_zip)
    log(f"旧版本: {old_version}  (来源: {os.path.basename(old_zip)})")
    log(f"新版本: {new_version}  (来源: {os.path.basename(new_zip)})")

    # 创建以版本号+时间戳命名的子文件夹
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pkg_dir = os.path.join(output_dir, f"{old_version}_to_{new_version}_{timestamp}")
    os.makedirs(pkg_dir, exist_ok=True)
    log(f"输出目录: {pkg_dir}")

    adiff = os.path.join(TOOL_DIR, "adiff.exe")
    if not os.path.exists(adiff):
        raise FileNotFoundError(f"adiff.exe 不存在: {adiff}")
    log(f"工具路径: {adiff}  [OK]")

    old_tmp = tempfile.mkdtemp(prefix="old_")
    new_tmp = tempfile.mkdtemp(prefix="new_")
    log(f"创建临时目录: old={old_tmp}, new={new_tmp}")

    results = []
    try:
        # 步骤1: 解压 ZIP 包
        log("[步骤1/4] 解压旧版本 ZIP 包...")
        extract_zip(old_zip, old_tmp)
        log("旧版本 ZIP 包解压完成。")

        log("[步骤2/4] 解压新版本 ZIP 包...")
        extract_zip(new_zip, new_tmp)
        log("新版本 ZIP 包解压完成。")

        # 解压装载包（含 partition.bin 的嵌套 zip，如 ML307C_APP.zip）
        extract_payload_zips(old_tmp)
        extract_payload_zips(new_tmp)

        # 查找关键文件
        system_old = find_file(old_tmp, "system.img")
        system_new = find_file(new_tmp, "system.img")
        user_app_old, name_old = find_app_image(old_tmp)
        user_app_new, name_new = find_app_image(new_tmp)

        if not system_old:
            raise FileNotFoundError("旧包中未找到 system.img")
        if not system_new:
            raise FileNotFoundError("新包中未找到 system.img")
        if not user_app_old:
            raise FileNotFoundError("旧包中未找到客户 app 镜像 (user_app.bin / ML307C_APP.bin)")
        if not user_app_new:
            raise FileNotFoundError("新包中未找到客户 app 镜像 (user_app.bin / ML307C_APP.bin)")

        # 依据版本包 ZIP 解析分区表 -> 客户 app 分区名（不再写死 "user_app"）
        app_part_old, entries_old = parse_and_log_table(old_tmp, "旧包 ")
        app_part_new, entries_new = parse_and_log_table(new_tmp, "新包 ")
        dump_layout_file(entries_old, pkg_dir, "old")
        dump_layout_file(entries_new, pkg_dir, "new")
        app_part_name = (app_part_new or app_part_old or {}).get('name') or "user_app"
        if app_part_old and app_part_new and app_part_old['start'] != app_part_new['start']:
            log("!! 新旧包的 %s 起始地址不一致: 0x%08X vs 0x%08X，请确认是否换过分区表" %
                (app_part_name, app_part_old['start'], app_part_new['start']), "WARN")

        log(f"  system.img (旧): {system_old}")
        log(f"  system.img (新): {system_new}")
        log(f"  客户 app 镜像 (旧): {user_app_old}  [{name_old}]")
        log(f"  客户 app 镜像 (新): {user_app_new}  [{name_new}]")
        log(f"  adiff -a1 使用的分区名: {app_part_name}")

        # 包1: system 差分包 A→B
        log("[步骤3/4] 生成 system 差分包 A→B...")
        system_output_ab = os.path.join(pkg_dir, f"QDM568_diff_system_{old_version}_to_{new_version}.bin")
        cmd_system_ab = [
            adiff, "-p",
            system_old, system_new, system_output_ab,
            "-a1", app_part_name, user_app_old, user_app_new,
            "-l", "fsall",
            "-s", "20000"
        ]
        log(f"  执行命令: {' '.join(cmd_system_ab)}")
        _, _adiff_text = run_tool(cmd_system_ab, "adiff")
        check_adiff_output(_adiff_text, system_output_ab)
        log(f"  system 差分包 A→B 生成成功: {system_output_ab}")
        results.append(system_output_ab)

        # 包2: system 差分包 B→A
        log("[步骤4/4] 生成 system 差分包 B→A...")
        system_output_ba = os.path.join(pkg_dir, f"QDM568_diff_system_{new_version}_to_{old_version}.bin")
        cmd_system_ba = [
            adiff, "-p",
            system_new, system_old, system_output_ba,
            "-a1", app_part_name, user_app_new, user_app_old,
            "-l", "fsall",
            "-s", "20000"
        ]
        log(f"  执行命令: {' '.join(cmd_system_ba)}")
        _, _adiff_text = run_tool(cmd_system_ba, "adiff")
        check_adiff_output(_adiff_text, system_output_ba)
        log(f"  system 差分包 B→A 生成成功: {system_output_ba}")
        results.append(system_output_ba)

        log("=" * 50)
        log("差分包（全量差分升级）制作完成! 输出文件:")
        for r in results:
            size = os.path.getsize(r)
            log(f"  {r}  ({size:,} bytes)")
        log("=" * 50)
        return results
    finally:
        shutil.rmtree(old_tmp, ignore_errors=True)
        shutil.rmtree(new_tmp, ignore_errors=True)
        log("临时目录已清理。")


def make_full_package(old_zip, new_zip, output_dir, config_path=None):
    """制作全量包（app 整包升级）：对应说明文档第2节，生成 app 全量包"""
    log("=" * 50)
    log("模式: 全量包-app整包升级 (Full Package - App)")
    log("=" * 50)

    old_version, new_version = distinct_labels(old_zip, new_zip)
    log(f"旧版本: {old_version}  (来源: {os.path.basename(old_zip)})")
    log(f"新版本: {new_version}  (来源: {os.path.basename(new_zip)})")
    log(f"升级方向: {old_version} -> {new_version}")

    # 创建以版本号+时间戳命名的子文件夹
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pkg_dir = os.path.join(output_dir, f"{old_version}_to_{new_version}_{timestamp}")
    os.makedirs(pkg_dir, exist_ok=True)
    log(f"输出目录: {pkg_dir}")

    fbfmake = os.path.join(TOOL_DIR, "FBFMake_CF_V1.6-150.exe")
    if not os.path.exists(fbfmake):
        raise FileNotFoundError(f"FBFMake_CF_V1.6-150.exe 不存在: {fbfmake}")
    log(f"工具路径: {fbfmake}  [OK]")

    adiff = os.path.join(TOOL_DIR, "adiff.exe")
    if not os.path.exists(adiff):
        raise FileNotFoundError(f"adiff.exe 不存在: {adiff}")
    log(f"adiff 路径: {adiff}  [OK]")

    if config_path is not None and not os.path.exists(config_path):
        raise FileNotFoundError(f"指定的配置文件不存在: {config_path}")
    if config_path is None:
        log("未指定 config -> 依据版本包 ZIP 自动生成（推荐，避免地址写死）")
    else:
        log(f"使用指定 config: {config_path}（稍后会与版本包分区表交叉校验）")

    old_tmp = tempfile.mkdtemp(prefix="diff_old_")
    new_tmp = tempfile.mkdtemp(prefix="diff_new_")
    log(f"创建临时目录: old={old_tmp}, new={new_tmp}")

    results = []
    try:
        # 步骤1: 解压旧版本 ZIP 包
        log("[步骤1/4] 解压旧版本 ZIP 包...")
        extract_zip(old_zip, old_tmp)
        log("旧版本 ZIP 包解压完成。")

        # 步骤2: 解压新版本 ZIP 包
        log("[步骤2/4] 解压新版本 ZIP 包...")
        extract_zip(new_zip, new_tmp)
        log("新版本 ZIP 包解压完成。")

        # 解压装载包（含 partition.bin 的嵌套 zip）
        extract_payload_zips(old_tmp)
        extract_payload_zips(new_tmp)

        # 查找关键文件
        user_app_old, name_old = find_app_image(old_tmp)
        user_app_new, name_new = find_app_image(new_tmp)
        system_old = find_file(old_tmp, "system.img")
        system_new = find_file(new_tmp, "system.img")

        if not user_app_old:
            raise FileNotFoundError("旧包中未找到客户 app 镜像 (user_app.bin / ML307C_APP.bin)")
        if not user_app_new:
            raise FileNotFoundError("新包中未找到客户 app 镜像 (user_app.bin / ML307C_APP.bin)")
        if not system_old:
            raise FileNotFoundError("旧包中未找到 system.img")
        if not system_new:
            raise FileNotFoundError("新包中未找到 system.img")

        app_image_name = name_new or "user_app.bin"
        log(f"  客户 app 镜像 (旧): {user_app_old}  [{name_old}]")
        log(f"  客户 app 镜像 (新): {user_app_new}  [{name_new}]")
        log(f"  system.img (旧): {system_old}")
        log(f"  system.img (新): {system_new}")

        # 说明文档要求：app 整包必须保证 OS(system.img) 一致，只有 app 不同
        _ho = hashlib.md5(open(system_old, 'rb').read()).hexdigest()
        _hn = hashlib.md5(open(system_new, 'rb').read()).hexdigest()
        if _ho != _hn:
            log("!! 新旧 system.img 不一致 (md5 %s vs %s)：app 整包只适用于「OS 相同、仅 app 不同」"
                "的场景，否则请改用差分包 / 最小系统包" % (_ho[:8], _hn[:8]), "WARN")
        else:
            log(f"  system.img 一致 (md5 {_ho[:8]}) -> 符合 app 整包升级条件")

        # 依据版本包 ZIP 生成 config（客户 app 分区 Start 从 partition.bin 取，不写死）
        app_part_new, entries_new = parse_and_log_table(new_tmp, "新包 ")
        app_part_old, entries_old = parse_and_log_table(old_tmp, "旧包 ")
        dump_layout_file(entries_old, pkg_dir, "old")
        dump_layout_file(entries_new, pkg_dir, "new")
        gen_config = os.path.join(pkg_dir, "config_app")
        config_path, app_part, _ = build_config_from_zip(new_tmp, gen_config, app_image_name)

        if app_part_old and app_part_old['start'] != app_part['start']:
            log("!! 新旧包的 %s 起始地址不一致: 0x%08X vs 0x%08X，请确认是否换过分区表" %
                (app_part['name'], app_part_old['start'], app_part['start']), "WARN")
        if os.path.exists(DEFAULT_CONFIG):
            static = read_config_address(DEFAULT_CONFIG)
            if static:
                _img, _addr = static
                if _addr != app_part['start']:
                    log("!! 工具目录里写死的 %s 地址 0x%08X 与版本包分区表 %s=0x%08X 不一致"
                        "（已改用版本包生成的值，写死的那份不要再用）"
                        % (os.path.basename(DEFAULT_CONFIG), _addr, app_part['name'], app_part['start']), "WARN")
                else:
                    log("  交叉校验通过: 工具目录 %s 的地址 0x%08X 与版本包一致"
                        % (os.path.basename(DEFAULT_CONFIG), _addr))

        # 包1: app 全量包 - 旧版本
        log("[步骤3/4] 准备 app 全量包 - 旧版本 (FBFMake)...")
        a_dir = os.path.join(TOOL_DIR, "a")
        b_dir = os.path.join(TOOL_DIR, "b")
        # 清空 a、b 文件夹，避免残留文件干扰
        for d in [a_dir, b_dir]:
            if os.path.exists(d):
                shutil.rmtree(d)
                log(f"  已清空文件夹: {d}")
        os.makedirs(a_dir, exist_ok=True)
        dest_old = os.path.join(a_dir, app_image_name)
        shutil.copy2(user_app_old, dest_old)
        log(f"  复制旧版本 {app_image_name} 到: {dest_old}（文件名须与 config 的 Image_Path 一致）")

        log("生成旧版本 app 全量包...")
        app_output_old = os.path.join(pkg_dir, f"QDM568_full_app_{old_version}.bin")
        cmd_app_old = [
            fbfmake,
            "-o", app_output_old,
            "-f", config_path,
            "-a", "a",
            "-b", "a"
        ]
        log(f"  执行命令: {' '.join(cmd_app_old)}")
        _, _fbf_text = run_tool(cmd_app_old, "FBFMake")
        check_fbfmake_output(app_output_old)
        log(f"  旧版本 app 全量包生成成功: {app_output_old}")
        results.append(app_output_old)

        # 清理 FBFMake 工作目录
        cleanup_app_workdir()

        # 包2: app 全量包 - 新版本
        log("[步骤4/4] 准备 app 全量包 - 新版本 (FBFMake)...")
        dest_new = os.path.join(a_dir, app_image_name)
        shutil.copy2(user_app_new, dest_new)
        log(f"  复制新版本 {app_image_name} 到: {dest_new}（文件名须与 config 的 Image_Path 一致）")

        log("生成新版本 app 全量包...")
        app_output_new = os.path.join(pkg_dir, f"QDM568_full_app_{new_version}.bin")
        cmd_app_new = [
            fbfmake,
            "-o", app_output_new,
            "-f", config_path,
            "-a", "a",
            "-b", "a"
        ]
        log(f"  执行命令: {' '.join(cmd_app_new)}")
        _, _fbf_text = run_tool(cmd_app_new, "FBFMake")
        check_fbfmake_output(app_output_new)
        log(f"  新版本 app 全量包生成成功: {app_output_new}")
        results.append(app_output_new)

        # 清理 FBFMake 工作目录
        cleanup_app_workdir()

        log("=" * 50)
        log(f"全量包（app 整包升级）制作完成! ({old_version} 和 {new_version})")
        log("输出文件:")
        for r in results:
            size = os.path.getsize(r)
            log(f"  {r}  ({size:,} bytes)")
        log("=" * 50)
        return results
    finally:
        shutil.rmtree(old_tmp, ignore_errors=True)
        shutil.rmtree(new_tmp, ignore_errors=True)
        cleanup_app_workdir()
        log("临时目录已清理。")


def make_minimal_package(old_zip, new_zip, output_dir):
    """制作最小系统包：生成 system 最小包 + app 最小包"""
    log("=" * 50)
    log("模式: 最小系统包 (Minimal Package)")
    log("=" * 50)

    old_version, new_version = distinct_labels(old_zip, new_zip)
    log(f"旧版本: {old_version}  (来源: {os.path.basename(old_zip)})")
    log(f"新版本: {new_version}  (来源: {os.path.basename(new_zip)})")
    # 创建以版本号+时间戳命名的子文件夹
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pkg_dir = os.path.join(output_dir, f"{old_version}_to_{new_version}_{timestamp}")
    os.makedirs(pkg_dir, exist_ok=True)
    log(f"输出目录: {pkg_dir}")

    adiff = os.path.join(TOOL_DIR, "adiff.exe")
    if not os.path.exists(adiff):
        raise FileNotFoundError(f"adiff.exe 不存在: {adiff}")
    log(f"工具路径: {adiff}  [OK]")

    old_tmp = tempfile.mkdtemp(prefix="min_old_")
    new_tmp = tempfile.mkdtemp(prefix="min_new_")
    log(f"创建临时目录: old={old_tmp}, new={new_tmp}")

    results = []
    try:
        # 步骤1: 解压旧版本 ZIP 包
        log("[步骤1/4] 解压旧版本 ZIP 包...")
        extract_zip(old_zip, old_tmp)
        log("旧版本 ZIP 包解压完成。")

        # 步骤2: 解压新版本 ZIP 包
        log("[步骤2/4] 解压新版本 ZIP 包...")
        extract_zip(new_zip, new_tmp)
        log("新版本 ZIP 包解压完成。")

        # 解压装载包（含 partition.bin 的嵌套 zip，如 ML307C_APP.zip）
        extract_payload_zips(old_tmp)
        extract_payload_zips(new_tmp)

        # 查找关键文件
        system_old = find_file(old_tmp, "system.img")
        system_new = find_file(new_tmp, "system.img")
        user_app_old, name_old = find_app_image(old_tmp)
        user_app_new, name_new = find_app_image(new_tmp)

        if not system_old:
            raise FileNotFoundError("旧包中未找到 system.img")
        if not system_new:
            raise FileNotFoundError("新包中未找到 system.img")
        if not user_app_old:
            raise FileNotFoundError("旧包中未找到客户 app 镜像 (user_app.bin / ML307C_APP.bin)")
        if not user_app_new:
            raise FileNotFoundError("新包中未找到客户 app 镜像 (user_app.bin / ML307C_APP.bin)")

        # 依据版本包 ZIP 解析分区表 -> 客户 app 分区名（不再写死 "user_app"）
        app_part_old, entries_old = parse_and_log_table(old_tmp, "旧包 ")
        app_part_new, entries_new = parse_and_log_table(new_tmp, "新包 ")
        dump_layout_file(entries_old, pkg_dir, "old")
        dump_layout_file(entries_new, pkg_dir, "new")
        app_part_name = (app_part_new or app_part_old or {}).get('name') or "user_app"
        if app_part_old and app_part_new and app_part_old['start'] != app_part_new['start']:
            log("!! 新旧包的 %s 起始地址不一致: 0x%08X vs 0x%08X，请确认是否换过分区表" %
                (app_part_name, app_part_old['start'], app_part_new['start']), "WARN")

        log(f"  system.img (旧): {system_old}")
        log(f"  system.img (新): {system_new}")
        log(f"  客户 app 镜像 (旧): {user_app_old}  [{name_old}]")
        log(f"  客户 app 镜像 (新): {user_app_new}  [{name_new}]")
        log(f"  adiff -a1 使用的分区名: {app_part_name}")

        # 包1: system 最小包 A→B
        log("[步骤3/4] 生成 system 最小包 A→B...")
        system_output_ab = os.path.join(pkg_dir, f"QDM568_minimal_system_{old_version}_to_{new_version}.bin")
        cmd_system_ab = [
            adiff,
            system_old, system_new, system_output_ab,
            "-a1", app_part_name, user_app_new,
            "-m"
        ]
        log(f"  执行命令: {' '.join(cmd_system_ab)}")
        _, _adiff_text = run_tool(cmd_system_ab, "adiff")
        check_adiff_output(_adiff_text, system_output_ab)
        log(f"  system 最小包 A→B 生成成功: {system_output_ab}")
        results.append(system_output_ab)

        # 包2: system 最小包 B→A
        log("[步骤4/5] 生成 system 最小包 B→A...")
        system_output_ba = os.path.join(pkg_dir, f"QDM568_minimal_system_{new_version}_to_{old_version}.bin")
        cmd_system_ba = [
            adiff,
            system_new, system_old, system_output_ba,
            "-a1", app_part_name, user_app_old,
            "-m"
        ]
        log(f"  执行命令: {' '.join(cmd_system_ba)}")
        _, _adiff_text = run_tool(cmd_system_ba, "adiff")
        check_adiff_output(_adiff_text, system_output_ba)
        log(f"  system 最小包 B→A 生成成功: {system_output_ba}")
        results.append(system_output_ba)

        log("=" * 50)
        log("最小系统包制作完成! 输出文件:")
        for r in results:
            size = os.path.getsize(r)
            log(f"  {r}  ({size:,} bytes)")
        log("=" * 50)
        return results
    finally:
        shutil.rmtree(old_tmp, ignore_errors=True)
        shutil.rmtree(new_tmp, ignore_errors=True)
        log("临时目录已清理。")


class FOTABuilderGUI:
    """FOTA 升级包制作工具 GUI"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("FOTA 升级包制作工具")
        self.root.geometry("750x660")
        self.root.resizable(True, True)

        self.old_zip_path = tk.StringVar()
        self.new_zip_path = tk.StringVar()
        self.config_path = tk.StringVar(value=DEFAULT_CONFIG)
        self.output_dir = tk.StringVar()
        self.mode = tk.StringVar(value="full")

        # 默认输出目录设为脚本所在目录下的 result 文件夹
        self.output_dir.set(os.path.join(os.path.dirname(os.path.abspath(__file__)), "result"))

        # 连接全局关键日志回调到 GUI
        set_gui_log_callback(self.key_log)

        # 初始化日志文件路径：日志放在脚本所在目录
        script_dir = os.path.dirname(os.path.abspath(__file__))
        set_log_file_path(os.path.join(script_dir, f"gui_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"))

        self.setup_ui()

    def setup_ui(self):
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 旧包选择
        row1 = ttk.Frame(main_frame)
        row1.pack(fill=tk.X, pady=5)
        ttk.Label(row1, text="旧版本 ZIP 包:", width=15).pack(side=tk.LEFT)
        ttk.Entry(row1, textvariable=self.old_zip_path).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(row1, text="浏览...", command=self.browse_old_zip).pack(side=tk.LEFT)

        # 新包选择
        row2 = ttk.Frame(main_frame)
        row2.pack(fill=tk.X, pady=5)
        ttk.Label(row2, text="新版本 ZIP 包:", width=15).pack(side=tk.LEFT)
        ttk.Entry(row2, textvariable=self.new_zip_path).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(row2, text="浏览...", command=self.browse_new_zip).pack(side=tk.LEFT)

        # 配置文件选择
        row3 = ttk.Frame(main_frame)
        row3.pack(fill=tk.X, pady=5)
        ttk.Label(row3, text="配置文件:", width=15).pack(side=tk.LEFT)
        ttk.Entry(row3, textvariable=self.config_path).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(row3, text="浏览...", command=self.browse_config).pack(side=tk.LEFT)

        # 输出目录选择
        row4 = ttk.Frame(main_frame)
        row4.pack(fill=tk.X, pady=5)
        ttk.Label(row4, text="输出目录:", width=15).pack(side=tk.LEFT)
        ttk.Entry(row4, textvariable=self.output_dir).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(row4, text="浏览...", command=self.browse_output).pack(side=tk.LEFT)

        # 模式选择
        row5 = ttk.Frame(main_frame)
        row5.pack(fill=tk.X, pady=10)
        ttk.Label(row5, text="制作模式:", width=15).pack(side=tk.LEFT)
        ttk.Radiobutton(row5, text="差分包(全量差分)", variable=self.mode, value="full").pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(row5, text="全量包(app整包)", variable=self.mode, value="diff").pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(row5, text="最小系统包", variable=self.mode, value="minimal").pack(side=tk.LEFT, padx=10)

        # 说明文字
        note_frame = ttk.LabelFrame(main_frame, text="模式说明", padding="5")
        note_frame.pack(fill=tk.X, pady=10)

        notes = (
            "差分包(全量差分): 需要新旧版本 ZIP 包，生成 1 个包 (system 差分包)\n"
            "全量包(app整包): 需要新旧版本 ZIP 包，生成 1 个包 (app 全量包)\n"
            "最小系统包: 需要新旧版本 ZIP 包，生成 2 个包 (system 最小包 + app 最小包)\n"
            "包名格式含版本号，差分包标注从旧版本到新版本"
        )
        ttk.Label(note_frame, text=notes, justify=tk.LEFT).pack(anchor=tk.W)

        # 进度条
        self.progress = ttk.Progressbar(main_frame, mode="indeterminate")
        self.progress.pack(fill=tk.X, pady=5)

        # 日志输出
        log_frame = ttk.LabelFrame(main_frame, text="日志", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.log_text = tk.Text(log_frame, height=8, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 按钮
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="开始制作", command=self.start_build).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="清空日志", command=self.clear_log).pack(side=tk.RIGHT, padx=5)

    def key_log(self, msg):
        """仅向 GUI 推送关键流程信息（线程安全，通过 after 调度到主线程）"""
        self.root.after(0, self._append_key_log, msg)

    def _append_key_log(self, msg):
        """在主线程中追加关键日志到 Text 控件"""
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)

    def clear_log(self):
        self.log_text.delete(1.0, tk.END)

    def browse_old_zip(self):
        path = filedialog.askopenfilename(filetypes=[["ZIP 文件", "*.zip"]])
        if path:
            self.old_zip_path.set(path)

    def browse_new_zip(self):
        path = filedialog.askopenfilename(filetypes=[["ZIP 文件", "*.zip"]])
        if path:
            self.new_zip_path.set(path)

    def browse_config(self):
        path = filedialog.askopenfilename(filetypes=[["配置文件", "*"], ["所有文件", "*.*"]])
        if path:
            self.config_path.set(path)

    def browse_output(self):
        path = filedialog.askdirectory()
        if path:
            self.output_dir.set(path)

    def _do_build(self, old_zip, new_zip, output, config, mode):
        """在后台线程中执行构建任务"""
        try:
            if mode == "full":
                result = make_diff_package_full(old_zip, new_zip, output)
            elif mode == "diff":
                result = make_full_package(old_zip, new_zip, output, config)
            elif mode == "minimal":
                result = make_minimal_package(old_zip, new_zip, output)
            else:
                raise ValueError(f"未知模式: {mode}")

            result_str = "\n".join(result) if isinstance(result, list) else str(result)
            # 保存日志文件
            log_file = write_log_to_file(output)
            gui_key_log(f"\n日志已保存到: {log_file}")
            self.root.after(0, self._build_success, result_str)
        except Exception as e:
            gui_key_log(f"\n错误: {e}")
            self.root.after(0, self._build_failed, str(e))

    def _build_success(self, result_str):
        gui_key_log(f"\n完成! 输出文件:\n{result_str}")
        self.progress.stop()
        messagebox.showinfo("成功", f"升级包制作成功!\n\n{result_str}")

    def _build_failed(self, error_msg):
        gui_key_log(f"\n错误: {error_msg}")
        self.progress.stop()
        messagebox.showerror("失败", f"制作失败:\n{error_msg}")

    def start_build(self):
        new_zip = self.new_zip_path.get().strip()
        old_zip = self.old_zip_path.get().strip()
        config = self.config_path.get().strip()
        output = self.output_dir.get().strip()
        mode = self.mode.get()

        if not os.path.exists(new_zip):
            messagebox.showerror("错误", f"新版本 ZIP 包不存在:\n{new_zip}")
            return
        if mode in ("full", "minimal") and not os.path.exists(old_zip):
            messagebox.showerror("错误", f"此模式需要旧版本 ZIP 包:\n{old_zip}")
            return
        if not output:
            output = os.path.dirname(new_zip)
            self.output_dir.set(output)
        if not os.path.exists(output):
            os.makedirs(output, exist_ok=True)

        self.progress.start()
        self.clear_log()
        self.key_log("开始制作...")

        # 在后台线程中执行构建，避免 GUI 卡顿
        thread = threading.Thread(
            target=self._do_build,
            args=(old_zip, new_zip, output, config, mode),
            daemon=True
        )
        thread.start()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = FOTABuilderGUI()
    app.run()
