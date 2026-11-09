# -*- coding: utf-8 -*-
"""基于历史 SystemTestReport 生成新版本系统测试报告（配置驱动）。

用法: python build_report.py --config <config.json>
配置字段说明见 SKILL.md「配置说明」。
每次运行都从 config.base_report 重新 load，天然幂等。
"""
import argparse
import copy
import json
import os
import re
import sys
import time

import openpyxl
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.styles import Color, Color as color
from openpyxl.utils import get_column_letter, column_index_from_string
from openpyxl.worksheet.hyperlink import Hyperlink


# ----------------------------------------------------------------- 取数
def _col(cells, key):
    for i, c in enumerate(cells):
        flat = str(c).replace("\n", "")
        if key == "blockReason":
            if "Blocked" in flat and "原因" in flat:
                return i
        elif key == "caseId":
            if "用例编号" in flat or "Case ID" in flat:
                return i
        elif key == "priority":
            if "优先级" in flat or "Priority" in flat:
                return i
        elif key == "result":
            if "实测结果" in flat or "Actual Result" in flat:
                return i
        elif key == "remark":
            if ("备注" in flat or "Remark" in flat) and "Blocked" not in flat:
                return i
    return None


def _find_header(rows):
    for i, r in enumerate(rows[:40]):
        cells = ["" if c is None else str(c) for c in r]
        has_id = any("用例编号" in c or "Case ID" in c for c in cells)
        has_res = any("实测结果" in c or "Actual Result" in c for c in cells)
        if has_id and has_res:
            return i, cells
    return None, None


def load_table(path, group_by):
    """返回 {group_key: [entry, ...]}，entry = {caseId,result,reason,priority}"""
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    groups = {}
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        hdr, cells = _find_header(rows)
        if hdr is None:
            continue
        idx = {k: _col(cells, k) for k in ("caseId", "priority", "result", "blockReason", "remark")}
        if idx["caseId"] is None or idx["result"] is None:
            continue
        for r in rows[hdr + 1:]:
            def g(k):
                n = idx.get(k)
                if n is None or n >= len(r) or r[n] is None:
                    return ""
                return str(r[n]).strip()
            cid, res = g("caseId"), g("result")
            if not cid or not res:
                continue
            if group_by == "sheet":
                key = ws.title
            else:
                m = re.match(r"^(.+?-\d+)-\d+$", cid)
                key = m.group(1) if m else cid
            groups.setdefault(key, []).append(
                {"caseId": cid, "result": res, "reason": g("blockReason"),
                 "remark": g("remark"), "priority": g("priority")}
            )
    wb.close()
    return groups


def aggregate(entries, default_reason=""):
    """FAIL > PASS > BLOCK"""
    if not entries:
        return None, ""
    results = [e["result"] for e in entries]
    if any(r == "FAIL" for r in results):
        return "FAIL", ""
    if any(r == "PASS" for r in results):
        return "PASS", ""
    blocked = [e for e in entries if e["result"].startswith("Blocked")]
    # 原因优先取「Blocked-NoRun原因」列；该列为空时退回「备注」列（有的表把「只测4G」写这里）
    reason = next((e["reason"] for e in blocked if e["reason"]), "")
    if not reason:
        reason = next((e.get("remark") for e in blocked if e.get("remark")), "")
    reason = reason or default_reason
    if blocked and all(e["result"] == "Blocked-NonSupport" for e in blocked):
        return "Blocked-NonSupport", reason
    return "Blocked-NoRun", reason


# ----------------------------------------------------------------- xlsx 工具
def cp_style(src, dst):
    dst._style = copy.copy(src._style)


