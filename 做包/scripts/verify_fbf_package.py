# -*- coding: utf-8 -*-
"""独立自检 FBFMake 产物（不靠工具日志）：头 / 地址 / **整张镜像是否真的连续嵌在包里**。

为什么需要它：FBFMake 报 `successfully` 不等于产物对（它不覆盖旧文件、参数被静默忽略也会"成功"）。
差分包与全量包的最硬差别就是——**全量包里应该能看到整张镜像连续出现**（工具日志里的
`image->length` 就是整张大小），差分包里只有变化的块。

顺带能回答两个常被问错的问题：
  * "这个包挑不挑设备当前版本？"  —— FBF 头里**没有任何版本号/产品名**，只有 写入地址/长度/校验，
    所以整包（整张镜像嵌入）本质是"把这个镜像写到这个地址"，与设备当前版本无关。
  * "这个包里带了几项镜像？"      —— 数头里"呈记录形态"的地址命中数（全量包 1 条，QDM562 差分 3 条），
    与 config 项数 / 工具日志 `nOfImages` 对账。

**判"整包 vs 差分"只能靠"整张镜像是否连续嵌入"**（本脚本的主检查）+ 体积 + `nOfImages`。
不要靠头里的 `0xFFFFFFFF` 槽判 —— 实测双向差分包的记录同样呈现 `0xFFFFFFFF`（2026-09-29 差点写错）。

用法：
    python verify_fbf_package.py --pkg QDM562_full_762.bin --src <抽出镜像的目录>
    python verify_fbf_package.py --pkg x.bin --img customer_app.bin=<路径> --addr 0x00322000
    python verify_fbf_package.py --pkg x.bin --addr 0x00016000 --addr 0x00322000 --addr 0x00030000
    python verify_fbf_package.py --pkg x.bin --expect-images 3 --dump-header 24
    # 不给 --src/--img 时只做 头 + 地址 + 大小 的基本检查
"""
import argparse
import hashlib
import io
import os
import re
import struct

HDR_SIZE = 8192          # 实测（762 / V03 / 751 / 双向差分包）FBF 头固定 8192 B
SLOT_FREE = 0xFFFFFFFF   # 差分基准槽为空的值


def md5(b):
    return hashlib.md5(b).hexdigest()


def ascii_runs(buf, minlen=4):
    return [s.decode('latin1') for s in re.findall(rb'[\x20-\x7e]{%d,}' % minlen, buf)]


