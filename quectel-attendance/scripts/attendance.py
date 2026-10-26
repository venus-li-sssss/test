#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
移远 QHR 考勤分析 CLI

用法:
  python attendance.py                 # 本月
  python attendance.py --month 2026-07 # 指定月
  python attendance.py --date 2026-08-03
  python attendance.py --last 7        # 最近 7 个有打卡的工作日
  python attendance.py --shift a       # 强制按 5点半班 (13:00-17:30, 18:30 起算加班)
  python attendance.py --shift b       # 强制按 6点班 (13:30-18:00, 19:00 起算加班)
  python attendance.py --json          # 输出 JSON

工时规则见 SKILL.md：两个班次（5:30 / 6:00 下班），前段实际 7.5h 也按 8h 标准工时计，
加班从各班次起算点（18:30 / 19:00）起按实际时长计。不指定 --shift 时自动推断：
末次打卡早于 18:00 → 只能是 5:30 班(A)；否则默认 6:00 班(B)。
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
STD_IN = timedelta(hours=9)                  # 标准上班 09:00（上午段，两个班次相同）
LUNCH_S = timedelta(hours=12)                # 午休从 12:00 起，到各班次下午上班点止
FLEX_LIMIT = timedelta(minutes=60)           # 弹性上班最晚缓冲（>9:00 且 <=10:00 视为弹性）
STD_WORK = timedelta(hours=8)                # 前段标准工时：实际 7.5h 也按 8h 算

# 班次表: pm_in=下午上班(午休结束) out=下班 ot_start=加班起算(=下班后留 1h 晚餐缓冲)
SHIFTS = {
    "A": {"label": "A班 13:00-17:30", "pm_in": timedelta(hours=13),
          "out": timedelta(hours=17, minutes=30), "ot_start": timedelta(hours=18, minutes=30)},
    "B": {"label": "B班 13:30-18:00", "pm_in": timedelta(hours=13, minutes=30),
          "out": timedelta(hours=18), "ot_start": timedelta(hours=19)},
}
DEFAULT_SHIFT = "B"                          # 自动推断不出时（末次打卡 >= 18:00）按 B 班


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


def resolve_shift(shift_key, l):
    """确定当天班次：显式 --shift 优先；否则按末次打卡推断——
    末次 < 18:00 只可能是 5:30 班(A)；否则默认 6:00 班(B)。
    注意：5:30 班但晚上留下来加班的日子，需要显式 --shift a。"""
    if shift_key in SHIFTS:
        return shift_key
    return "A" if l < SHIFTS["B"]["out"] else DEFAULT_SHIFT


def analyze_day(day: str, times, shift="", extra=None, shift_key=None):
    """times: 当天所有打卡 datetime 列表（已排序）
    shift_key: 'A'/'B'/None(auto)，None 时按末次打卡自动推断"""
    extra = extra or {}
    first, last = times[0], times[-1]
    f, l = td(first), td(last)
    rest = "休息" in (shift or "")   # 休息日/周末：全部计加班，不判迟到早退

    if rest:
        key = shift_key if shift_key in SHIFTS else DEFAULT_SHIFT
        sh = SHIFTS[key]
        span = l - f
        lunch = overlap(f, l, LUNCH_S, sh["pm_in"])
        dinner = overlap(f, l, sh["out"], sh["ot_start"]) if l > sh["ot_start"] else timedelta()
        work = span - lunch - dinner
        return {
            "date": day,
            "weekday": "一二三四五六日"[datetime.strptime(day, "%Y-%m-%d").weekday()],
            "shift": shift, "rest_day": True,
            "shift_used": key, "shift_label": sh["label"],
            "first": clock(f), "last": clock(l), "punch_count": len(times),
            "span": fmt(span), "work": fmt(work),
            "work_hours": round(work.total_seconds() / 3600, 2),
            "std_hours": 0.0,
            "lunch_deduct": fmt(lunch), "dinner_deduct": fmt(dinner),
            "late": "", "flex": False, "due_out": "-", "early_leave": "",
            "ot_start": clock(sh["ot_start"]),
            "overtime": fmt(work), "overtime_hours": round(work.total_seconds() / 3600, 2),
            "abnormal": False, "absent_hours": "",
        }

    key = resolve_shift(shift_key, l)
    sh = SHIFTS[key]

    # 弹性：早上迟到多久，晚上就晚下班多久（基准 = 本班次下班点）
    late = f - STD_IN if f > STD_IN else timedelta()
    due_out = sh["out"] + late
    early_leave = due_out - l if l < due_out else timedelta()

    # 前段（标准工时）：满班按 8h 计（实际 7.5h 也算 8h），早退扣差额
    std = STD_WORK - early_leave
    if std < timedelta():
        std = timedelta()

    # 后段（加班）：从起算点开始按实际时长计；应下班~起算点之间是晚餐缓冲，不计
    overtime = l - sh["ot_start"] if l > sh["ot_start"] else timedelta()

    work = std + overtime
    # 展示用：午休/晚餐在打卡区间内的实际占用
    lunch = overlap(f, l, LUNCH_S, sh["pm_in"])
    dinner = overlap(f, l, max(due_out, sh["out"]), sh["ot_start"])

    return {
        "date": day,
        "weekday": "一二三四五六日"[datetime.strptime(day, "%Y-%m-%d").weekday()],
        "shift": shift, "rest_day": False,
        "shift_used": key, "shift_label": sh["label"],
        "first": clock(f),
        "last": clock(l),
        "punch_count": len(times),
        "span": fmt(l - f),
        "work": fmt(work),
        "work_hours": round(work.total_seconds() / 3600, 2),
        "std_hours": round(std.total_seconds() / 3600, 2),
        "lunch_deduct": fmt(lunch),
        "dinner_deduct": fmt(dinner),
        "late": fmt(late) if late else "",
        "flex": bool(late) and late <= FLEX_LIMIT,
        "due_out": clock(due_out),
        "early_leave": fmt(early_leave) if early_leave else "",
        "ot_start": clock(sh["ot_start"]),
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


def collect(months, shift_key=None):
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
        out.append(analyze_day(d, ts, m.get("SHIFT", ""), m, shift_key=shift_key))
    return out, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", help="YYYY-MM，可逗号分隔多个")
    ap.add_argument("--date", help="YYYY-MM-DD 单日")
    ap.add_argument("--last", type=int, help="最近 N 个有打卡的日子")
    ap.add_argument("--shift", choices=["a", "b"],
                    help="班次: a=13:00-17:30(18:30起算加班) b=13:30-18:00(19:00起算加班)；"
                         "不填=自动（末次<18:00 判 a，否则 b）")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    shift_key = a.shift.upper() if a.shift else None

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

    rows, _ = collect(months, shift_key)
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

    print(f"{'日期':<12}{'周':<3}{'班':<3}{'首次':<7}{'末次':<7}{'工时':<7}{'应下班':<8}{'迟到':<7}{'早退':<7}{'加班':<6}")
    print("-" * 72)
    tw = to = 0.0
    for r in rows:
        print(f"{r['date']:<12}{r['weekday']:<3}{r['shift_used']:<3}{r['first']:<7}{r['last']:<7}"
              f"{r['work']:<7}{r['due_out']:<8}{r['late'] or '-':<7}"
              f"{r['early_leave'] or '-':<7}{r['overtime'] or '-':<6}")
        tw += r["work_hours"]
        to += r["overtime_hours"]
    print("-" * 72)
    print(f"合计 {len(rows)} 天 | 总工时 {tw:.2f}h | 日均 {tw/len(rows):.2f}h | 加班 {to:.2f}h")


if __name__ == "__main__":
    main()
