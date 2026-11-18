# -*- coding: utf-8 -*-
"""范例：把上一版（763）测试报告邮件 HTML 改成本版（765）。

用法:
    python rebuild_example.py --src mail_src.html --out body.html \
        --prev 763 --cur 765 \
        --data data.json

data.json 结构见 SKILL.md「脚本」章节；也可以直接改下面的 DEFAULTS 常量。
改造点：版本号 / 原因 / 测试风险 / 功能矩阵 / 缺陷统计 / 问题点记录 / 压力表 / 路测 / 表格宽度。
"""
import argparse
import io
import json
import re
import sys

from bs4 import BeautifulSoup

DEFAULTS = {
    "prev": "763",
    "cur": "765",
    "reason": "基础功能存在BUG",          # 用户口径：只写这一句
    "risks": [
        "1）开关机压力测试，出现1轮设备DUMP（小概率）",
        "2）组合升级压力测试，出现小概率下载失败（升级本身正常，下次升级也正常）",
    ],
    "bug_counts": {"new": 5, "old": 2, "A": 1, "B": 4, "C": 0, "D": 0, "E": 0},
    "new_bugs": [
        ["QDM562EA-353", "QDM562", "A-Critical", "SPM_Assigned", "描述…", "…_765", "升V修复", "—", "备注"],
    ],
    "old_bugs": [],
    "pressure": [
        ["1", "平台数据交互", "整车静置24h，查看设备在线状态", "无", "P1", "4GAUTO",
         "765", "864107081450429", "24h", "PASS", "24H平台数据交互正常", "Venus", ""],
    ],
    "drop_road_test": True,
    "table_scale": 0.5,        # Outlook 只认 px，按这个比例缩 td 宽度
    "widths": {
        "defect": [85, 55, 65, 85, 330, 120, 60, 60, 196],
        "pressure": [18, 55, 110, 90, 24, 50, 40, 95, 55, 40, 240, 25, 74],
    },
}


def set_cell(soup, td, text, red=False):
    """保留 td 样式，只换内部文本（沿用第一个 <p>）。"""
    p = td.find("p")
    target = p if p is not None else td
    target.clear()
    sp = soup.new_tag("span")
    if red:
        sp["style"] = "color:red"
    sp.string = text
    target.append(sp)


def cell_text(td):
    return td.get_text("", strip=True)


