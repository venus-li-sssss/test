# -*- coding: utf-8 -*-
"""路测三件套生成器 —— 产物固定三种（2026-09-29 用户定的契约）：

    ① KML          导入图新地球等工具里交互查看（黄=高精度 红=设备 白=同刻连线，可带距离白字）
    ② 截图         整体截图 / 区域整体截图 / 区域分段截图（肉眼查看，白线带距离白字）
    ③ CEP 表 Excel 行=CEP60/65/…/95（每 5 一档），列=整体 + 各场景区域，格子=该百分位的同刻距离(m)

输入 = 设备 NMEA + 对比(高精度) NMEA + 区域划分（KML 多边形 / 时间段 / 帧编号，KML 优先）

用法（Windows）：
    cd /d D:\\OSGeo4W\\bin
    python-qgis-ltr.bat "<本脚本路径>" "<区域划分.json 路径>"

区域划分优先级（写进 json，不用改代码）：
    ① KML 优先   kml_dir 目录里只要放进了 .kml（图新地球手绘多边形导出），就用它划分
    ② 时间划分   mode=time  + regions_time:  什么时间到什么时间是什么区域
    ③ 编号兜底   mode=image + regions_image: 第X帧到第Y帧是什么区域（先跑一遍拿编号帧）

要点（都是踩过坑换来的，别改）：
    * 全局图层一次构建，每张截图都画**整条轨迹的全部点**，绝不抽样
    * 帧沿轨迹每 seg_m 米一帧、编号全局连续，文件名 "编号_起始时间.jpg"，跨区域也不乱序
    * 一个区域必须是**连续帧段**，否则它的"区域整体截图"会把别的区域也框进来
    * QGIS setLayers 是自上而下：影像底图必须放最后，否则影像盖住轨迹
    * 矢量图层从 NMEA 建内存图层（KML 直接加载会得到 0 个要素）
    * 黄=高精度、红=设备、白=同刻连线（每 5 秒一条）；单图 <2MB 便于对话里显示
    * 同刻连线上**默认带距离白字**（label_lines，默认开）：白字 + 黑细描边，压在亮影像上也看得清；
      挑字逻辑在 labels.py（按屏幕像素防重叠、图幅越粗越疏 → 静止段不会叠成一坨）
    * CEP 的区域归属**复用截图那套帧归属**（同刻点按时间落到帧、帧属于哪个区域就归哪个区域），
      这样 Excel 里每个区域的数字和截图里的区域是同一批点
"""
import bisect
import datetime
import glob
import json
import math
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nmea
from nmea import FIXQ
from labels import dedupe_by_dist, pick_labels   # 纯 python，可离线单测

from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem, QgsFeature, QgsField,
                       QgsGeometry, QgsLineSymbol, QgsMapRendererSequentialJob, QgsMapSettings,
                       QgsMarkerSymbol, QgsPalLayerSettings, QgsPointXY, QgsProject,
                       QgsRasterLayer, QgsRectangle, QgsSingleSymbolRenderer,
                       QgsTextBufferSettings, QgsTextFormat, QgsVectorLayer,
                       QgsVectorLayerSimpleLabeling)
from qgis.PyQt.QtCore import QSize, QVariant
from qgis.PyQt.QtGui import QColor

XYZ_DEFAULT = ("type=xyz&url=https://server.arcgisonline.com/ArcGIS/rest/services/"
               "World_Imagery/MapServer/tile/{z}/{y}/{x}&zmax=19&zmin=0")
QGIS_PREFIX = r"D:\OSGeo4W\apps\qgis-ltr"


def hav(la0, lo0, la1, lo1):
    r = 6371000.0
    p0, p1 = math.radians(la0), math.radians(la1)
    a = math.sin((p1 - p0) / 2) ** 2 + math.cos(p0) * math.cos(p1) * \
        math.sin(math.radians(lo1 - lo0) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def dot_in(lon, lat, poly):
    c, n = False, len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1 + 1e-15) + x1:
            c = not c
    return c


