# -*- coding: utf-8 -*-
"""
按考勤批量补填 work.ikotek.com 工时（非交互，支持每天不同内容/多项目拆分，并发提交）。

提速设计：
  • 考勤/项目列表落盘缓存（.cache/），第二次跑不再登 QHR、不再拉 814 个项目
  • SSO 只登录一次，token 分发给线程池里每个 worker 的独立 session（线程安全）
  • 多天并发提交，默认 5 线程（--workers 调）

单日/多天同内容:
  python batch_fill_by_attendance.py --dates 2026-09-28,2026-09-29 \
      --desc "测试 QDM562 版本" --items "1. xxx---已完成" "2. yyy---进行中"

一天拆多项目:
  ... --dates 2026-10-09 --desc "QDM562 版本测试 | QDM559 报告" --split "792=4.1,611=4.1" --items ...

每天内容不同（推荐）:
  python batch_fill_by_attendance.py --plan plan.json [--commit]
  plan.json = [{"date":"2026-10-08","desc":"...","items":["..."],"split":"792=9.3"}, ...]

工时默认取自考勤：前段满班按 8h 算（5:30/6:00 两个班次实际 7.5h 都按 8h），
加班从班次起算点（A班18:30 / B班19:00）起按实际时长计，只传总时长、不手工拆加班。
⚠️ **--shift a|b 每次必填**：平台无默认班次、也不按打卡推断——先向用户确认
这批日期是 A班(5点半下班) 还是 B班(6点下班) 再跑；一个月两种班次混着时，按班次分两批跑。
默认 dry-run，加 --commit 才真提交。--refresh 强制刷新考勤/项目缓存。
"""
import argparse, json, os, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

_WH = os.path.dirname(os.path.abspath(__file__))
ATT = os.path.abspath(os.path.join(_WH, "..", "..", "quectel-attendance", "scripts"))  # 同级 skill
WH = _WH
sys.path.insert(0, ATT)
sys.path.insert(0, WH)

from attendance import collect                      # noqa: E402
from workhours import get_creds as wh_creds         # noqa: E402
from work_client import WorkClient, WORK            # noqa: E402

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".cache")
_cache_lock = threading.Lock()
# 考勤计算规则版本：attendance.py 的工时规则一变（如 2026-10 改双班次 8h 规则），
# 旧缓存里的 work_hours 就是旧算法算的，必须整体作废重拉，不能只信"当月强制刷新"。
RULE_VERSION = "shift2-2026-10"


def _cache_path(name):
    os.makedirs(CACHE, exist_ok=True)
    return os.path.join(CACHE, name)


def cached_attendance(months, refresh=False, shift_key=None):
    """考勤按 (规则版本, 班次, 月份) 缓存；只拉缓存里没有的月份。返回 {date: row}
    shift_key 必须显式 'A'/'B'（调用方先问用户；无 auto 桶、不推断）。

    ⚠️ 三个必须遵守的规则：
      1) **当月永远强制重拉**（打卡是当天一直在累积的）。踩过：缓存停在 10-22，
         拿它核对 10-26 时把 10-23（其实 09:22-20:29 上了班）误判成"没打卡不用填"。
      2) **拉回 0 行的月份不落盘**。QHR 接口只回溯最近 3 个自然月，早于此的月份
         必然返回空；若把空结果当数据缓存，以后每天白跑也不会重试，还会让人误以为
         "那个月没上班"。
      3) **缓存 key 带 RULE_VERSION 和班次**。规则一改旧数据全作废；A/B 班的
         work_hours 不同，混用会算错。
    """
    if shift_key not in ("A", "B"):
        raise SystemExit("cached_attendance 需要显式 shift_key='A'/'B'：先问用户班次，无默认不推断")
    path = _cache_path("attendance.json")
    data = {}
    if os.path.exists(path) and not refresh:
        try:
            loaded = json.load(open(path, encoding="utf-8"))
            if loaded.get("rule_version") == RULE_VERSION:
                data = loaded.get("buckets", {})
        except Exception:
            data = {}
    bucket = shift_key
    sub = data.setdefault(bucket, {})
    cur_month = date.today().strftime("%Y-%m")
    missing = [m for m in months if m not in sub or m == cur_month]
    if missing:
        rows, _ = collect(missing, shift_key=shift_key)
        for r in rows:
            sub.setdefault(r["date"][:7], {})[r["date"]] = r
        # 拉回 0 行的月份不会写进 sub，下次自然还会重试
        json.dump({"rule_version": RULE_VERSION, "buckets": data},
                  open(path, "w", encoding="utf-8"), ensure_ascii=False)
    out = {}
    for m in months:
        out.update(sub.get(m, {}))
    return out, bool(missing)


