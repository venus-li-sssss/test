# -*- coding: utf-8 -*-
"""清理历史报告里「不属于本项目」的版本数据（模板残留）。

用法:
    python purge_versions.py --config <purge.json>

purge.json:
{
  "base_report": "…历史报告.xlsx",
  "out_report":  "…清理后的干净底稿.xlsx",
  "keep": ["763"],                       # 保留哪些版本（列组名 / 矩阵行名 / 压力组版本）
  "foreign_tokens": ["QDM522","QDM559","QDM565","EC800M","NBEBIKE"],
  "plan_keep_last": 0                    # 测试计划里额外保留最后 N 个块（一般 0）
}

处理的四个 Sheet：
  常规功能  —— 每个版本占 4 列（从 F 起），表头「<ver>测试结果」；不在 keep 的整组删列
  摘要      —— 功能矩阵每个版本占 2 行（B 列为版本名）；不在 keep 的整对删除，下方内容整块上移
  测试计划  —— 每个版本块（E 列有功能项、C 列有版本）；块里出现 foreign_tokens 的整块删除
  常规压力  —— 每个版本占 7 列（从 H 起），表头「测试版本」；组内版本不在 keep 的整组删列

⚠️ openpyxl 的 delete_rows/delete_cols 不会搬「隐藏标记」「行高」「列宽」「合并区」，
   所以行删除一律改成「整块上移」，列删除后显式重设隐藏标记与列宽。
"""
import argparse
import copy
import json
import os
import re
import sys

import openpyxl
from openpyxl.utils import get_column_letter, column_index_from_string
from openpyxl.worksheet.hyperlink import Hyperlink


# ---------------------------------------------------------------- 整块搬运
def grab(ws, r1, r2, c1, c2):
    """把 [r1..r2] x [c1..c2] 的值/样式/超链接/行高 + 区间内合并 抓出来。"""
    data = []
    for r in range(r1, r2 + 1):
        row = []
        for c in range(c1, c2 + 1):
            cell = ws.cell(row=r, column=c)
            hl = cell.hyperlink
            row.append((cell.value, copy.copy(cell._style),
                        hl.location if hl else None, hl.target if hl else None))
        data.append((row, ws.row_dimensions[r].height))
    merges = [(m.min_row - r1, m.min_col, m.max_row - r1, m.max_col)
              for m in ws.merged_cells.ranges
              if m.min_row >= r1 and m.max_row <= r2 and m.min_col >= c1 and m.max_col <= c2]
    return data, merges


def put(ws, r1, data, merges, c1):
    for i, (row, h) in enumerate(data):
        for j, (v, st, loc, tgt) in enumerate(row):
            cell = ws.cell(row=r1 + i, column=c1 + j)
            cell.value = v
            cell._style = copy.copy(st)
            if loc or tgt:
                cell.hyperlink = Hyperlink(ref=cell.coordinate, location=loc, target=tgt)
            else:
                cell.hyperlink = None
        if h:
            ws.row_dimensions[r1 + i].height = h
    for mr1, mc1, mr2, mc2 in merges:
        try:
            ws.merge_cells(start_row=r1 + mr1, start_column=mc1,
                           end_row=r1 + mr2, end_column=mc2)
        except Exception as e:
            print("  ! 重并失败 %s" % e)


def clear(ws, r1, r2, c1, c2):
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            cell = ws.cell(row=r, column=c)
            cell.value = None
            cell.hyperlink = None


def prune_cols(ws, last):
    """删掉内容区之外的列定义（<col>）——否则 Excel 的 UsedRange 会一直延伸到 AC/BK，
    看着像右边还有一大片表，滚动/打印都别扭。"""
    n = 0
    for key in list(ws.column_dimensions.keys()):
        try:
            idx = column_index_from_string(key)
        except Exception:
            continue
        if idx > last:
            del ws.column_dimensions[key]
            n += 1
    if n:
        print("  [%s] 清掉内容区外 %d 个列定义（>%s 列）" % (ws.title, n, get_column_letter(last)))


def unmerge_from(ws, min_row, min_col=2):
    for rng in list(ws.merged_cells.ranges):
        if rng.min_row >= min_row and rng.max_col >= min_col:
            try:
                ws.unmerge_cells(str(rng))
            except Exception:
                pass


