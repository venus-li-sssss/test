# -*- coding: utf-8 -*-
"""把一次 pytest + allure 跑批的结果归档到版本目录（可重复、带自检）。

典型用法（QDM562 766 FCT）：
    python archive_results.py ^
        --src "D:\\work\\QDM562\\脚本\\自动化测试\\4G_ECU_FCT_TEST" ^
        --dst "D:\\work\\QDM562\\版本测试\\766\\FCT测试" ^
        --version 766 --device "IMEI 864897087029223" ^
        --firmware "ECU APP V0766 / 底包 0705" ^
        --console-log "_fct_run3.txt" ^
        --doc "D:\\work\\QDM562\\版本测试\\V01\\FCT测试\\4G-ECU FCT指令说明20260914_05BT.xlsx"

做的事：
    1. report/（allure HTML）→ <dst>/report/
    2. result/xml/（allure 原始数据）→ <dst>/result/xml/
    3. 最新一轮的 log/{script,serial,summary}_*.txt → <dst>/log/
    4. 控制台完整输出（--console-log，可选）→ <dst>/log/运行日志_<时间>.txt
    5. 指令文档（--doc，可选）→ <dst>/
    6. 生成 <dst>/说明.md（结论 / 跳过项 / 关键读数 / 目录说明）
    7. 自检：index.html 在、json 数量、文件数与总大小

只读源目录，不改任何东西；目标目录已存在就增量覆盖（不删旧文件）。
"""
import argparse
import datetime
import glob
import os
import re
import shutil
import sys


def latest(pattern, root):
    files = glob.glob(os.path.join(root, pattern))
    return max(files, key=os.path.getmtime) if files else None


def biggest(pattern, root):
    """同一轮会生成多个日志（模块级 import + pytest 各建一个，时间戳只差几秒），
    真实跑批的那份体积最大 → 按体积挑，比按 mtime 稳。"""
    files = glob.glob(os.path.join(root, pattern))
    return max(files, key=os.path.getsize) if files else None


def closest_to(pattern, root, ref_mtime):
    """挑与参考文件 mtime 最接近的那份（同一轮跑批的日志/汇总几乎同时落盘），
    时间相近时取体积大的（排除只有 banner 的小文件）。"""
    files = glob.glob(os.path.join(root, pattern))
    if not files:
        return None
    return min(files, key=lambda f: (abs(os.path.getmtime(f) - ref_mtime),
                                     -os.path.getsize(f)))


def copy_tree(src, dst):
    n = 0
    if not os.path.isdir(src):
        return 0
    for root, _dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        tgt = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(tgt, exist_ok=True)
        for f in files:
            shutil.copy2(os.path.join(root, f), os.path.join(tgt, f))
            n += 1
    return n


def parse_console(console):
    """从控制台输出里抠出 pytest 汇总行、跳过项、数据汇总表。"""
    info = {"summary_line": "", "total": "", "passed": "", "failed": "",
            "skipped": "", "rate": "", "duration": "", "skips": [],
            "mode": "", "rows": []}
    if not console or not os.path.exists(console):
        return info
    with open(console, encoding="utf-8", errors="replace") as f:
        text = f.read()

    m = re.findall(r"(\d+) passed(?:, (\d+) skipped)?(?:, (\d+) failed)? in ([\d.]+)s", text)
    if m:
        info["passed"], info["skipped"], info["failed"], info["duration"] = m[-1][0], m[-1][1] or "0", m[-1][2] or "0", m[-1][3]

    m = re.search(r"用例总数:\s*(\d+)\s+执行:\s*(\d+)\s+PASS:\s*(\d+)\s+FAIL:\s*(\d+)\s+SKIP:\s*(\d+)", text)
    if m:
        info["total"], info["passed"], info["failed"], info["skipped"] = m.group(1), m.group(3), m.group(4), m.group(5)
    m = re.search(r"通过率\s*:\s*([\d.]+%)", text)
    if m:
        info["rate"] = m.group(1)
    m = re.search(r"运行模式:\s*(.+)", text)
    if m:
        info["mode"] = m.group(1).strip()
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("SKIPPED ["):
            info["skips"].append(s)
    for line in text.splitlines():
        mm = re.match(r"^\[[^\]]+\]\s*(\d{3})\s+(.+?)\s{2,}(.+?)\s{2,}(PASS|FAIL|SKIP)\s*", line)
        if mm:
            info["rows"].append(mm.groups())
    return info


