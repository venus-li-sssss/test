# -*- coding: utf-8 -*-
"""生成后的收尾：用 Excel 自己给「长文本行」自动调行高（openpyxl 不会自动算）。

用法:
    python postfix_excel.py --config <报告 config.json> [--ranges 测试计划:13:19 问题统计表:22:29]
默认可不给 --ranges，用内置默认（测试计划 13:19、问题统计表 22:29、常规功能 FAIL 行）。
"""
import argparse
import json
import os
import sys

import win32com.client as win32

sys.stdout.reconfigure(encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--ranges", nargs="*", default=None)
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding="utf-8"))
    ranges = a.ranges or cfg.get("autofit_rows") or ["测试计划:13:19", "问题统计表:22:29"]
    path = os.path.abspath(cfg["out_report"])

    app = win32.DispatchEx("Excel.Application")
    app.Visible = False
    app.DisplayAlerts = False
    wb = app.Workbooks.Open(path)
    try:
        for spec in ranges:
            parts = spec.split(":")
            if len(parts) != 3:
                print("  跳过无法解析的 range:", spec)
                continue
            sh, r1, r2 = parts[0], int(parts[1]), int(parts[2])
            ws = wb.Worksheets(sh)
            rng = ws.Rows("%d:%d" % (r1, r2))
            before = [round(ws.Rows(r).RowHeight, 1) for r in range(r1, r2 + 1)]
            rng.EntireRow.AutoFit()
            after = [round(ws.Rows(r).RowHeight, 1) for r in range(r1, r2 + 1)]
            print("  [autofit] %s r%d-%d: %s → %s" % (sh, r1, r2, before, after))
        wb.Save()
        print("SAVED:", path, "%.2f MB" % (os.path.getsize(path) / 1048576))
    finally:
        wb.Close(SaveChanges=False)
        app.Quit()


if __name__ == "__main__":
    main()