def mk_label_layer(size=9.0, color="#ffffff", bold=True, buf=0.8, buf_color="#000000",
                   show_all=False):
    """建一个**空的**同刻距离白字标注层（只出文字，符号全透明）。

    QGIS 的文字**支持描边(buffer)**，这是它比 KML 强的地方：白字 + 黑细描边，
    压在亮影像/白路上也能看清。要素由 set_label_pts() 每次出图前按图幅重填。
    """
    vl = QgsVectorLayer("Point?crs=EPSG:4326", "同刻距离(白字)", "memory")
    vl.dataProvider().addAttributes([QgsField("dt", QVariant.String)])
    vl.updateFields()
    vl.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple(
        {"name": "circle", "size": "0.01", "color": "0,0,0,0", "outline_style": "no"})))

    pal = QgsPalLayerSettings()
    pal.fieldName = "dt"
    pal.placement = QgsPalLayerSettings.AroundPoint
    pal.dist = 1.0
    fmt = QgsTextFormat()
    fmt.setSize(size)
    fmt.setColor(QColor(color))
    if bold:
        fnt = fmt.font()
        fnt.setBold(True)
        fmt.setFont(fnt)
    if buf and buf > 0:
        bs = QgsTextBufferSettings()
        bs.setEnabled(True)
        bs.setSize(buf)
        bs.setColor(QColor(buf_color))
        fmt.setBuffer(bs)
    pal.setFormat(fmt)
    for attr, val in (("displayAll", show_all), ("obstacle", False)):
        try:
            setattr(pal, attr, val)          # 属性名随 QGIS 版本有差异，设不上就算了
        except Exception:
            pass
    vl.setLabeling(QgsVectorLayerSimpleLabeling(pal))
    vl.setLabelsEnabled(True)
    QgsProject.instance().addMapLayer(vl)
    return vl


def set_label_pts(vl, pts):
    """把这一张图要画的标注点填进标注层（pts = [(距离m, lat, lon), ...]）。"""
    dp = vl.dataProvider()
    dp.truncate()
    fs = []
    for d, la, lo in pts:
        f = QgsFeature(vl.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lo, la)))
        f["dt"] = "%.1f m" % d
        fs.append(f)
    dp.addFeatures(fs)
    vl.updateExtents()
    vl.triggerRepaint()


# ====================== 产物 ①：KML（导入图新地球等查看） ======================
# 颜色统一 aabbggrr：黄=高精度、红=设备、白=同刻连线（与"轨迹对比-图新地球"那套保持一致）
HI_LINE, DEV_LINE, COMB_LINE = "9900ffff", "990000aa", "ccffffff"
HIDE_LABEL = "<LabelStyle><color>00000000</color><scale>0</scale></LabelStyle>"
PIN_HI, PIN_DEV = "ylw-blank.png", "red-blank.png"
DEFAULT_EXE = (r"D:\work\路测工具\txdqdnb_160853\txdqdnb_160853"
               r"\LocaSpaceViewer4\LocaSpaceViewer.exe")


def xesc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def kml_color(css, alpha="ff"):
    """#rrggbb（配置里人读的颜色）→ KML 的 **aabbggrr**（KML 的字节序和 CSS 反过来）。

    踩过的坑：直接把 "#ffffff" 写进 <LabelStyle><color> 是**非法值**，图新地球/GE 会忽略或画黑。
    """
    s = (css or "").strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in s):
        s = "ffffff"
    return (alpha + s[4:6] + s[2:4] + s[0:2]).lower()


def balloon(title, rows):
    """气泡内容。字段名转义，值保留 HTML（里面可能带 <b>）。"""
    tds = "".join("<tr><td style='padding:1px 8px 1px 0;color:#666'>%s</td><td>%s</td></tr>"
                  % (xesc(k), v) for k, v in rows)
    return ("<![CDATA[<div style='font-family:Microsoft YaHei;font-size:13px'><b>%s</b>"
            "<table>%s</table></div>]]>" % (xesc(title), tds))


def epoch_rows(e):
    return [("本地时间", e["local"].strftime("%Y-%m-%d %H:%M:%S") if e["local"] else "-"),
            ("纬度, 经度", "%.6f, %.6f" % (e["lat"], e["lon"])),
            ("海拔", "%.1f m" % e["alt"]),
            ("速度", "%.1f km/h" % e["sog_kmh"]),
            ("卫星数", "%d" % e["sats"]),
            ("HDOP", "%.1f" % e["hdop"]),
            ("定位质量", FIXQ.get(e["fix"], str(e["fix"])))]


def pm_line(eps, color, width, desc="", name="", label=HIDE_LABEL, anchor=None):
    """一条轨迹线（anchor=(lon,lat) 时在该点加一个透明锚点，用来放白字）。"""
    c = "".join("          %.6f,%.6f,%.2f\n" % (e["lon"], e["lat"], e["alt"]) for e in eps)
    pt = ("          <Point><altitudeMode>clampToGround</altitudeMode>"
          "<coordinates>%.6f,%.6f,0</coordinates></Point>\n" % anchor) if anchor else ""
    return ("      <Placemark>\n        <name>%s</name>\n        <visibility>1</visibility>\n"
            "        <description>%s</description>\n"
            "        <Style><LineStyle><color>%s</color><width>%d</width></LineStyle>%s</Style>\n"
            "        <LineString><altitudeMode>clampToGround</altitudeMode><coordinates>\n%s"
            "        </coordinates></LineString>\n%s      </Placemark>\n"
            % (xesc(name), desc, color, width, label, c, pt))


