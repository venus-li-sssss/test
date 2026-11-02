# -*- coding: utf-8 -*-
"""离线单测 labels.pick_labels（**不需要 QGIS**，直接跑）。

    python test_pick_labels.py

改过挑字规则后跑一遍，确认三件事（都是 2026-09-29 实测基线）：
  * 静止段（连线中点挤在几米内）→ 只剩 1 个（而且是偏差最大的那个）；
  * 分段图尺度（0.32 m/px）正常行驶段 → 图内候选全标；
  * 整体截图尺度（1.12 m/px）→ 自动变疏（gap≈3.5）。
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from labels import dedupe_by_dist, pick_labels          # noqa: E402

LA0, LO0 = 23.025, 113.242              # 原点
M_LAT, M_LON = 110540.0, 111320.0


def mk_pts(offsets_m):
    """offsets_m = [(北向m, 东向m, 同刻距离m), ...]"""
    return [(d, LA0 + n / M_LAT, LO0 + e / M_LON) for n, e, d in offsets_m]


def case(name, pts, half_span_m, mpp):
    gap = max(1.0, mpp / 0.32)                     # 与 路测截图生成.py 的 shot() 一致
    cw = ch = int(round(2 * half_span_m / mpp))
    bb = (LA0 - half_span_m / M_LAT, LO0 - half_span_m / M_LON,
          LA0 + half_span_m / M_LAT, LO0 + half_span_m / M_LON)
    inside = sum(1 for _, la, lo in pts if bb[0] <= la <= bb[2] and bb[1] <= lo <= bb[3])
    keep = pick_labels(pts, bb, cw, ch, 9.0, gap=gap)
    print("%-30s 图内%3d/%3d → 画 %3d 个   (%.2f m/px, gap=%.1f)"
          % (name, inside, len(pts), len(keep), mpp, gap))
    return inside, len(keep)


# 静止段：15 条连线中点都落在 ~3 m 内（真实静止段：黄红相距约 30 m，中点几乎不动）
still = mk_pts([(1.2 * math.sin(i), 1.2 * math.cos(i * 1.7), 29.0 + i * 0.1) for i in range(15)])
# 行驶段：20 条连线，中点沿轨迹每 42 m 一个（约 30 km/h、5 s 一条）
drive = mk_pts([(i * 42.0, 0.0, 50.0 + i * 3.7) for i in range(20)])
# 掉头段：中点在小范围来回（半径 10 m）
turn = mk_pts([(10 * math.sin(i / 3.0), 10 * math.cos(i / 3.0), 45.0 + i) for i in range(20)])
# 慢速段：中点每 12 m 一个
slow = mk_pts([(i * 12.0, 0.0, 20.0 + i) for i in range(20)])

print("--- 分段图尺度（0.32 m/px，图内 ±500 m）---")
s, d, t, sl = [case("静止段(15条挤在3m内)", still, 500, 0.32),
               case("行驶段(20条·间距42m)", drive, 500, 0.32),
               case("掉头段(20条挤在20m内)", turn, 500, 0.32),
               case("慢速段(20条·间距12m)", slow, 500, 0.32)]
print("--- 整体截图尺度（1.12 m/px，图内 ±1500 m）---")
S, D, T, SL = [case("静止段(15条挤在3m内)", still, 1500, 1.12),
               case("行驶段(20条·间距42m)", drive, 1500, 1.12),
               case("掉头段(20条挤在20m内)", turn, 1500, 1.12),
               case("慢速段(20条·间距12m)", slow, 1500, 1.12)]

assert s[1] == 1 and S[1] == 1, "静止段（不管什么尺度）都应只剩 1 个"
assert d[1] == d[0], "分段图尺度：行驶段应把图内的字全画出来"
assert D[1] < D[0], "整体截图尺度：应该比图内候选少（自动变疏）"
assert SL[1] < SL[0], "整体截图尺度：慢速段也应稀疏"
print("自检 OK：静止段不叠、分段图全标、整体图自动变疏")

print("--- KML 用：dedupe_by_dist（按地面距离去重，默认 5 m；这是默认行为）---")
STILL = mk_pts([(1.5 * math.sin(i), 1.5 * math.cos(i * 1.7), 29.0 + i * 0.1) for i in range(40)])
DRIVE = mk_pts([(i * 42.0, 0.0, 50.0 + i * 3.7) for i in range(20)])
SLOWROLL = mk_pts([(i * 6.0, 0.0, 20.0 + i) for i in range(20)])      # 5 s 走 6 m ≈ 4.3 km/h
for nm, pts, th in (("静止段 40 条（中点都在 1.5 m 内）", STILL, 5.0),
                    ("行驶段 20 条（间隔 42 m）", DRIVE, 5.0),
                    ("慢速滚动 20 条（间隔 6 m ≈ 4 km/h）", SLOWROLL, 5.0)):
    k = dedupe_by_dist(pts, th)
    print("%-34s 候选%3d → 保留%3d" % (nm, len(pts), len(k)))
assert len(dedupe_by_dist(STILL, 5.0)) == 1, "KML 去重：静止段应只剩 1 个"
assert len(dedupe_by_dist(DRIVE, 5.0)) == 20, "KML 去重：行驶段应一条不丢"
assert len(dedupe_by_dist(SLOWROLL, 5.0)) == 20, "KML 去重：慢速滚动（>4 km/h）也应保留"
print("自检 OK：KML 默认全标；静止/重叠只留 1 个；行驶与慢速滚动一条不丢")