def apply_inserts(ws, inserts, first_col=2, last_col=29):
    """多段插行（第一版=全量测试时，底稿骨架行不够用）。

    inserts = [{after_row, rows:[{num,content,priority}], style_from?}]，after_row 用**原始行号**。
    ⚠️ 顺序要点：
      1) **自下而上**插（after_row 从大到小）——已处理的插入都在下方，上方锚点行号不受扰动；
      2) **先解合并再插行**：openpyxl 的 insert_rows 会把格子切碎，插完再 unmerge 会 KeyError
         （实测 (29,2)）；插完再 merge 才是安全的；
      3) insert_rows 不会搬合并区，所以要手动：跨过插入点的**延长 n 行**，插入点下方的**整体下移 n 行**。
    """
    for it in sorted(inserts, key=lambda x: -int(x["after_row"])):
        at = int(it["after_row"])
        rows = it.get("rows") or []
        n = len(rows)
        if not n:
            continue
        keep = []
        for rng in list(ws.merged_cells.ranges):
            lo, hi = rng.min_row, rng.max_row
            if hi <= at:
                continue                                   # 在锚点上方，不动
            new = (lo, hi + n) if lo <= at < hi else (lo + n, hi + n)
            try:
                ws.unmerge_cells(str(rng))
            except Exception as e:                          # 残留占位格：解不干净也别炸
                print("  ! unmerge %s 异常：%s" % (rng, e))
            keep.append((new[0], new[1], rng.min_col, rng.max_col))
        ws.insert_rows(at + 1, n)
        for lo, hi, c1, c2 in keep:
            try:
                ws.merge_cells(start_row=lo, start_column=c1, end_row=hi, end_column=c2)
            except Exception as e:
                print("  ! 重并 %s%d:%s%d 失败：%s" % (get_column_letter(c1), lo,
                                                      get_column_letter(c2), hi, e))
        src = int(it.get("style_from") or at)
        for i, spec in enumerate(rows):
            r = at + 1 + i
            for c in range(first_col, last_col + 1):
                cp_style(ws.cell(row=src, column=c), ws.cell(row=r, column=c))
            ws.cell(row=r, column=3).value = spec.get("num")
            ws.cell(row=r, column=4).value = spec.get("content")
            ws.cell(row=r, column=5).value = spec.get("priority")
        print("[insert] r%d 之后插 %d 行：%s" % (at, n, [x.get("num") for x in rows]))

    def fmap(orig):
        """原始行号 -> 最终行号（下方累计了多少次插入就加多少）。"""
        return orig + sum(len(it.get("rows") or []) for it in inserts
                          if int(it["after_row"]) < orig)
    return fmap