def pm_point(lon, lat, desc, pin, gem_rel):
    return ("      <Placemark>\n        <name></name>\n        <visibility>1</visibility>\n"
            "        <description>%s</description>\n"
            "        <Style><IconStyle><color>ffffffff</color><scale>0.6</scale>"
            "<Icon><href>%s/%s</href></Icon></IconStyle>%s</Style>\n"
            "        <Point><altitudeMode>clampToGround</altitudeMode>"
            "<coordinates>%.6f,%.6f,0</coordinates></Point>\n      </Placemark>\n"
            % (desc, gem_rel, pin, HIDE_LABEL, lon, lat))


def pm_label(text, lon, lat, desc, color, scale, gem_rel):
    """白字标注：图标全透明，只有文字。"""
    return ("      <Placemark>\n        <name>%s</name>\n        <visibility>1</visibility>\n"
            "        <description>%s</description>\n"
            "        <Style><IconStyle><color>00000000</color><scale>0.4</scale>"
            "<Icon><href>%s/%s</href></Icon></IconStyle>"
            "<LabelStyle><color>%s</color><scale>%s</scale></LabelStyle></Style>\n"
            "        <Point><altitudeMode>clampToGround</altitudeMode>"
            "<coordinates>%.6f,%.6f,0</coordinates></Point>\n      </Placemark>\n"
            % (xesc(text), desc, gem_rel, PIN_HI, color, scale, lon, lat))


def write_kml(path, cfg, hi, dev, pa, lbl, regs, gem_rel, hi_label, dev_label):
    """写对比 KML：黄线/红线/白连线(带气泡) + 可选白字距离 + 区域边界。"""
    points_on = bool(cfg.get("kml_points", True))     # 默认带定位点：点一下看时间/卫星数/HDOP…
    labels_on = bool(cfg.get("kml_labels", True))
    lcolor = kml_color(cfg.get("kml_label_color", "#ffffff"))
    lscale = str(cfg.get("kml_label_scale", 1.0))
    o = ['<?xml version="1.0" encoding="UTF-8"?>', "<kml>", "  <Document>",
         "    <name>%s 对比 %s（黄=高精度 红=设备 白=同刻连线）</name>"
         % (xesc(dev_label), xesc(hi_label)),
         "  <Folder>", "    <name>Tracks</name>", "    <visibility>1</visibility>"]

    for eps, color, pin, ttl, pttl, note in (
            (hi, HI_LINE, PIN_HI, "1. %s（黄线%s）" % (hi_label, "·黄点" if points_on else ""),
             "%s 定位点" % hi_label,
             "高精度参考轨迹。黄线=轨迹，黄图钉=定位点，点任意点看基础信息。"),
            (dev, DEV_LINE, PIN_DEV, "2. %s（红线%s）" % (dev_label, "·红点" if points_on else ""),
             "%s 定位点" % dev_label,
             "被测设备轨迹。红线=轨迹，红图钉=定位点，点任意点看基础信息。")):
        f = ["      <Folder>", "        <name>%s</name>" % xesc(ttl),
             "        <visibility>1</visibility>",
             "        <description><![CDATA[%s]]></description>" % note,
             pm_line(eps, color, 4)]
        if points_on:
            for e in eps:
                f.append(pm_point(e["lon"], e["lat"], balloon(pttl, epoch_rows(e)), pin, gem_rel))
        f.append("      </Folder>")
        o.append("".join(f))

    f = ["      <Folder>", "        <name>3. 同刻连线（白·每 5 秒一条）</name>",
         "        <visibility>1</visibility>",
         "        <description><![CDATA[同一 UTC 整秒的两点连线，线长=同刻距离。点击线看时间/距离/高度差。]]>"
         "</description>"]
    for _, a, b in pa[::5]:
        d = hav(a["lat"], a["lon"], b["lat"], b["lon"])
        rows = [("本地时间", a["local"].strftime("%Y-%m-%d %H:%M:%S") if a["local"] else "-"),
                ("同刻距离", "<b>%.1f m</b>" % d),
                ("高度差", "%+.1f m　(设备 %.1f − 高精度 %.1f)" % (b["alt"] - a["alt"], b["alt"], a["alt"])),
                ("高精度", "%.6f, %.6f" % (a["lat"], a["lon"])),
                ("设备", "%.6f, %.6f" % (b["lat"], b["lon"]))]
        f.append("      <Placemark>\n        <name>%.1f m</name>\n        <visibility>1</visibility>\n"
                 "        <description>%s</description>\n"
                 "        <Style><LineStyle><color>%s</color><width>2</width></LineStyle>%s</Style>\n"
                 "        <LineString><altitudeMode>clampToGround</altitudeMode><coordinates>\n"
                 "          %.6f,%.6f,0\n          %.6f,%.6f,0\n"
                 "        </coordinates></LineString>\n      </Placemark>\n"
                 % (d, balloon("同刻连线", rows), COMB_LINE, HIDE_LABEL,
                    a["lon"], a["lat"], b["lon"], b["lat"]))
    f.append("      </Folder>")
    o.append("".join(f))

    if labels_on and lbl:
        # 默认**每条同刻线都标**（every=1）；只掐掉"静止/重叠"那批（中点几乎没动）——
        # KML 里没有屏幕像素概念（缩放随时变），所以按地面距离去重
        every = max(1, int(cfg.get("kml_label_every", 1)))
        sel = [p for p in lbl if p[0] >= float(cfg.get("kml_label_min", 0))][::every]
        n_all = len(sel)
        sel = dedupe_by_dist(sel, float(cfg.get("kml_label_min_sep", 5)))
        print("  [KML] 距离标注 %d/%d 条（静止/重叠去掉 %d 条，最小间距 %.0f m）"
              % (len(sel), n_all, n_all - len(sel), float(cfg.get("kml_label_min_sep", 5))))
        f = ["      <Folder>", "        <name>4. 同刻距离标注（%d 条）</name>" % len(sel),
             "        <visibility>1</visibility>",
             "        <description><![CDATA[每条同刻连线的距离数字（静止/重叠的那批只留一个，否则会叠成一坨），"
             "单独一层方便勾选/取消。注意 KML 的文字**没有描边**，压在亮色影像上会发虚——"
             "看不清就把 kml_labels 关掉、或换 kml_label_color（如 #ff0000 红）、或调大 kml_label_scale。]]>"
             "</description>"]
        for d, la, lo in sel:
            f.append(pm_label("%.1f m" % d, lo, la, "", lcolor, lscale, gem_rel))
        f.append("      </Folder>")
        o.append("".join(f))

    if regs:
        f = ["      <Folder>", "        <name>5. 区域边界（划分用）</name>",
             "        <visibility>1</visibility>",
             "        <description><![CDATA[区域划分用的多边形（KML 划分时来自图新地球手绘）。]]></description>"]
        for nm, poly in regs:
            eps = [{"lon": lo, "lat": la, "alt": 0.0} for lo, la in list(poly) + [poly[0]]]
            f.append(pm_line(eps, "9900ffff", 2, name=nm))
        f.append("      </Folder>")
        o.append("".join(f))

    o += ["  </Folder>", "  </Document>", "</kml>"]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(o) + "\n")


