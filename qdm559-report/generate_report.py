"""
QDM559 报告生成器 - 彻底修复版

修复：
1. 标题完全清除列表编号（numPr + 样式继承）
2. 使用自定义标题样式避免模板干扰
3. 添加 TOC 更新提示
"""

import json
import shutil
from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from pathlib import Path
from PIL import Image

# ============================================================
# 配置
# ============================================================
BASE_TEMPLATE = Path(__file__).parent / "media" / "base_template.docx"
CONFIG = Path(__file__).parent / "config.json"
OUTPUT = Path(__file__).parent / "Ikotek_QDM559_V22_测试报告_20261009.docx"
ENV_IMAGE = Path(__file__).parent / "media" / "75ebb7868a964a6e800bfe80433002f1_6cccee7360e7ef1bdd6e98e4d4ab66ad.png"

with open(CONFIG, 'r', encoding='utf-8') as f:
    cfg = json.load(f)

# ============================================================
# 辅助函数
# ============================================================

def remove_all_numbering(p):
    """彻底清除段落的所有编号格式"""
    pPr = p._element.get_or_add_pPr()
    
    # 1. 删除 numPr（段落级编号）
    numPr = pPr.find(qn('w:numPr'))
    if numPr is not None:
        pPr.remove(numPr)
    
    # 2. 删除 ind（缩进，有时与编号关联）
    ind = pPr.find(qn('w:ind'))
    if ind is not None:
        # 只删除 left 和 hanging，保留 firstLine
        left = ind.find(qn('w:left'))
        hanging = ind.find(qn('w:hanging'))
        if left is not None:
            ind.remove(left)
        if hanging is not None:
            ind.remove(hanging)
    
    # 3. 设置 outlineLevel（标题级别）直接，不依赖样式
    outlineLvl = pPr.find(qn('w:outlineLvl'))
    if outlineLvl is None:
        outlineLvl = OxmlElement('w:outlineLvl')
        pPr.append(outlineLvl)
    
    return p

def add_custom_heading(doc, text, level):
    """添加自定义标题，完全避免模板样式干扰"""
    # 创建段落
    p = doc.add_paragraph()
    
    # 设置文本
    run = p.add_run(text)
    run.bold = True
    
    # 设置字体大小（根据级别）
    if level == 1:
        run.font.size = Pt(16)
        outline_level = 0
    elif level == 2:
        run.font.size = Pt(14)
        outline_level = 1
    else:  # level 3
        run.font.size = Pt(12)
        outline_level = 2
    
    # 设置段落间距
    pPr = p._element.get_or_add_pPr()
    
    # 设置 outlineLevel
    outlineLvl = pPr.find(qn('w:outlineLvl'))
    if outlineLvl is None:
        outlineLvl = OxmlElement('w:outlineLvl')
        pPr.append(outlineLvl)
    outlineLvl.set(qn('w:val'), str(outline_level))
    
    # 确保没有编号
    remove_all_numbering(p)
    
    # 设置段前段后间距
    spacing = pPr.find(qn('w:spacing'))
    if spacing is None:
        spacing = OxmlElement('w:spacing')
        pPr.append(spacing)
    spacing.set(qn('w:before'), '240')  # 段前 12pt
    spacing.set(qn('w:after'), '120')   # 段后 6pt
    
    return p

def set_cell_text(cell, text, bold=False, font_size=None, color=None):
    """设置单元格文本"""
    cell.text = ""
    p = cell.paragraphs[0]
    run = p.add_run(text)
    if bold:
        run.bold = True
    if font_size:
        run.font.size = font_size
    if color:
        run.font.color.rgb = color

