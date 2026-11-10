"""通用对外测试报告生成器（Word / docx）

设计原则
--------
1. **项目无关**：脚本里不出现任何项目名、型号、版本号。所有项目信息都来自配置文件。
2. **模板只读**：把模板复制一份再改，模板文件永远不动，重跑幂等。
3. **结构可配**：报告章节、章节顺序、测试项、结论内容全部由配置决定；
   某个项目没有的章节（比如没有路测图、没有压力测试）就不配它。

用法
----
    python generate_report.py                      # 用同目录 config.json
    python generate_report.py --config configs/<项目>_<版本>.json
    python generate_report.py --config x.json --output out.docx
    python generate_report.py --no-toc             # 不调 Word 更新目录

配置里的文本支持占位符：{project} {version} {date} {tester} {company} 等，
占位符取值来自 config 里 report / test_info 两段的扁平合并（见 build_context）。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

SKILL_DIR = Path(__file__).resolve().parent
DEFAULT_TEMPLATE = SKILL_DIR / "media" / "base_template.docx"
DEFAULT_ENV_IMAGE = SKILL_DIR / "media" / "env_image.png"
MARKER = "[INSERT_TABLES_HERE]"
RED = RGBColor(0xFF, 0x00, 0x00)

DEFAULT_HEADING_SIZES = {1: 16, 2: 14, 3: 12}


# ============================================================
# 小工具
# ============================================================
def fmt(text: str, ctx: dict) -> str:
    """替换 {project} 这类占位符；未知占位符原样保留，不抛异常。"""
    if not isinstance(text, str):
        return text
    return re.sub(r"\{(\w+)\}", lambda m: str(ctx.get(m.group(1), m.group(0))), text)


def fmt_deep(obj, ctx):
    """递归对配置里的所有字符串做占位符替换。"""
    if isinstance(obj, str):
        return fmt(obj, ctx)
    if isinstance(obj, list):
        return [fmt_deep(v, ctx) for v in obj]
    if isinstance(obj, dict):
        return {k: fmt_deep(v, ctx) for k, v in obj.items()}
    return obj


def heading_no(heading: str) -> str:
    """从章节标题里取出编号前缀：'2.2 修改点测试' -> '2.2'；没有编号就返回 ''。"""
    m = re.match(r"^\s*(\d+(?:\.\d+)*)", heading or "")
    return m.group(1) if m else ""


def remove_all_numbering(p):
    """彻底清除段落编号（模板里的 Heading 样式常带自动编号，会污染自定义标题）。"""
    pPr = p._element.get_or_add_pPr()
    numPr = pPr.find(qn("w:numPr"))
    if numPr is not None:
        pPr.remove(numPr)
    ind = pPr.find(qn("w:ind"))
    if ind is not None:
        for tag in ("w:left", "w:hanging"):
            el = ind.find(qn(tag))
            if el is not None:
                ind.remove(el)
    return p


def add_heading(doc, text, level, sizes=None):
    """自定义标题：直接挂 outlineLvl，不依赖模板 Heading 样式，避免列表编号干扰。"""
    sizes = sizes or DEFAULT_HEADING_SIZES
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(sizes.get(level, 12))

    pPr = p._element.get_or_add_pPr()
    outline = pPr.find(qn("w:outlineLvl"))
    if outline is None:
        outline = OxmlElement("w:outlineLvl")
        pPr.append(outline)
    outline.set(qn("w:val"), str(max(level - 1, 0)))

    remove_all_numbering(p)

    spacing = pPr.find(qn("w:spacing"))
    if spacing is None:
        spacing = OxmlElement("w:spacing")
        pPr.append(spacing)
    spacing.set(qn("w:before"), "240")
    spacing.set(qn("w:after"), "120")
    return p


def set_cell_text(cell, text, bold=False, font_size=None, color=None):
    cell.text = ""
    p = cell.paragraphs[0]
    run = p.add_run("" if text is None else str(text))
    if bold:
        run.bold = True
    if font_size:
        run.font.size = font_size
    if color:
        run.font.color.rgb = color


def set_cell_lines(cell, lines, bold=False, font_size=None, color=None):
    """多行文本写一个单元格（第一行用段落 0，其余新建段落，行距紧凑）。"""
    cell.text = ""
    lines = [ln for ln in (lines or []) if ln is not None]
    if not lines:
        return
    first = cell.paragraphs[0]
    for i, line in enumerate(lines):
        p = first if i == 0 else cell.add_paragraph()
        run = p.add_run(str(line))
        if bold:
            run.bold = True
        if font_size:
            run.font.size = font_size
        if color:
            run.font.color.rgb = color


# ============================================================
# 模板文字替换（封面 / 页眉 / 页脚）
# ============================================================
def replace_in_paragraph(p, mapping: dict) -> bool:
    """段落级替换：先按整段文本匹配，命中就把整段写回第一个 run（保留其格式）。"""
    if not p.runs:
        return False
    text = "".join(r.text for r in p.runs)
    new = text
    for find, repl in mapping.items():
        if find and find in new:
            new = new.replace(find, repl)
    if new == text:
        return False
    p.runs[0].text = new
    for r in p.runs[1:]:
        r.text = ""
    return True


def replace_in_container(container, mapping: dict) -> int:
    """对一个 story（正文 / 页眉 / 页脚 / 表格单元格）做替换，返回命中次数。"""
    n = 0
    if container is None:
        return 0
    paragraphs = list(getattr(container, "paragraphs", []) or [])
    for table in getattr(container, "tables", []) or []:
        for row in table.rows:
            for cell in row.cells:
                n += replace_in_container(cell, mapping)
    for p in paragraphs:
        n += 1 if replace_in_paragraph(p, mapping) else 0
    return n


def _stories(doc):
    for section in doc.sections:
        for story in (
            section.header,
            section.even_page_header,
            section.first_page_header,
            section.footer,
            section.even_page_footer,
            section.first_page_footer,
        ):
            if story is None:
                continue
            try:
                yield story
            except Exception:
                continue


def replace_body(doc, mapping: dict) -> int:
    """只替换正文和表格（不含页眉页脚）。"""
    return replace_in_container(doc, mapping) if mapping else 0


def replace_headers(doc, mapping: dict) -> int:
    """只替换页眉页脚（奇/偶/首页）。"""
    if not mapping:
        return 0
    n = 0
    for story in _stories(doc):
        try:
            n += replace_in_container(story, mapping)
        except Exception:
            pass
    return n


# ============================================================
# 表格
# ============================================================
def add_info_table(doc, info: dict, env_only=False, labels=None):
    """测试信息表（测试项目 / 地点 / 周期 / 样品 / 版本信息 [+ 步骤 / 结果 / 备注]）。

    info 字段：project tester location period samples sample_id
              components(有序 dict，HW 另起一行) steps result remark
    """
    labels = labels or {}
    L = lambda k, d: labels.get(k, d)  # noqa: E731

    table = doc.add_table(rows=0, cols=5)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    def kv_row(k1, v1, k2, v2, merge_tail=True):
        row = table.add_row()
        set_cell_text(row.cells[0], L(k1, k1), bold=True)
        set_cell_text(row.cells[1], v1)
        set_cell_text(row.cells[2], L(k2, k2), bold=True)
        set_cell_text(row.cells[3], v2)
        if merge_tail:
            row.cells[3].merge(row.cells[4])
        return row

    kv_row("测试项目", info.get("project", ""), "测试人员", info.get("tester", ""))
    kv_row("测试地点", info.get("location", ""), "测试周期", info.get("period", ""))
    kv_row(
        "样品数量",
        info.get("samples", ""),
        L("sample_id", "样品编号"),
        info.get("sample_label", f"IMEI: {info['imei']}" if info.get("imei") else ""),
    )

    # 版本信息表头
    head = table.add_row()
    set_cell_text(head.cells[0], L("versions", "版本信息"), bold=True)
    set_cell_text(head.cells[1], L("software", "软件"), bold=True)
    set_cell_text(head.cells[2], L("part", "部件类型"), bold=True)
    set_cell_text(head.cells[3], L("version", "版本信息"), bold=True)
    head.cells[3].merge(head.cells[4])

    components = info.get("components") or {}
    software = [(k, v) for k, v in components.items() if str(k).upper() != "HW"]
    hw = next((v for k, v in components.items() if str(k).upper() == "HW"), None)

    for comp, ver in software:
        row = table.add_row()
        set_cell_text(row.cells[2], comp)
        set_cell_text(row.cells[3], ver)
        row.cells[3].merge(row.cells[4])

    hw_row = None
    if hw is not None:
        hw_row = table.add_row()
        set_cell_text(hw_row.cells[1], L("hardware", "硬件"), bold=True)
        set_cell_text(hw_row.cells[2], "HW")
        set_cell_text(hw_row.cells[3], hw)
        hw_row.cells[3].merge(hw_row.cells[4])

    # 合并「版本信息」「软件」两列
    first_ver, last_ver = 3, 3 + len(software) + (1 if hw_row else 0)
    if last_ver > first_ver:
        table.cell(first_ver, 0).merge(table.cell(last_ver, 0))
        if software:
            table.cell(first_ver, 1).merge(table.cell(first_ver + len(software) - 1, 1))

    if env_only:
        return table

    steps = info.get("steps") or []
    steps_text = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps))
    row = table.add_row()
    set_cell_text(row.cells[0], L("steps", "测试步骤"), bold=True)
    set_cell_text(row.cells[1], steps_text)
    row.cells[1].merge(row.cells[4])

    result = str(info.get("result", "")).upper()
    color = RED if result == "FAIL" else None

    row = table.add_row()
    set_cell_text(row.cells[0], L("result", "测试结果"), bold=True)
    set_cell_text(row.cells[1], result, bold=True, color=color)
    row.cells[1].merge(row.cells[4])

    remark = info.get("remark") or ""
    row = table.add_row()
    set_cell_text(row.cells[0], L("remark", "备注"), bold=True)
    if remark:
        set_cell_lines(row.cells[1], str(remark).split("\n"), color=color)
    row.cells[1].merge(row.cells[4])
    return table


def add_bug_table(doc, bugs, labels=None):
    labels = labels or {}
    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    header = table.rows[0]
    for i, key in enumerate(("bug_id", "severity", "description", "remark")):
        set_cell_text(header.cells[i], labels.get(key, key), bold=True)
    for bug in bugs:
        row = table.add_row()
        set_cell_text(row.cells[0], bug.get("id", ""))
        set_cell_text(row.cells[1], bug.get("severity", ""))
        set_cell_text(row.cells[2], bug.get("description", ""))
        set_cell_text(row.cells[3], bug.get("remark", ""))
    return table


# ============================================================
# 配置归一化
# ============================================================
def build_context(cfg: dict) -> dict:
    ctx = {}
    for key in ("report", "test_info"):
        ctx.update({k: v for k, v in (cfg.get(key) or {}).items()})
    ctx.setdefault("project", "")
    ctx.setdefault("date", date.today().isoformat())
    return ctx


def normalize_sections(cfg: dict) -> list:
    """把配置变成统一的章节列表。

    推荐写法（任意章节、任意层数）：
        "sections": [
          {"heading": "2.2 修改点测试", "env_table": false,
           "items": [{"title": "...", "steps": [...], "result": "PASS", "remark": ""}]}
        ]

    兼容旧写法：modification_tests / basic_tests / stability_tests 三段会被转成
    2.2 / 2.3 / 2.4 三个章节。
    """
    if cfg.get("sections"):
        return cfg["sections"]

    legacy = [
        ("modification_tests", "修改点测试"),
        ("basic_tests", "基本功能测试"),
        ("stability_tests", "稳定性测试"),
    ]
    sections, idx = [], 1
    for key, name in legacy:
        items = cfg.get(key) or []
        if items:
            sections.append(
                {"heading": f"2.{idx + 1} {name}", "items": items, "env_table": idx == 1}
            )
            idx += 1
    return sections


# ============================================================
# 主流程
# ============================================================
def generate(config_path: Path, output_override: str | None, update_toc: bool) -> Path:
    with open(config_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    ctx = build_context(raw)
    cfg = fmt_deep(raw, ctx)  # 所有字符串先做占位符替换

    template = Path(cfg.get("template") or DEFAULT_TEMPLATE)
    if not template.is_absolute():
        template = (config_path.parent / template).resolve()
    if not template.exists():
        template = DEFAULT_TEMPLATE

    # 输出路径
    report = cfg.get("report") or {}
    if output_override:
        output = Path(output_override)
    elif report.get("output"):
        output = Path(report["output"])
        if not output.is_absolute():
            output = (config_path.parent / output).resolve()
    else:
        output = Path(
            report.get(
                "output_pattern", "Ikotek_{project}_{version}_测试报告_{date}.docx"
            )
        )
    if not output.is_absolute():
        output = (SKILL_DIR / "output" / output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    sizes = None
    if (cfg.get("styles") or {}).get("heading_sizes"):
        sizes = {int(k): v for k, v in cfg["styles"]["heading_sizes"].items()}

    print("=" * 60)
    print(f"对外测试报告生成：{ctx.get('project', '')} {report.get('version', '')}")
    print("=" * 60)

    # 1. 复制模板
    print(f"\n[1/6] 复制模板：{template.name}")
    shutil.copy2(template, output)
    doc = Document(str(output))

    # 2. 封面 / 页眉 / 页脚 文字替换（页眉先做，避免被封面替换规则抢先命中）
    print("\n[2/6] 替换封面与页眉页脚")
    header_map = cfg.get("header_replacements") or {}
    if header_map:
        print(f"  页眉页脚替换命中 {replace_headers(doc, header_map)} 处")
    n = replace_body(doc, cfg.get("template_replacements") or {})
    print(f"  正文模板占位替换命中 {n} 处")

    if report.get("title"):
        doc.core_properties.title = report["title"]
    if report.get("author"):
        doc.core_properties.author = report["author"]

    # 3. 修订记录
    rev = cfg.get("revision")
    if rev and doc.tables:
        print("\n[3/6] 写修订记录")
        t = doc.tables[0]
        if len(t.rows) > 1:
            row = t.rows[1]
            set_cell_text(row.cells[0], rev.get("version", "1.0"))
            set_cell_text(row.cells[1], rev.get("date", ctx.get("date", "")))
            set_cell_text(row.cells[2], rev.get("author", ctx.get("tester", "")))
            set_cell_text(row.cells[3], rev.get("note", "初始版本"))
            print("  已写入")
    else:
        print("\n[3/6] 跳过修订记录（配置未给 revision）")

    # 4. 删除标记段落
    print("\n[4/6] 定位插入点")
    marker_found = False
    for p in list(doc.paragraphs):
        if MARKER in p.text:
            p._element.getparent().remove(p._element)
            marker_found = True
            break
    print(f"  {MARKER} {'已删除，后续章节追加到文末' if marker_found else '未找到，章节追加到文末'}")

    labels = cfg.get("labels") or {}
    info = cfg.get("test_info") or {}

    # 5. 章节
    print("\n[5/6] 生成章节")
    purpose = cfg.get("purpose") or {}
    if purpose.get("heading", "1. 测试目的"):
        add_heading(doc, purpose.get("heading", "1. 测试目的"), 1, sizes)
        text = purpose.get(
            "text",
            "为验证{project}的修改点及基本功能，对{project}在常温下进行了功能和修改点测试。"
            "该报告主要总结了具体测试项以及测试数据。",
        )
        doc.add_paragraph(fmt(text, ctx))

    content_heading = cfg.get("content_heading", "2. 测试内容")
    add_heading(doc, content_heading, 1, sizes)

    env = cfg.get("env") or {}
    if env.get("enabled", True):
        add_heading(doc, env.get("heading", "2.1 测试环境"), 2, sizes)
        env_info = dict(info)
        env_info.update(env.get("test_info") or {})
        add_info_table(doc, env_info, env_only=True, labels=labels)

        image = env.get("image", str(DEFAULT_ENV_IMAGE))
        image_path = Path(image)
        if not image_path.is_absolute():
            image_path = (config_path.parent / image_path)
            if not image_path.exists():
                image_path = Path(image)
        if image_path.exists():
            try:
                from PIL import Image as PILImage

                with PILImage.open(image_path) as im:
                    width_cm = float(env.get("image_width_cm", 15))
                    _ = width_cm * im.height / im.width
                doc.add_paragraph()
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p.add_run().add_picture(str(image_path), width=Cm(width_cm))
                caption = env.get("caption")
                if caption:
                    cap = doc.add_paragraph(caption)
                    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                print(f"  测试环境图片：{image_path.name}")
            except Exception as exc:  # 图片坏了不影响出报告
                print(f"  ! 环境图片插入失败（跳过）：{exc}")
        else:
            print(f"  提示：环境图片不存在，跳过（{image}）")

    sections = normalize_sections(cfg)
    for sec in sections:
        heading = sec.get("heading", "")
        add_heading(doc, heading, 2, sizes)
        if sec.get("intro"):
            doc.add_paragraph(sec["intro"])

        if sec.get("env_table"):
            env_info = dict(info)
            env_info.update(sec.get("test_info") or {})
            add_info_table(doc, env_info, env_only=True, labels=labels)

        prefix = heading_no(heading)
        for i, item in enumerate(sec.get("items") or [], 1):
            title = str(item.get("title", "")).strip()
            if prefix and not re.match(r"^\d", title):
                title = f"{prefix}.{i} {title}"
            add_heading(doc, title, 3, sizes)
            merged = dict(info)
            merged.update({k: item[k] for k in ("steps", "result", "remark") if k in item})
            merged.update(item.get("test_info") or {})
            add_info_table(doc, merged, env_only=False, labels=labels)
        print(f"  {heading}：{len(sec.get('items') or [])} 项")

    conclusion = cfg.get("conclusion")
    if conclusion is None:
        conclusion = {}
    if conclusion.get("enabled", True):
        add_heading(doc, conclusion.get("heading", "3. 测试结论"), 1, sizes)
        add_heading(doc, conclusion.get("summary_heading", "3.1 测试小结"), 2, sizes)
        for line in cfg.get("test_summary") or []:
            doc.add_paragraph(line)

        bugs = cfg.get("bugs")
        if bugs:
            doc.add_paragraph()
            add_heading(doc, conclusion.get("bugs_heading", "问题统计表"), 2, sizes)
            add_bug_table(
                doc,
                bugs,
                labels={
                    "bug_id": "Bug 号",
                    "severity": "Bug 严重等级",
                    "description": "Bug 描述",
                    "remark": "备注",
                    **{k: v for k, v in (cfg.get("bug_labels") or {}).items()},
                },
            )
            print(f"  问题统计表：{len(bugs)} 条")

    # 6. 保存 + 目录
    doc.save(str(output))
    print(f"\n[6/6] 已保存：{output}")

    if update_toc:
        try:
            import os

            import win32com.client

            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            wdoc = word.Documents.Open(os.path.abspath(str(output)))
            wdoc.Fields.Update()
            for toc in wdoc.TablesOfContents:
                toc.Update()
            wdoc.Save()
            wdoc.Close()
            word.Quit()
            print("  目录已自动更新")
        except Exception as exc:
            print(f"  ! 自动更新目录失败（手动 Ctrl+A → F9 即可）：{exc}")

    return output


def main(argv=None):
    ap = argparse.ArgumentParser(description="通用对外测试报告生成器（docx）")
    ap.add_argument("--config", default=None, help="配置文件路径，默认同目录 config.json")
    ap.add_argument("--output", default=None, help="覆盖输出文件路径")
    ap.add_argument("--no-toc", action="store_true", help="跳过 Word 自动更新目录")
    args = ap.parse_args(argv)

    config_path = Path(args.config) if args.config else SKILL_DIR / "config.json"
    if not config_path.is_absolute():
        config_path = (Path.cwd() / config_path).resolve()
    if not config_path.exists():
        print(f"找不到配置文件：{config_path}")
        print("先复制 configs/ 里的参考配置，或跑 python make_config.py --init <新配置路径>")
        return 1

    out = generate(config_path, args.output, not args.no_toc)
    print("=" * 60)
    print(f"完成：{out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