def paint(cell, val, bold=False, blue_pass=False):
    """按结果给字上色（照抄历史报告的配色）：
    摘要矩阵结果行 = FAIL 红加粗 / PASS 蓝加粗 / BLOCK 黑加粗；
    常规功能结果列 = 只有 FAIL 是红字，其余默认黑字。"""
    f = copy.copy(cell.font)
    f.bold = bold
    if val == "FAIL":
        f.color = color("FFFF0000")
    elif val == "PASS" and blue_pass:
        f.color = color("FF0000FF")
    else:
        f.color = color("FF000000")
    cell.font = f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding="utf-8"))

    VER = cfg["version"]
    FULL = cfg["full_version"]
    PREV = cfg.get("prev_version") or ""
    TESTER = cfg.get("tester") or ""
    NDATE = cfg.get("test_date") or ""
    PERIOD = cfg.get("test_period") or NDATE

    # 本次写进报告的「版本级数据」同步落一份 sidecar（<out_report>.data.json），
    # 让 platform_push 直接用，不必再从 xlsx 里反解析历史报告（反解析很脆弱）。
    written = {
        "meta": {"version": VER, "full_version": FULL, "prev_version": PREV,
                 "tester": TESTER, "test_date": NDATE, "test_period": PERIOD,
                 "base_report": cfg.get("base_report"), "out_report": cfg.get("out_report"),
                 "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")},
        "summary_text": (cfg.get("summary") or {}).get("text")
        or "".join(seg for _c, seg in ((cfg.get("summary") or {}).get("runs") or [])),
        "matrix": (cfg.get("summary") or {}).get("matrix") or [],
        "function": [], "plan": [], "bugs": {"new": [], "old": [], "counts": {}},
        "pressure": [], "road_test": cfg.get("road_test") or {},
    }

    # --- 执行表
    tables = []
    for t in cfg.get("exec_tables") or []:
        tables.append(load_table(t["file"], t.get("group_by") or "case_prefix"))
        n = sum(len(v) for v in tables[-1].values())
        print("[exec] %s  groups=%d cases=%d" % (os.path.basename(t["file"]), len(tables[-1]), n))

    def pick(table_i, key):
        tb = tables[table_i]
        for k in tb:
            if k == key:
                return tb[k]
        for k, v in tb.items():
            if k == key:
                return v
        for k, v in tb.items():
            if k.startswith(key + "-") or k == key:
                return v
        # 精确 caseId 兜底
        for k, v in tb.items():
            for e in v:
                if e["caseId"] == key:
                    return [e]
        return []

    wb = openpyxl.load_workbook(cfg["base_report"])

    # ---------------- 1. 常规功能
    ws = wb["常规功能"]
    if cfg.get("gf_inserts"):
        apply_inserts(ws, cfg["gf_inserts"])       # after_row 用原始行号；gf_rows 行号用插入后的最终行号
    for row, spec in (cfg.get("gf_relabel") or {}).items():
        r = int(row)
        ws.cell(row=r, column=3).value = spec.get("num")
        ws.cell(row=r, column=4).value = spec.get("content")
        if spec.get("priority") is not None:
            ws.cell(row=r, column=5).value = spec.get("priority")
    for row in cfg.get("gf_clear_rows") or []:     # 底稿里属于别的项目的说明行文字
        ws.cell(row=int(row), column=4).value = None
    ins = cfg.get("gf_insert") or {}
    if ins:
        for pair in ins.get("merges") or []:
            try:
                ws.unmerge_cells(pair[0])
            except Exception:
                pass
        ws.insert_rows(int(ins["at_row"]), int(ins.get("count") or 1))
        for pair in ins.get("merges") or []:
            ws.merge_cells(pair[1])
    last_row = (ins.get("at_row", 1) + ins.get("count", 0) + 40) if ins else ws.max_row
    for r, spec in (cfg.get("gf_new_rows") or {}).items():
        r = int(r)
        src = int(ins.get("style_from") or (r - 1))
        for c in range(2, 30):
            cp_style(ws.cell(row=src, column=c), ws.cell(row=r, column=c))
        ws.cell(row=r, column=3).value = spec.get("num")
        ws.cell(row=r, column=4).value = spec.get("content")
        ws.cell(row=r, column=5).value = spec.get("priority")
    for r in range(3, last_row + 1):
        for off in range(4):
            cp_style(ws.cell(row=r, column=22 + off), ws.cell(row=r, column=26 + off))
    ws.cell(row=3, column=26).value = "%s测试结果" % VER
    ws.cell(row=3, column=27).value = "Blocked-NoRun原因"
    ws.cell(row=3, column=28).value = "测试人员"
    ws.cell(row=3, column=29).value = "Fail或者Block的原因"
    for off in range(4):
        src_col = ws.column_dimensions[get_column_letter(22 + off)].width
        ws.column_dimensions[get_column_letter(26 + off)].width = src_col

    # 顶部标题条（「功能点测试」那一行）必须横跨整张表合并成一条，
    # 否则隐藏旧版本列之后中间断开，看起来像两张独立的表。
    last_col = 26 + 3                       # 新列组的最后一列（AC）
    if cfg.get("gf_title_merge"):
        for m in [x for x in ws.merged_cells.ranges]:
            if m.min_row == 2 and m.min_col >= 3:
                ws.unmerge_cells(str(m))
        band = copy.copy(ws.cell(row=2, column=4)._style)   # 原合并带的样式
        for c in range(3, last_col + 1):
            ws.cell(row=2, column=c)._style = copy.copy(band)
        ws.merge_cells(start_row=2, start_column=2, end_row=2, end_column=last_col)
        print("[gf] 标题条合并 B2:%s2" % get_column_letter(last_col))

    # 标题条文字居中（2026-10-23 用户要求「功能点测试」绿条居中显示）
    if cfg.get("gf_title_center"):
        for c in range(2, last_col + 1):
            al = copy.copy(ws.cell(row=2, column=c).alignment)
            al.horizontal = "center"
            al.vertical = "center"
            ws.cell(row=2, column=c).alignment = al
        print("[gf] 标题条文字居中")

    # B 列（测试项/分区）合并区重建：插行后模板原合并没跟着扩，按最终几何重并
    # gf_col_merges = ["B4:B8", "B18:B23", ...]（只并可见分区行，隐藏行不并入，避免居中字跑到隐藏区）
    for rng in cfg.get("gf_col_merges") or []:
        lo_s, hi_s = rng.split(":")
        lo, hi = int(lo_s[1:]), int(hi_s[1:])
        for m in [x for x in ws.merged_cells.ranges]:
            if m.min_col == 2 and m.max_col == 2 and m.max_row >= lo and m.min_row <= hi:
                try:
                    ws.unmerge_cells(str(m))
                except Exception:
                    pass
        ws.merge_cells(start_row=lo, start_column=2, end_row=hi, end_column=2)
        al = copy.copy(ws.cell(row=lo, column=2).alignment)
        al.horizontal, al.vertical = "center", "center"
        ws.cell(row=lo, column=2).alignment = al
        print("[gf] B列合并 %s（%s）" % (rng, ws.cell(row=lo, column=2).value))

    for r, spec in (cfg.get("gf_rows") or {}).items():
        r = int(r)
        num = ws.cell(row=r, column=3).value
        content = ws.cell(row=r, column=4).value
        label = "%s/%s" % (num, content)
        if spec.get("label") and spec["label"].replace(" ", "") not in label.replace(" ", ""):
            print("  ! label 不匹配 r%d: 配置=%s 实际=%s" % (r, spec["label"], label))
        force = spec.get("force") or {}
        if force.get("result"):
            res, reason = force["result"], force.get("block_reason") or ""
        else:
            entries = []
            for s in spec.get("sources") or []:
                for k in s.get("keys") or []:
                    entries.extend(pick(int(s["table"]), k))
            res, reason = aggregate(entries, spec.get("block_reason") or "")
        if spec.get("block_reason") and res and res.startswith("Blocked"):
            reason = spec["block_reason"]
        ws.cell(row=r, column=26).value = res or None
        ws.cell(row=r, column=27).value = reason or None
        ws.cell(row=r, column=28).value = TESTER if res in ("PASS", "FAIL") else None
        ws.cell(row=r, column=29).value = (force.get("fail_reason") or None) if res == "FAIL" else None
        if res:
            paint(ws.cell(row=r, column=26), res)   # FAIL 红字，其余黑字
        # 分类（B 列）通常是竖向合并，值只在组首行 -> 向上找第一个非空
        cat = ""
        for rr in range(r, 2, -1):
            v = ws.cell(row=rr, column=2).value
            if v and "功能点测试" not in str(v):
                cat = str(v).strip()
                break
        written["function"].append({
            "row": r, "sheetName": cat or "常规功能", "testNumber": str(num or ""),
            "testItem": str(content or num or ""), "testContent": str(content or ""),
            "testDescription": str(spec.get("desc") or ""),
            "priority": str(ws.cell(row=r, column=5).value or ""),
            "result": res or "", "blockReason": reason if (res or "").startswith("Blocked") else "",
            "tester": TESTER if res in ("PASS", "FAIL") else "",
            "failReason": force.get("fail_reason") or "",
            "subCases": spec.get("subCases") or []})
        print("  r%-3d %-22s -> %s %s" % (r, label[:22], res, reason[:24]))
    for r, spec in (cfg.get("gf_new_rows") or {}).items():
        ws.cell(row=int(r), column=26).value = spec.get("result")
        ws.cell(row=int(r), column=28).value = TESTER
        written["function"].append({
            "row": int(r), "sheetName": str(spec.get("sheet") or "常规功能"),
            "testNumber": str(spec.get("num") or ""), "testItem": str(spec.get("content") or ""),
            "testContent": str(spec.get("content") or ""), "testDescription": "",
            "priority": str(spec.get("priority") or ""), "result": spec.get("result") or "",
            "blockReason": "", "tester": TESTER, "failReason": "", "subCases": []})

    # ---------------- 2. 摘要
    ws = wb["摘要"]
    ws[cfg.get("summary", {}).get("version_cell", "K8")].value = FULL
    ws[cfg.get("summary", {}).get("tester_cell", "D11")].value = TESTER
    ws[cfg.get("summary", {}).get("date_cell", "D12")].value = NDATE
    for cell, val in ((cfg.get("summary", {}).get("cells") or {}).items()):
        ws[cell] = val          # 第一版/新项目：底稿里属于别的项目的项目级字段按这里清空或改写
        if val in ("", None):
            ws[cell].hyperlink = None   # 带链接的单元格只清文字会留下「显示成 URL」的链接
    sm = cfg.get("summary", {})
    tc = sm.get("text_cell", "C19")
    runs = sm.get("runs")
    if runs:
        # 富文本：测试小结里「测试结果判定的值」和「测试风险各条」是红字，其余黑字
        ws[tc].value = CellRichText(*[
            TextBlock(InlineFont(sz=10, rFont="微软雅黑", color=Color(rgb=c)), s) for c, s in runs
        ])
    else:
        ws[tc].value = sm.get("text") or None
    legend_start = None
    for r in range(1, ws.max_row + 1):
        if ws.cell(row=r, column=2).value == "Sheet名称":
            legend_start = r
            break
    if legend_start:
        m1, m2 = legend_start - 1, legend_start
        # 先记下原本那条「空白分隔行」的样式（无框线），后面用来清掉旧图例留下的框线
        blank_styles = [copy.copy(ws.cell(row=m1, column=c)._style) for c in range(2, 10)]
        legend = []
        for r in range(legend_start, ws.max_row + 1):
            b = ws.cell(row=r, column=2)
            if not b.value and not ws.cell(row=r, column=3).value:
                break
            # 每一行的样式必须逐行存下来（黄底表头行、说明行的字体/边框都不一样），
            # 统一抄某一行的样式会把「Sheet名称」那行的黄色底纹和说明行的对齐/颜色弄丢
            legend.append((b.value, ws.cell(row=r, column=3).value,
                           b.hyperlink.location if b.hyperlink else None,
                           [copy.copy(ws.cell(row=r, column=c)._style) for c in range(2, 9)]))
        lr_end = legend_start + len(legend) - 1
        for rng in [x for x in ws.merged_cells.ranges]:
            if rng.min_row >= legend_start and rng.min_col >= 3:
                ws.unmerge_cells(str(rng))
        for r in range(legend_start, lr_end + 1):
            for c in range(2, 9):
                ws.cell(row=r, column=c).value = None
        for r in range(m1, lr_end + 1):
            ws.cell(row=r, column=2).hyperlink = None
            ws.cell(row=r, column=3).hyperlink = None
        for c in range(2, 10):
            cp_style(ws.cell(row=m1 - 2, column=c), ws.cell(row=m1, column=c))
        for c in range(3, 10):
            cp_style(ws.cell(row=m1 - 1, column=c), ws.cell(row=m2, column=c))
        matrix = cfg.get("summary", {}).get("matrix") or []
        for i, v in enumerate(matrix):
            ws.cell(row=m1, column=3 + i).value = "x" if v == "BLOCK" else "√"
            ws.cell(row=m2, column=3 + i).value = v
            paint(ws.cell(row=m2, column=3 + i), v, bold=True, blue_pass=True)
        ws.cell(row=m1, column=2).value = VER
        ws.merge_cells(start_row=m1, start_column=2, end_row=m2, end_column=2)
        # 「当前版本」汇总行（历史报告里它每版都同步成最新版本的值，B 列不带版本号）
        cur = cfg.get("summary", {}).get("current_row")
        if cur:
            cr = int(cur[0]) if isinstance(cur, (list, tuple)) else int(cur)
            for i, v in enumerate(matrix):
                ws.cell(row=cr, column=3 + i).value = "x" if v == "BLOCK" else "√"
                ws.cell(row=cr + 1, column=3 + i).value = v
        # 图例块必须紧跟在本版本两行之后（m2 的下下行），不能直接接在原位置后面
        new_start = legend_start + 2
        # 中间那行「空行」要把旧图例残留的框线清干净，否则两张表会连成一张
        for r in range(m2 + 1, new_start):
            for c in range(2, 10):
                ws.cell(row=r, column=c).value = None
                ws.cell(row=r, column=c)._style = copy.copy(blank_styles[c - 2])
        for i, (x, y, link, styles) in enumerate(legend):
            rr = new_start + i
            ws.cell(row=rr, column=2).value = x
            ws.cell(row=rr, column=3).value = y
            for j, st in enumerate(styles):
                ws.cell(row=rr, column=2 + j)._style = copy.copy(st)
            # 下方那张「Sheet名称/对应内容简述」表要左对齐（历史报告是右对齐，用户要求改左）
            if cfg.get("summary", {}).get("legend_left_align", True):
                for col in (2, 3):
                    cell = ws.cell(row=rr, column=col)
                    al = copy.copy(cell.alignment)
                    al.horizontal = "left"
                    cell.alignment = al
            if link:
                ws.cell(row=rr, column=2).hyperlink = Hyperlink(ref="B%d" % rr, location=link)
            ws.merge_cells(start_row=rr, start_column=3, end_row=rr, end_column=7)

    # ---------------- 3. 测试计划
    plan = cfg.get("plan") or []
    if plan:
        start = int(cfg.get("plan_start_row") or (ws.max_row + 1))
        ws = wb["测试计划"]
        start = int(cfg.get("plan_start_row") or 18)
        for i, p in enumerate(plan):
            r = start + i
            src = start - 6 + i
            for c in range(2, 12):
                cp_style(ws.cell(row=src, column=c), ws.cell(row=r, column=c))
            # 历史块里 版本/日期 用的是引用摘要的公式，照抄这个习惯
            use_formula = cfg.get("plan_use_formulas", True)
            # 每个版本块的「序号」都从 1 开始（历史块里 QDM522 块和 V20 块的序号都是 1）
            ws.cell(row=r, column=2).value = (cfg.get("plan_start_no", 1) if i == 0 else None)
            ws.cell(row=r, column=3).value = "=摘要!K8" if (i == 0 and use_formula) else (FULL if i == 0 else None)
            ws.cell(row=r, column=4).value = PERIOD if i == 0 else None
            ws.cell(row=r, column=5).value = p.get("item")
            ws.cell(row=r, column=6).value = p.get("count")
            ws.cell(row=r, column=7).value = p.get("manpower")
            ws.cell(row=r, column=8).value = p.get("status")
            ws.cell(row=r, column=9).value = "=摘要!D12" if use_formula else NDATE
            ws.cell(row=r, column=10).value = "=摘要!D12" if use_formula else NDATE
            ws.cell(row=r, column=11).value = p.get("remark") or None
            # 状态列：FAIL 红字、PASS 黑字（照抄历史报告的配色）
            paint(ws.cell(row=r, column=8), p.get("status"))
        end = start + len(plan) - 1
        for col in (2, 3, 4):
            ws.merge_cells(start_row=start, start_column=col, end_row=end, end_column=col)
        written["plan"] = [{
            "seqNo": int(cfg.get("plan_start_no", 1)) + i, "item": p.get("item"),
            "count": p.get("count"), "manpower": p.get("manpower"),
            "status": p.get("status"), "planEndDate": NDATE,
            "actualEndDate": p.get("actual_end_date") or NDATE,
            "remark": p.get("remark") or ""} for i, p in enumerate(plan)]

    # ---------------- 4. 问题统计表
    ws = wb["问题统计表"]
    bugs = []
    jpath = (cfg.get("jira") or {}).get("out")
    if jpath and os.path.exists(jpath):
        bugs = json.load(open(jpath, encoding="utf-8"))
    remarks = cfg.get("bug_remarks") or {}
    bug_rows = [[b["key"], b.get("project", ""), b.get("severity", ""), b.get("status", ""),
                 b.get("desc", ""), b.get("found_version", ""), b.get("st_review", ""),
                 b.get("sw_review", ""), remarks.get(b["key"], "")] for b in bugs]
    new_keys = set(cfg.get("new_bugs") or [])
    NEW = [r for r in bug_rows if r[0] in new_keys]
    OLD = [r for r in bug_rows if r[0] not in new_keys]
    ws.cell(row=7, column=3).value = len(NEW)
    ws.cell(row=8, column=3).value = len(OLD)
    for i, sev in enumerate(("A-Critical", "B-Major", "C-Normal", "D-Minor", "E-Enhancement")):
        ws.cell(row=9 + i, column=3).value = sum(1 for r in bug_rows if r[2] == sev)

    def _bd(rows):
        return [{"key": r[0], "project": r[1], "severity": r[2], "status": r[3], "desc": r[4],
                 "found_version": r[5], "st_review": r[6], "sw_review": r[7], "remark": r[8]}
                for r in rows]
    written["bugs"] = {
        "new": _bd(NEW), "old": _bd(OLD),
        "counts": {"new": len(NEW), "old": len(OLD),
                   "bySeverity": {sev: sum(1 for r in bug_rows if r[2] == sev)
                                  for sev in ("A-Critical", "B-Major", "C-Normal", "D-Minor",
                                              "E-Enhancement")}},
        "jql": (cfg.get("jira") or {}).get("jql") or ""}
    # 先在覆盖之前抓住原表的三种行样式：新增数据行(22) / 「历史bug」表头(24) / 历史数据行(25)
    sty_new = [copy.copy(ws.cell(row=22, column=c)._style) for c in range(2, 11)]
    sty_hdr = [copy.copy(ws.cell(row=24, column=c)._style) for c in range(2, 11)]
    sty_old = [copy.copy(ws.cell(row=25, column=c)._style) for c in range(2, 11)]

    start_new = 22
    hdr_old = start_new + len(NEW)
    start_old = hdr_old + 1
    # 先清空整段（原表可能有更多行，不清会留下重复的旧记录）
    for r in range(start_new, start_new + 40):
        for c in range(2, 11):
            ws.cell(row=r, column=c).value = None
            ws.cell(row=r, column=c).hyperlink = None   # 只清值会留下「没文字却有链接」的格子
    for i, row in enumerate(NEW):
        r = start_new + i
        for c in range(2, 11):
            ws.cell(row=r, column=c)._style = copy.copy(sty_new[c - 2])
        for c, v in enumerate(row, start=2):
            ws.cell(row=r, column=c).value = v or None
    for c in range(2, 11):
        ws.cell(row=hdr_old, column=c)._style = copy.copy(sty_hdr[c - 2])
    ws.cell(row=hdr_old, column=2).value = "历史bug"
    for i, row in enumerate(OLD):
        r = start_old + i
        for c in range(2, 11):
            ws.cell(row=r, column=c)._style = copy.copy(sty_old[c - 2])
        for c, v in enumerate(row, start=2):
            ws.cell(row=r, column=c).value = v or None
    if PREV:
        for r in (15, 16, 17):
            cell = ws.cell(row=r, column=3)
            old = cell.value
            if isinstance(old, str) and old:
                new = old.replace(PREV, VER)
                cell.value = new
                cell.hyperlink = Hyperlink(ref="C%d" % r, target=new)
    for r, u in (cfg.get("bug_links") or {}).items():   # 第一版/新项目：三条链接直接给定
        cell = ws.cell(row=int(r), column=3)
        cell.value = u
        cell.hyperlink = Hyperlink(ref="C%d" % int(r), target=u)

    # ---------------- 5. 常规压力
    ws = wb["常规压力"]
    # 行左侧标签按新项目改写（序号/功能项/测试内容/脚本/优先级/网络设置 = 列2~7）
    # 注意：功能项列常见竖向合并，非锚点格写入会抛异常，逐个 try 保护
    for r, spec in (cfg.get("pressure_relabel") or {}).items():
        rr = int(r)
        for col, key in ((2, "seq"), (3, "item"), (4, "content"),
                         (5, "script"), (6, "priority"), (7, "network")):
            if key in spec:
                try:
                    ws.cell(row=rr, column=col).value = spec.get(key)
                except AttributeError:
                    print("  ! 压力 r%d c%d 在合并区内，跳过(%s)" % (rr, col, key))
        print("[pressure] r%d 标签: %s" % (rr, spec))
    for r, vals in (cfg.get("pressure") or {}).items():
        for off, v in enumerate(vals):
            cp_style(ws.cell(row=int(r), column=8 + off), ws.cell(row=int(r), column=57 + off))
            ws.cell(row=int(r), column=57 + off).value = v or None
        # 测试结果列（组内第 4 列）：FAIL 红字、其余黑字
        paint(ws.cell(row=int(r), column=60), vals[3] if len(vals) > 3 else None)

        def _lb(col):
            v = ws.cell(row=int(r), column=col).value
            return "" if v is None else str(v).strip()
        written["pressure"].append({
            "row": int(r), "seqNo": int(_lb(2) or 0) if _lb(2).isdigit() else _lb(2),
            "functionItem": _lb(3), "testContent": _lb(4), "scriptName": _lb(5),
            "priority": _lb(6), "networkSetting": _lb(7),
            "version": vals[0] if len(vals) > 0 else "", "device": vals[1] if len(vals) > 1 else "",
            "duration": vals[2] if len(vals) > 2 else "", "result": vals[3] if len(vals) > 3 else "",
            "statistics": vals[4] if len(vals) > 4 else "", "tester": vals[5] if len(vals) > 5 else "",
            "remark": vals[6] if len(vals) > 6 else ""})
    for off in range(7):
        src = ws.cell(row=8, column=8 + off)
        cp_style(src, ws.cell(row=8, column=57 + off))
        ws.cell(row=8, column=57 + off).value = src.value   # 表头照抄第一个版本组
        ws.column_dimensions[get_column_letter(57 + off)].width = \
            ws.column_dimensions[get_column_letter(8 + off)].width
    for r in cfg.get("pressure_hide_rows") or []:
        ws.row_dimensions[int(r)].hidden = True

    # ---------------- 6. 隐藏旧版本的数据（本技能的核心约定）
    # 有新版本数据后，之前所有版本的行/列都要隐藏起来，报告里只露出最新版本
    for sheet_name, spec in (cfg.get("hide") or {}).items():
        s = wb[sheet_name]
        for rng in spec.get("cols") or []:
            if ":" in rng:
                lo, hi = rng.split(":")
                for i in range(column_index_from_string(lo), column_index_from_string(hi) + 1):
                    s.column_dimensions[get_column_letter(i)].hidden = True
            else:
                s.column_dimensions[rng].hidden = True
        for r in spec.get("rows") or []:
            s.row_dimensions[int(r)].hidden = True
        # 底稿里本来就隐藏、本轮却有数据的行要显式放开（hide 只加不减）
        for r in spec.get("unhide_rows") or []:
            s.row_dimensions[int(r)].hidden = False
        print("[hide] %s cols=%s rows=%s unhide=%s" % (sheet_name, spec.get("cols"), spec.get("rows"), spec.get("unhide_rows")))

    out = cfg["out_report"]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    wb.save(out)
    print("SAVED: %s (%.1f MB)" % (out, os.path.getsize(out) / 1048576))

    # sidecar 落盘（platform_push 优先读它，不再反解析 xlsx）
    dpath = os.path.splitext(out)[0] + ".data.json"
    if cfg.get("platform", {}).get("data_file"):
        dpath = cfg["platform"]["data_file"]
    json.dump(written, open(dpath, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("DATA : %s  功能%d 计划%d 缺陷%d 压力%d" % (
        dpath, len(written["function"]), len(written["plan"]),
        len(written["bugs"]["new"]) + len(written["bugs"]["old"]), len(written["pressure"])))


if __name__ == "__main__":
    main()
