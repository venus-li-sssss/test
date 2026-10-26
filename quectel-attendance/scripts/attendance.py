#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
移远 QHR 考勤分析 CLI

用法:
  python attendance.py --shift a       # 5点半班 (13:00-17:30, 加班自18:30)
  python attendance.py --shift b       # 6点班 (13:30-18:00, 加班自19:00)
  python attendance.py                 # 交互式: 问班次(首次)/确认本地默认(非首次)
  python attendance.py --month 2026-07 --shift b
  python attendance.py --date 2026-08-03 --shift a
  python attendance.py --last 7 --shift b --json

班次纪律（重要）：
  • 平台副本【没有默认班次】，也【不再按打卡时间自动推断】——班次必须人给。
  • 第一次使用：必须问用户选 A 还是 B，选完再问"是否设为默认"。
    默认只写本地文件 ../.shift_default.json，不进 git/仓库。
  • 已有本地默认：每次仍必须向使用者确认"用默认X吗"，允许当场换班。
  • 非交互环境（agent/管道/JSON）拿不到 --shift 会直接报错，
    由调用方（agent）先问用户再带 --shift 重跑。
工时规则见 SKILL.md。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qhr_client import QHR  # noqa: E402

CONF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".credentials.json")
SHIFT_CONF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".shift_default.json")

# ---------------- 规则参数 ----------------
STD_IN = timedelta(hours=9)                  # 标准上班 09:00（上午段，两个班次相同）
LUNCH_S = timedelta(hours=12)                # 午休从 12:00 起，到各班次下午上班点止
FLEX_LIMIT = timedelta(minutes=60)           # 弹性上班最晚缓冲（>9:00 且 <=10:00 视为弹性）
STD_WORK = timedelta(hours=8)                # 前段标准工时：实际 7.5h 也按 8h 算

# 班次表: pm_in=下午上班(午休结束) out=下班 ot_start=加班起算(=下班后留 1h 晚餐缓冲)
# ⚠️ 无 DEFAULT_SHIFT：平台不预设班次，班次必须由 --shift / 交互确认得到
SHIFTS = {
    "A": {"label": "A班 13:00-17:30", "pm_in": timedelta(hours=13),
          "out": timedelta(hours=17, minutes=30), "ot_start": timedelta(hours=18, minutes=30)},
    "B": {"label": "B班 13:30-18:00", "pm_in": timedelta(hours=13, minutes=30),
          "out": timedelta(hours=18), "ot_start": timedelta(hours=19)},
}


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


# ---------------- 本地默认班次（只存本机，不进仓库） ----------------

def read_default_shift():
    try:
        v = json.load(open(SHIFT_CONF, encoding="utf-8")).get("default_shift", "")
        return v.upper() if str(v).upper() in SHIFTS else None
    except Exception:
        return None


def save_default_shift(key: str):
    json.dump({"default_shift": key.lower()},
              open(SHIFT_CONF, "w", encoding="utf-8"), ensure_ascii=False)


def clear_default_shift():
    try:
        os.remove(SHIFT_CONF)
    except OSError:
        pass