def add_test_table(doc, steps, result, remark, is_env=False):
    """添加测试表格"""
    table = doc.add_table(rows=0, cols=5)
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    
    # 表头
    row = table.add_row()
    set_cell_text(row.cells[0], "测试项目", bold=True)
    set_cell_text(row.cells[1], cfg['test_info']['project'])
    set_cell_text(row.cells[2], "测试人员", bold=True)
    set_cell_text(row.cells[3], cfg['test_info']['tester'])
    row.cells[3].merge(row.cells[4])
    
    row = table.add_row()
    set_cell_text(row.cells[0], "测试地点", bold=True)
    set_cell_text(row.cells[1], cfg['test_info']['location'])
    set_cell_text(row.cells[2], "测试周期", bold=True)
    set_cell_text(row.cells[3], cfg['test_info']['period'])
    row.cells[3].merge(row.cells[4])
    
    row = table.add_row()
    set_cell_text(row.cells[0], "样品数量", bold=True)
    set_cell_text(row.cells[1], cfg['test_info']['samples'])
    set_cell_text(row.cells[2], "样品编号", bold=True)
    set_cell_text(row.cells[3], f"IMEI: {cfg['test_info']['imei']}")
    row.cells[3].merge(row.cells[4])
    
    # 版本信息标题
    row = table.add_row()
    set_cell_text(row.cells[0], "版本信息", bold=True)
    set_cell_text(row.cells[1], "软件", bold=True)
    set_cell_text(row.cells[2], "部件类型", bold=True)
    set_cell_text(row.cells[3], "版本信息", bold=True)
    row.cells[3].merge(row.cells[4])
    
    # 软件组件
    components = cfg['components']
    software = [(k, v) for k, v in components.items() if k != 'HW']
    for comp, ver in software:
        row = table.add_row()
        set_cell_text(row.cells[2], comp)
        set_cell_text(row.cells[3], ver)
        row.cells[3].merge(row.cells[4])
    
    # 硬件
    row = table.add_row()
    set_cell_text(row.cells[1], "硬件", bold=True)
    set_cell_text(row.cells[2], "HW")
    set_cell_text(row.cells[3], components['HW'])
    row.cells[3].merge(row.cells[4])
    
    # 合并单元格
    first_ver = 3
    last_ver = 3 + len(software) + 1
    table.cell(first_ver, 0).merge(table.cell(last_ver, 0))
    
    first_soft = 3
    last_soft = 3 + len(software)
    table.cell(first_soft, 1).merge(table.cell(last_soft, 1))
    
    # 如果不是测试环境表，添加测试步骤、结果、备注
    if not is_env:
        # 测试步骤
        row = table.add_row()
        set_cell_text(row.cells[0], "测试步骤", bold=True)
        steps_text = "\n".join([f"{i+1}. {s}" for i, s in enumerate(steps)])
        set_cell_text(row.cells[1], steps_text)
        row.cells[1].merge(row.cells[4])
        
        # 测试结果
        row = table.add_row()
        set_cell_text(row.cells[0], "测试结果", bold=True)
        color = RGBColor(0xFF, 0x00, 0x00) if result == "FAIL" else None
        set_cell_text(row.cells[1], result, bold=True, color=color)
        row.cells[1].merge(row.cells[4])
        
        # 备注
        row = table.add_row()
        set_cell_text(row.cells[0], "备注", bold=True)
        if remark:
            set_cell_text(row.cells[1], remark, color=color)
        row.cells[1].merge(row.cells[4])
    
    return table

# ============================================================
# 主流程
# ============================================================

print("=" * 60)
print("QDM559 报告生成器 - 彻底修复版")
print("=" * 60)

# 1. 复制基础模板
print(f"\n[1/7] 复制基础模板：{BASE_TEMPLATE.name}")
shutil.copy2(BASE_TEMPLATE, OUTPUT)
doc = Document(str(OUTPUT))

# 2. 修改封面信息
print(f"\n[2/7] 修改封面信息")
for p in doc.paragraphs:
    text = p.text
    
    if "QDM551-EA-QNA" in text:
        full_text = text.replace("QDM551-EA-QNA", "QDM559")
        if p.runs:
            p.runs[0].text = full_text
            for r in p.runs[1:]:
                r.text = ""
        print(f"  修改标题：QDM559")
    
    if "0x0126" in text:
        full_text = text.replace("0x0126", cfg['report']['version'])
        if p.runs:
            p.runs[0].text = full_text
            for r in p.runs[1:]:
                r.text = ""
        print(f"  修改版本：{cfg['report']['version']}")
    
    if "2026-01-21" in text:
        full_text = text.replace("2026-01-21", cfg['report']['date'])
        if p.runs:
            p.runs[0].text = full_text
            for r in p.runs[1:]:
                r.text = ""
        print(f"  修改日期：{cfg['report']['date']}")

# 2.5 修改页眉
print(f"\n[2.5/7] 修改页眉")
for section in doc.sections:
    # 修改奇数页页眉
    if section.header:
        for p in section.header.paragraphs:
            for run in p.runs:
                if "QDM551-EA-QNA" in run.text:
                    run.text = run.text.replace("QDM551-EA-QNA", "QDM559-EA-NA")
                    print(f"  奇数页页眉：QDM551-EA-QNA → QDM559-EA-NA")
                elif "QDM551-EA-QN" in run.text:
                    run.text = run.text.replace("QDM551-EA-QN", "QDM559-EA-NA")
                    print(f"  奇数页页眉：QDM551-EA-QN → QDM559-EA-NA")
    
    # 修改偶数页页眉
    if section.even_page_header:
        for p in section.even_page_header.paragraphs:
            for run in p.runs:
                if "QDM551-EA-QNA" in run.text:
                    run.text = run.text.replace("QDM551-EA-QNA", "QDM559-EA-NA")
                    print(f"  偶数页页眉：QDM551-EA-QNA → QDM559-EA-NA")
                elif "QDM551-EA-QN" in run.text:
                    run.text = run.text.replace("QDM551-EA-QN", "QDM559-EA-NA")
                    print(f"  偶数页页眉：QDM551-EA-QN → QDM559-EA-NA")
    
    # 修改首页页眉
    if section.first_page_header:
        for p in section.first_page_header.paragraphs:
            for run in p.runs:
                if "QDM551-EA-QNA" in run.text:
                    run.text = run.text.replace("QDM551-EA-QNA", "QDM559-EA-NA")
                    print(f"  首页页眉：QDM551-EA-QNA → QDM559-EA-NA")
                elif "QDM551-EA-QN" in run.text:
                    run.text = run.text.replace("QDM551-EA-QN", "QDM559-EA-NA")
                    print(f"  首页页眉：QDM551-EA-QN → QDM559-EA-NA")