def rebuild(src, out, cfg):
    prev, cur = cfg["prev"], cfg["cur"]
    soup = BeautifulSoup(io.open(src, encoding="utf-8").read(), "html.parser")
    tables = soup.find_all("table")

    # ---- 1) 功能矩阵：版本号 + 整车结果
    if tables:
        for tr in tables[0].find_all("tr"):
            tds = tr.find_all("td", recursive=False)
            if len(tds) == 8 and cell_text(tds[0]) == prev:
                set_cell(soup, tds[0], cur)
            if len(tds) == 7 and cell_text(tds[0]) == "PASS" and cell_text(tds[-1]) == "PASS":
                set_cell(soup, tds[0], "FAIL", red=True)

    # ---- 2) 缺陷统计 + 问题点记录
    if len(tables) > 1:
        t1 = tables[1]
        rows = t1.find_all("tr")
        bc = cfg["bug_counts"]
        for idx, val in ((1, bc["new"]), (2, bc["old"]), (3, bc["A"]),
                         (4, bc["B"]), (5, bc["C"]), (6, bc["D"]), (7, bc["E"])):
            if idx < len(rows):
                tds = rows[idx].find_all("td", recursive=False)
                if len(tds) >= 2:
                    set_cell(soup, tds[1], str(val))

        # 找到「新增 bug」/「历史 bug」锚点与一条 9 列数据行做模板
        anchor_new = anchor_old = tmpl = None
        for tr in rows:
            tds = tr.find_all("td", recursive=False)
            t = cell_text(tds[0]) if tds else ""
            if t == "新增 bug" or t == "新增bug":
                anchor_new = tr
            elif t == "历史 bug" or t == "历史bug":
                anchor_old = tr
            elif len(tds) == 9 and t.startswith("QDM") and tmpl is None:
                tmpl = str(tr)
        if tmpl and anchor_new and anchor_old:
            # 删掉原有数据行（锚点后、下个锚点前的 9 列行）
            for tr in rows:
                tds = tr.find_all("td", recursive=False)
                if len(tds) == 9 and cell_text(tds[0]).startswith("QDM"):
                    tr.decompose()
            for anchor, data_list in ((anchor_new, cfg["new_bugs"]), (anchor_old, cfg["old_bugs"])):
                cur_tr = anchor
                for data in data_list:
                    tr = BeautifulSoup(tmpl, "html.parser").find("tr")
                    tds = tr.find_all("td", recursive=False)
                    for i, v in enumerate(data[:len(tds)]):
                        set_cell(soup, tds[i], v)
                    cur_tr.insert_after(tr)
                    cur_tr = tr

    # ---- 3) 压力表
    if len(tables) > 2:
        t2 = tables[2]
        rows2 = t2.find_all("tr")
        if len(rows2) > 1:
            row_html = str(rows2[1])
            for tr in rows2[1:]:
                tr.decompose()
            head = rows2[0]
            cur_tr = head
            for data in cfg["pressure"]:
                tr = BeautifulSoup(row_html, "html.parser").find("tr")
                tds = tr.find_all("td", recursive=False)
                for i, v in enumerate(data[:len(tds)]):
                    set_cell(soup, tds[i], v, red=(v == "FAIL"))
                cur_tr.insert_after(tr)
                cur_tr = tr

    # ---- 4) 删路测（表格 + "N、路测" 段落）
    if cfg["drop_road_test"]:
        for t in tables[3:]:
            t.decompose()
        for p in soup.find_all("p"):
            if p.find_parent("table") is not None:
                continue
            t = p.get_text("", strip=True)
            if re.match(r"^\d+\s*、?\s*路测", t):
                p.decompose()

    # ---- 5) 正文：版本号 / 原因 / 风险
    for p in soup.find_all("p"):
        if p.find_parent("table") is not None:
            continue
        for sp in p.find_all("span"):
            s = sp.get_text()
            if "_" + prev in s:
                sp.string = s.replace("_" + prev, "_" + cur)
            if "当前报告的版本是" in s:
                sp.decompose()
            if "基础功能存在" in s or "整车存在" in s:
                sp.string = cfg["reason"]

    risk_ps = [p for p in soup.find_all("p")
               if p.find_parent("table") is None and re.match(r"^\u00a0*\d\s*）", p.get_text("", strip=True)]
    if risk_ps:
        holder = risk_ps[0]
        for i, rt in enumerate(cfg["risks"]):
            if i == 0:
                holder.clear()
            else:
                np = soup.new_tag("p")
                np["class"] = holder.get("class") or "MsoNormal"
                holder.insert_after(np)
                holder = np
            sp = soup.new_tag("span")
            sp["style"] = "color:red"
            sp.string = "\u00a0" * 3 + rt          # 3 个空格，与「测试风险」对齐
            holder.append(sp)
        for p in risk_ps[1:]:
            p.decompose()

    # ---- 6) 表格宽度：td px × scale，再按 widths 重分配
    k = cfg["table_scale"]
    for t in soup.find_all("table"):
        if t.has_attr("width"):
            del t["width"]
        st = re.sub(r"width:\s*[^;]+;?", "", t.get("style") or "")
        t["style"] = (st + " table-layout:fixed;").strip()
        for td in t.find_all("td"):
            if td.has_attr("width"):
                try:
                    td["width"] = str(int(float(td["width"]) * k))
                except ValueError:
                    pass

    W = cfg["widths"]
    for ti, key in ((1, "defect"), (2, "pressure")):
        if len(tables) <= ti:
            continue
        ws = W.get(key)
        if not ws:
            continue
        for tr in soup.find_all("table")[ti].find_all("tr"):
            tds = tr.find_all("td", recursive=False)
            if len(tds) == len(ws):
                for i, td in enumerate(tds):
                    td["width"] = str(ws[i])

    body = str(soup)
    io.open(out, "w", encoding="utf-8").write(body)
    print("写出:", out, len(body), "字符")
    return body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="上一版邮件 HTML")
    ap.add_argument("--out", required=True)
    ap.add_argument("--data", default=None, help="data.json（结构同 DEFAULTS）")
    ap.add_argument("--prev")
    ap.add_argument("--cur")
    a = ap.parse_args()

    cfg = json.loads(json.dumps(DEFAULTS))
    if a.data:
        cfg.update(json.load(io.open(a.data, encoding="utf-8")))
    if a.prev:
        cfg["prev"] = a.prev
    if a.cur:
        cfg["cur"] = a.cur
    rebuild(a.src, a.out, cfg)


if __name__ == "__main__":
    main()
