# -*- coding: utf-8 -*-
"""attendance.py 双班次规则自检：班次一律显式传入；不传必须报错（平台无默认、不推断）"""
import os
import sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from attendance import analyze_day


def ts(punches):
    out = []
    for p in punches:
        p = p + (":00" if len(p) == 5 else "")
        out.append(datetime.strptime("2026-10-26 " + p, "%Y-%m-%d %H:%M:%S"))
    return out


def T(punches, shift, expect_wh=None, expect_ot=None, expect_std=None, tag="", rest=False):
    r = analyze_day("2026-10-26", ts(punches), "休息" if rest else "", shift_key=shift)
    ok = True
    msg = f"{tag} [{shift}] {punches[0]}-{punches[-1]} work={r['work_hours']}h std={r['std_hours']}h ot={r['overtime_hours']}h"
    for key, exp in (("work_hours", expect_wh), ("overtime_hours", expect_ot), ("std_hours", expect_std)):
        if exp is not None and abs(r[key] - exp) > 0.011:
            ok = False
            msg += f"  << 期望{key}={exp}!"
    print(("PASS " if ok else "FAIL ") + msg)
    return ok


allok = True
# ---- 缺班次必须拒绝 ----
try:
    analyze_day("2026-10-26", ts(["09:00", "18:00"]), "", shift_key=None)
    print("FAIL 未传班次竟然算了!")
    allok = False
except ValueError:
    print("PASS 未传班次 -> ValueError 拒绝计算（平台无默认）")

# ---- B班(13:30-18:00, 加班起算19:00) ----
allok &= T(["09:00", "18:00"], "B", 8.0, 0.0, 8.0, "B班满班")
allok &= T(["09:00", "18:30"], "B", 8.0, 0.0, None, "B班18:30走-晚餐时段不计")
allok &= T(["09:00", "20:00"], "B", 9.0, 1.0, 8.0, "B班加班到20:00")
allok &= T(["09:00", "21:00"], "B", 10.0, 2.0, None, "B班加班到21:00")
allok &= T(["09:00", "16:30"], "B", 6.5, 0.0, 6.5, "B班早退1.5h")
# ---- A班(13:00-17:30, 加班起算18:30) ----
allok &= T(["09:00", "17:30"], "A", 8.0, 0.0, 8.0, "A班满班-实际7.5算8")
allok &= T(["09:00", "17:50"], "A", 8.0, 0.0, None, "A班17:50走")
allok &= T(["09:00", "20:00"], "A", 9.5, 1.5, 8.0, "A班加班到20:00")
# ---- 弹性：迟到多久晚走多久 ----
allok &= T(["09:30", "18:30"], "B", 8.0, 0.0, 8.0, "B班迟30min按18:30走")
allok &= T(["09:30", "18:00"], "B", 7.5, 0.0, 7.5, "B班迟30min但18:00走-早退30")
allok &= T(["09:30", "19:30"], "B", 8.5, 0.5, 8.0, "B班迟30min干到19:30")
allok &= T(["09:20", "17:50"], "A", 8.0, 0.0, 8.0, "A班迟20min应17:50走")
# ---- 休息日 ----
allok &= T(["09:00", "18:00"], "B", 7.5, 7.5, 0.0, "休息日9-18(B扣午休12:00-13:30)", rest=True)
allok &= T(["09:00", "20:00"], "B", 8.5, 8.5, None, "休息日9-20(扣午休1.5h+晚餐1h)", rest=True)
allok &= T(["09:00", "18:00"], "A", 8.0, 8.0, None, "休息日9-18(A扣午休12:00-13:00)", rest=True)
print("\n==>", "ALL PASS" if allok else "HAS FAIL")
sys.exit(0 if allok else 1)
