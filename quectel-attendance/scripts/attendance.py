#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
移远 QHR 考勤分析 CLI

用法:
  python attendance.py                 # 本月
  python attendance.py --month 2026-07 # 指定月
  python attendance.py --date 2026-08-03
  python attendance.py --last 7        # 最近 7 个有打卡的工作日
  python attendance.py --json          # 输出 JSON

工时规则见 SKILL.md
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qhr_client import QHR  # noqa: E402

CONF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".credentials.json")

# ---------------- 规则参数 ----------------
STD_IN = timedelta(hours=9)                  # 标准上班 09:00
STD_OUT = timedelta(hours=18)                # 标准下班 18:00
LUNCH_S, LUNCH_E = timedelta(hours=12), timedelta(hours=13)   # 午休 1h
OT_START = timedelta(hours=19)               # 19:00 起算加班
DINNER_S, DINNER_E = timedelta(hours=18), timedelta(hours=19)  # 晚餐 1h（加班时扣除）
STD_WORK = timedelta(hours=8)                # 标准工时
FLEX_LIMIT = timedelta(minutes=60)           # 弹性上班最晚缓冲（>9:00 且 <=10:00 视为弹性）


def td(s):
    """'HH:MM:SS' 或 datetime -> timedelta since midnight"""
    return timedelta(hours=s.hour, minutes=s.minute, seconds=s.second)


def fmt(t: timedelta) -> str:
    if t is None:
        return "--"
    m = int(t.total_seconds() // 60)
    sign = "-" if m < 0 else ""
    m = abs(m)
    return f"{sign}{m // 60}:{m % 60:02d}"


def clock(t: timedelta) -> str:
    m = int(t.total_seconds() // 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def overlap(a1, a2, b1, b2):
    """两区间重叠长度"""
    s, e = max(a1, b1), min(a2, b2)
    return e - s if e > s else timedelta()


def analyze_day(day: str, times, shift="", extra=None):
    """times: 当天所有打卡 datetime 列表（已排序）"""
    extra = extra or {}
    first, last = times[0], times[-1]
    f, l = td(first), td(last)
    rest = "休息" in (shift or "")   # 休息日/周末：全部计加班，不判迟到早退

    if rest:
        span = l - f
        lunch = overlap(f, l, LUNCH_S, LUNCH_E)
        dinner = overlap(f, l, DINNER_S, DINNER_E) if l > OT_START else timedelta()
        work = span - lunch - dinner
        return {
            "date": day,
            "weekday": "一二三四五六日"[datetime.strptime(day, "%Y-%m-%d").weekday()],
            "shift": shift, "rest_day": True,
            "first": clock(f), "last": clock(l), "punch_count": len(times),
            "span": fmt(span), "work": fmt(work),
            "work_hours": round(work.total_seconds() / 3600, 2),
            "lunch_deduct": fmt(lunch), "dinner_deduct": fmt(dinner),
            "late": "", "flex": False, "due_out": "-", "early_leave": "",
            "overtime": fmt(work), "overtime_hours": round(work.total_seconds() / 3600, 2),
            "abnormal": False, "absent_hours": "",
        }

    # 弹性：实际上班基准 = max(9:00, 首次打卡)
    actual_in = max(STD_IN, f)
    late = f - STD_IN if f > STD_IN else timedelta()
    # 弹性补偿：迟到多久，晚上就晚下班多久
    due_out = STD_OUT + late
    early_leave = due_out - l if l < due_out else timedelta()

    span = l - f                                   # 在司时长
    lunch = overlap(f, l, LUNCH_S, LUNCH_E)        # 扣午休
    dinner = overlap(f, l, DINNER_S, DINNER_E) if l > OT_START else timedelta()
    work = span - lunch - dinner                   # 有效工作时长

    overtime = l - OT_START if l > OT_START else timedelta()  # 19:00 后算加班

    return {
        "date": day,
        "weekday": "一二三四五六日"[datetime.strptime(day, "%Y-%m-%d").weekday()],
        "shift": shift, "rest_day": False,
        "first": clock(f),
        "last": clock(l),
        "punch_count": len(times),
        "span": fmt(span),
        "work": fmt(work),
        "work_hours": round(work.total_seconds() / 3600, 2),
        "lunch_deduct": fmt(lunch),
        "dinner_deduct": fmt(dinner),
        "late": fmt(late) if late else "",
        "flex": bool(late) and late <= FLEX_LIMIT,
        "due_out": clock(due_out),
        "early_leave": fmt(early_leave) if early_leave else "",
        "overtime": fmt(overtime) if overtime else "",
        "overtime_hours": round(overtime.total_seconds() / 3600, 2),
        "abnormal": extra.get("ISEXCEPTION") == "是",
        "absent_hours": extra.get("ABST") or "",
    }


def get_creds():
    u, p = os.environ.get("QHR_USER"), os.environ.get("QHR_PASS")
    if u and p:
        return u, p
    if os.path.exists(CONF):
        c = json.load(open(CONF, encoding="utf-8"))
        return c["username"], c["password"]
    raise SystemExit("缺少凭据：设置 QHR_USER / QHR_PASS 环境变量，或创建 .credentials.json")


def collect(months):
    u, p = get_creds()
    c = QHR(u, p).login()
    punches, daily = [], []
    for m in months:
        punches += c.punches(m)
        daily += c.daily(m)
    by_day = {}
    for r in punches:
        by_day.setdefault(r["SHIFTTERM"], []).append(
            datetime.strptime(r["CARDTIME"], "%Y-%m-%d %H:%M:%S"))
    meta = {r["TERM"]: r for r in daily}
    out = []
    for d in sorted(by_day):
        ts = sorted(by_day[d])
        m = meta.get(d, {})
        out.append(analyze_day(d, ts, m.get("SHIFT", ""), m))
    return out, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", help="YYYY-MM，可逗号分隔多个")
    ap.add_argument("--date", help="YYYY-MM-DD 单日")
    ap.add_argument("--last", type=int, help="最近 N 个有打卡的日子")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    today = date.today()
    if a.date:
        months = [a.date[:7]]
    elif a.month:
        months = a.month.split(",")
    else:
        months = [today.strftime("%Y-%m")]
        if a.last and today.day < a.last + 3:  # 跨月补上个月
            prev = today.replace(day=1) - timedelta(days=1)
            months.insert(0, prev.strftime("%Y-%m"))

    rows, _ = collect(months)
    if a.date:
        rows = [r for r in rows if r["date"] == a.date]
    if a.last:
        rows = rows[-a.last:]

    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return

    if not rows:
        print("无打卡记录")
        return

    print(f"{'日期':<12}{'周':<3}{'首次':<7}{'末次':<7}{'工时':<7}{'应下班':<8}{'迟到':<7}{'早退':<7}{'加班':<6}")
    print("-" * 66)
    tw = to = 0.0
    for r in rows:
        print(f"{r['date']:<12}{r['weekday']:<3}{r['first']:<7}{r['last']:<7}"
              f"{r['work']:<7}{r['due_out']:<8}{r['late'] or '-':<7}"
              f"{r['early_leave'] or '-':<7}{r['overtime'] or '-':<6}")
        tw += r["work_hours"]
        to += r["overtime_hours"]
    print("-" * 66)
    print(f"合计 {len(rows)} 天 | 总工时 {tw:.2f}h | 日均 {tw/len(rows):.2f}h | 加班 {to:.2f}h")


if __name__ == "__main__":
    main()