# ====================== 产物 ③：CEP 表（xlsx） ======================
def percentile(vals_sorted, p):
    """线性插值百分位（Excel 的 PERCENTILE.INC 同口径）。"""
    n = len(vals_sorted)
    if n == 0:
        return None
    if n == 1:
        return vals_sorted[0]
    k = (n - 1) * p / 100.0
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    if lo == hi:
        return vals_sorted[lo]
    return vals_sorted[lo] + (vals_sorted[hi] - vals_sorted[lo]) * (k - lo)


def _cell_ref(col, row):
    s = ""
    c = col
    while c:
        c, r = divmod(c - 1, 26)
        s = chr(65 + r) + s
    return "%s%d" % (s, row)


def write_xlsx(path, sheets):
    """最小 xlsx 写出（只用标准库：OSGeo4W 的 python 没有 openpyxl / pip）。

    sheets = [(表名, [[单元格, ...], ...]), ...]，单元格 = str / int / float / None。
    """
    def xa(s):
        return (str(s).replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))
    ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
          '<Default Extension="xml" ContentType="application/xml"/>',
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>']
    for i in range(len(sheets)):
        ct.append('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/'
                  'vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % (i + 1))
    ct.append("</Types>")
    wb = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>']
    for i, (nm, _) in enumerate(sheets):
        wb.append('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (xa(nm), i + 1, i + 1))
    wb.append("</sheets></workbook>")
    rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    for i in range(len(sheets)):
        rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/'
                    'officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>'
                    % (i + 1, i + 1))
    rels.append("</Relationships>")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "".join(ct))
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
                   '2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", "".join(wb))
        z.writestr("xl/_rels/workbook.xml.rels", "".join(rels))
        for i, (_, rows) in enumerate(sheets):
            sd = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                  '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
                  "<sheetData>"]
            for r, row in enumerate(rows, 1):
                sd.append('<row r="%d">' % r)
                for c, val in enumerate(row, 1):
                    if val is None or val == "":
                        continue
                    if isinstance(val, bool):
                        val = str(val)
                    if isinstance(val, (int, float)):
                        sd.append('<c r="%s"><v>%s</v></c>' % (_cell_ref(c, r), val))
                    else:
                        sd.append('<c r="%s" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
                                  % (_cell_ref(c, r), xa(val)))
                sd.append("</row>")
            sd.append("</sheetData></worksheet>")
            z.writestr("xl/worksheets/sheet%d.xml" % (i + 1), "".join(sd))


