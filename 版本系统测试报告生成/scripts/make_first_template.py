# -*- coding: utf-8 -*-
"""从一份已生成的报告剥离出「首份报告模板」（8 Sheet 骨架，版本级数据清空）。

用法: python make_first_template.py --src <已生成的报告.xlsx> --out <模板.xlsx>

保留：Sheet 结构/样式/合并区/隐藏行列状态/常规功能的行骨架（含备用隐藏行）。
清空：所有版本级数据（列组结果、摘要矩阵/小结/项目字段、测试计划块、问题统计、
      压力数据、隐藏旧版本列组里的历史值），供新项目第一份报告当 base_report 用。
"""
import argparse
import os

import openpyxl
from openpyxl.utils import get_column_letter


def clear_cells(ws, rows, cols):
    for r in rows:
        for c in cols:
            cell = ws.cell(row=r, column=c)
            try:
                cell.value = None
            except AttributeError:
                pass  # 合并区从属格


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    # Windows cmd 传中文路径易乱码：src 支持 glob 兜底解析
    src = a.src
    if not os.path.exists(src):
        import glob
        d, pat = os.path.dirname(src), os.path.basename(src)
        key = pat.split("【")[0][:12] or pat[:12]
        cands = [f for f in glob.glob(os.path.join(d, "*.xlsx")) if key and key in os.path.basename(f)]
        if not cands:
            cands = [f for f in glob.glob(os.path.join(d, "*SystemTestReport*.xlsx"))]
        if not cands:
            raise FileNotFoundError(src)
        src = max(cands, key=os.path.getmtime)
        print("SRC resolved by glob:", src)
    wb = openpyxl.load_workbook(src)

    # ---- 常规功能：新列组(26-29)结果清空、旧列组 F:Y(6-25) 历史值清空、备用隐藏行编号清空
    ws = wb["常规功能"]
    maxr = ws.max_row
    clear_cells(ws, range(3, maxr + 1), range(6, 26))     # 旧版本列组整段清空
    clear_cells(ws, range(4, maxr + 1), range(26, 30))    # 本版本列组数据清空（表头行3保留改写）
    ws.cell(row=3, column=26).value = "测试结果"
    for r in list(range(9, 18)) + list(range(46, 53)):    # 备用隐藏行的编号/内容/优先级
        clear_cells(ws, [r], [3, 4, 5])

    # ---- 摘要：版本级字段与矩阵清空（结构、图例、密级/审核/批准/等级勾选保留）
    ws = wb["摘要"]
    for cell in ("K8", "D5", "D6", "D7", "D11", "D12", "D13", "D15", "D16", "D17", "D18", "C19"):
        ws[cell].value = None
        if cell in ("D5", "D6", "D7", "D13", "D15", "D16", "D17"):
            ws[cell].hyperlink = None
    clear_cells(ws, range(25, 27), range(2, 10))          # 当前版本汇总行
    clear_cells(ws, range(47, 49), range(2, 10))          # 最近一个版本对（B47=版本号）
    clear_cells(ws, range(27, 47), range(2, 10))          # 隐藏的历史版本对

    # ---- 测试计划：全部数据行清空（含隐藏历史块），保留表头行5
    ws = wb["测试计划"]
    clear_cells(ws, range(6, ws.max_row + 1), range(2, 12))

    # ---- 问题统计表：统计数/链接/清单清空，保留标签与样式
    ws = wb["问题统计表"]
    for r in (7, 8, 9, 10, 11, 12, 13):
        ws.cell(row=r, column=3).value = None
    for r in (15, 16, 17):
        c = ws.cell(row=r, column=3)
        c.value = None
        c.hyperlink = None
    clear_cells(ws, range(22, 32), range(2, 11))

    # ---- 常规压力：旧列组 H:BD(8-56) 与新列组数据(57-63, 行9+)清空；左侧标签清空（行9-14）
    ws = wb["常规压力"]
    clear_cells(ws, range(8, 16), range(8, 57))
    clear_cells(ws, range(9, 16), range(57, 64))
    clear_cells(ws, range(9, 15), range(2, 8))

    # ---- 路测：隐藏历史行清空（图片保留也无妨，行是隐藏的）
    ws = wb["路测"]
    clear_cells(ws, range(2, 6), range(2, 9))
    # 底稿带来的旧项目路测截图不属于模板，删掉（体积大头）
    if getattr(ws, "_images", None):
        print("路测: 删除 %d 张旧图" % len(ws._images))
        ws._images = []

    # 其他 Sheet 若也有残留图片（Revision/摘要的 logo 属于模板，保留）
    for name in ("常规功能", "常规压力", "问题统计表", "测试计划"):
        s = wb[name]
        if getattr(s, "_images", None):
            print("%s: 删除 %d 张图" % (name, len(s._images)))
            s._images = []

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    wb.save(a.out)
    print("TEMPLATE SAVED:", a.out, "(%.1f MB)" % (os.path.getsize(a.out) / 1048576))


if __name__ == "__main__":
    main()
