# -*- coding: utf-8 -*-
"""用 Excel 自己（COM）清掉外来版本数据 —— 合并区/行高/列宽/边框/名称全部由 Excel 原生处理，
不会出现 openpyxl 手删导致的断框、幽灵行、合并错位。

用法: python purge_via_excel.py --src <原报告> --out <干净底稿> --keep 763
"""
import argparse
import os
import sys

import win32com.client as win32
XL_TO_LEFT, XL_CENTER = -4159, -4108   # Excel 常量：xlToLeft / xlCenter

sys.stdout.reconfigure(encoding="utf-8")


def num2col(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--keep", default="763")
    ap.add_argument("--fix10", default="562平台IOT升级压力_V03.py")
    ap.add_argument("--fix12", default="QDM562_组合升级压力_V01.py")
    a = ap.parse_args()
    keep = a.keep

    app = win32.DispatchEx("Excel.Application")
    app.Visible = False
    app.DisplayAlerts = False
    app.AskToUpdateLinks = False
    wb = app.Workbooks.Open(os.path.abspath(a.src))
    try:
        # ---------- 常规功能：每版本 4 列（从 F 起），表头第 3 行
        ws = wb.Worksheets("常规功能")
        groups, c = [], 6
        while ws.Cells(3, c).Value:
            groups.append((c, str(ws.Cells(3, c).Value)))
            c += 4
        print("[常规功能] 版本组:", groups)
        for c, lab in sorted(groups, key=lambda x: -x[0]):
            ver = lab.replace("测试结果", "").strip()
            if ver not in keep:
                ws.Range(ws.Columns(c), ws.Columns(c + 3)).Delete(Shift=XL_TO_LEFT)
                print("  删除列组", lab, "→", num2col(c), "-", num2col(c + 3))
        # 标题条合并区跟着 Excel 自动调整；再居中一次
        last = 6 + 4 * sum(1 for _c, l in groups if l.replace("测试结果", "").strip() in keep) - 1
        ws.Range(ws.Cells(2, 2), ws.Cells(2, last)).HorizontalAlignment = XL_CENTER
        ws.Range(ws.Cells(2, 2), ws.Cells(2, last)).VerticalAlignment = XL_CENTER

        # ---------- 常规压力：每版本 7 列（从 H 起），表头第 8 行
        ws = wb.Worksheets("常规压力")
        groups, c = [], 8
        while str(ws.Cells(8, c).Value or "").strip() == "测试版本":
            ver = ""
            r = 9
            while r <= ws.UsedRange.Rows.Count + 8:
                v = ws.Cells(r, c).Value
                if v not in (None, ""):
                    ver = str(v).strip()
                    break
                r += 1
            groups.append((c, ver))
            c += 7
        print("[常规压力] 版本组:", groups)
        for c, ver in sorted(groups, key=lambda x: -x[0]):
            if ver not in keep:
                ws.Range(ws.Columns(c), ws.Columns(c + 6)).Delete(Shift=XL_TO_LEFT)
                print("  删除版本组", ver or "(空)", "→", num2col(c), "-", num2col(c + 6))
        ws.Range("E10").Value = a.fix10
        ws.Range("E12").Value = a.fix12
        if str(ws.Range("N9").Value or "").strip() in ("）", ")"):
            ws.Range("N9").Value = None

        # ---------- 摘要：功能矩阵每版本 2 行（B 列版本名）
        ws = wb.Worksheets("摘要")
        pairs, r = [], 1
        used = ws.UsedRange.Rows.Count
        while r <= used:
            v = ws.Cells(r, 2).Value
            if v is not None:
                s = str(v).strip()
                if s.startswith("V") or s.isdigit():
                    pairs.append((r, s))
            r += 1
        print("[摘要] 矩阵版本:", [p[1] for p in pairs])
        drop = [(r_, s) for r_, s in pairs if s not in keep]
        for r_, s in sorted(drop, key=lambda x: -x[0]):
            ws.Rows("%d:%d" % (r_, r_ + 1)).Delete()
            print("  删除矩阵行对", s, "→ r%d-%d" % (r_, r_ + 1))

        # ---------- 测试计划：块里出现别的项目就整块删（自下而上）
        ws = wb.Worksheets("测试计划")
        starts = [r for r in range(1, ws.UsedRange.Rows.Count + 1)
                  if ws.Cells(r, 5).Value and ws.Cells(r, 3).Value]
        blocks = [(s, (starts[i + 1] - 1) if i + 1 < len(starts) else ws.UsedRange.Rows.Count)
                  for i, s in enumerate(starts)]
        print("[测试计划] 块:", blocks)
        for s, e in sorted(blocks, key=lambda x: -x[0]):
            txt = " ".join(str(ws.Cells(r, c).Value or "")
                           for r in range(s, e + 1) for c in range(2, 12))
            if any(t in txt for t in ("QDM522", "QDM559", "QDM565", "EC800M", "NBEBIKE")):
                ws.Rows("%d:%d" % (s, e)).Delete()
                print("  删除外来块 r%d-%d" % (s, e))

        # ---------- 摘要图例跳转链接按文字重新配对
        lm = {"摘要": "'摘要'!A1", "测试指南": "'测试指南'!A1", "功能": "'常规功能'!A1",
              "常规压力": "'常规压力'!A1", "问题统计表": "'问题统计表'!A1"}
        ws = wb.Worksheets("摘要")
        for r in range(1, ws.UsedRange.Rows.Count + 1):
            v = ws.Cells(r, 2).Value
            if isinstance(v, str) and v.strip() in lm:
                ws.Hyperlinks.Add(Anchor=ws.Cells(r, 2), Address="", SubAddress=lm[v.strip()],
                                  TextToDisplay=v.strip())
        print("[摘要] 图例跳转链接已重配")

        out = os.path.abspath(a.out)
        if os.path.exists(out):
            os.remove(out)
        wb.SaveAs(out, FileFormat=51)      # xlOpenXMLWorkbook
        print("SAVED:", out, "%.2f MB" % (os.path.getsize(out) / 1048576))
    finally:
        wb.Close(SaveChanges=False)
        app.Quit()


if __name__ == "__main__":
    main()
