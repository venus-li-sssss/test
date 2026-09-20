#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_diff_fbfmake.py —— QDM562 / ql-sdk 路线：用 FBFMake 做**双向差分包**（升级包 + 回滚包）

原理（对应《FOTA方法》docx 二、差分包）：
  1. 从两个版本包里抽镜像：system.img + 客户 app 镜像（默认 customer_app.bin）
  2. 解析 partition.bin（BTPA）→ 取 system / cust 分区的 Start，**现场生成 config**（不写死地址）
  3. 目录模型：exe / config / a\\ / b\\ 同目录，a\\ = 更新后、b\\ = 更新前
  4. 跑 FBFMake_CF_V1.6-150.exe -f config -d 0x10000 -a a -b b -o fbf_dfota.bin -q
  5. 交换 a\\/b\\ 再跑一次 = 回滚包

⚠️ 两条硬性要求（都踩过坑）：
  * 路径必须全 ASCII（FBFMake 是 ANSI 程序，中文路径弹模态框后永久卡住）
  * config 必须与 exe 同目录 —— FBFMake 只会读 **exe 自己目录**里的 config；
    否则它会读别人残留的 config，报 "a\\app.bin ... is not exist for Differential Upgrading."

用法：
  python make_diff_fbfmake.py --old <旧版本包.zip> --new <新版本包.zip> [-o 输出目录]
  python make_diff_fbfmake.py --old A.zip --new B.zip --only up      # 只出升级包
  python make_diff_fbfmake.py --old A.zip --new B.zip --app user_app.bin   # 改客户 app 镜像名
  python make_diff_fbfmake.py --old A.zip --new B.zip --prefix QDM562
