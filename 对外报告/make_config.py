"""生成 / 体检对外报告配置

用法
----
    # 1. 从骨架新建一份项目配置（会填好 project/version/tester/date）
    python make_config.py --project QDM5xx --version 0x0001 --tester Venus \
                          --date 2026-11-10 --out configs/qdm5xx_v1.json

    # 2. 体检已有配置：语法、必需字段、还没填的 <占位符>、模板/图片是否存在
    python make_config.py --check configs/<项目>_<版本>.json

说明：本脚本**不做**任何数据抓取（执行表/JIRA 解析）。数据要按项目实际填，
解析脚本各项目差异太大，硬写一个通用解析器只会给出假的完整度。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
TEMPLATE = SKILL_DIR / "config_template.json"

REQUIRED = [
    ("test_info", "project"),
    ("test_info", "tester"),
    ("test_info", "period"),
    ("test_info", "samples"),
    ("test_info", "components"),
]
PLACEHOLDER = re.compile(r"<[^<>]{1,40}>")


def _set(d: dict, key: str, value):
    if value:
        d[key] = value


def scaffold(args) -> int:
    if not TEMPLATE.exists():
        print(f"找不到骨架：{TEMPLATE}")
        return 1
    with open(TEMPLATE, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    cfg.pop("_说明", None)
    info = cfg.setdefault("test_info", {})
    _set(info, "project", args.project)
    _set(info, "tester", args.tester)
    _set(info, "location", args.location)
    _set(info, "imei", args.sample_id)
    _set(cfg.setdefault("report", {}), "version", args.version)

    out = Path(args.out)
    if not out.is_absolute():
        out = (SKILL_DIR / out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    print(f"已生成配置：{out}")
    print("下一步：把 <...> 占位符逐项换成真实数据，再跑")
    print(f"  python generate_report.py --config {out}")
    leftover = len(PLACEHOLDER.findall(out.read_text(encoding="utf-8")))
    print(f"当前还剩 {leftover} 处 <占位符> 待填")
    return 0


def check(path: Path) -> int:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    problems, notes = [], []

    try:
        cfg = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"JSON 语法错误：{exc}")
        return 1

    for section, key in REQUIRED:
        if not (cfg.get(section) or {}).get(key):
            problems.append(f"缺少必需字段 {section}.{key}")

    if not (cfg.get("sections") or cfg.get("basic_tests") or cfg.get("stability_tests")):
        problems.append("没有任何测试章节：sections / basic_tests / stability_tests 都是空")

    for sec in cfg.get("sections") or []:
        if not sec.get("heading"):
            problems.append("sections 里有章节没写 heading")
        for item in sec.get("items") or []:
            if not item.get("title"):
                problems.append(f"章节 {sec.get('heading')} 有测试项没写 title")
            if str(item.get("result", "")).upper() not in ("PASS", "FAIL", "BLOCK", "BLOCKED"):
                problems.append(
                    f"{item.get('title')} 的 result 不规范：{item.get('result')!r}（应为 PASS/FAIL/BLOCK）"
                )
            if str(item.get("result", "")).upper() == "BLOCK" and not item.get("remark"):
                notes.append(f"{item.get('title')} 是 Block，但备注是空的（对外报告一般要写原因）")

    samples = str((cfg.get("test_info") or {}).get("samples", ""))
    if "<" not in samples and re.search(r"(?i)pcs", samples):
        problems.append(f"samples 写成了 {samples!r}，按惯例用中文「2片」")

    left = PLACEHOLDER.findall(text)
    if left:
        problems.append(f"还有 {len(left)} 处未填占位符，例如 {', '.join(sorted(set(left))[:5])}")

    tpl = cfg.get("template")
    if tpl:
        p = Path(tpl)
        if not p.is_absolute():
            p = (path.parent / p)
            if not p.exists():
                p = Path(tpl)
        if not p.exists():
            notes.append(f"template 指向的模板不存在：{tpl}（运行时回落到内置 media/base_template.docx）")

    print(f"配置：{path}")
    if problems:
        print(f"\n❌ {len(problems)} 个问题：")
        for item in problems:
            print(f"  - {item}")
    else:
        print("\n✅ 结构检查通过")
    if notes:
        print(f"\n⚠️  {len(notes)} 条提醒：")
        for item in notes:
            print(f"  - {item}")
    return 0 if not problems else 2


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成/体检对外报告配置")
    ap.add_argument("--check", default=None, help="体检指定配置文件")
    ap.add_argument("--project", default="", help="项目名，如 QDM5xx")
    ap.add_argument("--version", default="", help="版本号，如 0x0242 / V22")
    ap.add_argument("--tester", default="", help="测试人")
    ap.add_argument("--location", default="", help="测试地点")
    ap.add_argument("--sample-id", default="", help="样品编号 / IMEI")
    ap.add_argument("--date", default=date.today().isoformat(), help="日期（默认今天）")
    ap.add_argument("--out", default="configs/new_project.json", help="输出配置路径")
    args = ap.parse_args(argv)

    if args.check:
        p = Path(args.check)
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        if not p.exists():
            print(f"找不到配置：{p}")
            return 1
        return check(p)
    return scaffold(args)


if __name__ == "__main__":
    sys.exit(main())