def cached_projects(client, refresh=False):
    path = _cache_path("projects.json")
    if os.path.exists(path) and not refresh:
        try:
            return {str(p["id"]): p for p in json.load(open(path, encoding="utf-8"))}
        except Exception:
            pass
    ps = client.get_projects()
    json.dump(ps, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    return {str(p["id"]): p for p in ps}


def spawn_client(token):
    """复用已取得的 token，给线程各建一个 session（requests.Session 不宜跨线程共享）"""
    u, p = wh_creds()
    c = WorkClient(u, p)
    c.token = token
    c.s.headers.update({"Authorization": token})
    c.s.cookies.set("quectel_token", token, domain="work.ikotek.com")
    c.s.get(f"{WORK}/", timeout=30)
    return c


def build_summary(items):
    lines = [re.sub(r"^\d+[\.\、\)]\s*", "", it.strip()) for it in items]
    return "".join(f"<p>{i}. {ln}</p>" for i, ln in enumerate(lines, 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dates", help="逗号分隔 YYYY-MM-DD（--plan 时可不填）")
    ap.add_argument("--plan", help="JSON 计划文件：[{date,desc,items,split}]")
    ap.add_argument("--desc", help="工作描述（简洁栏），多项目用 ' | ' 分隔")
    ap.add_argument("--items", nargs="*", help="总结条目（不带序号）")
    ap.add_argument("--project", default="792", help="单项目时的项目 ID，默认 QDM562-EA-MCN(792)")
    ap.add_argument("--split", help="多项目拆分 proj_id=工时,proj_id=工时")
    ap.add_argument("--hours", help="覆盖工时：d=8.0 形式，或单个数字用于全部日期")
    ap.add_argument("--shift", choices=["a", "b"], required=True,
                    help="班次必填: a=5点半下班(18:30起算加班) b=6点下班(19:00起算加班)；"
                         "先问用户，无默认不推断")
    ap.add_argument("--commit", action="store_true", help="真正提交")
    ap.add_argument("--workers", type=int, default=5, help="并发提交线程数，默认 5")
    ap.add_argument("--refresh", action="store_true", help="强制刷新考勤/项目缓存")
    a = ap.parse_args()

    t0 = time.time()
    if a.plan:
        plan = json.load(open(a.plan, encoding="utf-8"))
    else:
        if not (a.dates and a.desc and a.items):
            ap.error("需要 --plan，或同时给 --dates/--desc/--items")
        plan = [{"date": d.strip(), "desc": a.desc, "items": a.items, "split": a.split}
                for d in a.dates.split(",") if d.strip()]
    dates = [p["date"] for p in plan]

    if not a.shift:
        ap.error("必须指定 --shift a|b：先向用户确认这批日期是 5点半班(a) 还是 6点班(b)；"
                 "平台无默认班次，也不允许按打卡推断")
    shift_key = a.shift.upper()

    months = sorted({d[:7] for d in dates})
    att_idx, fetched = cached_attendance(months, a.refresh, shift_key=shift_key)
    print(f"[{time.time()-t0:.1f}s] 考勤{'现拉' if fetched else '缓存命中'} "
          f"{len(dates)} 天里的 {sum(1 for d in dates if d in att_idx)} 天有打卡")

    hrs = {d: (round(att_idx[d]["work_hours"], 1) if d in att_idx else None) for d in dates}
    if a.hours:
        if "=" in a.hours:
            for kv in a.hours.split(","):
                k, v = kv.split("=")
                hrs[k.strip()] = float(v)
        else:
            for d in dates:
                hrs[d] = float(a.hours)

    base = WorkClient(*wh_creds()).login()
    projects = cached_projects(base, a.refresh)
    print(f"[{time.time()-t0:.1f}s] 登录+项目列表完成（{len(projects)} 个项目，缓存复用）")

    y, m = map(int, dates[0][:7].split("-"))
    start = f"{y:04d}-{m:02d}-01"
    y2, m2 = map(int, dates[-1][:7].split("-"))
    end = f"{y2 + 1:04d}-01-01" if m2 == 12 else f"{y2:04d}-{m2 + 1:02d}-01"
    by_date = {w["reportDate"]: w for w in base.get_work_list(start, end)}

    # ---- 主线程只做校验与 payload 构造（纯本地，快） ----
    jobs, results = [], {}
    for p in plan:
        d = p["date"]
        w, h = by_date.get(d), hrs.get(d)
        if w is None:
            results[d] = ("fail", "工时系统里没有记录"); continue
        if h is None:
            results[d] = ("fail", "考勤无打卡，需 --hours 指定"); continue
        if w.get("status") == "2" and not p.get("force"):
            results[d] = ("skip", f"已提交 {w['workTime']}h"); continue

        if p.get("split"):
            alloc = []
            for kv in str(p["split"]).split(","):
                pid, ph = kv.split("=")
                alloc.append((projects[pid.strip()], float(ph)))
        else:
            alloc = [(projects[p.get("project", a.project)], None)]
        descs = p["desc"].split(" | ") if " | " in p["desc"] else [p["desc"]] * len(alloc)
        if len(descs) < len(alloc):
            descs = descs + [descs[-1]] * (len(alloc) - len(descs))
        summary_html = build_summary(p["items"])

        vos = []
        for (proj, ph), desc in zip(alloc, descs):
            vos.append({
                "projectId": proj["id"], "productNameId": proj["productNameId"],
                "projectName": proj["projectName"], "workTime": str(h if ph is None else ph),
                "projectPhase": proj["projectPhase"], "productLine": proj["productLineName"],
                "overtime": "0.0", "description": desc,
                "projectManager": proj["projectManager"],
                "coManager": proj.get("coManager", ""), "options": [],
            })
        total = round(sum(float(v["workTime"]) for v in vos), 1)
        if abs(total - h) > 0.05:
            for v in vos:
                v["workTime"] = str(round(float(v["workTime"]) * h / total, 1))

        payload = {
            "id": w["id"], "userId": w["userId"], "type": "2",
            "reportTime": w["reportTime"], "summary": summary_html,
            "workTime": str(h), "overTime": 0, "remark": "",
            "detailVos": vos, "status": "1", "isBatch": False,
        }
        jobs.append((d, h, payload, summary_html, vos))

    # ---- 并发提交 ----
    def work(item):
        d, h, payload, summary_html, vos = item
        c = spawn_client(base.token)          # 每线程独立 session
        try:
            resp = c.submit_work(payload)
            return d, ("ok" if resp.get("success") else "fail"), h, resp.get("msg", ""), summary_html, vos
        except Exception as e:
            return d, "fail", h, f"异常 {e}", summary_html, vos
        finally:
            c.s.close()

    if not jobs:
        for d, (st, msg) in results.items():
            print(f"-- {d} {st}: {msg}")
        print("\n没有需要提交的日期"); return 0

    print(f"\n待提交 {len(jobs)} 天，并发 {min(a.workers, len(jobs))} 线程"
          f"{'（dry-run，不写）' if not a.commit else ''}")
    if not a.commit:
        for d, h, payload, sh, vos in jobs:
            print(f"\n=== {d}  {h}h  {' + '.join(v['projectName'] + '=' + v['workTime'] for v in vos)} ===")
            print(sh)
        print(f"\n[dry-run] 用时 {time.time()-t0:.1f}s；加 --commit 提交")
        return 0

    with ThreadPoolExecutor(max_workers=min(a.workers, len(jobs))) as ex:
        for d, st, h, msg, sh, vos in (f.result() for f in as_completed([ex.submit(work, j) for j in jobs])):
            results[d] = (st, f"{h}h {msg}".strip())

    for d in dates:
        st, msg = results.get(d, ("fail", "无结果"))
        mark = {"ok": "OK", "skip": "--", "fail": "XX"}.get(st, "??")
        print(f"{mark} {d}  {st}  {msg}")
    nok = sum(1 for s, _ in results.values() if s == "ok")
    print(f"\n提交 {nok} | 跳过 {sum(1 for s, _ in results.values() if s == 'skip')} | "
          f"失败 {sum(1 for s, _ in results.values() if s == 'fail')} | 总用时 {time.time()-t0:.1f}s")
    return 1 if any(s == "fail" for s, _ in results.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
