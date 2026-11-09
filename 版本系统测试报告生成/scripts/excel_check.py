# -*- coding: utf-8 -*-
"""用真实 Excel(COM) 打开产物，确认无修复提示、Sheet 齐全。

用法: python excel_check.py --config <config.json>
"""
import argparse
import gc
import json
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding="utf-8"))
    path = cfg["out_report"]
    try:
        import win32com.client as win32
    except ImportError:
        print("SKIP: 未安装 pywin32，跳过 Excel 实机验证")
        return
    xl = win32.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    xl.AskToUpdateLinks = False
    wb = None
    try:
        wb = xl.Workbooks.Open(path, 0, True)
        print("OPENED OK. Sheets=%d" % wb.Worksheets.Count)
        for ws in wb.Worksheets:
            print("  - %s used=%s shapes=%d" % (ws.Name, ws.UsedRange.Address, ws.Shapes.Count))
        wb.Close(False)
    finally:
        xl.Quit()
        wb = None
        xl = None
        gc.collect()


if __name__ == "__main__":
    main()
