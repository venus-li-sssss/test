# -*- coding: utf-8 -*-
"""按 config.jira 拉取 JIRA 缺陷明细并落盘 JSON（已归一化成报告需要的字段）。

用法: python jira_pull.py --config <config.json>
产物写到 config.jira.out
"""
import argparse
import json
import os
import sys

DEFAULT_SCRIPTS = (
    r"C:\Users\venus.li\.qwenpaw\workspaces\default\skills\jira-data-access\scripts"
)


def norm(row):
    a = row.get("a_version") or ""
    v = row.get("v_version") or ""
    fv = (a + "_" + v) if (a and v) else (a or v)
    return {
        "key": row["key"],
        "project": row.get("project") or "",
        "severity": row.get("severity") or "",
        "status": row.get("status") or "",
        "desc": row.get("summary") or "",
        "found_version": fv,
        "st_review": row.get("st_review") or "",
        "sw_review": row.get("sw_review") or "",
        "summary": row.get("summary") or "",
        "comments": row.get("comments") or [],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding="utf-8"))
    j = cfg.get("jira") or {}
    sys.path.insert(0, j.get("scripts_dir") or DEFAULT_SCRIPTS)
    from jira_client import JIRAClient  # noqa

    client = JIRAClient(j["account"], j["password"])
    # 优先用 config.jira.bug_keys 精确取（问题统计表是人工维护的清单，
    # 且 search_issues 默认会剔除 ST_Closed，会把历史报告里本来列出的已关闭缺陷漏掉）
    keys = j.get("bug_keys")
    if not keys:
        keys = [it["key"] for it in client.search_issues(j["jql"], max_results=None)]
    rows = []
    for k in keys:
        raw, d = client.get_issue_detail(k)
        cf = d.get("custom_fields") or {}
        rows.append({
            "key": d.get("key") or k,
            "summary": d.get("summary"),
            # 用 JIRA 真实工作流状态（ST_Open/STL_Checked/DO/Working/SPM_Assigned…）。
            # 自定义字段「BUG状态」会滞后（例：131 实际已 ST_Closed，该字段仍写 ST_Open）
            "status": d.get("status") or cf.get("BUG状态") or "",
            "severity": cf.get("BUG严重等级") or "",
            "a_version": cf.get("BUG发现的A版本") or "",
            "v_version": cf.get("BUG发现的V版本") or "",
            "st_review": cf.get("ST BUG评估意见") or "",
            "sw_review": cf.get("SW BUG评估意见") or "",
            "project": j.get("project_label") or (rows_project(d.get("key"))),
            "comments": d.get("comments") or [],
        })
    out = [norm(r) for r in rows]
    path = j.get("out") or os.path.join(os.path.dirname(a.config), "jira_bugs.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("JIRA rows=%d -> %s" % (len(out), path))


def rows_project(key):
    p = (key or "").split("-")[0]
    return p[:-2] if p.endswith("EA") else p


if __name__ == "__main__":
    main()
