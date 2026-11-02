# -*- coding: utf-8 -*-
"""自检：出图能不能被正常打开、体积会不会超限

很多聊天/文档通道对图片有 **2 MB 显示上限**，超了就"图看不了"。
本脚本逐张检查：能否打开、真实格式、像素、体积，并给出结论。

用法: python verify_shots.py <out_dir>            （默认 <out_dir>\\路测截图）
"""
import glob
import os
import sys

from PIL import Image

base = sys.argv[1] if len(sys.argv) > 1 else r"D:\work\路测工具\gps_kml"
root = base if os.path.basename(base).startswith("路测截图") else os.path.join(base, "路测截图")
LIMIT = 2 * 1024 * 1024          # 常见通道上限
COMFY = 1.5 * 1024 * 1024

files = sorted(glob.glob(os.path.join(root, "*", "轨迹.*"))) + \
        sorted(glob.glob(os.path.join(root, "_场景拼图.*")))
if not files:
    print("!! %s 下没找到图" % root)
    sys.exit(1)

print("%-34s %9s %-12s %-6s %s" % ("图", "体积", "像素", "格式", "结论"))
bad = 0
for p in files:
    sz = os.path.getsize(p)
    try:
        im = Image.open(p)
        im.load()
        wh = "%dx%d" % im.size
        fmt = im.format
        ok = True
    except Exception as e:
        wh, fmt, ok = "-", "-", False
        print("  !! 打不开: %s (%s)" % (p, e))
    verdict = []
    if not ok:
        verdict.append("打不开")
    if sz > LIMIT:
        verdict.append("超2MB上限，通道可能显示不了")
    elif sz > COMFY:
        verdict.append("偏大(建议压缩)")
    if fmt not in ("JPEG", "PNG"):
        verdict.append("格式异常")
    tag = "OK" if not verdict else " / ".join(verdict)
    if verdict:
        bad += 1
    print("%-34s %7.0f KB %-12s %-6s %s" % (os.path.relpath(p, root), sz / 1024.0, wh, fmt, tag))

print("\n共 %d 张，%d 张有问题。上限 %.1f MB（JPEG≈0.5MB 安全；PNG 这种卫星图会到 2~3MB）"
      % (len(files), bad, LIMIT / 1048576.0))
sys.exit(1 if bad else 0)
