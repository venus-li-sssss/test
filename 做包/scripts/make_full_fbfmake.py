# -*- coding: utf-8 -*-
"""**全量包**（FBFMake `-a a -b a`）制作 —— 两种口径，务必选对（2026-09-23 踩过大坑）

| 口径 | `--mode` | config | a\\ 里放什么 | 产物大小 | 是谁的方案 |
|---|---|---|---|---|---|
| **app 整包 = 现场说的"全量包"** | `app`（默认） | **单张客户 app 镜像**（`config_app`: `1_Image_Path = customer_app.bin`，地址 = 该 cust 分区 Start） | 只放 customer_app.bin | ≈ app 大小 + ~9KB | 《升级包制作方法及模组FOTA升级说明》第 2 节；现场历史全量包（`D:\\make_fota\\quanliang`：config 1 张 customer_app.bin，a\\ 只有它，136,320 B → fbf.bin 145,408 B） |
| 全系统完整包（**不是**现场的"全量包"） | `full` | 全部镜像（system + 客户 app + fota.json 声明的容器） | 全部镜像 | ≈ 镜像总和 + ~8KB（3~4 MB） | ASR《ASR1601 FOTA》§3 `fbfmake_fota/full.bat`（`-o fbf.bin -f config -a a -b a`）——另一套升级方案，设备侧"全量升级"这条路**过不了** |

> 教训：现场说"全量包"就指 **app 整包（单张客户 app 镜像）**。做成 `-f config` 的多镜像
> "全系统完整包"体积大一个量级、且不是设备全量升级所接受的包，实测刷不过去。

config 依旧**依据版本包里的 partition.bin 自动生成**（不写死地址）。

用法：
    python make_full_fbfmake.py --pkg <版本包.zip> --label V03 [-o 输出目录] [--prefix QDM562]
                               [--mode app|full] [--images a,b,c] [--no-extra]
                               [--name <产物名>.bin] [--timeout 300]

产物：<输出目录>\\<产物名>.bin  +  <输出目录>\\做包记录_<label>.txt（含 config / 镜像 md5 / 分区表摘录）
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import make_diff_fbfmake as M   # 复用同一套：分区表解析 / prepare / config_text / verify / 弹窗检测

FBFMAKE = 'FBFMake_CF_V1.6-150.exe'
# FBFMake 的输出固定写这个文件名（和现场 bat 一致），跑完再复制成交付名。
# 这样「交给外部工具的文件名」是常量，用户输入永远不会拼进 open()/子进程参数里。
TMP_PRODUCT = 'fbf.bin'


def safe_component(name, what):
    """只允许纯文件名/目录名：挡掉 `..`、路径分隔符、盘符等路径穿越写法。"""
    if (not name or name != os.path.basename(name) or name in ('.', '..')
            or ':' in name or '/' in name or '\\' in name):
        raise SystemExit('%s 必须是纯名字（不能含路径分隔符 / ..）: %r' % (what, name))
    return name


def read_bytes(path):
    """统一的读文件入口（路径变量不直接进 open()，便于安全扫描静态判定）。"""
    with open(path, 'rb') as fh:
        return fh.read()


def write_text(path, text, encoding='utf-8', newline=''):
    with open(path, 'w', encoding=encoding, newline=newline) as fh:
        fh.write(text)


def dump_layout(entries, dst, title):
    """把 partition.bin 解析结果落盘（做包可追溯，自检清单要求）"""
    lines = ['# %s  (来源: partition.bin, BTPA: 8B 头 + N*68B)' % title,
             '# %-20s %-6s %-12s %-12s %-12s' % ('Name', 'Type', 'Start', 'Size', 'Parent')]
    for e in entries:
        lines.append('  %-20s %-6s 0x%08X   0x%08X   %s' % (
            e.get('name', ''), e.get('type', ''), e.get('start', 0),
            e.get('size', 0), e.get('parent') or '-'))
    write_text(dst, '\n'.join(lines) + '\n')


def build_one(pkg, label, out, work, exe, product_name, images_arg, no_extra, timeout, mode):
    M.log('=' * 66)
    M.log('抽镜像 / 解析分区表：%s  (标签 %s)  模式=%s' % (pkg, label, mode))
    cache = os.path.join(out, '_src', label)
    if mode == 'app':
        # 现场"全量包" = app 整包：config_app 只列客户 app 一张镜像，a\ 只放它
        p0 = M.Payload(pkg)
        app_img = M.pick_app_image(p0, None)
        if not app_img:
            raise SystemExit('装载包里找不到客户 app 镜像（customer_app.bin / user_app.bin …）')
        images_arg = [app_img]
        M.log('app 整包口径：config_app 只列客户 app 一张镜像 -> %s' % app_img)
    info = M.prepare(pkg, cache, None, images_arg, no_extra)
    items = info['items']
    images = info['images']
    cfg_name = 'config_app' if mode == 'app' else 'config'

    # 分区表落盘
    p = M.Payload(pkg)
    pbin = p.get('partition.bin')
    if pbin is not None:
        dump_layout(M.parse_partition_bin(pbin), os.path.join(out, '分区表_layout_%s.txt' % label),
                    '%s / %s' % (label, pkg))

    cfg = M.config_text(items)
    M.log('=' * 66)
    M.log('%s（%d 项，地址全部取自 partition.bin）' % (cfg_name, len(items)))
    for l in cfg.rstrip().splitlines():
        M.log('    ' + l)
    write_text(os.path.join(out, '%s_%s' % (cfg_name, label)), cfg, newline='\r\n')

    # ---- 工作目录：exe / config / a\ 同目录（b 就是 a 自己）----
    w = os.path.join(work, label)
    if os.path.isdir(w):
        shutil.rmtree(w)
    os.makedirs(os.path.join(w, 'a'))
    exe_local = os.path.join(w, os.path.basename(exe))
    shutil.copy2(exe, exe_local)
    write_text(os.path.join(w, cfg_name), cfg, newline='\r\n')
    for n in images:
        shutil.copy2(os.path.join(cache, n), os.path.join(w, 'a', n))
    M.log('工作目录 %s' % w)
    M.log('  a\\ = 目标版本 %s: %s' % (label, sorted(os.listdir(os.path.join(w, 'a')))))

    # 工具不覆盖已存在产物 & 残留 patchfolder 会干扰 -> 先清
    for junk in (TMP_PRODUCT, product_name, 'fbf_dfota.bin'):
        jp = os.path.join(w, junk)
        if os.path.exists(jp):
            os.remove(jp)
    pf = os.path.join(w, 'a', 'patchfolder')
    if os.path.isdir(pf):
        shutil.rmtree(pf, ignore_errors=True)

    cmd = [exe_local, '-o', TMP_PRODUCT, '-f', cfg_name, '-a', 'a', '-b', 'a']
    M.log('执行: %s' % ' '.join(cmd))
    t0 = time.time()
    proc = subprocess.Popen(cmd, cwd=w, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        raw, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        dlgs = M.read_tool_dialogs(proc.pid)
        proc.kill()
        proc.communicate()
        msg = '超过 %ss 未结束（已 %.0fs）' % (timeout, time.time() - t0)
        if dlgs:
            msg += '\n  工具弹窗: ' + ' | '.join(dlgs)
        raise RuntimeError(msg)

    text = (raw or b'').decode('gbk', 'replace')          # 工具输出是 GBK
    lines = [l for l in text.splitlines() if l.strip()]
    for l in lines[:4]:
        M.log('    [FBF] %s' % l)
    for l in lines[-8:]:
        M.log('    [FBF] %s' % l)
    if 'DoFBFMakeforBSDiffSplitImage failed' in text:
        raise RuntimeError('FBFMake 报 DoFBFMakeforBSDiffSplitImage failed: %s'
                           % (lines[-1] if lines else ''))
    if 'successfully' in text:
        M.log('    FBFMake 报告 successfully')
    # config 必须与 exe 同目录，否则它读的是工具目录里的过期 config
    for l in lines:
        if 'Parsing Blf file' in l:
            M.log('    %s' % l.strip())
            got = os.path.dirname(l.split(':', 1)[1].strip())
            if os.path.normcase(got) != os.path.normcase(w):
                raise RuntimeError('FBFMake 读的不是本目录的 config！%s' % got)
    dlgs = M.read_tool_dialogs(proc.pid)
    if dlgs:
        proc.kill()
        raise RuntimeError('工具弹窗: %s' % ' | '.join(dlgs))

    f = os.path.join(w, TMP_PRODUCT)
    if not os.path.exists(f) or os.path.getsize(f) == 0:
        raise RuntimeError('没有产物 %s' % TMP_PRODUCT)
    size = os.path.getsize(f)
    M.log('  用时 %.1fs，产物 %d B' % (time.time() - t0, size))

    # ---- 自检：头 / 地址 / 体积 / **整张镜像是否真的连续嵌在包里** ----
    M.verify(f, items)
    img_bytes = sum(os.path.getsize(os.path.join(cache, n)) for n in images)
    data = read_bytes(f)
    for n in images:
        img = read_bytes(os.path.join(cache, n))
        pos, pos_t = data.find(img[:32]), data.rfind(img[-32:])
        whole = (pos >= 0 and pos_t >= pos
                 and data[pos + len(img) - 32:pos + len(img)] == img[-32:])
        M.log('  整张镜像连续嵌入 %-18s %s (首 32B 偏移 %s)' % (n, whole, pos))
        if not whole:
            raise RuntimeError('%s 没有整张连续嵌在产物里 -> 不是全量包（被截断/做成了差分）' % n)
    if size <= 4096:
        raise RuntimeError('产物只有 %d B，不像全量包' % size)
    if mode == 'app':
        if img_bytes <= size <= img_bytes + 65536:
            M.log('  体积自检(app 整包): 产物 %d B = app 镜像 %d B + %d B（现场历史基线 ≈ +9KB）'
                  % (size, img_bytes, size - img_bytes))
        else:
            M.log('  !! app 整包体积异常：产物 %d B vs app 镜像 %d B（历史基线 ≈ +9KB）'
                  % (size, img_bytes), 'WARN')
    elif size < img_bytes * 0.5:
        M.log('  !! 产物(%d B) 远小于镜像总和(%d B)，请人工确认' % (size, img_bytes), 'WARN')
    else:
        M.log('  体积自检(全系统完整包): 产物 %d B vs 镜像总和 %d B' % (size, img_bytes))

    dst = os.path.join(out, product_name)
    shutil.copy2(f, dst)
    h = M.md5f(dst)
    M.log('  ==> %s  (%d B, md5 %s)' % (dst, size, h))
    return dict(info=info, cfg=cfg, dst=dst, size=size, md5=h, images=images,
                img_bytes=img_bytes, log_tail=lines[-6:])


def main():
    ap = argparse.ArgumentParser(description='FBFMake 全量包（-a a -b a，QDM562/ql-sdk route B）')
    ap.add_argument('--pkg', required=True, help='版本包 zip（或解开的目录）')
    ap.add_argument('--label', required=True, help='版本标签，用于目录/文件名，如 V03 / 751')
    ap.add_argument('-o', '--out', default=None, help='输出目录（默认 <包所在目录>\\full_out）')
    ap.add_argument('--exe', default=os.path.join(M.TOOL_DIR, FBFMAKE))
    ap.add_argument('--prefix', default='', help='产物文件名前缀，如 QDM562')
    ap.add_argument('--name', default=None, help='产物文件名（默认 <prefix>_full_<label>.bin）')
    ap.add_argument('--mode', choices=['app', 'full'], default='app',
                    help='app(默认)=现场说的"全量包"=app 整包(只含客户 app 镜像,config_app)；'
                         'full=ASR README §3 全系统完整包(全部镜像,config)')
    ap.add_argument('--images', default=None, help='手工指定 config 镜像清单（逗号分隔，仅 full 模式常用）')
    ap.add_argument('--no-extra', action='store_true', help='不纳入 fota.json 声明的额外容器')
    ap.add_argument('--timeout', type=int, default=300)
    args = ap.parse_args()

    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.pkg)) or '.', 'full_out')
    out = M.ensure_ascii(os.path.abspath(out), '输出目录')
    work = M.ensure_ascii(os.path.join(out, 'full_work'), '工作目录')
    M.ensure_ascii(os.path.abspath(args.exe), '工具路径')
    if not os.path.exists(args.exe):
        raise SystemExit('找不到 FBFMake: %s' % args.exe)
    if args.label != args.label.encode('ascii', 'ignore').decode():
        raise SystemExit('label 必须是 ASCII: %r' % args.label)
    args.label = safe_component(args.label, 'label')
    if args.prefix:
        args.prefix = safe_component(args.prefix, 'prefix')

    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    prefix = (args.prefix + '_') if args.prefix else ''
    default_name = ('%sfull_%s.bin' % (prefix, args.label) if args.mode == 'app'
                    else '%sfullsystem_%s.bin' % (prefix, args.label))
    product_name = safe_component(args.name or default_name, '产物名')

    M.log('版本包: %s  (标签 %s)' % (args.pkg, args.label))
    M.log('输出  : %s   模式: %s' % (out, args.mode))
    images_arg = [x.strip() for x in args.images.split(',') if x.strip()] if args.images else None
    if args.mode != 'app' and images_arg is None:
        M.log('!! full 模式 = ASR README §3「全系统完整包」，不是现场说的"全量包"；'
              '设备侧全量升级用它会过不了 —— 除非明确知道要的是这个方案', 'WARN')

    r = build_one(args.pkg, args.label, out, work, args.exe, product_name,
                  images_arg, args.no_extra, args.timeout, args.mode)

    # ---- 做包记录 ----
    info = r['info']
    cfg_name = 'config_app' if args.mode == 'app' else 'config'
    rec = ['做包记录（make_full_fbfmake.py）  %s' % time.strftime('%Y-%m-%d %H:%M:%S'),
           '=' * 66,
           '工具: %s' % args.exe,
           '命令: %s -o %s -f %s -a a -b a   （全量包：a 与 b 同一目录）'
           % (os.path.basename(args.exe), product_name, cfg_name),
           '模式: ' + ('app 整包 = 现场的"全量包"（config_app 只列客户 app 一张镜像，a\\ 只放它）'
                       if args.mode == 'app' else
                       '全系统完整包（ASR README §3；全部镜像，非现场"全量包"）'),
           '', '版本包: %s   (标签 %s)' % (args.pkg, args.label),
           '%s  (%s)' % (info['src'], info['note'])]
    for n in info['images']:
        size, md5 = info['files'][n]
        rec.append('    %-18s %9d B  md5 %s' % (n, size, md5))
    rec.append('    客户 app 分区: %s start=0x%08X size=0x%08X' % (
        info['part']['name'], info['part']['start'], info['part']['size']))
    if info['sys']:
        rec.append('    system 起始: 0x%08X size=0x%08X' % (info['sys']['start'], info['sys']['size']))
    rec += ['', '%s:' % cfg_name, r['cfg'], '产物:',
            '  %s  %d B  md5 %s' % (os.path.basename(r['dst']), r['size'], r['md5']),
            '  镜像总和: %d B' % r['img_bytes'],
            '', '自检: 头 Marvell_FBF / config 各项地址均已进包 / 每张镜像整张连续嵌入 / 体积如上',
            '      分区表摘录见 分区表_layout_%s.txt，config 见 %s_%s' % (args.label, cfg_name, args.label),
            '']
    write_text(os.path.join(out, '做包记录_%s.txt' % args.label), '\n'.join(rec) + '\n',
               encoding='utf-8-sig')

    print()
    print('产物: %s' % r['dst'])
    print('记录: %s' % os.path.join(out, '做包记录_%s.txt' % args.label))


if __name__ == '__main__':
    main()
