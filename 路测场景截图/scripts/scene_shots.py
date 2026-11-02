# -*- coding: utf-8 -*-
"""场景轨迹截图生成器（通用，不依赖图新地球、不限路段）

  · 底图：Esri World Imagery 卫星瓦片（Web Mercator），自动挑层级、缓存到本地
  · 轨迹：黄 = 参考(高精度)，红 = 被测设备；全路线淡灰打底，场景段加粗 + 打点
  · 标注：右上角红字场景说明（可自定义结论），底部白底信息条（时间/时长/里程/卫星/HDOP/同刻距离）
  · 场景：自动识别（整体 / 静止 / 高速 / 弱信号 / 偏差最大 / 低速转弯密集 / 起终点）+ 自定义 JSON

用法:
  python scene_shots.py --hi <参考日志> --dev <被测日志> --out-dir <目录>
                        [--hi-label 高精度] [--dev-label 设备] [--scenes auto|scenes.json]
                        [--canvas 1500x1125] [--max-zoom 19] [--no-cache]

自定义场景 JSON（可选，用来把"公司周边/小区/隧道"这类真实语义对上）:
  {"scenes": [
     {"name": "公司周边", "start": "2026-09-24 16:01:36", "end": "2026-09-24 16:10:00",
      "note": "公司附近有定位放大器干扰，数据无效"},
     {"name": "隧道", "bbox": [23.030, 113.240, 23.034, 113.245], "note": "隧道内无星"}
  ]}
  时间段用本地时间（东八区）；bbox = [南纬, 西经, 北纬, 东经]
"""
import argparse
import datetime
import io
import json
import math
import os
import sys
import time
import urllib.request

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nmea import parse, build_epochs, haversine        # noqa: E402

TILE_URL = ("https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}")
BING_URL = "https://ecn.t0.tiles.virtualearth.net/tiles/a{qk}.jpeg?g=13034"
TILE = 256
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) scene-shots/1.0"
YEL = (255, 222, 0)
RED = (232, 0, 0)
GRAY = (200, 200, 200)
FONT_PATH = r"C:\Windows\Fonts\msyh.ttc"


def font(size):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