"""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import zipfile

TOOL_DIR = r'D:\work\package\fota_tool'
FBFMAKE = 'FBFMake_CF_V1.6-150.exe'
PT_ENTRY = 68          # BTPA：8 字节头 + N×68 字节记录
PT_NAME = 32
PT_TYPE = 16
APP_CANDIDATES = ('customer_app.bin', 'user_app.bin', 'ML307C_APP.bin', 'cusapp.bin', 'app.bin')


# ----------------------------------------------------------------- 日志
LOGS = []


def log(msg, level='INFO'):
    line = '[%s] %s' % (level, msg)
    print(line)
    LOGS.append(line)


# ------------------------------------------------------- 工具弹窗（卡死）检测
def read_tool_dialogs(pid):
    """FBFMake 出错时弹模态框并永久等人点确定；把它的文本读出来当报错原因"""
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
            cls = ctypes.create_unicode_buffer(64)
            u.GetClassNameW(h, cls, 64)
            if cls.value != '#32770':
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


# ------------------------------------------------------------ 分区表 / 取镜像
class Payload(object):
    """把「外层包 zip / 装载包 zip / 解好的目录」统一成 {name: bytes}"""

    def __init__(self, path):
        self.path = path
        self.members = {}
        self.note = ''
        if os.path.isdir(path):
            for n in os.listdir(path):
                fp = os.path.join(path, n)
                if os.path.isfile(fp):
                    with open(fp, 'rb') as f:
                        self.members[n] = f.read()
            self.note = '目录'
            return
        self._load(path, 0)

    def _load(self, path, depth):
        z = zipfile.ZipFile(path)
        names = [i.filename for i in z.infolist()]
        flat = [os.path.basename(n) for n in names]
        if 'partition.bin' not in flat:
            if depth >= 3:
                raise SystemExit('没找到 partition.bin（不是装载包）: %s' % path)
            cands = [n for n in names
                     if n.lower().endswith('.zip') and 'source' not in n.lower()]
            for cand in cands:
                try:
                    zz = zipfile.ZipFile(io.BytesIO(z.read(cand)))
                    if any(os.path.basename(x) == 'partition.bin' for x in zz.namelist()):
                        self._load(io.BytesIO(z.read(cand)), depth + 1)
                        self.note = '外层包 -> 装载包 %s' % os.path.basename(cand)
                        return
                except Exception:
                    continue
            raise SystemExit('嵌套 zip 里都没有 partition.bin: %s' % path)
        for n in names:
            if n.endswith('/'):
                continue
            self.members[os.path.basename(n)] = z.read(n)
        self.note = self.note or 'zip 直读'

    def get(self, name):
        return self.members.get(name)


def parse_partition_bin(data):
    if data[:4] != b'BTPA':
        raise ValueError('不是 BTPA 分区表: %r' % data[:4])
    out, off = [], 8
    while off + PT_ENTRY <= len(data):
        rec = data[off:off + PT_ENTRY]
        name = rec[0:PT_NAME].split(b'\x00')[0].decode('ascii', 'replace')
        typ = rec[PT_TYPE:PT_TYPE + PT_TYPE].split(b'\x00')[0].decode('ascii', 'replace')
        start, size, vstart, vsize = struct.unpack('<IIII', rec[48:64])
        if name:
            out.append(dict(name=name, type=typ, start=start, size=size,
                            vstart=vstart, vsize=vsize))
        off += PT_ENTRY
    return out


def pick(entries, name):
    for e in entries:
        if e['name'] == name:
            return e
    return None


def pick_app_partition(entries):
    for e in entries:
        if e['type'] == 'cust':
            return e
    for cand in ('user_app', 'customer_app', 'cusapp', 'app'):
        e = pick(entries, cand)
        if e:
            return e
    return None


def pick_app_image(payload, wanted=None):
    if wanted:
        if payload.get(wanted) is None:
            raise SystemExit('包里没有 %s（可用: %s）' % (
                wanted, [n for n in sorted(payload.members) if n.endswith(('.bin', '.img'))]))
        return wanted
    for cand in APP_CANDIDATES:
        if payload.get(cand) is not None:
            return cand
    raise SystemExit('包里找不到客户 app 镜像，候选: %s' % (APP_CANDIDATES,))


# ------------------------------------------------------------------ 小工具
def md5f(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def label_of(path):
    """取短标签：尾部 _V03 / _BETA260820 / _751 优先，其次 1.2.3，兜底文件名"""
    base = os.path.splitext(os.path.basename(path.rstrip('\\/')))[0]
    m = re.search(r'[_-](V\d+(?:[._]\d+)*|BETA\w*)$', base, re.IGNORECASE)
    if m:
        t = m.group(1)
        return t.upper() if t.lower().startswith('beta') else t
    m = re.search(r'[_-](\d{3,})$', base)
    if m:
        return m.group(1)
    m = re.search(r'[Vv]?(\d+\.\d+\.\d+(?:\.\d+)?)', base)
    if m:
        return m.group(0) if m.group(0)[0] in 'Vv' else 'V' + m.group(0)
    return re.sub(r'[^A-Za-z0-9._-]', '', base)[-20:] or 'unknown'


def config_text(items):
    """items = [(镜像文件名, 起始地址), ...]"""
    lines = ['[Image_List]', 'Number_of_Images = %d' % len(items)]
    for i, (img, addr) in enumerate(items, 1):
        lines += ['%d_Image_Enable = 1' % i,
                  '%d_Image_Image_ID = 0x%02X' % (i, 0x2F + i),
                  '%d_Image_Path = %s' % (i, img),
                  '%d_Image_Flash_Entry_Address = 0x%08X' % (i, addr),
                  '%d_Image_ID_Name = %d' % (i, i)]
    return '\n'.join(lines) + '\n'


def ensure_ascii(path, what):
    try:
        path.encode('ascii')
        return path
    except UnicodeEncodeError:
        raise SystemExit('%s 必须全 ASCII 路径（FBFMake 是 ANSI 程序，中文路径会弹框卡死）: %s'
                         % (what, path))


# ------------------------------------------------------------------ 主流程
def prepare(src, cache, wanted_app, images_arg=None, no_extra=False):
    """抽镜像 + 解析分区表 -> (镜像名列表, [(名, 地址)], 信息 dict)"""
    p = Payload(src)
    log('装载包来源: %s  (%s)' % (src, p.note))
    pbin = p.get('partition.bin')
    if pbin is None:
        raise SystemExit('装载包里没有 partition.bin')
    entries = parse_partition_bin(pbin)
    sys_part = pick(entries, 'system')
    app_part = pick_app_partition(entries)
    if app_part is None:
        raise SystemExit('分区表里没有 cust / customer_app / user_app 分区')
    app_img = pick_app_image(p, wanted_app)
    raw_fota = p.get('fota.json')
    fota = []
    if raw_fota:
        try:
            fota = json.loads(raw_fota.decode('utf-8', 'replace'))
        except Exception:
            fota = []

    if images_arg:
        # 手工指定清单：完全照给定的来（地址仍从 partition.bin 取）
        images = list(images_arg)
        addr = {}
        for n in images:
            if p.get(n) is None:
                raise SystemExit('装载包里没有 %s（可用: %s）' % (
                    n, sorted(x for x in p.members if x.endswith(('.img', '.bin')))))
            part = pick(entries, os.path.splitext(n)[0])
            if part is None:
                for f in fota:
                    if f.get('image') == n and isinstance(f.get('start'), int):
                        part = dict(name=n, start=f['start'])
                        break
            if part is None:
                raise SystemExit('分区表里找不到 %s 对应的分区，无法确定地址' % n)
            addr[n] = part['start']
    else:
        # 默认清单 = system + 客户 app + 包内 fota.json 声明的其它容器
        # （QDM562 的 ext_gnss 就是这样进来的：它是独立容器(spi 通道)，不像 btlst/btbin 那样在 system 容器里）
        if p.get('system.img') is None:
            raise SystemExit('装载包里没有 system.img')
        images = ['system.img']
        addr = {'system.img': sys_part['start'] if sys_part else 0}
        if app_img not in images:
            images.append(app_img)
            addr[app_img] = app_part['start']
        if not no_extra:
            for f in fota:
                n = f.get('image')
                if not n or n in images or p.get(n) is None:
                    continue
                part = pick(entries, f.get('partition') or os.path.splitext(n)[0])
                a = part['start'] if part else f.get('start')
                if a is None:
                    log('  跳过 fota.json 声明的 %s（分区表与 fota.json 里都没有地址）' % n, 'WARN')
                    continue
                images.append(n)
                addr[n] = a
                log('  fota.json 声明 -> 纳入 config: %s @0x%08X（分区 %s）'
                    % (n, a, part['name'] if part else '(仅 fota.json)'))

    os.makedirs(cache, exist_ok=True)
    for n in images:
        with open(os.path.join(cache, n), 'wb') as f:
            f.write(p.get(n))

    items = [(n, addr[n]) for n in images]

    files = {}
    for n in images:
        fp = os.path.join(cache, n)
        files[n] = (os.path.getsize(fp), md5f(fp))
    info = dict(src=src, note=p.note, part=app_part, sys=sys_part, items=items,
                images=images, files=files)
    log('  分区表: %s=%s  type=%s start=0x%08X size=0x%08X' % (
        app_part['name'], app_img, app_part['type'], app_part['start'], app_part['size']))
    if sys_part:
        log('  system start=0x%08X size=0x%08X' % (sys_part['start'], sys_part['size']))
    fota_txt = p.get('fota.json')
    if fota_txt:
        txt = fota_txt.decode('utf-8', 'replace').replace('\n', ' ').replace('\r', '')
        log('  包内 fota.json: %s' % re.sub(r'\s+', ' ', txt)[:200])
    for n in images:
        fp = os.path.join(cache, n)
        log('  抽出 %-18s %9d B  md5 %s' % (n, os.path.getsize(fp), md5f(fp)))
    return info


def run_direction(work, exe, after_tag, before_tag, after_cache, before_cache, images, timeout):
    """a\\ = after（更新后 / 升级后的状态）, b\\ = before（更新前）；产物 = 把设备从 before 打到 after"""
    for sub in ('a', 'b'):
        d = os.path.join(work, sub)
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d)
    for n in images:
        shutil.copy2(os.path.join(after_cache, n), os.path.join(work, 'a', n))
        shutil.copy2(os.path.join(before_cache, n), os.path.join(work, 'b', n))
    log('  a\\ [更新后/after  %s]: %s' % (after_tag, sorted(os.listdir(os.path.join(work, 'a')))))
    log('  b\\ [更新前/before %s]: %s' % (before_tag, sorted(os.listdir(os.path.join(work, 'b')))))

    cmd = [exe, '-f', 'config', '-d', '0x10000', '-a', 'a', '-b', 'b', '-o', 'fbf_dfota.bin', '-q']
    log('  执行: %s' % ' '.join(cmd))
    # 原厂 bat 开头的两行清理不能省：FBFMake 不会覆盖已存在的输出，
    # 不删就会把上一次（另一个方向）的包原样留下 → 两个方向产物 md5 相同。
    for junk in (os.path.join(work, 'fbf_dfota.bin'),
                 os.path.join(work, 'a', 'patchfolder'),
                 os.path.join(work, 'fbf.bin')):
        if os.path.isdir(junk):
            shutil.rmtree(junk, ignore_errors=True)
        elif os.path.exists(junk):
            os.remove(junk)
    t0 = time.time()
    proc = subprocess.Popen(cmd, cwd=work, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        raw, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        dlgs = read_tool_dialogs(proc.pid)
        proc.kill()
        proc.communicate()
        msg = '超过 %ss 未结束（耗时 %.0fs）' % (timeout, time.time() - t0)
        if dlgs:
            msg += '\n  工具弹窗: ' + ' | '.join(dlgs)
        raise RuntimeError(msg)

    text = (raw or b'').decode('gbk', 'replace')       # 工具输出是 GBK
    lines = [l for l in text.splitlines() if l.strip()]
    for l in lines[:3]:
        log('    [FBF] %s' % l)
    for l in lines[-6:]:
        log('    [FBF] %s' % l)
    if 'DoFBFMakeforBSDiffSplitImage failed' in text:
        raise RuntimeError('FBFMake 报 DoFBFMakeforBSDiffSplitImage failed'
                           '（blf 里声明的镜像在 a\\b 里凑不齐 / config 地址不对）: %s'
                           % (lines[-1] if lines else ''))
    if 'successfully' in text:
        log('    FBFMake 报告 successfully')
    malformed = [l for l in lines if 'Parsing Blf file' in l]
    for l in malformed:
        log('    %s' % l.strip())
        if os.path.normcase(os.path.dirname(l.split(':', 1)[1].strip())) != os.path.normcase(work):
            raise RuntimeError('FBFMake 读的不是本目录的 config！(config 必须与 exe 同目录)')
    dlgs = read_tool_dialogs(proc.pid)
    if dlgs:
        proc.kill()
        raise RuntimeError('工具弹窗: %s' % ' | '.join(dlgs))
    out = os.path.join(work, 'fbf_dfota.bin')
    if not os.path.exists(out) or os.path.getsize(out) == 0:
        raise RuntimeError('没有产物 fbf_dfota.bin（看上面日志尾部与 DoFBFMakeforBSDiffSplitImage）')
    log('  用时 %.1fs，产物 %d B' % (time.time() - t0, os.path.getsize(out)))
    return out


def verify(path, items):
    d = open(path, 'rb').read()
    if d[:11] != b'Marvell_FBF':
        log('产物头不是 Marvell_FBF: %r' % d[:11], 'WARN')
    ok = True
    for name, addr in items:
        n = d.count(struct.pack('<I', addr))
        if n == 0:
            ok = False
        log('  校验 0x%08X (%s) 出现 %d 次' % (addr, name, n))
    if not ok:
        log('有地址没在产物里出现，请人工确认', 'WARN')
    return ok


def emit(src, dst, results, seen):
    """拷贝产物 + 两个方向互相校验（md5 相同 = 第二次没重算）"""
    shutil.copy2(src, dst)
    size, h = os.path.getsize(dst), md5f(dst)
    log('  ==> %s  (%d B, md5 %s)' % (dst, size, h))
    if h in seen:
        raise RuntimeError('两个方向的产物 md5 相同(%s) —— 第二次没真正重算，'
                           '通常是工作目录里旧的 fbf_dfota.bin 没删掉' % h)
    seen[h] = dst
    results.append(dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--old', required=True, help='旧版本包 zip 或目录')
    ap.add_argument('--new', required=True, help='新版本包 zip 或目录')
    ap.add_argument('-o', '--out', default=None, help='输出目录（默认 <旧包所在目录>\\diff_out）')
    ap.add_argument('--exe', default=os.path.join(TOOL_DIR, FBFMAKE))
    ap.add_argument('--app', default=None, help='客户 app 镜像文件名（默认自动: customer_app.bin -> user_app.bin ...）')
    ap.add_argument('--images', default=None,
                    help='手工指定 config 的镜像清单（逗号分隔）。默认 = system.img + 客户 app + 包内 fota.json 声明的其它容器')
    ap.add_argument('--no-extra', action='store_true', help='不纳入 fota.json 声明的额外容器（如 ext_gnss）')
    ap.add_argument('--prefix', default='', help='产物文件名前缀，如 QDM562')
    ap.add_argument('--labels', default=None, help='手工指定新旧标签: "旧,新"')
    ap.add_argument('--only', choices=['up', 'rb', 'both'], default='both')
    ap.add_argument('--naming', choices=['pair', 'target'], default='pair',
                    help='产物命名: pair=diff_upgrade_A_to_B.bin(默认); target=<目标版本标签>.bin（现场习惯，如 7FF.bin）')
    ap.add_argument('--timeout', type=int, default=600, help='单次工具调用超时秒数（默认 600）')
    args = ap.parse_args()

    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.old)) or '.', 'diff_out')
    out = ensure_ascii(os.path.abspath(out), '输出目录')
    work = ensure_ascii(os.path.join(out, 'diff_work'), '工作目录')
    if not os.path.exists(args.exe):
        raise SystemExit('找不到 FBFMake: %s' % args.exe)
    ensure_ascii(os.path.abspath(args.exe), '工具路径')

    old_tag, new_tag = (args.labels.split(',') if args.labels
                        else (label_of(args.old), label_of(args.new)))
    if old_tag == new_tag:
        log('新旧标签相同(%s)，加 _OLD/_NEW 区分以免产物重名' % old_tag, 'WARN')
        old_tag, new_tag = old_tag + '_OLD', new_tag + '_NEW'

    os.makedirs(out, exist_ok=True)
    log('旧: %s  (标签 %s)' % (args.old, old_tag))
    log('新: %s  (标签 %s)' % (args.new, new_tag))
    log('输出: %s' % out)

    log('=' * 66)
    log('抽镜像 / 解析分区表')
    images_arg = [x.strip() for x in args.images.split(',') if x.strip()] if args.images else None
    old_info = prepare(args.old, os.path.join(out, '_src', old_tag), args.app, images_arg, args.no_extra)
    new_info = prepare(args.new, os.path.join(out, '_src', new_tag), args.app, images_arg, args.no_extra)

    if old_info['images'] != new_info['images']:
        raise SystemExit('两个包的镜像集合不一致: %s vs %s' % (old_info['images'], new_info['images']))
    images = new_info['images']
    if old_info['part']['start'] != new_info['part']['start']:
        log('!! 两个包 %s 起始地址不同: 0x%08X vs 0x%08X（是否换过分区表？）'
            % (new_info['part']['name'], old_info['part']['start'], new_info['part']['start']), 'WARN')

    items = new_info['items']
    log('=' * 66)
    log('config（%d 项，地址取自 partition.bin）' % len(items))
    cfg = config_text(items)
    for l in cfg.rstrip().splitlines():
        log('    ' + l)

    # 工作目录：exe / config / a\ / b\ 同目录
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    exe_local = os.path.join(work, os.path.basename(args.exe))
    shutil.copy2(args.exe, exe_local)
    with open(os.path.join(work, 'config'), 'w', encoding='utf-8', newline='\r\n') as f:
        f.write(cfg)
    bat_src = os.path.join(os.path.dirname(args.exe), 'fbfmake_fast.bat')
    if os.path.exists(bat_src):
        shutil.copy2(bat_src, os.path.join(work, 'fbfmake_fast.bat'))
    log('工作目录 %s （exe/config/a\\/b\\ 同目录）' % work)

    results = []
    seen = {}
    prefix = (args.prefix + '_') if args.prefix else ''
    new_cache = os.path.join(out, '_src', new_tag)
    old_cache = os.path.join(out, '_src', old_tag)
    if args.only in ('up', 'both'):
        log('=' * 66)
        log('升级包: %s -> %s   (a\\=新版 %s, b\\=旧版 %s)' % (old_tag, new_tag, new_tag, old_tag))
        f = run_direction(work, exe_local, new_tag, old_tag, new_cache, old_cache,
                          images, args.timeout)
        verify(f, items)
        dst = os.path.join(out, ('%s%s.bin' % (prefix, new_tag)) if args.naming == 'target'
                           else ('%sdiff_upgrade_%s_to_%s.bin' % (prefix, old_tag, new_tag)))
        emit(f, dst, results, seen)
    if args.only in ('rb', 'both'):
        log('=' * 66)
        log('回滚包: %s -> %s   (a\\=旧版 %s, b\\=新版 %s)' % (new_tag, old_tag, old_tag, new_tag))
        f = run_direction(work, exe_local, old_tag, new_tag, old_cache, new_cache,
                          images, args.timeout)
        verify(f, items)
        dst = os.path.join(out, ('%s%s.bin' % (prefix, old_tag)) if args.naming == 'target'
                           else ('%sdiff_rollback_%s_to_%s.bin' % (prefix, new_tag, old_tag)))
        emit(f, dst, results, seen)

    # 做包记录
    rec = ['做包记录（make_diff_fbfmake.py）  %s' % time.strftime('%Y-%m-%d %H:%M:%S'),
           '=' * 66,
           '工具: %s' % args.exe,
           '命令: %s -f config -d 0x10000 -a a -b b -o fbf_dfota.bin -q' % os.path.basename(args.exe),
           '',
           '旧版本包: %s   (标签 %s)' % (args.old, old_tag),
           '新版本包: %s   (标签 %s)' % (args.new, new_tag),
           '']
    for info in (old_info, new_info):
        rec.append('%s  (%s)' % (info['src'], info['note']))
        for n in info['images']:
            size, md5 = info['files'][n]
            rec.append('    %-18s %9d B  md5 %s' % (n, size, md5))
        rec.append('    客户 app 分区: %s start=0x%08X size=0x%08X' % (
            info['part']['name'], info['part']['start'], info['part']['size']))
        if info['sys']:
            rec.append('    system 起始: 0x%08X size=0x%08X'
                       % (info['sys']['start'], info['sys']['size']))
        rec.append('')
    rec.append('config:')
    rec.append(cfg)
    rec.append('产物:')
    for r in results:
        rec.append('  %s  %d B  md5 %s' % (os.path.basename(r), os.path.getsize(r), md5f(r)))
    rec.append('')
    rec.append('注意: system.img 是容器镜像(cp/dsp/rf/btlst/btbin 内容都在里面), 不单列子分区;')
    rec.append('      ext_gnss 是独立容器(spi 通道), 由包内 fota.json 声明纳入 config;')
    rec.append('      若某容器只在一个包里存在, 会因两侧镜像集合不一致而报错退出。')
    with open(os.path.join(out, '做包记录.txt'), 'w', encoding='utf-8-sig') as f:
        f.write('\n'.join(rec) + '\n')

    print()
    print('产物:')
    for r in results:
        print('  %s' % r)
    print('记录: %s' % os.path.join(out, '做包记录.txt'))


if __name__ == '__main__':
    main()
