# -*- coding: utf-8 -*-
"""把生成好的 SystemTestReport 推给妙搭报告平台，出对应的正式页面/Excel。

用法:
  python platform_push.py --config <config.json> [--only summary,test-plan,...]
                          [--dry-run] [--env prod|dev] [--out-dir DIR]

**数据源只有一个：`out_report` 那份生成好的报告**（不是执行表、不是平台缓存）。
所以必须排在 build_report / road_test / verify 之后跑，报告里改了什么就推什么。

配置段 `platform`：
  enabled   false 时整步跳过（批处理里不会报错）
  env       prod（默认）/ dev
  out_dir   下载落盘目录，默认 <out_report 同目录>/平台导出
  do        要推哪些：summary / test-plan / function / pressure / road-test / jira
  overrides 覆盖自动解析不出来的字段（reviewer / approver / implementationTime /
            documentType / testPlatform / mainVersionNumber / testType ...）
  jira_url  JIRA 过滤器链接；不给就用 config.jira.jql + jira.base_url 拼

字段映射（全部按模板里的标签文本找，不写死行号）：
  摘要!密级/文档类型/审核人/批准人/版本号/项目行业/测试类型/测试等级/测试内容勾选/
        测试人/日期/报告存放路径/送测单存放路径/BaselinesVersion/Baselines项目级路径/
        For Windows/For Linux/测试小结  ->  summary-report
  摘要!功能矩阵（主测版本两行 + 本 V 版本两行） ->  basicFunctionStates / functionItems
  测试计划!本版本块                          ->  test-plan & summary.testPlanData
  常规功能!本版本 4 列组（结果/Blocked/人/Fail） -> function-report & summary.functionTestTable
  常规压力!本版本 7 列组                     ->  pressure-report
  路测!config.road_test.dir 的场景目录        ->  road-test-report
  config.jira（账号/密码/JQL）              ->  reports/generate + status 轮询
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

import openpyxl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from platform_client import (ReportPlatformClient, plan_item, state,  # noqa: E402
                             summary_payload, ApiError)

# ---------------------------------------------------------------- 小工具
CHECKED = ("■", "√", "☑", "█")
UNCHECKED = ("□", "x", "✗", "X", " ")


def _s(v):
    return "" if v is None else str(v).replace("\n", " ").strip()


def find_row(ws, label, max_row=40, cols=(2, 3)):
    """按标签文本找 (行, 标签列)。标签可能在 B 或 C 列。"""
    for r in range(1, max_row + 1):
        for c in cols:
            if label in _s(ws.cell(row=r, column=c).value):
                return r, c
    return None, None


def value_after(ws, row, col):
    """标签右边的第一个非空值。"""
    for c in range(col + 1, min(col + 10, ws.max_column + 1)):
        v = _s(ws.cell(row=row, column=c).value)
        if v:
            return v, c
    return "", col


def pick_checked(text, options):
    """从「绝密□ 保密■ 公开□」里挑被勾的那个。"""
    t = text.replace(" ", "")
    for opt in options:
        i = t.find(opt)
        if i < 0:
            continue
        tail = t[i + len(opt): i + len(opt) + 3]
        if any(ch in tail for ch in CHECKED):
            return opt
    return ""


def main_version_of(full_version):
    """QDM559_STM32G0B0_APP_01.001.01.001_V22 -> 主版本号 01。"""
    m = re.search(r"(\d{2})\.\d{3}\.\d{2}\.\d{3}", full_version)
    return m.group(1) if m else ""


def sidecar_path(cfg, plat):
    """build_report 落的 sidecar（<out_report去扩展名>.data.json），有就用它，别反解析 xlsx。
    sidecar 比报告旧 = 报告被人手改过 -> 视为过期，回退去解析 xlsx（否则会推旧值）。"""
    p = plat.get("data_file") or (os.path.splitext(cfg["out_report"])[0] + ".data.json")
    if not os.path.exists(p):
        return ""
    try:
        if os.path.getmtime(p) < os.path.getmtime(cfg["out_report"]):
            print("  ! sidecar 比报告旧（%s < 报告），报告可能被手改过 -> 本次改为直接解析 xlsx"
                  % os.path.basename(p))
            return ""
    except OSError:
        return ""
    return p


def build_from_sidecar(cfg, side, plat):
    """sidecar -> 平台 payload。功能/压力/计划/缺陷直接取写入时的值。"""
    full, ver = cfg["full_version"], cfg["version"]
    summ = {"versionNumber": full, "tester": cfg.get("tester") or "",
            "testDate": cfg.get("test_date") or "",
            "implementationTime": cfg.get("test_date") or time.strftime("%Y-%m-%d"),
            "mainVersionNumber": main_version_of(full),
            "testSummary": side.get("summary_text") or "",
            "testPlanData": [], "functionTestTable": []}
    plan = [plan_item(p["seqNo"], full, cfg.get("test_period") or cfg.get("test_date") or "",
                      p["item"], p["count"], p.get("manpower") or 0, p["status"],
                      p.get("planEndDate") or summ["testDate"],
                      p.get("actualEndDate"), p.get("remark") or "")
            for p in side.get("plan") or []]
    summ["testPlanData"] = plan
    items = side.get("function") or []
    summ["functionTestTable"] = [{
        "version": summ["mainVersionNumber"], "vVersion": ver,
        "results": [{"category": it.get("sheetName") or "常规功能",
                     "item": it.get("testNumber") or it.get("testItem"),
                     "result": it.get("result") or "",
                     "checked": "√" if (it.get("result") or "") in ("PASS", "FAIL") else "x"}
                    for it in items]}]
    return summ, plan, items, side.get("pressure") or []


# ---------------------------------------------------------------- 固定值
def load_fixed(cfg, plat):
    """平台摘要的固定值：configs/platform_defaults.json（组织基线 global + 项目级 projects）。
    这些字段不用每次输入；本版本相关的字段不在这里。"""
    path = plat.get("defaults") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "configs", "platform_defaults.json")
    path = os.path.normpath(path)
    if not os.path.exists(path):
        return {}, path
    d = json.load(open(path, encoding="utf-8"))
    stem = cfg["full_version"].rsplit("_V", 1)[0]
    subs = {"stem": stem, "version": cfg["version"], "full_version": cfg["full_version"],
            "tester": cfg.get("tester") or "", "test_date": cfg.get("test_date") or ""}
    key = (cfg.get("jira") or {}).get("project_label") or cfg.get("project") \
        or stem.split("_")[0]
    merged = dict(d.get("global") or {})
    proj = (d.get("projects") or {}).get(key)
    for k, v in (proj or {}).items():
        merged[k] = v

    def sub(x):
        if isinstance(x, str):
            for kk, vv in subs.items():
                x = x.replace("{%s}" % kk, str(vv))
            return x
        if isinstance(x, dict):
            return {k: sub(v) for k, v in x.items()}
        return x
    return {k: sub(v) for k, v in merged.items() if not k.startswith("_")}, path


# ---------------------------------------------------------------- 摘要
def read_summary(ws):
    """摘要 Sheet -> summary-report 必填字段（不含 testSummary/矩阵，那些单独取）。"""
    out = {}
    for label, key, opts in (
            ("该文件保密等级", "confidentialityLevel", ("绝密", "保密", "公开")),
            ("主测版本测试等级", "testLevel", ("Level0", "Level1", "Level2", "Level3")),
            ("测试内容", "testContent", ("功能测试", "修改点", "常规压力", "bug验证", "CIT测试")),
            # 摘要里「测试类型」那行勾的是 主测/辅测版本，和平台字段 testType（功能测试…）不是一个概念，
            # 所以不在这里映射，交给 platform_defaults.json
    ):
        r, c = find_row(ws, label)
        if not r:
            continue
        v, _ = value_after(ws, r, c)
        if key == "testContent":
            out[key] = {
                "functionTest": bool(pick_checked(v, ("功能测试",))),
                "modificationPoint": bool(pick_checked(v, ("修改点",))),
                "routinePressure": bool(pick_checked(v, ("常规压力",))),
                "bugVerification": bool(pick_checked(v, ("bug验证", "缺陷验证"))),
                "citTest": bool(pick_checked(v, ("CIT测试", "CIT"))),
            }
        else:
            out[key] = pick_checked(v, opts) or v
    plain = {
        "documentType": ("软件测试报告", None),      # 值在标题行 B2
        "versionNumber": ("版本号", None),
        "projectIndustry": ("项目行业", None),
        "tester": ("测试人", None),
        "testDate": ("日期", None),
        "reportPath": ("报告存放路径", None),
        "submissionPath": ("送测单存放路径", None),
        "baselinesVersion": ("BaselinesVersion", None),
        "baselinesProjectPath": ("Baselines项目级路径", None),
        "forWindows": ("For Windows", None),
        "forLinux": ("For Linux", None),
    }
    for key, (label, _) in plain.items():
        r, c = find_row(ws, label)
        if not r:
            continue
        v, _ = value_after(ws, r, c)
        out[key] = v
    r2, _ = find_row(ws, "软件测试报告")
    if r2:
        out["documentType"] = _s(ws.cell(row=r2, column=2).value) or "软件测试报告"
    # 审核人/批准人在第一行右侧，标签和值成对出现
    for label, key in (("审核人", "reviewer"), ("批准人", "approver")):
        r, c = find_row(ws, label, max_row=3, cols=(2, 3, 5, 7, 9, 10, 11))
        if r:
            v, _ = value_after(ws, r, c)
            out[key] = v
    r, c = find_row(ws, "测试平台", max_row=8)
    if r:
        v, _ = value_after(ws, r, c)
        out["testPlatform"] = v
    # 测试小结（富文本读回来是纯文本，够用）
    r, c = find_row(ws, "测试小结")
    if r:
        v, _ = value_after(ws, r, c)
        out["testSummary"] = v
    return out


def read_matrix(ws, full_version, ver):
    """功能矩阵 -> (basicFunctionStates, functionItems)。

    表头行 B/C 有 Basic Function 与 Function 两段列区间；
    主测版本 = B 列等于完整版本号的那两行，本 V 版本 = B 列等于 ver 的**最后**两行。
    """
    hdr = None
    for r in range(1, ws.max_row + 1):
        if _s(ws.cell(row=r, column=3).value) == "整车" or \
           (r > 1 and "Basic Function" in _s(ws.cell(row=r - 1, column=3).value)):
            hdr = r
            break
    if not hdr:
        return [], []
    names = {}
    for c in range(3, 12):
        v = _s(ws.cell(row=hdr, column=c).value)
        if v:
            names[c] = v
    # 分组表头（'Basic Function' / 'Function' 两个标签）决定哪几列算基础功能、哪几列算功能项；
    # 有的模板写成合并区，有的就是单格标签，两种都兼容
    basic_cols, func_cols = set(), set()
    top = {c: _s(ws.cell(row=hdr - 1, column=c).value) for c in range(2, 12)
           if _s(ws.cell(row=hdr - 1, column=c).value)}
    keys = sorted(top)
    for i, c in enumerate(keys):
        end = keys[i + 1] if i + 1 < len(keys) else max(names) + 1
        cols = [x for x in names if c <= x < end]     # 标签列自己那一列也算进本组
        if "Basic" in top[c]:
            basic_cols.update(cols)
        elif "Function" in top[c]:
            func_cols.update(cols)
    for rng in ws.merged_cells.ranges:
        if rng.min_row <= hdr - 1 <= rng.max_row:
            t = _s(ws.cell(row=rng.min_row, column=rng.min_col).value)
            for c in range(rng.min_col, rng.max_col + 1):
                if c in names:
                    (basic_cols if "Basic" in t else func_cols).add(c)
    if not basic_cols and not func_cols:
        for c in names:
            func_cols.add(c)

    def pair_rows(match):
        """B 列等于该版本号的最后一对行（主测版本行模板里不带 _Vxx 后缀，两种写法都认）。"""
        wants = {match}
        if match == full_version:
            wants.add(match.rsplit("_V", 1)[0])
        hits = [r for r in range(hdr + 1, ws.max_row + 1)
                if _s(ws.cell(row=r, column=2).value) in wants]
        return (hits[-1], hits[-1] + 1) if hits else (None, None)

    m1, m2 = pair_rows(full_version)
    v1, v2 = pair_rows(ver)

    def build(cols):
        items = []
        for c in sorted(cols):
            items.append(state(
                names[c],
                main_checked=bool(m1 and _s(ws.cell(row=m1, column=c).value) in ("√", "x")),
                main_result=_s(ws.cell(row=m2, column=c).value) if m2 else "",
                v_checked=bool(v1 and _s(ws.cell(row=v1, column=c).value) in ("√", "x")),
                v_result=_s(ws.cell(row=v2, column=c).value) if v2 else ""))
        return items

    return build(basic_cols or set(names)), build(func_cols) if func_cols else []


# ---------------------------------------------------------------- 常规功能
def read_function(ws, ver):
    """本版本 4 列组 -> (reportItems, functionTestTable.results)。"""
    hdr_row, res_col = None, None
    for r in range(1, 12):
        for c in range(1, ws.max_column + 1):
            v = _s(ws.cell(row=r, column=c).value)
            if v == "%s测试结果" % ver:
                hdr_row, res_col = r, c
        if res_col:
            break
    if not res_col:
        return [], []
    items, results = [], []
    category = ""
    for r in range(hdr_row + 1, ws.max_row + 1):
        num = _s(ws.cell(row=r, column=3).value)
        content = _s(ws.cell(row=r, column=4).value)
        cat = _s(ws.cell(row=r, column=2).value)
        if cat and cat not in ("功能点测试",):
            category = cat
        if not num or num == "--":
            continue
        result = _s(ws.cell(row=r, column=res_col).value)
        blocked = _s(ws.cell(row=r, column=res_col + 1).value)
        tester = _s(ws.cell(row=r, column=res_col + 2).value)
        fail = _s(ws.cell(row=r, column=res_col + 3).value)
        items.append({
            "id": "f_%s" % num, "testItem": content or num, "testNumber": num,
            "testContent": content, "testDescription": "", "priority": _s(
                ws.cell(row=r, column=5).value),
            "result": result, "blockReason": blocked, "tester": tester,
            "failReason": fail, "sheetName": category or "常规功能", "subCases": []})
        results.append({"category": category, "item": num, "result": result,
                        "checked": "√" if result in ("PASS", "FAIL") else "x"})
    return items, results


# ---------------------------------------------------------------- 常规压力
def read_pressure(ws):
    """最后一组「测试版本」表头 = 本版本 7 列组。"""
    groups = [c for c in range(1, ws.max_column + 1)
              if _s(ws.cell(row=8, column=c).value) == "测试版本"]
    if not groups:
        return []
    base = max(groups)
    items = []
    for r in range(9, ws.max_row + 1):
        vals = [_s(ws.cell(row=r, column=base + i).value) for i in range(7)]
        if not any(vals):
            continue
        items.append({
            "id": "p_%s" % (_s(ws.cell(row=r, column=2).value) or r),
            "seqNo": int(re.sub(r"\D", "", _s(ws.cell(row=r, column=2).value)) or 0),
            "functionItem": _s(ws.cell(row=r, column=3).value),
            "testContent": _s(ws.cell(row=r, column=4).value),
            "scriptName": _s(ws.cell(row=r, column=5).value),
            "priority": _s(ws.cell(row=r, column=6).value),
            "networkSetting": _s(ws.cell(row=r, column=7).value),
            "version": vals[0], "device": vals[1], "duration": vals[2], "result": vals[3],
            "statistics": vals[4], "tester": vals[5], "remark": vals[6]})
    return items


# ---------------------------------------------------------------- 测试计划
def read_plan(ws, full_version, cfg):
    """本版本块：**优先按配置的 plan_start_row + plan 条数定位**。
    模板里版本/日期列写的是 `=摘要!K8` 这类公式，openpyxl 读不到缓存值就是 None，
    靠 C 列文本匹配不可靠（实测 V22 报告 C 列就是 None）。"""
    start, n = cfg.get("plan_start_row"), len(cfg.get("plan") or [])
    if not start:
        span = None
        for rng in ws.merged_cells.ranges:
            if rng.min_col == 3 and rng.max_col == 3:
                if _s(ws.cell(row=rng.min_row, column=3).value) == full_version:
                    span = (rng.min_row, rng.max_row)
        if not span:
            for r in range(1, ws.max_row + 1):
                if _s(ws.cell(row=r, column=3).value) == full_version:
                    span = (r, r)
                    break
        if not span:
            return []
        start, n = span[0], span[1] - span[0] + 1

    dflt = cfg.get("test_date") or ""
    seq0 = int(cfg.get("plan_start_no", 1))
    items = []
    for r in range(int(start), int(start) + int(n)):
        item = _s(ws.cell(row=r, column=5).value)
        if not item:
            continue
        cnt = ws.cell(row=r, column=6).value
        man = ws.cell(row=r, column=7).value

        def cell(col, fallback=""):
            return _s(ws.cell(row=r, column=col).value) or fallback
        items.append(plan_item(
            seq0 + len(items), full_version,
            cell(4, cfg.get("test_period") or dflt), item,
            cnt if isinstance(cnt, int) else (int(cnt) if str(cnt).isdigit() else 0),
            float(man) if man not in (None, "") else 0.0,
            cell(8), cell(9, dflt), cell(10, dflt) or None, cell(11)))
    return items


# ---------------------------------------------------------------- 主流程
def build_payloads(cfg, wb, plat, side=None):
    full, ver = cfg["full_version"], cfg["version"]
    summ = read_summary(wb["摘要"])
    basic, funcs = read_matrix(wb["摘要"], full, ver)
    if side:
        s2, plan, rep_items, press = build_from_sidecar(cfg, side, plat)
        summ.update({k: v for k, v in s2.items() if v not in ("", None, {}, [])})
        gf_results = [x for x in (summ.get("functionTestTable") or [{}])[0].get("results", [])]
        src = "sidecar"
    else:
        plan = read_plan(wb["测试计划"], full, cfg)
        rep_items, gf_results = read_function(wb["常规功能"], ver)
        press = read_pressure(wb["常规压力"])
        src = "报告"

    prov = {k: "报告" for k in summ}
    # 三层：报告解析 -> 固定值(platform_defaults.json) -> 本版本 config -> platform.overrides
    fixed, fixed_path = load_fixed(cfg, plat)
    for k, v in fixed.items():
        old = summ.get(k)
        # 比原文会误报（报告里的换行被拍平成空格），先归一化空白再比
        if old not in (None, "", {}, []) and _s(old) != _s(v):
            print("  ! %s 报告=%r 与固定值=%r 不一致，按固定值推送（改 %s 可调整）"
                  % (k, str(old)[:48], str(v)[:48], fixed_path))
        summ[k] = v
        prov[k] = "固定值"
    for k, v in (("versionNumber", full), ("tester", cfg.get("tester")),
                 ("testDate", cfg.get("test_date")),
                 ("implementationTime", cfg.get("test_date") or time.strftime("%Y-%m-%d"))):
        if v:
            summ[k] = v
            prov[k] = "config"
    if not summ.get("mainVersionNumber"):
        summ["mainVersionNumber"] = main_version_of(full)
        prov["mainVersionNumber"] = "版本号推导"
    else:
        prov["mainVersionNumber"] = src if side else "报告"
    summ["testPlanData"] = plan
    for k in ("testPlanData", "basicFunctionStates", "functionItems", "functionTestTable",
              "testSummary"):
        prov[k] = src
    if basic:
        summ["basicFunctionStates"] = basic
    if funcs:
        summ["functionItems"] = funcs
    summ["functionTestTable"] = [{"version": summ["mainVersionNumber"], "vVersion": ver,
                                  "results": gf_results}]
    for ov_k, ov_v in (plat.get("overrides") or {}).items():
        summ[ov_k] = ov_v
        prov[ov_k] = "platform.overrides"
    payload = {
        "summary": summ,
        "test-plan": {"version": full, "planItems": plan},
        "function": {"reportItems": rep_items},
        "pressure": {"items": press},
    }
    counts = {"summary": 1, "test-plan": len(plan), "function": len(rep_items),
              "pressure": len(press),
              "road-test": len([d for d in os.listdir(cfg["road_test"]["dir"])
                                if os.path.isdir(os.path.join(cfg["road_test"]["dir"], d))]
                               if cfg.get("road_test") else 0),
              "jira": 1 if cfg.get("jira") else 0}
    return payload, counts, prov, src


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--only", default="", help="逗号分隔：summary,test-plan,function,pressure,road-test,jira")
    ap.add_argument("--dry-run", action="store_true", help="只解析并打印映射结果，不调接口")
    ap.add_argument("--env", default="", choices=["", "prod", "dev"])
    ap.add_argument("--out-dir", default="")
    ap.add_argument("--no-sidecar", action="store_true",
                    help="忽略 build_report 落的 sidecar，硬要从 xlsx 反解析（调试用）")
    a = ap.parse_args()

    cfg = json.load(open(a.config, encoding="utf-8"))
    plat = cfg.get("platform") or {}
    if not a.dry_run and not plat.get("enabled"):
        print("SKIP: 配置里没有 platform 段或 platform.enabled=false")
        return
    do = [x.strip() for x in (a.only or ",".join(plat.get("do") or
            ["summary", "test-plan", "function", "pressure", "road-test", "jira"])).split(",") if x.strip()]

    report = cfg["out_report"]
    if not os.path.exists(report):
        sys.exit("报告不存在：%s（先跑 build_report）" % report)
    wb = openpyxl.load_workbook(report, data_only=True)
    sp = "" if a.no_sidecar else sidecar_path(cfg, plat)
    side = json.load(open(sp, encoding="utf-8")) if sp else None
    payload, counts, prov, src = build_payloads(cfg, wb, plat, side)

    out_dir = a.out_dir or plat.get("out_dir") or os.path.join(
        os.path.dirname(report), "平台导出")
    env = a.env or plat.get("env") or "prod"
    print("[platform] 报告=%s\n           环境=%s  输出=%s\n           数据量=%s  来源=%s" % (
        os.path.basename(report), env, out_dir, counts,
        ("sidecar: " + os.path.basename(sp)) if sp else "解析报告 xlsx（没找到 sidecar，建议重跑 build_report）"))
    if a.dry_run:
        s = payload["summary"]
        print("\n摘要字段来源（固定值不用每次输入）：")
        for k in sorted(s, key=lambda x: (prov.get(x) != "固定值", x)):
            v = s[k]
            v = ("<%d 项>" % len(v)) if isinstance(v, (list, dict)) else str(v)[:56]
            print("   %-24s %-12s %s" % (k, prov.get(k, "报告"), v))
        print("常规功能 reportItems 前 2 条：")
        print(json.dumps(payload["function"]["reportItems"][:2], ensure_ascii=False, indent=2))
        print("常规压力 items 前 1 条：")
        print(json.dumps(payload["pressure"]["items"][:1], ensure_ascii=False, indent=2))
        return

    c = ReportPlatformClient(env=env)
    os.makedirs(out_dir, exist_ok=True)
    manifest, failed = [], []
    for kind in do:
        try:
            if kind == "summary":
                j = c.summary_report(summary_payload(**payload["summary"]))
            elif kind == "test-plan":
                j = c.test_plan(payload["test-plan"]["planItems"], payload["test-plan"]["version"])
            elif kind == "function":
                j = c.function_report(payload["function"]["reportItems"])
            elif kind == "pressure":
                j = c.pressure_report(payload["pressure"]["items"])
            elif kind == "road-test":
                rt = cfg.get("road_test") or {}
                if not rt:
                    print("  路测 SKIP：配置没有 road_test 段")
                    continue
                j = c.road_test_from_dir(rt["dir"], payload["summary"]["versionNumber"],
                                         rt.get("result", ""), rt.get("remark", ""))
            elif kind == "jira":
                jr = cfg.get("jira") or {}
                url = plat.get("jira_url") or (
                    (jr.get("base_url") or "https://ticket.ikotek.com") + "/issues/?jql=" +
                    __import__("urllib.parse", fromlist=["quote"]).quote(jr.get("jql", ""), safe=""))
                print("  JIRA %s" % url[:110])
                g = c.jira_generate(jr["account"], jr["password"], url,
                                    payload["summary"]["versionNumber"])
                j = c.jira_wait(g["reportId"], timeout=float(plat.get("jira_timeout", 900)),
                                verbose=False)
            else:
                print("  未知类型：%s" % kind)
                continue
            name = j.get("fileName") or ("%s_%s.xlsx" % (kind, time.strftime("%Y%m%d")))
            path = c.download(j["downloadUrl"], os.path.join(out_dir, name))
            manifest.append({"kind": kind, "fileName": name, "local": path,
                             "reportId": j.get("reportId", ""), "downloadUrl": j["downloadUrl"]})
            print("  %-10s OK  %s" % (kind, path))
        except ApiError as e:
            failed.append({"kind": kind, "error": str(e)[:500]})
            print("  %-10s FAIL %s" % (kind, str(e)[:260]), file=sys.stderr)
    mpath = os.path.join(out_dir, "推送清单_%s_%s.json" % (
        cfg["version"], time.strftime("%Y%m%d%H%M%S")))
    json.dump({"env": env, "report": report, "ok": manifest, "failed": failed},
              open(mpath, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("\n成功 %d / 失败 %d，清单：%s" % (len(manifest), len(failed), mpath))
    if failed:
        sys.exit("有接口推送失败，见上面报错原文与清单")


if __name__ == "__main__":
    main()
