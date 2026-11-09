# -*- coding: utf-8 -*-
"""核对生成结果：常规功能新列 / 测试计划 / 问题统计表 / 常规压力 / 缺陷链接。

用法: python verify_report.py --config <config.json>
"""
import argparse
import json
import re
import sys

import openpyxl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding="utf-8"))
    wb = openpyxl.load_workbook(cfg["out_report"])
    print("SHEETS:", wb.sheetnames)

    ws = wb["常规功能"]
    hdr_col = next((c for c in range(6, ws.max_column + 1)
                    if str(ws.cell(3, c).value or "").startswith(cfg["version"])), None)
    print("\n--- 常规功能 %s 列 (col %s) ---" % (cfg["version"], hdr_col))
    for r in range(4, ws.max_row + 1):
        v = ws.cell(r, hdr_col).value if hdr_col else None
        if not v:
            continue
        print("  r%-3d %-22s %-20s | %s" % (
            r, str(ws.cell(r, 3).value or "")[:22], str(ws.cell(r, 4).value or "")[:20], v))

    ws = wb["测试计划"]
    print("\n--- 测试计划 ---")
    for r in range(5, ws.max_row + 1):
        if ws.cell(r, 5).value:
            print("  r%-3d %s" % (r, [ws.cell(r, c).value for c in range(3, 12)]))

    ws = wb["问题统计表"]
    print("\n--- 问题统计表 ---")
    for r in range(6, 14):
        print("  %s = %s" % (ws.cell(r, 2).value, ws.cell(r, 3).value))
    for r in (15, 16, 17):
        print("  %s -> %s" % (ws.cell(r, 2).value, str(ws.cell(r, 3).value)[:130]))
    for r in range(20, ws.max_row + 1):
        if ws.cell(r, 2).value:
            print("  r%-3d %s" % (r, [str(ws.cell(r, c).value or "")[:26] for c in range(2, 5)]))

    ws = wb["常规压力"]
    print("\n--- 常规压力 ---")
    for r in range(8, ws.max_row + 1):
        print("  r%-3d hidden=%-5s %-28s %s" % (
            r, ws.row_dimensions[r].hidden, str(ws.cell(r, 4).value or "")[:28],
            [ws.cell(r, c).value for c in range(57, 64)]))


if __name__ == "__main__":
    main()
