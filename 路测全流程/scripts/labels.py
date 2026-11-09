# -*- coding: utf-8 -*-
"""同刻距离白字标注的"挑字"逻辑 —— 纯 Python，不依赖 QGIS，可以离线单测。

被 路测截图生成.py 用（截图按屏幕像素挑字、KML 按地面距离去重），
被 test_pick_labels.py 单测（不用开 QGIS 就能验证改规则后没跑偏）。
"""
import math


def dist_m(lat0, lon0, lat1, lon1):
    """两点水平距离（米）。等距近似够用：本地几十米尺度上误差可忽略，且比 haversine 快。"""
    dy = (lat1 - lat0) * 111320.0
    dx = (lon1 - lon0) * 111320.0 * math.cos(math.radians((lat0 + lat1) / 2.0))
    return math.hypot(dx, dy)


def dedupe_by_dist(pts, min_sep_m=10.0):
    """按**地面距离**去重：中点彼此相距 < min_sep_m 的只留一个（先出现的留下）。

    给 KML 用：KML 里"是否重叠"跟缩放有关、没法按屏幕像素算，所以用地面距离——
    静止段 / 原地打转 / 重叠的连线，中点几乎不动，几十上百个数字会叠成一坨，只留一个即可；
    正常行驶时相邻连线中点差几十米，全部保留。
    pts = [(距离m, lat, lon), ...]
    """
    keep = []
    for d, la, lo in pts:
        if any(dist_m(la, lo, ka, ko) < min_sep_m for _, ka, ko in keep):
            continue
        keep.append((d, la, lo))
    return keep


def pick_labels(pts, bbox, cw, ch, size=9.0, gap=1.0):
    """按**屏幕像素**挑字：同一处只留一个、不重叠、随图幅自动变疏。

    pts  = [(同刻距离m, lat, lon), ...]，点是同刻连线的**中点**
    bbox = (la0, lo0, la1, lo1)，这一张图的取景范围
    cw/ch = 这张图的像素宽/高
    gap  = 屏幕上的最小间隔倍数，调用方按 mpp 给（0.32 m/px 的分段图 = 1.0，整体截图 ≈3.5）

    为什么需要：字号是固定像素，图幅越粗（整体截图 ≈1.1 m/px）同样多的字越挤；
    静止段/掉头段的连线中点几乎重合，十几个字会叠成一坨（2026-09-29 实测）。
    规则：把候选按**同刻距离从大到小**排序，只有与已选字的屏幕框不重叠才留下
    → 同一处自然只剩 1 个（而且留下的是偏差最大的那个）。

    返回：挑中的点（保持输入顺序）。调用方想强制全画就跳过本函数（config: label_all=true）。
    """
    la0, lo0, la1, lo1 = bbox
    span_la, span_lo = max(la1 - la0, 1e-9), max(lo1 - lo0, 1e-9)
    cand = []
    for i, (d, la, lo) in enumerate(pts):
        if la0 <= la <= la1 and lo0 <= lo <= lo1:          # 画面外的直接不要
            cand.append((d, i, (lo1 - lo) / span_lo * cw, (la1 - la) / span_la * ch))
    cand.sort(key=lambda c: -c[0])                         # 先放大偏差，小的让位
    ch_w = size * 0.62 + 0.4                               # ≈ 每字符像素宽（粗体无衬线，够用）
    h = size * 1.7
    boxes, keep = [], []
    for d, i, sx, sy in cand:
        w = ch_w * len("%.1f m" % d) + 6
        if any(abs(sx - bx) < (w + bw) / 2 * gap and abs(sy - by) < (h + bh) / 2 * gap
               for bx, by, bw, bh in boxes):
            continue
        boxes.append((sx, sy, w, h))
        keep.append(i)
        if len(keep) >= 400:                               # 兜底，别无限增长
            break
    ks = set(keep)
    return [p for j, p in enumerate(pts) if j in ks]       # 保持原顺序