def delete_cols_keep(ws, start, n):
    """删列但保住其它合并区与列宽。

    openpyxl 的 delete_cols 既不动合并区、也不动列宽，所以：先记下全部合并与列宽 → 全解合并
    → delete_cols → 按「列的删除映射」重建合并区（完全落在删除区的丢弃，右侧整体左移 n，
    跨界的两头裁一裁）→ 按映射重设列宽。
    ⚠️ 早期版本直接 `unmerge_from(ws, 1)` 把所有合并都解掉且不恢复，导致常规功能 B 列分区合并、
      常规压力 C10:C13「升级」等全丢，表现为「测试项/功能项只写在首行、下面一片空白」。
    """
    merges = [(m.min_row, m.min_col, m.max_row, m.max_col) for m in ws.merged_cells.ranges]
    widths = {i: ws.column_dimensions[get_column_letter(i)].width
              for i in range(1, ws.max_column + 1)}
    heights = {r: ws.row_dimensions[r].height for r in range(1, ws.max_row + 1)}
    for m in list(ws.merged_cells.ranges):
        try:
            ws.unmerge_cells(str(m))
        except Exception:
            pass
    ws.delete_cols(start, n)
    end = start + n - 1
    for r1, c1, r2, c2 in merges:
        if c2 < start:
            nc1, nc2 = c1, c2
        elif c1 > end:
            nc1, nc2 = c1 - n, c2 - n
        else:
            nc1 = c1 if c1 < start else start
            nc2 = c2 if c2 > end else start - 1
            if nc2 < nc1:
                continue
        try:
            ws.merge_cells(start_row=r1, start_column=nc1, end_row=r2, end_column=nc2)
        except Exception as e:
            print("  ! 重并 %s%d:%s%d 失败：%s" % (get_column_letter(nc1), r1,
                                                  get_column_letter(nc2), r2, e))
    for i in range(1, ws.max_column + 1):
        w = widths.get(i if i < start else i + n)
        if w is not None:
            ws.column_dimensions[get_column_letter(i)].width = w
    for r, h in heights.items():                     # 行高不会被列操作影响，保险起见补一次
        if h:
            ws.row_dimensions[r].height = h


def compact_rows(ws, drops, c1=2, c2=20):
    """把 drops 覆盖的行整块删掉（下方内容上移），合并/行高/超链接一起搬。

    ⚠️ 搬完必须把「尾部多出来的行」物理删掉：clear() 只清值和超链接，样式/边框还在，
       会在表格下面留下一格一格带框线的空行（= 幽灵表格），看起来像表格没结束。
    """
    if not drops:
        return 0
    drops = sorted(drops)
    for i in range(1, len(drops)):
        if drops[i][0] != drops[i - 1][1] + 1:
            raise ValueError("drops 必须连续：%s" % drops)
    first, last_end = drops[0][0], drops[-1][1]
    shift = last_end - first + 1
    old_max = ws.max_row
    data, merges = grab(ws, last_end + 1, old_max, c1, c2)   # 先抓（合并区还在）
    unmerge_from(ws, first, c1)                              # 再解
    clear(ws, first, old_max, c1, c2)
    put(ws, first, data, merges, c1)
    for r in range(first, first + len(data)):        # 搬过来的行一律显示
        ws.row_dimensions[r].hidden = False
    tail = first + len(data)
    if tail <= old_max:                              # 删掉残留的空壳行
        ws.delete_rows(tail, old_max - tail + 1)
        for r in list(ws.row_dimensions.keys()):
            if r >= tail:
                del ws.row_dimensions[r]
        print("   ↳ 清掉尾部 %d 行空壳（r%d-%d）" % (old_max - tail + 1, tail, old_max))
    print("   ↳ 删除 %d 行（r%d-%d），下方 %d 行上移" % (shift, first, last_end, len(data)))
    return shift