def kml_polys(path):
    """返回 [(区域名, [(lon,lat)...]), ...]"""
    out = []
    try:
        root = ET.parse(path).getroot()
    except Exception as e:
        print("  !! KML 解析失败 %s: %s" % (path, e))
        return out
    for pm in root.iter():
        if not pm.tag.endswith("Placemark"):
            continue
        nm = ""
        for ch in pm:
            if ch.tag.endswith("name"):
                nm = (ch.text or "").strip()
                break
        pts = []
        for one in [c for c in pm.iter() if c.tag.endswith("coordinates")]:
            for tok in (one.text or "").split():
                f = tok.split(",")
                if len(f) >= 2:
                    pts.append((float(f[0]), float(f[1])))
        if len(pts) >= 3:
            out.append((nm or os.path.splitext(os.path.basename(path))[0], pts))
    return out


def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "区域划分.json")
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    ROOT = cfg["out_root"]
    SEG = float(cfg.get("seg_m", 250))
    PIX_MAX = float(cfg.get("pix_max", 4_000_000))
    PAD = float(cfg.get("pad", 0.20))
    QUAL = int(cfg.get("quality", 84))

    hi = nmea.build_epochs(*nmea.parse(cfg["hi_log"]))
    dev = nmea.build_epochs(*nmea.parse(cfg["dev_txt"]))
    dbyu = {e["utc"]: e for e in dev}
    pa = [(e["utc"], e, dbyu[e["utc"]]) for e in hi if e["utc"] in dbyu]
    if not pa:
        print("!! 两条日志没有同刻数据，检查 utc 是否对齐"); return
    HP, DP = [(e["lat"], e["lon"]) for e in hi], [(e["lat"], e["lon"]) for e in dev]
    CONN, LBL = [], []          # CONN=白线几何；LBL=白字标注候选（连线中点 + 同刻距离）
    for i, (_, a, b) in enumerate(pa):
        if i % 5:
            continue
        CONN.append([(a["lat"], a["lon"]), (b["lat"], b["lon"])])
        LBL.append((hav(a["lat"], a["lon"], b["lat"], b["lon"]),
                    (a["lat"] + b["lat"]) / 2.0, (a["lon"] + b["lon"]) / 2.0))
    print("数据：高精度 %d 点 / 设备 %d 点 / 同刻连线 %d 条" % (len(HP), len(DP), len(CONN)))

    # 同刻线白字距离：**默认开**（用户 2026-09-29 要求）。要关掉就把 label_lines 设成 false
    LB_ON = bool(cfg.get("label_lines", True))
    LB_EVERY = max(1, int(cfg.get("label_every", 1)))
    LB_MIN = float(cfg.get("label_min", 0.0))
    LB_ALL = bool(cfg.get("label_all", False))
    LBP = [p for p in LBL if p[0] >= LB_MIN][::LB_EVERY] if LB_ON else []
    print("同刻距离白字标注 %d 条（label_lines=%s every=%d min=%.0fm 全画=%s）"
          % (len(LBP), LB_ON, LB_EVERY, LB_MIN, LB_ALL))

    QgsApplication.setPrefixPath(QGIS_PREFIX, True)
    app = QgsApplication([], False)
    app.initQgis()
    base = QgsRasterLayer(cfg.get("xyz_url", XYZ_DEFAULT), "影像底图", "wms")
    if not base.isValid():
        print("!! 影像图层无效（检查 xyz_url / 网络）"); return

    def mk(kind, name, geoms, color, w):
        vl = QgsVectorLayer("%s?crs=EPSG:4326" % ("LineString" if kind == "l" else "Point"),
                            name, "memory")
        fs = []
        for g in geoms:
            f = QgsFeature()
            if kind == "l":
                f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(lo, la) for la, lo in g]))
            else:
                f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(g[1], g[0])))
            fs.append(f)
        vl.dataProvider().addFeatures(fs)
        vl.updateExtents()
        if kind == "l":
            vl.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple(
                {"line_color": color, "line_width": str(w)})))
        else:
            vl.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple(
                {"name": "circle", "color": color, "size": str(w),
                 "outline_color": "white", "outline_width": "0.15"})))
        QgsProject.instance().addMapLayer(vl)
        return vl

    STACK = [mk("p", "设备点", DP, "#e81414", 2.6), mk("p", "高精度点", HP, "#ffd700", 2.6),
             mk("l", "设备线", [DP], "#e81414", 1.1), mk("l", "高精度线", [HP], "#ffd700", 1.1),
             mk("l", "同刻连线", CONN, "#ffffff", 0.5)]
    LB_SIZE = float(cfg.get("label_size", 9))
    LB_VL = mk_label_layer(size=LB_SIZE, color=cfg.get("label_color", "#ffffff"),
                           bold=bool(cfg.get("label_bold", True)),
                           buf=float(cfg.get("label_buffer", 0.8)),
                           buf_color=cfg.get("label_buffer_color", "#000000"),
                           show_all=LB_ALL) if LBP else None

    def clip(bbox):
        la0, lo0, la1, lo1 = bbox
        return [p for p in HP + DP if la0 <= p[0] <= la1 and lo0 <= p[1] <= lo1]

    def bbox(pts, pad=None):
        pad = PAD if pad is None else pad
        la0, la1 = min(p[0] for p in pts), max(p[0] for p in pts)
        lo0, lo1 = min(p[1] for p in pts), max(p[1] for p in pts)
        return (la0 - max((la1 - la0) * pad, 0.0010), lo0 - max((lo1 - lo0) * pad, 0.0010),
                la1 + max((la1 - la0) * pad, 0.0010), lo1 + max((lo1 - lo0) * pad, 0.0010))

    def shot(bbox, out_path, tag=""):
        la0, lo0, la1, lo1 = bbox
        h_m = (la1 - la0) * 110540.0
        w_m = (lo1 - lo0) * 111320.0 * math.cos(math.radians((la0 + la1) / 2))
        mpp = max(0.32, math.sqrt(w_m * h_m / PIX_MAX))
        cw, ch = int(round(w_m / mpp)), int(round(h_m / mpp))
        # 这一张画哪些距离白字：按屏幕像素挑 → 图幅越粗自动越疏、同一处只留一个
        txt = []
        if LB_VL:
            if LB_ALL:
                txt = [p for p in LBP if la0 <= p[1] <= la1 and lo0 <= p[2] <= lo1]
            else:
                txt = pick_labels(LBP, bbox, cw, ch, LB_SIZE, gap=max(1.0, mpp / 0.32))
            set_label_pts(LB_VL, txt)
        ms = QgsMapSettings()
        ms.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
        ms.setLayers(([LB_VL] if LB_VL else []) + STACK + [base])   # 标注最上，底图最后（最底下）
        ms.setExtent(QgsRectangle(lo0, la0, lo1, la1))
        ms.setOutputSize(QSize(cw, ch))
        job = QgsMapRendererSequentialJob(ms)
        job.start()
        job.waitForFinished()
        img = job.renderedImage()
        img.save(out_path, "JPEG", QUAL)
        if os.path.getsize(out_path) > 1_900_000:      # 保证 <2MB 能在对话里显示
            img.save(out_path, "JPEG", 72)
        # 自检：黄/红/白像素计数
        ny = nr = nw = 0
        for y in range(0, img.height(), 7):
            for x in range(0, img.width(), 7):
                c = img.pixelColor(x, y)
                if c.red() > 200 and c.green() > 160 and c.blue() < 110:
                    ny += 1
                elif c.red() > 170 and c.green() < 80 and c.blue() < 80:
                    nr += 1
                elif c.red() > 235 and c.green() > 235 and c.blue() > 235:
                    nw += 1
        print("   %-24s %4dx%-5d %.2f m/px %5dKB 黄%d 红%d 白%d 字%d %s"
              % (os.path.basename(out_path), cw, ch, mpp,
                 os.path.getsize(out_path) // 1024, ny, nr, nw, len(txt), tag))
        if ny + nr == 0:
            print("   !! 警告：这张图没检测到轨迹像素")

    # ---- 切帧：沿轨迹每 ~SEG 米一帧，编号全局连续 ----
    mov = [(u, a) for u, a, _ in pa if a["sog_kmh"] > 0.6] or [(pa[0][0], pa[0][1])]
    cuts, st, acc = [], 0, 0.0
    for i in range(1, len(mov)):
        acc += hav(mov[i - 1][1]["lat"], mov[i - 1][1]["lon"], mov[i][1]["lat"], mov[i][1]["lon"])
        if acc >= SEG:
            cuts.append((st, i)); st, acc = i, 0.0
    if st < len(mov) - 1:
        cuts.append((st, len(mov)))
    FR = []
    for k, (a0, b0) in enumerate(cuts, 1):
        seg = [mov[i][1] for i in range(a0, b0)]
        FR.append({"no": k, "t": mov[a0][1]["local"], "pts": [(e["lat"], e["lon"]) for e in seg]})
    print("帧数 %d（每帧约 %.0f m，编号 01→%d 连续）" % (len(FR), SEG, len(FR)))

    # ---- 区域归属：KML 优先 > 时间 > 编号 ----
    regs = []
    kml_dir = cfg.get("kml_dir")
    for p in (sorted(glob.glob(os.path.join(kml_dir, "*.kml"))) if kml_dir else []):
        got = kml_polys(p)
        print("KML %s -> %d 个多边形" % (os.path.basename(p), len(got)))
        regs += got
    for it in cfg.get("regions_kml", []):
        if os.path.isfile(it.get("kml", "")):
            regs += [(it.get("name") or os.path.basename(it["kml"]), pl)
                     for _, pl in kml_polys(it["kml"])]
    mode = "kml" if regs else cfg.get("mode", "image")
    if regs and cfg.get("mode") in ("time", "image"):
        print("→ KML 区域可用，按优先级使用 KML 划分")

    def assign(fr):
        if mode == "kml":
            best, bn = 0.0, ""
            for nm, poly in regs:
                r = float(sum(1 for la, lo in fr["pts"] if dot_in(lo, la, poly))) / max(1, len(fr["pts"]))
                if r > best:
                    best, bn = r, nm
            return bn if best >= float(cfg.get("kml_min_ratio", 0.3)) else "其他"
        if mode == "time":
            t = fr["t"].strftime("%H:%M:%S")
            for it in cfg.get("regions_time", []):
                if any(a <= t <= b for a, b in it["ranges"]):
                    return it["name"]
            return "其他"
        for it in cfg.get("regions_image", []):
            if it["from"] <= fr["no"] <= it["to"]:
                return it["name"]
        return "其他"

    for fr in FR:
        fr["reg"] = assign(fr)
    order = list(dict.fromkeys(f["reg"] for f in FR))
    print("划分方式 %s：" % mode +
          " | ".join("%s %d帧" % (r, sum(1 for f in FR if f["reg"] == r)) for r in order))

    # ---- 同刻点 → 区域：复用"帧归属"（按时间落到帧，帧属于哪个区域就归哪个区域），
    #      这样 Excel 里每个区域的数字和截图里的区域就是同一批点 ----
    fstarts = [f["t"] for f in FR]

    def pair_reg(t_local):
        if not FR or not t_local:
            return "其他"
        return FR[max(0, bisect.bisect_right(fstarts, t_local) - 1)]["reg"]

    by_reg, all_ds = {}, []
    for _, a, b in pa:
        d = hav(a["lat"], a["lon"], b["lat"], b["lon"])
        all_ds.append(d)
        by_reg.setdefault(pair_reg(a["local"]), []).append(d)

    os.makedirs(ROOT, exist_ok=True)
    HI_LBL = cfg.get("hi_label", "高精度")
    DEV_LBL = cfg.get("dev_label", "设备")
    cep_out = kml_out = None

    # ---- 产物 ③：CEP 表（列=整体 + 各区域，行=CEP60/65/…/95）----
    if cfg.get("cep_enable", True):
        c0, c1 = int(cfg.get("cep_start", 60)), int(cfg.get("cep_end", 95))
        cs = max(1, int(cfg.get("cep_step", 5)))
        cep_list = list(range(c0, c1 + 1, cs))
        cols = [("整体", all_ds)] + [(nm, by_reg.get(nm, [])) for nm in order]
        rows = [["CEP"] + [nm for nm, _ in cols]]
        for p in cep_list:
            rows.append([p] + [(round(percentile(sorted(ds), p), 1) if ds else "-")
                               for _, ds in cols])
        notes = [["列", "样本数(同刻点)", "说明"],
                 ["整体", len(all_ds), "全部同刻点（同一 UTC 整秒配对）"]]
        for nm in order:
            notes.append([nm, len(by_reg.get(nm, [])), "落在该区域帧段内的同刻点"])
        notes += [["", "", ""],
                  ["单位", "米", "水平直线距离（haversine）"],
                  ["CEP 口径", "百分位", "同刻距离的第 p 百分位（= Excel PERCENTILE.INC），行号就是 p"],
                  ["区域划分方式", mode, "kml=多边形 / time=时间段 / image=帧编号"]]
        cep_out = os.path.join(ROOT, cfg.get("cep_name", "CEP_列表.xlsx"))
        write_xlsx(cep_out, [("CEP", rows), ("说明", notes)])
        print("[CEP 表] %s" % cep_out)
        for r in rows:
            print("   " + "  ".join("%-9s" % v for v in r))
        try:                                   # 自检：能当 zip 打开、两个 sheet 都在
            with zipfile.ZipFile(cep_out) as z:
                bad = z.testzip()
                names = z.namelist()
            assert not bad and "xl/worksheets/sheet2.xml" in names
            print("   [自检] xlsx OK：%d 个 part（%s）" % (len(names), "CEP + 说明"))
        except Exception as e:
            print("   !! xlsx 自检失败: %s" % e)

    # ---- 产物 ①：KML（导入图新地球等查看）----
    if cfg.get("kml_enable", True):
        exe = cfg.get("kml_exe") or DEFAULT_EXE
        pin_dir = os.path.join(os.path.dirname(os.path.abspath(exe)),
                               "Resource", "image", "GEMarker")
        gem_rel, ok = ".", True
        for n in (PIN_HI, PIN_DEV):
            src = os.path.join(pin_dir, n)
            if os.path.isfile(src):
                try:
                    shutil.copy2(src, os.path.join(ROOT, n))
                except Exception as e:
                    print("!! 图钉拷贝失败(%s)" % e)
                    ok = False
            else:
                ok = False
        if not ok:
            gem_rel = os.path.relpath(pin_dir, ROOT).replace("\\", "/")
            print("!! 没拷到图钉（%s 里找不到 ylw-blank.png/red-blank.png）→ KML 改成引用该目录；"
                  "单独把这个 KML 拷给别人会丢图钉" % pin_dir)
        nm = cfg.get("kml_name") or ("对比轨迹_%s.kml"
                                    % datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
        kml_out = os.path.join(ROOT, nm)
        write_kml(kml_out, cfg, hi, dev, pa, LBP, regs, gem_rel, HI_LBL, DEV_LBL)
        print("[KML] %s  %.2f MB（黄=高精度 红=设备 白=同刻连线）"
              % (kml_out, os.path.getsize(kml_out) / 1048576.0))
        try:                                   # 自检：XML 合法 + 图钉跟 KML 在一起
            root_k = ET.parse(kml_out).getroot()
            folders = [e.text for e in root_k.iter()
                       if e.tag.endswith("name") and e.text and re.match(r"^\d+\.\s", e.text)]
            if gem_rel == ".":
                miss = [n for n in (PIN_HI, PIN_DEV) if not os.path.isfile(os.path.join(ROOT, n))]
                assert not miss, "缺图钉 %s" % miss
            print("   [自检] KML OK：图层 %s" % " / ".join(folders))
        except Exception as e:
            print("   !! KML 自检失败: %s" % e)

    # ---- 出图 ----
    o = os.path.join(ROOT, "整体")
    os.makedirs(o, exist_ok=True)
    print("[整体截图]")
    shot(bbox(HP + DP), os.path.join(o, "整体.jpg"))

    lines = ["编号  起始时间    所属区域"]
    if mode == "image" and not cfg.get("regions_image"):
        od = os.path.join(ROOT, "0_全部帧")
        os.makedirs(od, exist_ok=True)
        print("[全部编号帧]（先看编号，再回头告诉我 第X帧~第Y帧 是什么区域）")
        for f in FR:
            t = f["t"].strftime("%H%M%S")
            shot(bbox(f["pts"]), os.path.join(od, "%02d_%s.jpg" % (f["no"], t)))
            lines.append("%02d    %s:%s:%s   待定" % (f["no"], t[0:2], t[2:4], t[4:6]))
    else:
        for nm in order:
            sub = [f for f in FR if f["reg"] == nm]
            nos = [f["no"] for f in sub]
            if nos != list(range(min(nos), min(nos) + len(nos))):
                print("   ⚠ 区域「%s」帧号不连续 %s —— 它的区域整体截图可能框进别的区域" % (nm, nos))
            od = os.path.join(ROOT, nm)
            os.makedirs(od, exist_ok=True)
            t0, t1 = sub[0]["t"], sub[-1]["t"]
            extra = [(a["lat"], a["lon"]) for _, a, _ in pa if t0 <= a["local"] <= t1]
            print("[区域 %s] %d 帧" % (nm, len(sub)))
            shot(bbox([p for f in sub for p in f["pts"]] + extra),
                 os.path.join(od, "区域整体.jpg"), tag="区域整体")
            for f in sub:
                t = f["t"].strftime("%H%M%S")
                shot(bbox(f["pts"]), os.path.join(od, "%02d_%s.jpg" % (f["no"], t)))
                lines.append("%02d    %s:%s:%s   %s" % (f["no"], t[0:2], t[2:4], t[4:6], nm))
    open(os.path.join(ROOT, "帧清单.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("完成 -> %s" % ROOT)
    print("  ① KML   : %s" % (kml_out or "(未生成，kml_enable=false)"))
    print("  ② 截图  : %s\\整体\\ 与 各区域目录" % ROOT)
    print("  ③ CEP表 : %s" % (cep_out or "(未生成，cep_enable=false)"))
    os._exit(0)


if __name__ == "__main__":
    main()
