#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_config.py —— 从 aboot 烧录包(zip/目录)自动生成 FBFMake 差分/全量包用的 config

原理：
  1. 从包里取出 partition.bin（BTPA 分区表二进制），解析出每个分区的
     name / type / start / size / vstart / vsize
  2. 建立 flash 通道(spi/qspi...) -> 顶层分区 -> 子分区 的层级关系
  3. FOTA 候选 = 顶层(父是 flash 通道)且 type in (part, cust) 的分区
     即：容器型分区(part) 和 客户分区(cust) —— raw/ubi 分区不参与 FOTA
  4. 用候选分区名去包里找镜像文件 (<name>.img / <name>.bin / <name>.pkg，
     外加别名 user_app.bin / app.bin -> customer_app)
  5. 按 system -> 客户分区(cust) -> 其他容器分区 的顺序输出 config

用法:
  python make_config.py <包.zip|目录> [-o 输出config] [--include a,b] [--exclude c]
  python make_config.py <包.zip> --list          # 只列分区表和镜像清单
  python make_config.py <包.zip> --diff <config> # 与已有 config 对比
"""
import argparse
import io
import json
import os
import struct
import sys
import zipfile

ENTRY_SIZE = 68          # BTPA 每条记录 68 字节
NAME_LEN = 32
TYPE_LEN = 16

ALIASES = {              # 镜像文件名 -> 分区名（不同 SDK 的命名差异）
    'user_app.bin': 'customer_app',
    'user_app.img': 'customer_app',
    'app.bin': 'customer_app',
    'cusapp.bin': 'customer_app',
    'btbin.bin': 'btbin',
    'btlst.bin': 'btlst',
    'rf.bin': 'rfbin',
}


class Src(object):
    """把 zip / 目录 / 外层zip包内层zip 统一成 {name: bytes}"""

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
        self._load_zip(path, 0)

    def _load_zip(self, path, depth):
        z = zipfile.ZipFile(path)
        names = [i.filename for i in z.infolist()]
        # 本层没有 partition.bin 时，钻进"内含 partition.bin"的那个嵌套 zip
        # （QDM568 版本包里同时有 ML307C_APP.zip 和 ML307C_APP_Source.zip，只能挑前者）
        if depth < 3 and 'partition.bin' not in names:
            cands = [n for n in names if n.lower().endswith('.zip') and 'source' not in n.lower()]
            for cand in cands:
                try:
                    zz = zipfile.ZipFile(io.BytesIO(z.read(cand)))
                    if any(os.path.basename(x) == 'partition.bin' for x in zz.namelist()):
                        self.members = {}
                        self._load_zip(io.BytesIO(z.read(cand)), depth + 1)
                        self.note = '外层包 -> 内层 %s' % cand
                        return
                except Exception:
                    continue
        for n in names:
            if n.endswith('/'):
                continue
            self.members[n] = z.read(n)
        self.note = self.note or 'zip 直读'

    def get(self, name):
        return self.members.get(name)

    def images(self):
        out = []
        for n in sorted(self.members):
            low = n.lower()
            if low.endswith(('.img', '.bin', '.pkg')):
                out.append((n, len(self.members[n])))
        return out


def parse_partition_bin(data):
    """BTPA 分区表: 8 字节头 + N 条 68 字节记录"""
    if data[:4] != b'BTPA':
        raise ValueError('不是 BTPA 分区表 (magic=%r)' % data[:4])
    entries = []
    off = 8
    while off + ENTRY_SIZE <= len(data):
        rec = data[off:off + ENTRY_SIZE]
        name = rec[0:NAME_LEN].split(b'\x00')[0].decode('ascii', 'replace')
        ptype = rec[NAME_LEN:NAME_LEN + TYPE_LEN].split(b'\x00')[0].decode('ascii', 'replace')
        start, size, vstart, vsize = struct.unpack('<IIII', rec[48:64])
        if not name:
            off += ENTRY_SIZE
            continue
        entries.append(dict(name=name, type=ptype, start=start, size=size,
                            vstart=vstart, vsize=vsize))
        off += ENTRY_SIZE
    return entries


def build_tree(entries):
    """标记 flash 通道 / 父分区 / 是否顶层"""
    channel = None
    for e in entries:
        e['channel'] = None
        e['parent'] = None
        if e['type'] == 'flash':
            channel = e['name']
            e['channel'] = e['name']
            continue
        e['channel'] = channel

    for e in entries:
        if e['type'] == 'flash':
            continue
        best = None
        for q in entries:
            if q is e or q['type'] not in ('part', 'cust'):
                continue
            if q['channel'] != e['channel']:
                continue
            if q['start'] <= e['start'] < q['start'] + q['size']:
                if best is None or q['size'] < best['size']:
                    best = q
        e['parent'] = best['name'] if best else e['channel']


def fota_candidates(entries):
    """顶层 + part/cust = 可做 FOTA 的分区"""
    out = []
    for e in entries:
        if e['type'] in ('part', 'cust') and e['parent'] == e['channel']:
            out.append(e)
    return out


def rank(part):
    if part['name'] == 'system':
        return 0
    if part['type'] == 'cust':
        return 1
    return 2


def match_image(src, part_name):
    """在包里找这个分区对应的镜像文件"""
    wanted = [part_name + '.img', part_name + '.bin', part_name + '.pkg']
    for n in src.members:
        if n.lower() in wanted:
            return n
    for fname, pname in ALIASES.items():
        if pname == part_name and fname in src.members:
            return fname
    return None


def make_config(src, include=None, exclude=None, app_only=False):
    pbin = src.get('partition.bin')
    if pbin is None:
        raise SystemExit('包里没有 partition.bin，无法解析分区表')
    entries = parse_partition_bin(pbin)
    build_tree(entries)

    fota_json = []
    raw = src.get('fota.json')
    if raw:
        try:
            fota_json = json.loads(raw.decode('utf-8', 'replace'))
        except Exception:
            fota_json = []

    items = []
    skipped = []
    for e in sorted(fota_candidates(entries), key=rank):
        if include and e['name'] not in include:
            continue
        if exclude and e['name'] in exclude:
            continue
        img = match_image(src, e['name'])
        if not img:
            skipped.append(e)
            continue
        items.append(dict(part=e['name'], ptype=e['type'], start=e['start'],
                          size=e['size'], image=img,
                          imgsize=len(src.members[img]),
                          in_fota_json=any(x.get('image') == img for x in fota_json)))

    if app_only:
        keep = [it for it in items if it['ptype'] == 'cust']
        items = keep or items[:1]

    lines = ['[Image_List]', 'Number_of_Images = %d' % len(items)]
    for i, it in enumerate(items, 1):
        lines.append('%d_Image_Enable = 1' % i)
        lines.append('%d_Image_Image_ID = 0x%02X' % (i, 0x2F + i))
        lines.append('%d_Image_Path = %s' % (i, it['image']))
        lines.append('%d_Image_Flash_Entry_Address = 0x%08X' % (i, it['start']))
        lines.append('%d_Image_ID_Name = %d' % (i, i))
    return '\n'.join(lines) + '\n', items, skipped, entries, fota_json


def parse_config_text(text):
    """读回一个 config，返回 [(image, addr)]"""
    out = []
    cur = {}
    for line in text.splitlines():
        line = line.strip()
        if '=' not in line:
            continue
        k, v = line.split('=', 1)
        k, v = k.strip(), v.strip()
        if k.endswith('_Image_Path'):
            cur['image'] = v
        elif k.endswith('_Image_Flash_Entry_Address'):
            cur['addr'] = v
            out.append((cur.get('image'), cur.get('addr')))
            cur = {}
    return out


def fmt_addr(s):
    try:
        return '0x%08X' % int(s, 16)
    except Exception:
        return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src', help='烧录包 zip 或目录')
    ap.add_argument('-o', '--out', default=None, help='输出 config 路径')
    ap.add_argument('--include', default=None, help='只包含这些分区(逗号分隔)')
    ap.add_argument('--exclude', default=None, help='排除这些分区(逗号分隔)')
    ap.add_argument('--list', action='store_true', help='只列分区表/镜像清单')
    ap.add_argument('--app-only', action='store_true',
                    help='只输出客户 app 分区(cust)一项，即 app 整包/FBFMake 用的 config')
    ap.add_argument('--diff', default=None, help='与已有 config 对比')
    args = ap.parse_args()

    src = Src(args.src)
    print('来源: %s  (%s)' % (args.src, src.note))

    if args.list:
        entries = parse_partition_bin(src.get('partition.bin'))
        build_tree(entries)
        print('\n%-18s %-6s %-12s %-10s %-12s %s' % ('Name', 'Type', 'Start', 'Size', 'vStart', '父分区'))
        for e in entries:
            print('%-18s %-6s %-12s %-10s %-12s %s' % (
                e['name'], e['type'], '0x%08X' % e['start'], '0x%08X' % e['size'],
                '0x%08X' % e['vstart'], e['parent']))
        print('\n镜像文件:')
        for n, s in src.images():
            print('  %-24s %d' % (n, s))
        return

    include = set(args.include.split(',')) if args.include else None
    exclude = set(args.exclude.split(',')) if args.exclude else None
    text, items, skipped, entries, fota_json = make_config(src, include, exclude, args.app_only)

    print('\n== FOTA 候选（顶层 part/cust 分区）==')
    for e in sorted(fota_candidates(entries), key=rank):
        img = match_image(src, e['name'])
        mark = 'OK ' if img else '-- '
        print('  %s%-14s %-5s start=0x%08X size=0x%08X  -> %s' % (
            mark, e['name'], e['type'], e['start'], e['size'], img or '(包里没有对应镜像)'))
    if fota_json:
        print('\n== 包内 fota.json 声明 ==')
        for x in fota_json:
            _img = x.get('image', '(未写)')
            _part = x.get('partition', '?')
            _st = x.get('start')
            _st_txt = ('%d (0x%X)' % (_st, _st)) if isinstance(_st, int) else '(未写)'
            print('  image=%-14s partition=%-12s start=%s' % (_img, _part, _st_txt))
    print('\n== 生成的 config ==')
    print(text)

    if args.diff:
        old = open(args.diff, 'r', encoding='utf-8-sig').read()
        a, b = parse_config_text(old), parse_config_text(text)
        print('== 与 %s 对比 ==' % args.diff)
        ok = True
        for i in range(max(len(a), len(b))):
            x = a[i] if i < len(a) else None
            y = b[i] if i < len(b) else None
            same = x and y and x[0] == y[0] and fmt_addr(x[1]) == fmt_addr(y[1])
            ok = ok and same
            print('  %d: 现有 %-22s %-12s | 生成 %-22s %-12s %s' % (
                i + 1,
                x[0] if x else '-', fmt_addr(x[1]) if x else '-',
                y[0] if y else '-', fmt_addr(y[1]) if y else '-',
                'OK' if same else '<<< 不一致'))
        print('结论:', '完全一致' if ok and len(a) == len(b) else '存在差异')

    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(text)
        print('已写出:', args.out)


if __name__ == '__main__':
    main()
