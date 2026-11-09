# -*- coding: utf-8 -*-
"""把路测截图按「一张图一行」填进报告的「路测」Sheet。

用法: python road_test.py --config <config.json>

配置段 road_test:
  dir          路测图片根目录（下面每个子目录 = 一个场景）
  scene_order  场景顺序（子目录名列表）；不写则按目录修改时间排序
  start_row    追加块的起始行（历史块结束行的下一行）
  number_start 「编号」列的起始数字（接着历史编号往下排）
  date/version/content/result/remark   该块共用的字段
  box          [宽px, 高px] 图片在单元格里的显示尺寸上限（等比缩放）
  row_height   行高（磅）
  quality      JPEG 质量（先等比缩到显示尺寸的 1.25 倍再存，控制 xlsx 体积）

行为：
  - 同一场景内的图片按「先横图（轨迹对比图）、后竖图（场景实拍）」排序
  - 场景名写进 E 列并跨该场景的所有行合并
  - B/C/D 列（测试日期/测试版本/测试内容）跨整块合并，与历史块一致
  - WEBP 会自动转成 JPEG（Excel 不认 webp）
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

import openpyxl
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Color
from PIL import Image as PILImage

EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def collect(root, order, one_per_scene=True, pick="first"):
    """one_per_scene=True 时每个场景只取一张代表图（历史报告就是这么做的：
    「一张图一行」，不是把所有截图都塞进去）。"""
    scenes = []
    names = order or sorted(
        [d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))],
        key=lambda d: os.path.getmtime(os.path.join(root, d)),
    )
    for name in names:
        p = os.path.join(root, name)
        if not os.path.isdir(p):
            continue
        files = [f for f in sorted(os.listdir(p)) if f.lower().endswith(EXTS)]
        if not files:
            continue
        # 先横图（轨迹对比图），后竖图（环境/整车实拍）
        def key(f):
            with PILImage.open(os.path.join(p, f)) as im:
                portrait = im.height > im.width
            return (portrait, f)
        files.sort(key=key)
        picked = files[:1] if one_per_scene else files
        if one_per_scene and pick == "largest":
            picked = [max(files, key=lambda f: os.path.getsize(os.path.join(p, f)))]
        scenes.append((name, [os.path.join(p, f) for f in picked]))
    return scenes


def prepare(src, dst_dir, box, quality):
    """等比缩放到 box 之内，返回 (临时 jpg 路径, 显示宽px, 显示高px)。"""
    im = PILImage.open(src)
    im = im.convert("RGB") if im.mode not in ("RGB",) else im
    sw, sh = im.size
    scale = min(box[0] / sw, box[1] / sh)
    disp = (max(1, round(sw * scale)), max(1, round(sh * scale)))
    phys = scale * 1.25
    im = im.resize((max(1, round(sw * phys)), max(1, round(sh * phys))), PILImage.LANCZOS)
    out = os.path.join(dst_dir, os.path.splitext(os.path.basename(src))[0] + ".jpg")
    im.save(out, "JPEG", quality=quality, optimize=True)
    return out, disp


GAP = 8


def build_strip(files, dst_dir, box, quality, name):
    """把一个场景的图横向拼成一张长图（统一缩放，总宽<=box[0]，高<=box[1]）。
    返回 (临时 jpg 路径, 显示宽px, 显示高px)。"""
    ims = []
    for f in files:
        im = PILImage.open(f)
        ims.append(im.convert("RGB"))
    wsum = sum(i.width for i in ims) + GAP * (len(ims) - 1)
    hmax = max(i.height for i in ims)
    s = min(box[1] / hmax, box[0] / wsum)
    sizes = [(max(1, round(i.width * s)), max(1, round(i.height * s))) for i in ims]
    W = sum(w for w, _ in sizes) + GAP * (len(sizes) - 1)
    H = max(h for _, h in sizes)
    canvas = PILImage.new("RGB", (W, H), (255, 255, 255))
    x = 0
    for im, (w, h) in zip(ims, sizes):
        canvas.paste(im.resize((w, h), PILImage.LANCZOS), (x, 0))
        x += w + GAP
    pw, ph = max(1, round(W * 1.2)), max(1, round(H * 1.2))
    out = os.path.join(dst_dir, "strip_%s.jpg" % name)
    canvas.resize((pw, ph), PILImage.LANCZOS).save(out, "JPEG", quality=quality, optimize=True)
    return out, (W, H)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding="utf-8"))
    rt = cfg.get("road_test")
    if not rt:
        print("SKIP: 配置里没有 road_test 段")
        return

    scenes = collect(rt["dir"], rt.get("scene_order"),
                     rt.get("one_per_scene", True), rt.get("pick") or "first")
    total = sum(len(v) for _, v in scenes)
    print("[road] 场景=%d 图片=%d (one_per_scene=%s)" % (len(scenes), total, rt.get("one_per_scene", True)))

    wb = openpyxl.load_workbook(cfg["out_report"])
    # ⚠️ openpyxl 读回富文本会拍平成纯文本，测试小结里的红字会丢。
    # 这一步是「再 load/save 一次」，所以必须在这里把富文本重新写回去。
    sm = cfg.get("summary") or {}
    if sm.get("runs"):
        s2 = wb[sm.get("sheet", "摘要")]
        s2[sm.get("text_cell", "C19")].value = CellRichText(*[
            TextBlock(InlineFont(sz=10, rFont="微软雅黑", color=Color(rgb=c)), s)
            for c, s in sm["runs"]
        ])
        print("[road] 已重写 摘要!%s 的富文本（红字）" % sm.get("text_cell", "C19"))
    ws = wb["路测"]
    start = int(rt.get("start_row") or (ws.max_row + 1))
    num = int(rt.get("number_start") or 1)
    style_row = start - 1
    box = rt.get("box") or [770, 400]
    tmp = tempfile.mkdtemp(prefix="roadtest_")

    r = start
    scene_spans = []
    widest = 0
    for name, files in scenes:
        for c in range(1, 9):
            src = ws.cell(row=style_row, column=c)
            ws.cell(row=r, column=c)._style = __import__("copy").copy(src._style)
        ws.cell(row=r, column=1).value = num
        ws.cell(row=r, column=2).value = rt.get("date")
        ws.cell(row=r, column=3).value = rt.get("version")
        ws.cell(row=r, column=4).value = rt.get("content")
        ws.cell(row=r, column=5).value = name
        ws.cell(row=r, column=7).value = rt.get("result")
        ws.cell(row=r, column=8).value = rt.get("remark")
        path, (dw, dh) = build_strip(files, tmp, box, rt.get("quality") or 82, str(num))
        img = XLImage(path)
        img.width, img.height = dw, dh      # 必须在 add_image 之前设
        ws.add_image(img, "F%d" % r)
        ws.row_dimensions[r].height = max(60, round(dh * 0.75))
        widest = max(widest, dw)
        scene_spans.append((r, r))
        print("   %-8s row %d  %d 张  拼图 %dx%d px  -> 行高 %.0fpt" % (
            name, r, len(files), dw, dh, ws.row_dimensions[r].height))
        num += 1
        r += 1

    last = r - 1
    # 列宽按最宽的那条拼图来（用户要求：放不下就加大列宽）
    ws.column_dimensions["F"].width = max(rt.get("col_width") or 0, round(widest / 7.0) + 2)
    print("   F 列宽 -> %.0f 字符 (最宽拼图 %dpx)" % (ws.column_dimensions["F"].width, widest))
    for col, val in ((2, rt.get("date")), (3, rt.get("version")), (4, rt.get("content"))):
        ws.cell(row=start, column=col).value = val
        ws.merge_cells(start_row=start, start_column=col, end_row=last, end_column=col)
    for first, end in scene_spans:
        if end > first:
            ws.merge_cells(start_row=first, start_column=5, end_row=end, end_column=5)

    wb.save(cfg["out_report"])
    shutil.rmtree(tmp, ignore_errors=True)
    print("SAVED: %s (%.1f MB)" % (cfg["out_report"], os.path.getsize(cfg["out_report"]) / 1048576))


if __name__ == "__main__":
    main()
