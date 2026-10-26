# -*- coding: utf-8 -*-
"""attendance.py 新班次规则的自检"""
import os
import sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from attendance import analyze_day

def T(punches, shift_text="", expect_wh=None, expect_ot=None, expect_std=None, tag="", shift_key=None):
    ts = [datetime.strptime("2026-10-26 " + p + (":00" if len(p) == 5 else ""), "%Y-%m-%d %H:%M:%S") for p in punches]
    r = analyze_day("2026-10-26", ts, shift_text, shift_key=shift_key)
    ok = True
    msg = f"{tag} {punches[0]}-{punches[-1]} [{r['shift_used']}] work={r['work_hours']}h std={r['std_hours']}h ot={r['overtime_hours']}h"
    for key, exp in (("work_hours", expect_wh), ("overtime_hours", expect_ot), ("std_hours", expect_std)):
        if exp is not None and abs(r[key] - exp) > 0.011:
            ok = False
            msg += f"  << 期望{key}={exp}!"
    print(("PASS " if ok else "FAIL ") + msg)
    return ok

allok = True
# ---- B班(6点班, 13:30-18:00, 19:00起算加班) ----
allok &= T(["09:00", "18:00"], expect_wh=8.0, expect_std=8.0, expect_ot=0.0, tag="B班满班")
allok &= T(["09:00", "18:30"], expect_wh=8.0, expect_ot=0.0, tag="B班18:30走-晚餐时段不计")
allok &= T(["09:00", "20:00"], expect_wh=9.0, expect_std=8.0, expect_ot=1.0, tag="B班加班到20:00")
allok &= T(["09:00", "21:00"], expect_wh=10.0, expect_ot=2.0, tag="B班加班到21:00")
# 早退扣差额（注意：末次16:30 会被自动判成 A 班，这里显式指定 B 班测早退逻辑）
allok &= T(["09:00", "16:30"], expect_wh=6.5, expect_std=6.5, expect_ot=0.0, tag="B班早退1.5h", shift_key="B")
# ---- A班(5点半班, 13:00-17:30, 18:30起算加班) 末次<18:00自动判A ----
allok &= T(["09:00", "17:30"], expect_wh=8.0, expect_std=8.0, expect_ot=0.0, tag="A班满班-实际7.5算8")
allok &= T(["09:00", "17:50"], expect_wh=8.0, expect_ot=0.0, tag="A班17:50走")
allok &= T(["09:00", "20:00"], shift_key="A", expect_wh=9.5, expect_ot=1.5, tag="A班晚走显式shift=A")
# ---- 弹性：迟到多久晚走多久 ----
allok &= T(["09:30", "18:30"], expect_wh=8.0, expect_std=8.0, expect_ot=0.0, tag="B班迟30min按18:30走")
allok &= T(["09:30", "18:00"], expect_wh=7.5, expect_std=7.5, tag="B班迟30min但18:00走-早退30")
allok &= T(["09:30", "19:30"], expect_wh=8.5, expect_std=8.0, expect_ot=0.5, tag="B班迟30min干到19:30")
allok &= T(["09:20", "17:50"], expect_wh=8.0, tag="A班迟20min应17:50走")   # 09:20末次17:50 => A班 due 17:50 => 满8h
# ---- 午休/晚餐区间展示 ----
r = analyze_day("2026-10-26", [datetime.strptime("2026-10-26 "+p+":00", "%Y-%m-%d %H:%M:%S") for p in ("09:00","20:00")])
print("B班区间扣减展示: 午休", r["lunch_deduct"], "晚餐", r["dinner_deduct"], "应下班", r["due_out"], "加班起算", r["ot_start"])
# ---- 休息日：整段计加班，扣午休(到pm_in)和晚餐 ----
allok &= T(["09:00", "18:00"], shift_text="休息", expect_wh=7.5, expect_ot=7.5, tag="休息日9-18(B默认扣午休12:00-13:30)")
allok &= T(["09:00", "20:00"], shift_text="休息", expect_wh=8.5, tag="休息日9-20(扣午休1.5h+晚餐1h)")
print("\n==>", "ALL PASS" if allok else "HAS FAIL")