def probe_addr(header, addr):
    """在头里找这个写入地址（u32 LE），区分"真记录命中"与偶然命中。

    实测（762/V03/751 单镜像整包 与 双向差分包 5 个产物一致）：一条镜像记录的形态是
    `... 长度/类型/数量 ... [ADDR] ... 0xFFFFFFFF 0xFFFFFFFF ...`，即 **addr+8 与 addr+12 两个
    u32 都是 0xFFFFFFFF**。用这一点过滤掉偶然命中的字节，只看"呈记录形态"的命中。

    注意：这两个 FFFFFFFF 在整包和差分包里都有（本脚本实测双向差分包同样如此），
    所以它只能回答"包里带了这一项吗 / 写到哪里"，**不能**用来判整包 vs 差分。

    返回 (offsets, rec_offsets)：rec_offsets = 呈记录形态的命中位置。
    """
    pat = struct.pack('<I', addr)
    offs, i = [], header.find(pat)
    while i >= 0:
        offs.append(i)
        i = header.find(pat, i + 1)
    rec = [o for o in offs if o + 16 <= len(header)
           and struct.unpack_from('<II', header, o + 8) == (SLOT_FREE, SLOT_FREE)]
    return offs, rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pkg', required=True, help='FBFMake 产物 .bin')
    ap.add_argument('--src', default=None, help='抽出镜像的目录（其中的 .img/.bin 全拿来比对）')
    ap.add_argument('--img', action='append', default=[], help='显式指定 名字=路径（可多次）')
    ap.add_argument('--addr', action='append', default=[], help='期望在包里出现的地址，如 0x322000（可多次）')
    ap.add_argument('--expect-images', type=int, default=None,
                    help='期望头里出现的"写入地址记录"条数：全量包=1，QDM562 差分=3；对不上报错退出')
    ap.add_argument('--dump-header', type=int, default=0, metavar='N',
                    help='额外 dump 头里前 N 个 u32（排错用）')
    args = ap.parse_args()

    d = io.open(args.pkg, 'rb').read()
    header = d[:HDR_SIZE]
    print('%s   %d B   md5 %s' % (os.path.basename(args.pkg), len(d), md5(d)))
    print('  头 16 字节: %r' % d[:16])
    print('  magic Marvell_FBF : %s' % (d[:11] == b'Marvell_FBF'))
    runs = ascii_runs(header)
    ver_like = [s for s in runs if re.search(r'\d+\.\d+\.\d+', s)]
    print('  头内 ASCII 串 (%d 个): %s' % (len(runs), runs[:8]))
    print('  头内"版本号样式"串 : %s   （无 => 头里没有版本字段，整包=整分区覆盖、不挑设备当前版本）'
          % (ver_like or '无'))

    if args.dump_header:
        print('  头前 %d 个 u32:' % args.dump_header)
        for o in range(0, min(args.dump_header * 4, HDR_SIZE), 4):
            print('    @%-5d 0x%08X' % (o, struct.unpack_from('<I', header, o)[0]))

    recs = 0
    for a in args.addr:
        v = int(a, 16) if a.lower().startswith('0x') else int(a)
        offs, rec = probe_addr(header, v)
        if rec:
            recs += 1
        print('  地址 0x%08X  头内命中 %d 次 %s；呈记录形态 %d 处（首个 @%s）'
              % (v, len(offs), offs, len(rec), rec[0] if rec else '-'))
        if not rec:
            print('       ⚠️ 没有记录形态的命中 —— 地址可能不在头里，或头布局变了')

    if args.addr:
        print('  （头记录只说明"包带了这一项、写到哪个地址"，用来核对 config 项数 / nOfImages；'
              '判整包 vs 差分请看下面的"整张连续嵌入"）')

    if args.expect_images is not None:
        ok = (recs == args.expect_images)
        print('  记录条数自检: 呈记录形态 %d 条 / 期望 %d 条 -> %s'
              % (recs, args.expect_images, 'OK' if ok else '不符'))
        if not ok:
            raise SystemExit('地址记录条数与期望不符（全量包=1、QDM562 差分=3）—— 包型可能做错了')

    imgs = list(args.img)
    if args.src:
        for n in sorted(os.listdir(args.src)):
            if n.lower().endswith(('.img', '.bin')):
                imgs.append('%s=%s' % (n, os.path.join(args.src, n)))
    if not imgs:
        print('  （未给 --src/--img：跳过"整张镜像连续嵌入"检查）')
        return
    for spec in imgs:
        n, path = spec.split('=', 1)
        img = io.open(path, 'rb').read()
        pos, pos_t = d.find(img[:32]), d.rfind(img[-32:])
        whole = False
        if pos >= 0 and pos_t >= pos:
            whole = d[pos + len(img) - 32:pos + len(img)] == img[-32:]
        print('  %-18s %9d B  md5 %s | 首 32B 偏移 %-9s 末 32B 偏移 %-9s | 整张连续嵌入 %s'
              % (n, len(img), md5(img), pos, pos_t, whole))
        if not whole:
            print('     ⚠️ 整张镜像没连续出现在包里 —— 若期望做的是**全量包**，说明它其实做成了差分/被截断')
        elif pos >= 0:
            print('     -> 全量包口径成立：整分区覆盖（镜像自偏移 %d 起整张写入）' % pos)


if __name__ == '__main__':
    main()
