#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""送测邮件 → SMOD 修改点 + 测试用例 → 修改点报告。默认 dry-run，只读不写。

用法：
    python sendtest_flow.py --project QDM562 --version-hint 766
    python sendtest_flow.py --project QDM562 --version-hint 766 --apply ^
        --hw-platform ASR1602S --executor me --case-result ps --out-dir "D:\\work\\QDM562\\版本测试\\766"

设计要点（踩过的坑，别改）：
  * 没有 changelist 附件时 fail-closed 退出（exit 2），不许拿旧版本顶替。
  * 版本号前缀不是项目名（LTE01R07A05_...），项目关键字一律用 --project。
  * 硬件平台不猜，猜不到就报错让人显式给（QDM562 历史里 ASR1602/ASR1602S/ASR1606 混着）。
"""
import argparse
import base64
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.path.abspath(os.path.join(HERE, "..", "..", ".."))          # <工作区>
MAIL_DIR = os.path.join(WS, "scripts", "delegated-outlook-ikotek")   # 邮件 skill 实现 + 令牌
CL_DIR = os.path.join(WS, "skills", "changelist2xlsx", "scripts")    # 修改点 skill 实现
SHARED_DIR = os.path.join(WS, "scripts")                             # 共用小工具（凭据读取）

PLATFORM_TOKENS = [
    # 只认 SMOD 的「硬件平台」口径（芯片），模块名（EG800AK / ML307C / Y028D）不是平台
    "ASR1602S", "ASR1602", "ASR1605", "ASR1606", "ASR1603", "ASR1601",
    "STM32G0", "STM32U5", "STM32F4",
]
VERSION_LINE_RE = re.compile(
    r"(?:测试版本|版本信息|客户版本号|软件版本|版本号)\s*[:：]\s*([A-Za-z0-9][A-Za-z0-9_.\-]{10,})"
)
VERSION_CAND_RE = re.compile(r"\b([A-Z][A-Za-z0-9_.\-]{12,})_[0-9A-Fa-fVv]{3,}\b")
CHANGELIST_NAME_RE = re.compile(r"(changelist|修改点).*\.txt$", re.IGNORECASE)
SAFE_NAME_RE = re.compile(r"[^0-9A-Za-z._\-\u4e00-\u9fff]")


def say(msg=""):
    print(msg, flush=True)


def die(msg, code=1):
    say("ERROR: " + msg)
    sys.exit(code)


def need_path(p, what):
    if not os.path.exists(p):
        die("找不到%s：%s" % (what, p))
    return p


def safe_filename(name, fallback="attachment.bin"):
    """只保留文件名本身（去目录）并替换非法字符，防路径穿越。"""
    base = os.path.basename((name or "").replace("\\", "/"))
    base = SAFE_NAME_RE.sub("_", base).lstrip(".")
    return base or fallback


# ---------------------------------------------------------------- 邮件
def load_mail_client():
    need_path(os.path.join(MAIL_DIR, "graph_mail.py"), "邮件 skill 实现目录")
    sys.path.insert(0, MAIL_DIR)
    from graph_mail import GraphMailClient  # noqa: E402
    return GraphMailClient()


def pick_mail(client, project, version_hint, limit=30):
    """搜项目相关邮件，挑最新一封「送测 / 送样 / 提测」主题的。"""
    msgs = client.search_messages(project, top=limit)
    say("搜索关键词 %r -> 命中 %d 封" % (project, len(msgs)))
    cands = []
    for m in msgs:
        subj = (m.get("subject") or "").strip()
        if "DO NOT REPLY" in subj.upper():
            continue
        if not any(k in subj for k in ("送测", "送样", "提测")):
            continue
        if version_hint and version_hint.lower() not in json.dumps(m, ensure_ascii=False).lower():
            continue
        cands.append(m)
    if not cands:
        die("没找到符合条件的送测邮件（project=%s, hint=%s）。放宽 --version-hint 或先手工确认邮件。"
            % (project, version_hint), 2)
    cands.sort(key=lambda m: m.get("receivedDateTime", ""), reverse=True)
    return cands


def fetch_detail(client, mid, outdir):
    """取正文 + 非内嵌附件（附件落 outdir，文件名做过清洗）。"""
    sel = "subject,from,receivedDateTime,body,hasAttachments"
    m = client._request("GET", "/me/messages/%s?$select=%s" % (mid, sel))
    body = (m.get("body") or {}).get("content", "")
    txt = re.sub(r"<br\s*/?>|</p>|</div>", "\n", body)
    txt = re.sub(r"<[^>]+>", "", txt)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"')):
        txt = txt.replace(a, b)
    txt = re.sub(r"\n{3,}", "\n\n", txt)

    files = []
    try:
        atts = client._request("GET", "/me/messages/%s/attachments" % mid).get("value", [])
    except Exception as e:  # 附件接口失败不致命，交给闸门判断
        say("  (附件读取失败：%s)" % e)
        atts = []
    for a in atts:
        if a.get("isInline"):
            continue
        name = safe_filename(a.get("name"))
        data = base64.b64decode(a["contentBytes"]) if a.get("contentBytes") else b""
        os.makedirs(outdir, exist_ok=True)
        p = os.path.join(outdir, name)
        Path(p).write_bytes(data)
        files.append({"name": name, "path": p, "size": len(data)})
    return m, txt, files


# ---------------------------------------------------------------- 解析
def parse_version(text, project):
    for m in VERSION_LINE_RE.finditer(text):
        v = m.group(1).strip().rstrip("，,;；")
        if project.split("_")[0] in v or len(v) > 20:
            return v
    cands = [m.group(0) for m in VERSION_CAND_RE.finditer(text)]
    cands = [c for c in cands if project[:3] in c or len(c) > 25]
    if not cands:
        return None
    return max(cands, key=len)


def parse_platform(text):
    up = text.upper()
    for t in PLATFORM_TOKENS:      # 列表已按长串优先，ASR1602S 先于 ASR1602 命中
        if t.upper() in up:
            return t
    return None


def pick_changelist(files):
    return [f for f in files if CHANGELIST_NAME_RE.search(f["name"])]


# ---------------------------------------------------------------- SMOD
def smod_client():
    need_path(os.path.join(CL_DIR, "smod_client.py"), "修改点 skill 实现目录")
    sys.path.insert(0, CL_DIR)
    if SHARED_DIR not in sys.path:
        sys.path.insert(0, SHARED_DIR)
    from smod_client import SmodClient                 # noqa: E402
    from smod_creds import load_credentials            # noqa: E402
    cred = load_credentials()
    c = SmodClient(platform_code="odmm")
    c.login_by_password(cred["username"], cred["password"])
    say("SMOD 登录：%s" % (c.get_user() or {}).get("name"))
    return c


def find_beta_ver(c, project, version):
    res = c.search_projects(keyword=project, page=1, size=100, platform_code="odmm")
    recs = res.get("records", []) if isinstance(res, dict) else []
    for r in recs:
        if str(r.get("code", "")).strip().lower() == version.strip().lower():
            return r
    return None


def download_report(c, id_beta_ver, version, out_dir):
    """导修改点报告（含用例），按 <完整版本号>_修改点测试报告_Report.xlsx 归档。"""
    os.makedirs(out_dir, exist_ok=True)
    r = c.session.get("%s/api/projects/odmm/betavers/%s/report" % (c.base_url, id_beta_ver),
                      params={"access_token": c.access_token}, timeout=60)
    if r.status_code != 200:
        return None, "report 接口 %s: %s" % (r.status_code, r.text[:200])
    url = (r.json() or {}).get("data")
    if not url:
        return None, "report 接口未返回下载地址：%s" % r.text[:200]
    d = c.session.get(url, timeout=120)
    dst = os.path.join(out_dir, "%s_修改点测试报告_Report.xlsx" % version)
    Path(dst).write_bytes(d.content)
    return dst, None


# ---------------------------------------------------------------- 主流程
def _run_import(txt_path, version, platform, project, args):
    """导入 + 建用例，逻辑全在 changelist2xlsx。"""
    if CL_DIR not in sys.path:
        sys.path.insert(0, CL_DIR)
    if SHARED_DIR not in sys.path:
        sys.path.insert(0, SHARED_DIR)
    from smod_changelist_import import run_workflow   # noqa: E402
    from smod_creds import load_credentials           # noqa: E402
    cred = load_credentials()
    run_workflow(
        txt_path=txt_path,
        version_code=version,
        username=cred["username"],
        password=cred["password"],
        platform_code="odmm",
        hw_platform=platform,
        project_keyword=project,
        auto_create=True,
        create_cases=True,
        case_result=args.case_result,
        executor=args.executor,
    )


def main():
    ap = argparse.ArgumentParser(description="送测邮件 -> SMOD 修改点 -> 测试用例 -> 修改点报告")
    ap.add_argument("--project", required=True, help="项目号，如 QDM562（同时作为搜邮件与 SMOD 项目关键字）")
    ap.add_argument("--version-hint", default=None, help="只用主题/内容含该串的邮件，如 766")
    ap.add_argument("--hw-platform", default=None, help="SMOD 硬件平台，如 ASR1602S")
    ap.add_argument("--executor", default=None, help="修改点执行人：me / 用户 id / 当前登录人姓名或邮箱")
    ap.add_argument("--case-result", default="ti", help="用例与修改点结论：ps=PASS / ti=Test-in-Process / pc=PASS With Comments")
    ap.add_argument("--apply", action="store_true", help="真写平台（默认只 dry-run 打印计划）")
    ap.add_argument("--out-dir", default=None, help="报告归档目录，默认 D:\\work\\<项目>\\版本测试\\<版本末段>")
    ap.add_argument("--mail-limit", type=int, default=30, help="邮件搜索条数上限")
    args = ap.parse_args()

    project = args.project.strip()
    say("=" * 70)
    say("① 读送测邮件  project=%s  hint=%s" % (project, args.version_hint or "-"))
    client = load_mail_client()
    cands = pick_mail(client, project, args.version_hint, args.mail_limit)
    top = cands[0]
    say("选中邮件：%s" % top.get("subject"))
    say("  时间 %s | 来自 %s" % (top.get("receivedDateTime"),
                                 (top.get("from") or {}).get("emailAddress", {}).get("address")))

    tmp_dir = os.path.join(WS, "tmp", "sendtest_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    detail, body, files = fetch_detail(client, top["id"], tmp_dir)
    say("  非内嵌附件：%d 个 %s" % (len(files), [f["name"] for f in files]))

    say("\n② 解析版本号 / 平台")
    version = parse_version(body, project)
    platform = args.hw_platform or parse_platform(body)
    if not version:
        die("没从邮件正文解析出版本号，请手工确认后走 changelist2xlsx 的分步命令。", 2)
    say("  版本号：%s" % version)
    say("  硬件平台：%s" % (platform or "(未识别)"))
    ver_tail = version.split("_")[-1]

    say("\n③ 闸门校验")
    changelists = pick_changelist(files)
    if not changelists:
        say("  ✗ 该邮件没有 changelist / 修改点 txt 附件。")
        say("    正确动作：向发件人索要本版本的修改点文件；")
        say("    绝不能用上一版 changelist 顶替（版本对不上会把旧修改点写进新版本）。")
        die("缺修改点文件，已拦下未导入。", 2)
    say("  ✓ 修改点文件：%s" % ", ".join("%s(%dB)" % (f["name"], f["size"]) for f in changelists))
    if not platform:
        if args.apply:
            die("硬件平台未识别，请显式给 --hw-platform（QDM562 固定 ASR1602S）。", 2)
        say("  ! 硬件平台未识别：正文里没有芯片型号，--apply 时必须用 --hw-platform 指定")

    say("\n④ 计划")
    out_dir = args.out_dir or os.path.join("D:\\work", project, "版本测试", ver_tail)
    plan = {
        "mail": top.get("subject"),
        "version": version,
        "hw_platform": platform,
        "project": project,
        "changelist": [f["path"] for f in changelists],
        "executor": args.executor,
        "case_result": args.case_result,
        "out_dir": out_dir,
        "apply": bool(args.apply),
    }
    say(json.dumps(plan, ensure_ascii=False, indent=2))

    if not args.apply:
        say("\n[dry-run] 未写平台。确认无误后加 --apply 重跑。")
        return

    say("\n⑤ 导入 SMOD + 建用例")
    for cl in changelists:          # 一封邮件通常只有一个修改点文件；多个时依次导入
        _run_import(cl["path"], version, platform, project, args)

    say("\n⑥ 导修改点报告")
    c = smod_client()
    row = find_beta_ver(c, project, version)
    if not row:
        die("导入后在 SMOD 查不到该版本，请到平台确认。")
    say("  id_beta_ver=%s" % row.get("id"))
    dst, err = download_report(c, row["id"], version, out_dir)
    if err:
        die("报告下载失败：" + err)
    say("  报告：%s" % dst)

    say("\n⑦ 复核")
    pts = c.list_points(row["id"], page=1, size=500, platform_code="odmm").get("records", [])
    for p in sorted(pts, key=lambda x: x["id"]):
        cases = c.list_cases_for_point(p["id"], platform_code="odmm")
        say("  修改点 %s | %s | 执行人=%s | 用例 %d 条"
            % (p.get("id"), p.get("test_result_name"), p.get("name_executor") or "-", len(cases)))
        for x in cases:
            say("     - %s %s %s" % (x.get("code"), x.get("test_result_name"), x.get("summary")))
    say("\n完成：%s" % dst)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