# ---------------------------------------------------------------- 各 Sheet
def purge_gf(ws, keep):
    groups, c = [], 6
    while c <= ws.max_column and ws.cell(3, c).value is not None:
        groups.append((c, str(ws.cell(3, c).value)))
        c += 4
    drop = [(s, lab) for s, lab in groups if lab.replace("测试结果", "").strip() not in keep]
    for s, lab in sorted(drop, key=lambda x: -x[0]):
        delete_cols_keep(ws, s, 4)                   # 保合并、保列宽
        print("  [常规功能] 删除列组 %s（第%d列起）" % (lab, s))
    nkeep = len(groups) - len(drop)
    last = 6 + 4 * nkeep - 1 if nkeep else 5
    for cc in range(1, max(last, ws.max_column) + 1):    # 所有列都显示（隐藏标记不随删列走）
        ws.column_dimensions[get_column_letter(cc)].hidden = False
    # 标题条：「功能点测试」绿条（B2）的样式必须刷到 C..last，
    # ⚠️ 千万不能用合并区里的空单元格（F2/D2）当模板，否则绿底/粗体/边框全被刷掉；
    # ⚠️ B2 自身不能覆盖，它是整条合并区显示用的样式源。
    title_style = copy.copy(ws.cell(row=2, column=2)._style)
    for m in list(ws.merged_cells.ranges):
        if m.min_row == 2 and m.max_col > 2:
            ws.unmerge_cells(str(m))
    for cc in range(3, last + 1):
        ws.cell(row=2, column=cc)._style = copy.copy(title_style)
        al = copy.copy(ws.cell(row=2, column=cc).alignment)
        al.horizontal, al.vertical = "center", "center"
        ws.cell(row=2, column=cc).alignment = al
    al = copy.copy(ws.cell(row=2, column=2).alignment)
    al.horizontal, al.vertical = "center", "center"
    ws.cell(row=2, column=2).alignment = al
    if last > 2:
        ws.merge_cells(start_row=2, start_column=2, end_row=2, end_column=last)
    prune_cols(ws, last)
    print("  [常规功能] 标题条重并 B2:%s2，保留 %d 个版本组：%s"
          % (get_column_letter(last), nkeep, [l for _s, l in groups if l.replace("测试结果", "").strip() in keep]))


def purge_summary(ws, keep):
    OK = {"√", "x", "X", "PASS", "FAIL", "BLOCK", "N", "BLOCKED-NORUN"}
    pairs = []
    for r in range(1, ws.max_row):
        b = ws.cell(row=r, column=2).value
        if b is None:
            continue
        b = str(b).strip()
        if not re.match(r"^V?\d+$", b):              # 只认 V01/V11/V20/763 这类版本名
            continue
        nxt = [str(ws.cell(row=r + 1, column=c).value or "").strip() for c in range(3, 10)]
        if not any(nxt) or any(v.upper() not in OK for v in nxt if v):
            continue
        pairs.append((r, b))
    drops = [(r, r + 1) for r, b in pairs if b not in keep]
    print("  [摘要] 矩阵版本：%s → 删除 %s" % ([b for _r, b in pairs], [b for r, b in pairs if b not in keep]))
    if drops:
        compact_rows(ws, drops, 2, 17)
    # 兜底：清掉历史上「超链接 location 被写成单元格值」的脏格子
    for r in range(1, ws.max_row + 1):
        v = ws.cell(row=r, column=2).value
        if isinstance(v, str) and "!" in v and "$" not in v and v.endswith(("A1",)):
            ws.cell(row=r, column=2).value = None
            ws.cell(row=r, column=2).hyperlink = None


def purge_plan(ws, foreign_tokens, keep_last):
    starts = [r for r in range(1, ws.max_row + 1)
              if ws.cell(row=r, column=5).value and ws.cell(row=r, column=3).value]
    if not starts:
        return
    blocks = [(s, (starts[i + 1] - 1) if i + 1 < len(starts) else ws.max_row)
              for i, s in enumerate(starts)]
    drop = []
    for s, e in blocks:
        text = " ".join(str(ws.cell(row=r, column=c).value or "")
                        for r in range(s, e + 1) for c in range(2, 12))
        if any(t in text for t in foreign_tokens):
            drop.append((s, e))
    if keep_last:
        drop = [b for b in drop if b not in blocks[len(blocks) - keep_last:]]
    print("  [测试计划] 版本块 %s → 删除 %s" % (blocks, drop))
    if drop:
        compact_rows(ws, drop, 2, 11)