# ---------------- 瓦片底图 ----------------
def deg2px(lat, lon, z):
    n = 2 ** z * TILE
    x = (lon + 180.0) / 360.0 * n
    lat_r = math.radians(lat)
    y = (1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n
    return x, y


def quadkey(x, y, z):
    qk = []
    for i in range(z, 0, -1):
        d = 0
        mask = 1 << (i - 1)
        if x & mask:
            d += 1
        if y & mask:
            d += 2
        qk.append(str(d))
    return "".join(qk)


def tile_url(src, z, x, y):
    if src == "bing":
        return BING_URL.format(qk=quadkey(int(x), int(y), z))
    return TILE_URL.format(z=z, x=x, y=y)


def fetch_tile(z, x, y, cache_dir, src, retry=3):
    path = os.path.join(cache_dir, src, str(z), str(x), "%d.jpg" % y)
    if os.path.exists(path) and os.path.getsize(path) > 200:
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    url = tile_url(src, z, x, y)
    for i in range(retry):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = r.read()
            if len(data) > 200:
                open(path, "wb").write(data)
                time.sleep(0.08)
                return path
        except Exception as e:
            if i == retry - 1:
                print("   !! 瓦片失败[%s] z%d x%d y%d: %s" % (src, z, x, y, e))
            time.sleep(0.6)
    return None


def detail_score(img):
    """清晰度 = 拉普拉斯边缘方差（越大越清晰），用来选影像源"""
    from PIL import ImageFilter, ImageStat
    g = img.convert("L").filter(ImageFilter.FIND_EDGES)
    return ImageStat.Stat(g).var[0]


def pick_source(lat, lon, cache_dir, want=("bing", "esri"), z=17):
    """同一位置各源取一张瓦片，挑细节最多的那个源（Esri 在部分地区很糊）"""
    best, score = None, -1.0
    for src in want:
        x, y = deg2px(lat, lon, z)
        p = fetch_tile(z, int(x // TILE), int(y // TILE), cache_dir, src)
        if not p:
            print("   源 %s: 取不到" % src)
            continue
        try:
            s = detail_score(Image.open(p))
        except Exception:
            continue
        print("   源 %s: 清晰度 %.0f" % (src, s))
        if s > score:
            best, score = src, s
    return best or "esri"


def pick_zoom(bbox, cw, ch, max_zoom):
    """选能塞进画布的最大层级"""
    s, w, n, e = bbox
    for z in range(max_zoom, 5, -1):
        x0, y0 = deg2px(n, w, z)
        x1, y1 = deg2px(s, e, z)
        if (x1 - x0) <= cw and (y1 - y0) <= ch:
            return z
    return 6


def base_map(bbox, cw, ch, cache_dir, src, max_zoom):
    """返回 (底图 Image, 把经纬度换算成像素的函数)"""
    z = pick_zoom(bbox, cw, ch, max_zoom)
    s, w, n, e = bbox
    # 画布中心对应经纬度
    clat, clon = (s + n) / 2.0, (w + e) / 2.0
    cx, cy = deg2px(clat, clon, z)
    left, top = cx - cw / 2.0, cy - ch / 2.0
    tx0, ty0 = int(left // TILE), int(top // TILE)
    tx1, ty1 = int((left + cw) // TILE), int((top + ch) // TILE)
    img = Image.new("RGB", ((tx1 - tx0 + 1) * TILE, (ty1 - ty0 + 1) * TILE), (60, 60, 60))
    got = 0
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            p = fetch_tile(z, tx, ty, cache_dir, src)
            if not p:
                continue
            try:
                t = Image.open(p).convert("RGB").resize((TILE, TILE))
            except Exception:
                continue
            img.paste(t, ((tx - tx0) * TILE, (ty - ty0) * TILE))
            got += 1
    crop = img.crop((int(left) - tx0 * TILE, int(top) - ty0 * TILE,
                     int(left) - tx0 * TILE + cw, int(top) - ty0 * TILE + ch))
    print("   底图 z=%d 瓦片 %d/%d 张，%.0f×%.0f" % (z, got, (tx1 - tx0 + 1) * (ty1 - ty0 + 1), cw, ch))
    ox, oy = int(left), int(top)

    def to_px(lat, lon):
        x, y = deg2px(lat, lon, z)
        return x - ox, y - oy
    return crop, to_px


# ---------------- 场景自动识别 ----------------
def win_stats(eps, i0, i1):
    seg = eps[i0:i1 + 1]
    if not seg:
        return None
    sp = [e["sog_kmh"] for e in seg]
    st = [e["sats"] for e in seg if e["sats"]]
    hd = [e["hdop"] for e in seg if e["hdop"]]
    dist = sum(haversine(a["lat"], a["lon"], b["lat"], b["lon"]) for a, b in zip(seg, seg[1:]))
    return {"seg": seg, "n": len(seg), "vs": sum(sp) / len(sp), "vmax": max(sp),
            "sats_min": min(st) if st else 0, "sats_max": max(st) if st else 0,
            "sats_mean": sum(st) / len(st) if st else 0,
            "hdop_max": max(hd) if hd else 0, "hdop_mean": sum(hd) / len(hd) if hd else 0,
            "dist": dist}


def find_window(eps, span_s, score):
    """滑窗找 score 最优窗口（窗口时长 span_s 秒）→ ((i0,i1), 最优分值)"""
    best, win = None, None
    i = 0
    while i < len(eps):
        j = i
        while j < len(eps) - 1 and (eps[j + 1]["utc"] - eps[i]["utc"]).total_seconds() <= span_s:
            j += 1
        if j > i:
            v = score(win_stats(eps, i, j))
            if best is None or v > best:
                best, win = v, (i, j)
        i += 1
    return win, best


def bearing(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return math.degrees(math.atan2(y, x))


def turn_sum(eps, i0, i1):
    """累计转角（度）：衡量"弯多不多"。静止点不参与，避免噪声"""
    s, prev = 0.0, None
    for k in range(i0, min(i1, len(eps) - 2)):
        a, b = eps[k], eps[k + 1]
        if a["sog_kmh"] < 2.0 or b["sog_kmh"] < 2.0:
            prev = None
            continue
        br = bearing(a["lat"], a["lon"], b["lat"], b["lon"])
        if prev is not None:
            d = abs((br - prev + 180) % 360 - 180)
            if d < 60:                     # 跳变（定位跳点）不算转弯
                s += d
        prev = br
    return s


def auto_scenes(hi, dev, pairs):
    """返回场景列表：[{name, note, eps, t0, t1, extra}]"""
    scenes = []
    # 整体
    scenes.append({"name": "整体", "note": "整段路测：黄=参考 红=被测",
                   "halo": False, "eps": hi, "t0": hi[0]["utc"], "t1": hi[-1]["utc"], "extra": {}})

    # 静止段（速度≈0 最长连续段，≥3 分钟）
    runs, i = [], 0
    while i < len(hi):
        if hi[i]["sog_kmh"] < 0.5:
            j = i
            while j < len(hi) and hi[j]["sog_kmh"] < 0.5:
                j += 1
            if (hi[j - 1]["utc"] - hi[i]["utc"]).total_seconds() >= 180:
                runs.append((i, j - 1))
            i = j
        else:
            i += 1
    if runs:
        i, j = max(runs, key=lambda r: r[1] - r[0])
        s = win_stats(hi, i, j)
        scenes.append({"name": "静止段", "note": "长时间静止（速度≈0）", "eps": hi[i:j + 1],
                       "t0": hi[i]["utc"], "t1": hi[j]["utc"], "extra": s})

    # 高速段 / 弱信号段 / 低速转弯密集段：60 秒滑窗
    r, _ = find_window(hi, 60, lambda s: s["vs"])
    if r:
        i, j = r
        scenes.append({"name": "高速段", "note": "速度最高的一段（开阔路面）", "eps": hi[i:j + 1],
                       "t0": hi[i]["utc"], "t1": hi[j]["utc"], "extra": win_stats(hi, i, j)})

    # 弱信号段：跳过开头 120 s（冷启动搜星），且优先"在动且信号差"的窗口（隧道/遮挡才是有意义的场景）
    cold = 120
    i_start = 0
    for i, e in enumerate(hi):
        if (e["utc"] - hi[0]["utc"]).total_seconds() > cold:
            i_start = i
            break
    r, _ = find_window(hi[i_start:], 60,
                       lambda s: (-s["sats_mean"] - 10 * s["hdop_mean"]) if s["vs"] >= 5 else -1e9)
    if r:
        i, j = r[0] + i_start, r[1] + i_start
        scenes.append({"name": "弱信号段", "note": "卫星最少 / HDOP 最差（遮挡、隧道、地下）",
                       "eps": hi[i:j + 1], "t0": hi[i]["utc"], "t1": hi[j]["utc"],
                       "extra": win_stats(hi, i, j)})

    # 低速转弯密集段（小区/村道/园区内）
    best, win = None, None
    i = i_start
    while i < len(hi):
        j = i
        while j < len(hi) - 1 and (hi[j + 1]["utc"] - hi[i]["utc"]).total_seconds() <= 90:
            j += 1
        st = win_stats(hi, i, j)
        if st["vs"] < 25:
            v = turn_sum(hi, i, j)
            if best is None or v > best:
                best, win = v, (i, j)
        i += 1
    if win:
        i, j = win
        scenes.append({"name": "低速转弯密集段", "note": "低速多弯（小区、村道、园区内道路）",
                       "eps": hi[i:j + 1], "t0": hi[i]["utc"], "t1": hi[j]["utc"],
                       "extra": win_stats(hi, i, j)})

    # 偏差最大段（两台设备同刻距离最大）
    if pairs:
        t_best, d_best = max(pairs, key=lambda p: p[3])[0], max(p[3] for p in pairs)
        t0 = t_best - datetime.timedelta(seconds=60)
        t1 = t_best + datetime.timedelta(seconds=60)
        seg = [e for e in hi if t0 <= e["utc"] <= t1]
        if seg:
            scenes.append({"name": "偏差最大段", "note": "两台设备同刻距离最大处（%.1f m）" % d_best,
                           "eps": seg, "t0": seg[0]["utc"], "t1": seg[-1]["utc"],
                           "extra": win_stats(hi, hi.index(seg[0]), hi.index(seg[-1]))})
    return scenes


# ---------------- 绘制 ----------------
def wrapped(draw, text, fnt, max_w):
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=fnt) > max_w:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def render(scene, hi, dev, canvas, out_png, cache_dir, src, max_zoom,
           hi_label, dev_label, pairs, fmt="jpg"):
    cw, ch = canvas
    eps = scene["eps"]
    lat0 = min(e["lat"] for e in eps)
    lat1 = max(e["lat"] for e in eps)
    lon0 = min(e["lon"] for e in eps)
    lon1 = max(e["lon"] for e in eps)
    pad_lat = max((lat1 - lat0) * 0.18, 4e-4)
    pad_lon = max((lon1 - lon0) * 0.18, 4e-4)
    bbox = (lat0 - pad_lat, lon0 - pad_lon, lat1 + pad_lat, lon1 + pad_lon)
    print(" [%s]" % scene["name"])
    base, to_px = base_map(bbox, cw, ch, cache_dir, src, max_zoom)

    ov = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)

    # 全路线淡灰打底（整体场景不画）
    if scene["name"] != "整体":
        for i in range(len(hi) - 1):
            d.line([to_px(hi[i]["lat"], hi[i]["lon"]), to_px(hi[i + 1]["lat"], hi[i + 1]["lon"])],
                   fill=(255, 255, 255, 90), width=2)

    # 色带段：参考(黄) 与 被测(红)
    t0, t1 = scene["t0"], scene["t1"]
    dev_seg = [e for e in dev if t0 <= e["utc"] <= t1] if scene["name"] != "整体" else dev
    for eps2, col in ((eps, YEL), (dev_seg, RED)):
        pts = [to_px(e["lat"], e["lon"]) for e in eps2]
        if len(pts) > 1:
            d.line(pts, fill=col + (235,), width=6, joint="curve")
        step = max(1, len(pts) // 140)
        for p in pts[::step]:
            d.ellipse([p[0] - 3.5, p[1] - 3.5, p[0] + 3.5, p[1] + 3.5], fill=col + (255,))

    img = Image.alpha_composite(base.convert("RGBA"), ov).convert("RGB")
    d2 = ImageDraw.Draw(img)

    # 右上角红字场景说明（带白描边，模仿示例）
    f = font(30)
    lines = wrapped(d2, scene.get("note", ""), f, cw * 0.42)
    y = 18
    for ln in lines:
        wpx = d2.textlength(ln, font=f)
        d2.text((cw - 24 - wpx, y), ln, font=f, fill=(200, 0, 0), stroke_width=3, stroke_fill=(255, 255, 255))
        y += int(f.size * 1.35)

    # 左上角图例
    f2 = font(26)
    d2.rectangle([14, 14, 330, 108], fill=(255, 255, 255), outline=(130, 130, 130))
    d2.rectangle([26, 30, 74, 44], fill=YEL)
    d2.text((84, 24), hi_label, font=f2, fill=(20, 20, 20))
    d2.rectangle([26, 74, 74, 88], fill=RED)
    d2.text((84, 68), dev_label, font=f2, fill=(20, 20, 20))

    # 底部信息条
    ex = scene.get("extra") or {}
    rows = []
    if t0 and t1:
        lt0 = t0 + datetime.timedelta(hours=8)
        lt1 = t1 + datetime.timedelta(hours=8)
        rows.append("时间 %s ~ %s（%s）"
                    % (lt0.strftime("%m-%d %H:%M:%S"), lt1.strftime("%H:%M:%S"),
                       fmt_dur((t1 - t0).total_seconds())))
    if ex:
        rows.append("里程 %.2f km　速度 均 %.1f / 最大 %.1f km/h"
                    % (ex["dist"] / 1000.0, ex["vs"], ex["vmax"]))
        rows.append("卫星 %.0f~%.0f（均 %.1f）　HDOP 均 %.2f / 最大 %.2f"
                    % (ex["sats_min"], ex["sats_max"], ex["sats_mean"],
                       ex["hdop_mean"], ex["hdop_max"]))
    # 该场景内的同刻距离统计
    if pairs:
        ds = sorted(d for t, _a, _b, d in pairs if t0 <= t <= t1)
        if ds:
            rows.append("同刻距离（%d 点）中位 %.1f m　P95 %.1f m　最大 %.1f m"
                        % (len(ds), ds[len(ds) // 2], ds[min(len(ds) - 1, int(len(ds) * .95))], ds[-1]))
    if rows:
        m_w = haversine((lat0 + lat1) / 2, lon0, (lat0 + lat1) / 2, lon1)
        if m_w < 120 and ex and ex["vs"] < 1.0:
            rows.append("注：该段基本静止，空间范围仅约 %.0f m，图上已按最大层级放大" % m_w)
        f3 = font(24)
        h = 18 + len(rows) * int(f3.size * 1.4)
        d2.rectangle([0, ch - h, cw, ch], fill=(255, 255, 255), outline=(160, 160, 160))
        y = ch - h + 9
        for r in rows:
            d2.text((16, y), r, font=f3, fill=(20, 20, 20))
            y += int(f3.size * 1.4)

    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    if fmt == "png":
        img.save(out_png)
    else:
        img.save(out_png.replace(".png", ".jpg"), quality=88, subsampling=0)
        out_png = out_png.replace(".png", ".jpg")
    print("   -> %s (%d×%d, %.0f KB)" % (out_png, img.size[0], img.size[1],
                                         os.path.getsize(out_png) / 1024.0))
    return out_png


def contact_sheet(made, out_png, cols=3, tw=520, th=390, fmt="jpg"):
    """把所有场景图缩略拼成一张总览（便于放进报告/发群里）；默认也出 JPEG 控制体积"""
    if not made:
        return None
    rows = (len(made) + cols - 1) // cols
    pad, top = 14, 46
    sheet = Image.new("RGB", (cols * tw + (cols + 1) * pad, rows * (th + top) + pad), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    f = font(28)
    for k, (scene, path) in enumerate(made):
        c, r = k % cols, k // cols
        x, y = pad + c * (tw + pad), pad + r * (th + top)
        d.text((x, y + 6), scene["name"], font=f, fill=(20, 20, 20))
        try:
            th_img = Image.open(path).convert("RGB").resize((tw, th))
            sheet.paste(th_img, (x, y + top))
        except Exception as e:
            print("   !! 拼图跳过 %s: %s" % (path, e))
        d.rectangle([x, y + top, x + tw, y + top + th], outline=(150, 150, 150))
    if fmt == "png":
        sheet.save(out_png)
    else:
        out_png = out_png.replace(".png", ".jpg")
        sheet.save(out_png, quality=88, subsampling=0)
    print("拼图 -> %s (%d×%d, %.0f KB)" % (out_png, sheet.size[0], sheet.size[1],
                                          os.path.getsize(out_png) / 1024.0))
    return out_png


def fmt_dur(sec):
    sec = int(sec)
    if sec >= 3600:
        return "%d h %02d min" % (sec // 3600, sec % 3600 // 60)
    if sec >= 60:
        return "%.1f min" % (sec / 60.0)
    return "%d s" % sec


def load_scenes(path, hi):
    """自定义场景 JSON → 场景字典"""
    cfg = json.load(open(path, encoding="utf-8"))
    out = []
    for s in cfg.get("scenes", cfg if isinstance(cfg, list) else []):
        if "start" in s and "end" in s:
            t0 = datetime.datetime.strptime(s["start"], "%Y-%m-%d %H:%M:%S") - datetime.timedelta(hours=8)
            t1 = datetime.datetime.strptime(s["end"], "%Y-%m-%d %H:%M:%S") - datetime.timedelta(hours=8)
            seg = [e for e in hi if t0 <= e["utc"] <= t1]
        elif "bbox" in s:
            a, b, c, d_ = s["bbox"]
            seg = [e for e in hi if a <= e["lat"] <= c and b <= e["lon"] <= d_]
        else:
            raise SystemExit("场景 %s 缺少 start/end 或 bbox" % s.get("name"))
        if not seg:
            print("!! 场景 %s 没圈到点，跳过" % s.get("name"))
            continue
        out.append({"name": s["name"], "note": s.get("note", s["name"]), "eps": seg,
                    "t0": seg[0]["utc"], "t1": seg[-1]["utc"],
                    "extra": win_stats(hi, hi.index(seg[0]), hi.index(seg[-1]))})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hi", required=True)
    ap.add_argument("--dev", required=True)
    ap.add_argument("--out-dir", default=r"D:\work\路测工具\gps_kml")
    ap.add_argument("--hi-label", default="参考(高精度)")
    ap.add_argument("--dev-label", default="被测设备")
    ap.add_argument("--scenes", default="auto", help="auto 或场景 JSON 路径")
    ap.add_argument("--canvas", default="1500x1125")
    ap.add_argument("--max-zoom", type=int, default=19)
    ap.add_argument("--tile-url", default=TILE_URL)
    ap.add_argument("--tile-source", default="auto", choices=["auto", "esri", "bing"],
                    help="影像源；auto = 同位置同层级比清晰度后自动选（Esri 在部分地区很糊，Bing 更细）")
    ap.add_argument("--format", default="jpg", choices=["jpg", "png"],
                    help="出图格式，默认 jpg（PNG 一张 2~3 MB，很多聊天/文档通道显示不出来）")
    a = ap.parse_args()

    cw, ch = [int(x) for x in a.canvas.lower().split("x")]
    cache_dir = os.path.join(a.out_dir, "_tiles")
    stamp = os.path.join(a.out_dir, "路测截图")

    hi = build_epochs(*parse(a.hi))
    dev = build_epochs(*parse(a.dev))
    hi_map = {e["utc"]: e for e in hi if e["utc"]}
    dev_map = {e["utc"]: e for e in dev if e["utc"]}
    pairs = [(t, hi_map[t], dev_map[t],
              haversine(hi_map[t]["lat"], hi_map[t]["lon"], dev_map[t]["lat"], dev_map[t]["lon"]))
             for t in sorted(set(hi_map) & set(dev_map))]
    print("点数: 参考 %d / 被测 %d；同刻配对 %d" % (len(hi), len(dev), len(pairs)))

    scenes = auto_scenes(hi, dev, pairs) if a.scenes == "auto" else load_scenes(a.scenes, hi)
    print("场景 %d 个: %s" % (len(scenes), ", ".join(s["name"] for s in scenes)))
    if a.tile_source == "auto":
        mid = hi[len(hi) // 2]
        print("挑影像源（同一位置同一层级比清晰度）:")
        src = pick_source(mid["lat"], mid["lon"], cache_dir)
        print("   -> 用 %s" % src)
    else:
        src = a.tile_source
    made = []
    for s in scenes:
        p = render(s, hi, dev, (cw, ch), os.path.join(stamp, s["name"], "轨迹.png"),
                   cache_dir, src, a.max_zoom, a.hi_label, a.dev_label, pairs, a.format)
        made.append((s, p))

    # 汇总
    with open(os.path.join(stamp, "场景汇总.txt"), "w", encoding="utf-8") as f:
        f.write("场景截图汇总（%s vs %s）\n\n" % (a.hi_label, a.dev_label))
        for s, p in made:
            ex = s.get("extra") or {}
            f.write("%s\n  时间 %s ~ %s\n  说明 %s\n" % (
                s["name"], (s["t0"] + datetime.timedelta(hours=8)).strftime("%m-%d %H:%M:%S"),
                (s["t1"] + datetime.timedelta(hours=8)).strftime("%H:%M:%S"),
                s.get("note", "")))
            if ex:
                f.write("  里程 %.2f km，均速 %.1f km/h，卫星 %.0f~%.0f，HDOP 均 %.2f\n"
                        % (ex["dist"] / 1000.0, ex["vs"], ex["sats_min"], ex["sats_max"], ex["hdop_mean"]))
            ds = sorted(d for t, _a, _b, d in pairs if s["t0"] <= t <= s["t1"])
            if ds:
                f.write("  同刻距离 中位 %.1f m / 最大 %.1f m（%d 点）\n"
                        % (ds[len(ds) // 2], ds[-1], len(ds)))
            f.write("  图 %s\n\n" % p)
    print("汇总 -> %s" % os.path.join(stamp, "场景汇总.txt"))
    contact_sheet(made, os.path.join(stamp, "_场景拼图.png"), fmt=a.format)


if __name__ == "__main__":
    main()