def resolve_shift_cli(cli_shift):
    """得到本次运行班次：--shift 显式 > 交互（首次询问/有默认必须确认）> 报错。
    绝不静默使用默认、绝不自动推断。"""
    if cli_shift and str(cli_shift).upper() in SHIFTS:
        return str(cli_shift).upper()

    default = read_default_shift()

    if not sys.stdin.isatty():
        raise SystemExit(
            "未指定班次，且非交互环境不会猜（平台副本无默认）。"
            "请先向用户询问当天/这批日期是 A班(13:00-17:30, 加班自18:30) 还是 "
            "B班(13:30-18:00, 加班自19:00)，再带 --shift a|b 重跑。"
            + (f"（本地存在默认 {default}，确认后才能用，命令行不接受'确认'，请确认后显式传 --shift {default.lower()}）"
               if default else ""))

    if default:
        ans = input(f"本地默认班次是 {SHIFTS[default]['label']}，本次使用默认吗？ "
                    f"[Y]=用默认 / a=改用A班 / b=改用B班 / s=清除默认: ").strip().lower()
        if ans in ("", "y"):
            return default                      # 用默认 = 已确认过
        if ans == "s":
            clear_default_shift()
            print("已清除本地默认。")
        elif ans in ("a", "b"):
            key = ans.upper()
            if input(f"要把 {SHIFTS[key]['label']} 更新为本地默认吗？(仅存本机，不进仓库) [y/N]: ").strip().lower() == "y":
                save_default_shift(key)
            return key

    key = input("选择班次: a=5点半班(13:00-17:30, 加班自18:30) / b=6点班(13:30-18:00, 加班自19:00) → ").strip().lower()
    if key not in ("a", "b"):
        raise SystemExit("必须输入 a 或 b")
    key = key.upper()
    if input(f"设为本地默认？（之后每次仍会先跟你确认，默认只存本机不进仓库） [y/N]: ").strip().lower() == "y":
        save_default_shift(key)
    return key


def analyze_day(day: str, times, shift="", extra=None, shift_key=None):
    """times: 当天所有打卡 datetime 列表（已排序）
    shift_key: 必须显式 'A'/'B'（由 --shift / 交互确认得到），不再自动推断"""
    extra = extra or {}
    if shift_key not in SHIFTS:
        raise ValueError("shift_key 必须显式指定 'A' 或 'B'（先问用户；平台无默认、不自动推断）")
    sh = SHIFTS[shift_key]
    first, last = times[0], times[-1]
    f, l = td(first), td(last)
    rest = "休息" in (shift or "")   # 休息日/周末：全部计加班，不判迟到早退

    if rest:
        span = l - f
        lunch = overlap(f, l, LUNCH_S, sh["pm_in"])
        dinner = overlap(f, l, sh["out"], sh["ot_start"]) if l > sh["ot_start"] else timedelta()
        work = span - lunch - dinner
        return {
            "date": day,
            "weekday": "一二三四五六日"[datetime.strptime(day, "%Y-%m-%d").weekday()],
            "shift": shift, "rest_day": True,
            "shift_used": shift_key, "shift_label": sh["label"],
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

    # 弹性：早上迟到多久，晚上就晚下班多久（基准 = 本班次下班点）
    late = f - STD_IN if f > STD_IN else timedelta()
    due_out = sh["out"] + late
    early_leave = due_out - l if l < due_out else timedelta()

    # 前段（标准工时）：满班按 8h 计（实际 7.5h 也算 8h），早退扣差额
    std = STD_WORK - early_leave
    if std < timedelta():
        std = timedelta()

    # 后段（加班）：从起算点开始按实际时长计；应下班→起算点之间是晚餐缓冲，不计
    overtime = l - sh["ot_start"] if l > sh["ot_start"] else timedelta()

    work = std + overtime
    # 展示用：午休/晚餐在打卡区间内的实际占用
    lunch = overlap(f, l, LUNCH_S, sh["pm_in"])
    dinner = overlap(f, l, max(due_out, sh["out"]), sh["ot_start"])

    return {
        "date": day,
        "weekday": "一二三四五六日"[datetime.strptime(day, "%Y-%m-%d").weekday()],
        "shift": shift, "rest_day": False,
        "shift_used": shift_key, "shift_label": sh["label"],
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
    """shift_key 必须显式 'A'/'B'（CLI/调用方确认后传入）"""
    if shift_key not in SHIFTS:
        raise SystemExit("collect() 需要显式班次 shift_key='A'/'B'：先问用户，平台无默认、不自动推断")
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
                         "不填则交互式询问（首次问选班+是否设默认；有默认也必须确认）")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    shift_key = resolve_shift_cli(a.shift)      # 绝不含自动推断/静默默认

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

    print(f"班次: {SHIFTS[shift_key]['label']}（本次显式/已确认）")
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
