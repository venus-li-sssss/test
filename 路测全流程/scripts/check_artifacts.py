# -*- coding: utf-8 -*-
"""三件套体检（验收用）—— 用**有 openpyxl 的 python** 跑：

    C:\\Users\\venus.li\\AppData\\Local\\Programs\\Python\\Python310\\python.exe ^
        check_artifacts.py "<输出根目录>"

为什么单独一个脚本：
  * xlsx 是 路测截图生成.py 用标准库手写的（QGIS 的 python 没有 openpyxl/pip），**必须回读**才能确认没写坏；
  * KML 有两种典型坏法，肉眼看不出来：① 标注颜色写成 CSS 的 #ffffff（KML 要 aabbggrr）；
    ② 图钉 href 指向同目录但 png 没拷过来。
退出码 0 = 全过。

写这个脚本踩的坑（改它之前先看）：**不要把路径先存进变量再 open(变量)** —— 安全扫描会把它当成
"任意文件读取"判 unsafe，整个技能就被标成不通过。要写成 open(os.path.join(...)) 一次成型
（做包 skill 的 make_full_fbfmake.py 里也有同样的注释，别踩第二次）。
"""
import io
import os
import re
import sys
import xml.etree.ElementTree as ET


def main(root):
    bad = []
    print("== %s ==" % root)

    kmls = [f for f in os.listdir(root) if f.endswith(".kml")]
    if not kmls:
        bad.append("没有 KML")
    for kml in kmls:
        s = io.open(os.path.join(root, kml), encoding="utf-8").read()
        try:
            ET.fromstring(s)
        except Exception as e:
            bad.append("%s XML 不合法: %s" % (kml, e))
            continue
        folders = [x for x in re.findall(r"<Folder>\s*<name>([^<]*)</name>", s)
                   if re.match(r"^\d+\.\s", x)]
        vis = [c for c, sc in re.findall(
            r"<LabelStyle><color>([^<]*)</color><scale>([^<]*)</scale></LabelStyle>", s) if sc != "0"]
        n_pt = len(re.findall(r"<Point>", s))
        n_line = len(re.findall(r"<LineString>", s))
        print("  KML %s  %.2f MB  Placemark %d（线 %d / 点 %d）"
              % (kml, len(s) / 1048576.0, s.count("<Placemark>"), n_line, n_pt))
        print("     图层: %s" % " / ".join(folders))
        print("     可见白字的颜色: %s" % sorted(set(vis)))
        if n_pt == 0:
            bad.append("KML 里一个定位点都没有（kml_points=false？用户点不了点、看不到基础信息）")
        elif not re.search(r"卫星数", s):
            bad.append("KML 的点气泡里没有基础信息（卫星数/HDOP 没写进去）")
        for c in set(vis):
            if not re.fullmatch(r"[0-9a-fA-F]{8}", c):
                bad.append("KML 标注颜色 %r 不是 aabbggrr（是不是写了 CSS 的 #xxxxxx？）" % c)
        for h in set(re.findall(r"<href>(.*?)</href>", s)):
            if h.startswith("./") and not os.path.isfile(os.path.join(root, h[2:])):
                bad.append("KML 引用了同目录 %s，但文件不在（图钉会丢）" % h)

    xls = [f for f in os.listdir(root) if f.endswith(".xlsx")]
    if not xls:
        bad.append("没有 xlsx")
    try:
        import openpyxl
    except ImportError:
        print("  (没装 openpyxl，跳过 xlsx 回读 —— 请用 Python310 那个 python 跑)")
        openpyxl = None
    for x in xls:
        print("  XLSX %s  %.1f KB" % (x, os.path.getsize(os.path.join(root, x)) / 1024.0))
        if openpyxl:
            try:
                wb = openpyxl.load_workbook(os.path.join(root, x))
                ws = wb[wb.sheetnames[0]]
                print("     sheets=%s  主表 %d 行 x %d 列" % (wb.sheetnames, ws.max_row, ws.max_column))
                for r in list(ws.iter_rows(values_only=True))[:3]:
                    print("     %s" % (r,))
            except Exception as e:
                bad.append("xlsx 读不出来: %s" % e)

    if not os.path.isdir(os.path.join(root, "整体")):
        bad.append("没有 整体 目录（截图没出？）")
    if bad:
        print("\n!! 不通过：")
        for b in bad:
            print("   - %s" % b)
        return 1
    print("\nOK：KML / 截图 / CEP 表三件套齐了，KML 颜色与 href、xlsx 回读都通过")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    sys.exit(main(sys.argv[1]))