def main():
    ap = argparse.ArgumentParser(description="归档 FCT/自动化测试跑批结果到版本目录")
    ap.add_argument("--src", required=True, help="测试项目目录（含 report/result/log）")
    ap.add_argument("--dst", required=True, help="归档目标目录，如 D:\\work\\...\\版本测试\\766\\FCT测试")
    ap.add_argument("--version", default="", help="版本号，如 766")
    ap.add_argument("--device", default="", help="被测设备标识（IMEI/SN）")
    ap.add_argument("--firmware", default="", help="固件版本描述")
    ap.add_argument("--console-log", default="", help="控制台完整输出文件（相对 src 或绝对路径）")
    ap.add_argument("--script-log", default="", help="指定脚本日志（默认自动挑体积最大的那份）")
    ap.add_argument("--serial-log", default="", help="指定串口逐帧日志（默认自动挑体积最大的那份）")
    ap.add_argument("--doc", default="", help="用例依据文档（xlsx 等），复制到目标根目录")
    ap.add_argument("--title", default="", help="说明.md 的标题，默认自动生成")
    ap.add_argument("--dry-run", action="store_true", help="只打印要做什么，不落盘")
    a = ap.parse_args()

    src, dst = os.path.abspath(a.src), os.path.abspath(a.dst)
    if not os.path.isdir(src):
        sys.exit("源目录不存在: %s" % src)

    console = a.console_log
    if console and not os.path.isabs(console):
        console = os.path.join(src, console)

    # 自动挑「最新一轮」的日志：以最新 summary 的 mtime 为锚，取落盘时间最接近的那份
    # （同一轮会生成多个时间戳只差几秒的日志，其中一个可能只有 banner，按体积二次排除）
    summary = latest("log/summary_*.txt", src)
    ref = os.path.getmtime(summary) if summary else None
    if a.script_log:
        script_log = a.script_log if os.path.isabs(a.script_log) else os.path.join(src, a.script_log)
    else:
        script_log = closest_to("log/script_log_*.txt", src, ref) if ref else biggest("log/script_log_*.txt", src)
    if a.serial_log:
        serial_log = a.serial_log if os.path.isabs(a.serial_log) else os.path.join(src, a.serial_log)
    else:
        serial_log = closest_to("log/serial_log_*.txt", src, ref) if ref else biggest("log/serial_log_*.txt", src)

    stamp = datetime.datetime.fromtimestamp(os.path.getmtime(summary)).strftime("%Y-%m-%d") if summary else \
        datetime.date.today().isoformat()

    plan = []
    if os.path.isdir(os.path.join(src, "report")):
        plan.append(("report/", os.path.join(dst, "report")))
    if os.path.isdir(os.path.join(src, "result", "xml")):
        plan.append(("result/xml/", os.path.join(dst, "result", "xml")))
    for f in filter(None, [script_log, serial_log, summary]):
        plan.append((os.path.relpath(f, src), os.path.join(dst, "log", os.path.basename(f))))
    if console and os.path.exists(console):
        plan.append((os.path.relpath(console, src), os.path.join(dst, "log", "运行日志_%s.txt" % stamp)))
    if a.doc:
        plan.append((a.doc, os.path.join(dst, os.path.basename(a.doc))))

    print("源：%s\n目标：%s\n" % (src, dst))
    for s, d in plan:
        print("  %-56s -> %s" % (s if len(s) < 56 else "..." + s[-53:], d))
    if a.dry_run:
        print("\n[dry-run] 未落盘。")
        return

    os.makedirs(dst, exist_ok=True)
    n_report = copy_tree(os.path.join(src, "report"), os.path.join(dst, "report"))
    n_xml = copy_tree(os.path.join(src, "result", "xml"), os.path.join(dst, "result", "xml"))
    for f in filter(None, [script_log, serial_log, summary]):
        os.makedirs(os.path.join(dst, "log"), exist_ok=True)
        shutil.copy2(f, os.path.join(dst, "log", os.path.basename(f)))
    if console and os.path.exists(console):
        os.makedirs(os.path.join(dst, "log"), exist_ok=True)
        shutil.copy2(console, os.path.join(dst, "log", "运行日志_%s.txt" % stamp))
    if a.doc and os.path.exists(a.doc):
        shutil.copy2(a.doc, os.path.join(dst, os.path.basename(a.doc)))

    # 说明.md
    info = parse_console(console)
    title = a.title or "版本 %s 自动化测试结果" % (a.version or "")
    lines = ["# %s" % title, ""]
    if a.version:
        lines.append("- 版本：**%s**" % a.version)
    if a.device:
        lines.append("- 被测设备：%s" % a.device)
    if a.firmware:
        lines.append("- 固件：%s" % a.firmware)
    if info["mode"]:
        lines.append("- 运行参数：%s" % info["mode"])
    if summary:
        lines.append("- 测试时间：%s（取自 %s）" % (stamp, os.path.basename(summary)))
    lines += ["", "## 结论", "", "```"]
    lines.append("用例总数: %s   执行: %s   PASS: %s   FAIL: %s   SKIP: %s" % (
        info["total"] or "-", info["passed"] or "-", info["passed"] or "-",
        info["failed"] or "-", info["skipped"] or "-"))
    lines.append("通过率  : %s   耗时: %ss" % (info["rate"] or "-", info["duration"] or "-"))
    lines.append("```")
    if info["skips"]:
        lines += ["", "## 跳过项", ""]
        lines += ["- `%s`" % s for s in info["skips"]]
    if info["rows"]:
        lines += ["", "## 数据汇总", "", "| 行号 | 项目 | 数据 | 判定 |", "|---|---|---|---|"]
        for no, name, data, verdict in info["rows"]:
            lines.append("| %s | %s | %s | %s |" % (no, name.strip()[:30], data.strip()[:40], verdict))
    lines += ["", "## 目录说明", "",
              "| 路径 | 内容 |", "|---|---|",
              "| `report/` | allure HTML 报告（**必须 HTTP 打开**：`allure open ./report`，双击 index.html 会白屏） |",
              "| `result/xml/` | allure 原始数据（可重新 generate） |",
              "| `log/` | 脚本日志 / 串口逐帧日志 / 数据汇总 / 控制台完整输出 |"]
    if a.doc:
        lines.append("| `%s` | 用例依据文档 |" % os.path.basename(a.doc))
    lines.append("")
    with open(os.path.join(dst, "说明.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    total = sum(len(fs) for _r, _d, fs in os.walk(dst))
    size = sum(os.path.getsize(os.path.join(r, f)) for r, _d, fs in os.walk(dst) for f in fs)
    print("\n已归档：report %d 个文件 / result %d 个文件 / 合计 %d 个文件, %.1f MB"
          % (n_report, n_xml, total, size / 1048576.0))
    print("自检: index.html = %s ; allure json = %d 个 ; 说明.md = %s"
          % (os.path.exists(os.path.join(dst, "report", "index.html")),
             len(glob.glob(os.path.join(dst, "result", "xml", "*.json"))),
             os.path.exists(os.path.join(dst, "说明.md"))))


if __name__ == "__main__":
    main()