# 3. 修改修订记录表
print(f"\n[3/7] 修改修订记录表")
if len(doc.tables) > 0:
    rev_table = doc.tables[0]
    if len(rev_table.rows) > 1:
        row = rev_table.rows[1]
        set_cell_text(row.cells[0], "1.0")
        set_cell_text(row.cells[1], cfg['report']['date'])
        set_cell_text(row.cells[2], "Venus")
        set_cell_text(row.cells[3], "初始版本")
        print(f"  已修改修订记录")

# 4. 找到标记位置并删除
print(f"\n[4/7] 删除标记段落")
marker_idx = None
for i, p in enumerate(doc.paragraphs):
    if "[INSERT_TABLES_HERE]" in p.text:
        marker_idx = i
        print(f"  找到标记在段落 {i}")
        p._element.getparent().remove(p._element)
        break

# 5. 添加"1. 测试目的"
print(f"\n[5/7] 添加'1. 测试目的'")
add_custom_heading(doc, '1. 测试目的', 1)
doc.add_paragraph(f"为验证{cfg['test_info']['project']}的修改点及基本功能，对{cfg['test_info']['project']}在常温下进行了功能和修改点测试。该报告主要总结了具体测试项以及测试数据。")

# 6. 添加"2. 测试内容"
print(f"\n[6/7] 添加'2. 测试内容'")
add_custom_heading(doc, '2. 测试内容', 1)

# 6.1 测试环境
add_custom_heading(doc, '2.1 测试环境', 2)
add_test_table(doc, [], "PASS", "", is_env=True)
print(f"  已插入测试环境表格")

# 插入测试环境图片
if ENV_IMAGE.exists():
    img = Image.open(ENV_IMAGE)
    width_cm = 15
    height_cm = width_cm * img.height / img.width
    
    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    run.add_picture(str(ENV_IMAGE), width=Cm(width_cm))
    print(f"  已插入测试环境图片")

p = doc.add_paragraph('图表 1：常温测试环境')
p.alignment = WD_ALIGN_PARAGRAPH.CENTER

# 6.2 修改点测试
add_custom_heading(doc, '2.2 修改点测试', 2)
for test in cfg['modification_tests']:
    add_custom_heading(doc, test['title'], 3)
    add_test_table(doc, test['steps'], test['result'], test['remark'])
    print(f"  已生成：{test['title']}")

# 6.3 基本功能测试
add_custom_heading(doc, '2.3 基本功能测试', 2)
for test in cfg['basic_tests']:
    add_custom_heading(doc, test['title'], 3)
    add_test_table(doc, test['steps'], test['result'], test['remark'])
    print(f"  已生成：{test['title']}")

# 6.4 稳定性测试
add_custom_heading(doc, '2.4 稳定性测试', 2)
for test in cfg['stability_tests']:
    add_custom_heading(doc, test['title'], 3)
    add_test_table(doc, test['steps'], test['result'], test['remark'])
    print(f"  已生成：{test['title']}")

# 7. 添加"3. 测试结论"
print(f"\n[7/7] 添加'3. 测试结论'")
add_custom_heading(doc, '3. 测试结论', 1)
add_custom_heading(doc, '3.1 测试小结', 2)
for item in cfg['test_summary']:
    doc.add_paragraph(item)

# Bug 表
doc.add_paragraph()
add_custom_heading(doc, '问题统计表', 2)
bug_table = doc.add_table(rows=1, cols=4)
bug_table.style = 'Table Grid'
header = bug_table.rows[0]
set_cell_text(header.cells[0], "Bug 号", bold=True)
set_cell_text(header.cells[1], "Bug 严重等级", bold=True)
set_cell_text(header.cells[2], "Bug 描述", bold=True)
set_cell_text(header.cells[3], "备注", bold=True)

for bug in cfg['bugs']:
    row = bug_table.add_row()
    set_cell_text(row.cells[0], bug['id'])
    set_cell_text(row.cells[1], bug['severity'])
    set_cell_text(row.cells[2], bug['description'])
    set_cell_text(row.cells[3], bug['remark'])

print(f"  已生成 Bug 表（{len(cfg['bugs'])} 条）")

# 保存
doc.save(str(OUTPUT))

print(f"\n{'='*60}")
print(f"✅ 报告已生成：{OUTPUT}")

# 自动更新目录
print(f"\n[8/8] 自动更新目录...")
try:
    import win32com.client
    import os
    
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    
    abs_path = os.path.abspath(str(OUTPUT))
    doc_word = word.Documents.Open(abs_path)
    
    # 更新所有域（包括 TOC）
    doc_word.Fields.Update()
    
    # 保存并关闭
    doc_word.Save()
    doc_word.Close()
    word.Quit()
    
    print(f"  ✅ 目录已自动更新")
except Exception as e:
    print(f"  ⚠️  自动更新目录失败：{e}")
    print(f"  请手动在 Word 中按 Ctrl+A 然后 F9 更新目录")

print(f"{'='*60}")