def purge_pressure(ws, keep):
    groups, c = [], 8
    while c <= ws.max_column and str(ws.cell(row=8, column=c).value or "").strip() == "测试版本":
        ver = ""
        for r in range(9, ws.max_row + 1):
            v = ws.cell(row=r, column=c).value
            if v not in (None, ""):
                ver = str(v).strip()
                break
        groups.append((c, ver))
        c += 7
    drop = [(s, v) for s, v in groups if v not in keep]
    for s, v in sorted(drop, key=lambda x: -x[0]):
        delete_cols_keep(ws, s, 7)                   # 保合并（C10:C13「升级」等）、保列宽
        print("  [常规压力] 删除版本组「%s」（第%d列起）" % (v or "空", s))
    nkeep = len(groups) - len(drop)
    last = 8 + 7 * nkeep - 1
    for cc in range(1, max(last, ws.max_column) + 1):
        ws.column_dimensions[get_column_letter(cc)].hidden = False
    prune_cols(ws, last)
    print("  [常规压力] 保留 %d 个版本组：%s" % (nkeep, [v for _s, v in groups if v in keep]))


def scan_foreign(wb, tokens):
    bad = {}
    for sh in wb.sheetnames:
        ws = wb[sh]
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str):
                    for t in tokens:
                        if t in cell.value:
                            bad.setdefault(sh, []).append("%s:%s" % (cell.coordinate, t))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding="utf-8"))
    keep = [str(k) for k in cfg["keep"]]
    ftokens = cfg.get("foreign_tokens") or ["QDM522", "QDM559", "QDM565"]

    wb = openpyxl.load_workbook(cfg["base_report"])
    print("keep =", keep)
    purge_gf(wb["常规功能"], keep)
    purge_summary(wb["摘要"], keep)
    purge_plan(wb["测试计划"], ftokens, int(cfg.get("plan_keep_last") or 0))
    purge_pressure(wb["常规压力"], keep)

    ws = wb["常规压力"]                     # 历史遗留的孤立字符
    if isinstance(ws["N9"].value, str) and ws["N9"].value.strip() in ("）", ")", ")"):
        ws["N9"].value = None
        print("  [常规压力] 清掉 N9 的孤立字符")

    # 手工指定要改写的单元格（比如压力脚本名还是别的项目的）
    for sheet, cells in (cfg.get("cell_fixes") or {}).items():
        for coord, nv in cells.items():
            wb[sheet][coord].value = nv
            print("  [fix] %s!%s = %s" % (sheet, coord, nv))

    # 摘要图例块的内部跳转超链接：历史报告里本来就是错位的（点「摘要」会跳到「测试指南」），
    # 这里按「文字 = Sheet 名」重新配对；没有对应 Sheet 的（用例概要/Sheet名称表头）清掉链接。
    if cfg.get("fix_legend_links"):
        ws = wb["摘要"]
        mapping = {"摘要": "'摘要'!A1", "测试指南": "'测试指南'!A1", "功能": "'常规功能'!A1",
                   "测试计划": "'测试计划'!A1", "常规压力": "'常规压力'!A1",
                   "问题统计表": "'问题统计表'!A1", "路测": "'路测'!A1"}
        for r in range(1, ws.max_row + 1):
            v = ws.cell(row=r, column=2).value
            if not isinstance(v, str):
                continue
            v = v.strip()
            if v in mapping:
                ws.cell(row=r, column=2).hyperlink = Hyperlink(ref="B%d" % r, location=mapping[v])
            elif v in ("用例概要", "Sheet名称", "Revision"):
                ws.cell(row=r, column=2).hyperlink = None
        print("  [fix] 摘要图例跳转链接已按 Sheet 名重新配对")

    bad = scan_foreign(wb, ftokens)
    print("\n=== 残留外来项目关键字 ===")
    if bad:
        for k, v in bad.items():
            print("  %s: %d 处 %s" % (k, len(v), v[:6]))
    else:
        print("  无")

    # 列「隐藏」标记同样不跟随 delete_cols 走，清掉这两个 Sheet 里所有遗留的隐藏列
    for sh in ("常规功能", "常规压力"):
        ws = wb[sh]
        n = 0
        for dim in ws.column_dimensions.values():
            if dim.hidden:
                dim.hidden = False
                n += 1
        if n:
            print("  [%s] 清掉 %d 个遗留隐藏列" % (sh, n))

    out = cfg["out_report"]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    wb.save(out)
    print("\nSAVED clean base: %s (%.2f MB)" % (out, os.path.getsize(out) / 1048576))


if __name__ == "__main__":
    main()
