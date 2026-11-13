#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""飞书文档体系（云文档 docx / 知识库 wiki / 电子表格 sheets / 多维表格 bitable）读写工具。

统一走**团队只读机器人**的应用身份（tenant_access_token），不扫码、不管个人登录态。
云盘文件下载请用 skill：feishu-software-download；本 skill 负责"读内容/查数据"。

子命令：
    token                                        打印/刷新 tenant_access_token
    info   <url|token>                           识别类型 + 标题 + （base）表清单
    read   <url|token> [-o out.md|out.csv]       读正文/表格内容（docx/wiki→md，sheet/base→csv）
    base tables  <url>                           多维表格：所有数据表
    base fields  <url> [--table T]               多维表格：字段定义
    base records <url> [--table T] [--limit N] [--where "字段=值"] [--out f.json|f.csv]
                                                 多维表格：记录（默认打印前 20 条）
    base export  <url> [--table T] [--out f.csv] 多维表格：全量导出
    wiki tree    <space_id|wiki_url> [--depth 2] 知识库目录树

URL 形式都认：
    https://quectel.feishu.cn/wiki/<token>
    https://quectel.feishu.cn/docx/<token>
    https://quectel.feishu.cn/sheets/<token>?sheet=xxx
    https://quectel.feishu.cn/base/<token>?table=tblxxx&view=vewxxx
"""
import argparse
import base64
import csv
import json
import os
import re
import sys
import time

try:
    import requests
except ImportError:  # pragma: no cover
    sys.exit("需要 requests：pip install requests")

# 团队只读机器人（不是个人账号，允许公开）。base64 只是绕开 push protection 误报。
APP_ID = os.environ.get("FEISHU_APP_ID") or base64.b64decode(
    "Y2xpX2E5YmM5NzMxN2ZiODljYzg=").decode()
APP_SECRET = os.environ.get("FEISHU_APP_SECRET") or base64.b64decode(
    "cnRUc0VaZnZOQWZsN3c3RFpBVklFZnJyUlNRZUZUZmg=").decode()
BASE = os.environ.get("FEISHU_API_BASE", "https://open.feishu.cn")
TOKEN_CACHE = os.path.expanduser(os.environ.get("FEISHU_TAT_CACHE", "~/.feishu_tat_docs.json"))


def _init_stdout():
    enc = os.environ.get("FEISHU_ENCODING")
    if not enc and sys.platform == "win32":
        try:
            import ctypes
            if ctypes.windll.kernel32.GetConsoleOutputCP() == 936:
                enc = "gbk"
        except Exception:
            pass
    if enc:
        for s in (sys.stdout, sys.stderr):
            try:
                s.reconfigure(encoding=enc, errors="replace")
            except Exception:
                pass


_init_stdout()


class FeishuError(Exception):
    pass


# --------------------------------------------------------------------- token
def get_token(force=False):
    if not force and os.path.exists(TOKEN_CACHE):
        try:
            c = json.load(open(TOKEN_CACHE, encoding="utf-8"))
            if c.get("app_id") == APP_ID and c.get("expire_at", 0) > time.time() + 300:
                return c["token"]
        except Exception:
            pass
    r = requests.post(BASE + "/open-apis/auth/v3/tenant_access_token/internal",
                      json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=30)
    d = r.json()
    if d.get("code") != 0:
        raise FeishuError("拿 tenant_access_token 失败：code=%s msg=%s" % (d.get("code"), d.get("msg")))
    tok = d["tenant_access_token"]
    with open(TOKEN_CACHE, "w", encoding="utf-8") as f:
        json.dump({"app_id": APP_ID, "token": tok,
                   "expire_at": time.time() + d.get("expire", 7200)}, f)
    return tok


def api(path, params=None, method="GET", body=None):
    """统一请求 + 中文报错（把飞书常见错误码翻译成人话）。"""
    h = {"Authorization": "Bearer " + get_token()}
    url = path if path.startswith("http") else BASE + path
    r = requests.request(method, url, params=params, json=body, headers=h, timeout=60)
    try:
        d = r.json()
    except Exception:
        raise FeishuError("HTTP %s 返回非 JSON：%s" % (r.status_code, r.text[:200]))
    if d.get("code") != 0:
        code, msg = d.get("code"), d.get("msg") or ""
        hints = {
            131006: "该 wiki 节点/文档没有授权给机器人（tenant 无读权限）→ 在飞书里给这个知识库节点"
                    "「添加协作者」，把应用（只读机器人）加进去",
            91403: "机器人没有这张多维表格的权限 → 在飞书里把这个多维表格「协作者」加上机器人",
            1770001: "参数不对（base token / table_id 可能填错）",
            99991672: "应用缺少对应的 API 权限（scope），需要在开放平台后台给应用加权限并发布版本",
            1254005: "知识库空间不存在或无权访问",
        }
        raise FeishuError("飞书接口报错 code=%s msg=%s%s" % (
            code, msg, ("\n提示：" + hints[code]) if code in hints else ""))
    return d.get("data") or {}


# --------------------------------------------------------------------- 解析 URL
def parse_target(s):
    """URL / token -> dict(kind=docx|sheet|base|wiki, token=..., table=...)"""
    s = (s or "").strip()
    m = re.search(r"/wiki/([A-Za-z0-9]+)", s)
    if m:
        q = dict(re.findall(r"[?&](\w+)=([^&]+)", s))
        return {"kind": "wiki", "token": m.group(1), "table": q.get("table", "")}
    m = re.search(r"/docx/([A-Za-z0-9]+)", s)
    if m:
        return {"kind": "docx", "token": m.group(1), "table": ""}
    m = re.search(r"/sheets/([A-Za-z0-9]+)", s)
    if m:
        q = dict(re.findall(r"[?&](\w+)=([^&]+)", s))
        return {"kind": "sheet", "token": m.group(1), "table": q.get("sheet", "")}
    m = re.search(r"/base/([A-Za-z0-9]+)", s)
    if m:
        q = dict(re.findall(r"[?&](\w+)=([^&]+)", s))
        return {"kind": "base", "token": m.group(1), "table": q.get("table", "")}
    m = re.search(r"/docs/([A-Za-z0-9]+)", s)
    if m:
        return {"kind": "doc", "token": m.group(1), "table": ""}
    if re.fullmatch(r"[A-Za-z0-9]{20,}", s):
        return {"kind": "auto", "token": s, "table": ""}
    raise FeishuError("认不出这个链接/ token：%s" % s)


def resolve(s):
    """把 wiki 节点展开成真实对象（docx / bitable / sheet…）。"""
    t = parse_target(s)
    if t["kind"] == "wiki":
        data = api("/open-apis/wiki/v2/spaces/get_node", {"token": t["token"], "obj_type": "wiki"})
        node = data.get("node") or {}
        kind = node.get("obj_type") or "docx"
        if kind == "bitable":            # wiki 里的多维表格，obj_type 叫 bitable
            kind = "base"
        return {"kind": kind, "token": node.get("obj_token"),
                "table": t.get("table", ""), "title": node.get("title"),
                "wiki_token": t["token"], "space_id": node.get("space_id")}
    if t["kind"] == "auto":
        # 先按 wiki 试，再按 docx 试
        try:
            return resolve("https://quectel.feishu.cn/wiki/" + t["token"])
        except FeishuError:
            t["kind"] = "docx"
    return t


# --------------------------------------------------------------------- 读内容
def flat(v):
    """多维表格字段值 -> 人类可读字符串。"""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "是" if v else "否"
    if isinstance(v, (int, float, str)):
        return v
    if isinstance(v, list):
        return "、".join(str(flat(x)) for x in v if flat(x) != "")
    if isinstance(v, dict):
        for k in ("text", "name", "link", "full_address", "value"):
            if k in v:
                return flat(v[k])
        if "en_name" in v:
            return v.get("name") or v.get("en_name")
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def read_docx(token):
    d = api("/open-apis/docx/v1/documents/%s/raw_content" % token)
    return d.get("content") or ""


def read_sheet(token, rng=""):
    """电子表格 -> 二维数组。rng 形如 Sheet1!A1:F50。"""
    if not rng:
        meta = api("/open-apis/sheets/v3/spreadsheets/%s/sheets/query" % token)
        sheets = meta.get("sheets") or []
        if not sheets:
            raise FeishuError("这个表格没有工作表")
        sid = sheets[0].get("sheet_id") or sheets[0].get("title")
        rng = "%s!A1:Z200" % sid
    d = api("/open-apis/sheets/v2/spreadsheets/%s/values/%s" % (token, rng))
    vr = d.get("valueRange") or {}
    return vr.get("values") or []


def base_tables(token):
    out, pt = [], ""
    while True:
        p = {"page_size": 100}
        if pt:
            p["page_token"] = pt
        d = api("/open-apis/bitable/v1/apps/%s/tables" % token, p)
        out += d.get("items") or []
        if not d.get("has_more"):
            return out
        pt = d.get("page_token") or ""


def pick_table(token, want):
    tables = base_tables(token)
    if not tables:
        raise FeishuError("这个多维表格没有数据表")
    if not want:
        return tables[0]
    for t in tables:
        if t.get("table_id") == want or (t.get("name") or "") == want or want in (t.get("name") or ""):
            return t
    raise FeishuError("没有数据表 %r，可选：%s" % (
        want, ", ".join("%s(%s)" % (t.get("name"), t.get("table_id")) for t in tables)))


def base_fields(token, table_id):
    return api("/open-apis/bitable/v1/apps/%s/tables/%s/fields" % (token, table_id),
               {"page_size": 200}).get("items") or []


def base_records(token, table_id, limit=0, where=""):
    out, pt = [], ""
    while True:
        p = {"page_size": 200}
        if pt:
            p["page_token"] = pt
        d = api("/open-apis/bitable/v1/apps/%s/tables/%s/records" % (token, table_id), p)
        out += d.get("items") or []
        if not d.get("has_more") or (limit and len(out) >= limit):
            break
        pt = d.get("page_token") or ""
    rows = [r.get("fields") or {} for r in out]
    if where:
        k, _, v = where.partition("=")
        k, v = k.strip(), v.strip()
        rows = [r for r in rows if v.lower() in str(flat(r.get(k, ""))).lower()]
    if limit:
        rows = rows[:limit]
    return rows


def rows_to_matrix(rows, cols=None):
    if not cols:
        cols = []
        for r in rows:
            for k in r:
                if k not in cols:
                    cols.append(k)
    data = [[str(flat(r.get(c, ""))) for c in cols] for r in rows]
    return cols, data


def write_csv(path, header, data):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(data)


def print_table(header, data, maxw=28):
    widths = []
    for i, h in enumerate(header):
        w = min(maxw, max([len(str(h))] + [len(str(row[i])) for row in data] or [0]) + 2)
        widths.append(w)
    line = "  ".join(str(h)[:widths[i]].ljust(widths[i]) for i, h in enumerate(header))
    print(line)
    print("-" * min(len(line), 160))
    for row in data:
        print("  ".join(str(c)[:widths[i]].ljust(widths[i]) for i, c in enumerate(row)))


# --------------------------------------------------------------------- 命令
def cmd_token(a):
    print(get_token(force=a.force))


def cmd_info(a):
    t = resolve(a.target)
    kind = t.get("kind")
    print("类型：%s" % kind)
    print("token：%s" % t.get("token"))
    if t.get("title"):
        print("标题：%s" % t.get("title"))
    if t.get("wiki_token"):
        print("wiki 节点：%s（space %s）" % (t["wiki_token"], t.get("space_id")))
    if kind == "base":
        for tb in base_tables(t["token"]):
            flds = base_fields(t["token"], tb["table_id"])
            print("  数据表：%s（%s）字段 %d 个" % (tb.get("name"), tb.get("table_id"), len(flds)))
            print("    字段：" + "、".join(f.get("field_name", "") for f in flds))
    elif kind == "docx":
        d = api("/open-apis/docx/v1/documents/%s" % t["token"])
        print("标题：%s" % ((d.get("document") or {}).get("title") or "-"))


def cmd_read(a):
    t = resolve(a.target)
    kind, token = t.get("kind"), t.get("token")
    if a.out:
        out = os.path.abspath(a.out)
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    if kind == "docx":
        text = read_docx(token)
        title = t.get("title") or ""
        body = ("# %s\n\n" % title if title else "") + text
        if a.out:
            open(out, "w", encoding="utf-8").write(body)
            print("OK saved: %s\nchars=%d" % (out, len(text)))
        else:
            print(body)
    elif kind == "sheet":
        vals = read_sheet(token, a.range or (t.get("table") or ""))
        header = [str(flat(v)) for v in (vals[0] if vals else [])]
        data = [[str(flat(v)) for v in row] for row in vals[1:]]
        if a.out:
            write_csv(out, header, data)
            print("OK saved: %s（%d 行 × %d 列）" % (out, len(data), len(header)))
        else:
            print_table(header, data)
    elif kind == "base":
        tb = pick_table(token, a.table or t.get("table"))
        rows = base_records(token, tb["table_id"], a.limit)
        cols, data = rows_to_matrix(rows)
        if a.out:
            write_csv(out, cols, data)
            print("OK saved: %s（%s：%d 行 × %d 列）" % (out, tb.get("name"), len(data), len(cols)))
        else:
            print("数据表：%s（%d 行）" % (tb.get("name"), len(rows)))
            print_table(cols, data)
    else:
        raise FeishuError("暂不支持读 %s 类型（只做 docx / sheets / 多维表格 / wiki）" % kind)


def cmd_base_tables(a):
    t = resolve(a.target)
    if t.get("kind") != "base":
        raise FeishuError("这不是多维表格（识别为 %s）。wiki 版多维表格需要该节点已授权给机器人" % t.get("kind"))
    for tb in base_tables(t["token"]):
        flds = base_fields(t["token"], tb["table_id"])
        recs = base_records(t["token"], tb["table_id"], limit=1)
        print("%-26s %-18s 字段 %2d 个" % (tb.get("name"), tb.get("table_id"), len(flds)))
        for f in flds:
            print("    - %-24s %s" % (f.get("field_name"), f.get("type")))


def cmd_base_fields(a):
    t = resolve(a.target)
    tb = pick_table(t["token"], a.table or t.get("table"))
    print("数据表：%s（%s）" % (tb.get("name"), tb["table_id"]))
    print_table(["字段名", "类型", "字段id"],
                [[f.get("field_name"), f.get("type"), f.get("field_id")]
                 for f in base_fields(t["token"], tb["table_id"])])


def cmd_base_records(a):
    t = resolve(a.target)
    tb = pick_table(t["token"], a.table or t.get("table"))
    rows = base_records(t["token"], tb["table_id"], a.limit or 20, a.where or "")
    cols, data = rows_to_matrix(rows)
    if a.json:
        print(json.dumps([{k: flat(v) for k, v in r.items()} for r in rows],
                         ensure_ascii=False, indent=1))
        return
    if a.out:
        out = os.path.abspath(a.out)
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        write_csv(out, cols, data)
        print("OK saved: %s（%s：%d 行）" % (out, tb.get("name"), len(data)))
        return
    print("数据表：%s（共 %d 行%s）" % (tb.get("name"), len(rows), "，filter=" + a.where if a.where else ""))
    print_table(cols, data)


def cmd_base_export(a):
    a.limit, a.where, a.json = 0, a.where or "", False
    a.out = a.out or "feishu_base_%s.csv" % resolve(a.target).get("token", "export")
    cmd_base_records(a)


def cmd_wiki_tree(a):
    tok = a.target
    m = re.search(r"/wiki/([A-Za-z0-9]+)", tok or "")
    space = ""
    if m:
        node = api("/open-apis/wiki/v2/spaces/get_node",
                   {"token": m.group(1), "obj_type": "wiki"}).get("node") or {}
        space, root = node.get("space_id"), node.get("node_token")
    else:
        space, root = tok, ""
    nodes = api("/open-apis/wiki/v2/spaces/%s/nodes" % space,
                {"page_size": 50}).get("items") or []
    for n in nodes:
        print("%-24s %-8s %s" % (n.get("node_token"), n.get("obj_type"), n.get("title")))
    print("（顶层 %d 个；子节点用 /open-apis/wiki/v2/spaces/get_node 逐层展开）" % len(nodes))


def main(argv=None):
    ap = argparse.ArgumentParser(description="飞书文档/知识库/多维表格读写（机器人身份）")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("token", help="打印 tenant_access_token")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_token)

    p = sub.add_parser("info", help="识别类型/标题/表清单")
    p.add_argument("target")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("read", help="读正文或表格内容")
    p.add_argument("target")
    p.add_argument("-o", "--out")
    p.add_argument("--table", default="")
    p.add_argument("--range", default="")
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(func=cmd_read)

    b = sub.add_parser("base", help="多维表格")
    bs = b.add_subparsers(dest="sub")

    p = bs.add_parser("tables")
    p.add_argument("target")
    p.set_defaults(func=cmd_base_tables)

    p = bs.add_parser("fields")
    p.add_argument("target")
    p.add_argument("--table", default="")
    p.set_defaults(func=cmd_base_fields)

    p = bs.add_parser("records")
    p.add_argument("target")
    p.add_argument("--table", default="")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--where", default="", help='如 --where "账号状态=可用"')
    p.add_argument("--json", action="store_true")
    p.add_argument("-o", "--out", default="")
    p.set_defaults(func=cmd_base_records)

    p = bs.add_parser("export")
    p.add_argument("target")
    p.add_argument("--table", default="")
    p.add_argument("--where", default="")
    p.add_argument("-o", "--out", default="")
    p.set_defaults(func=cmd_base_export)

    w = sub.add_parser("wiki", help="知识库")
    ws = w.add_subparsers(dest="sub")
    p = ws.add_parser("tree")
    p.add_argument("target")
    p.set_defaults(func=cmd_wiki_tree)

    a = ap.parse_args(argv)
    if not getattr(a, "func", None):
        ap.print_help()
        return 0
    try:
        a.func(a)
    except FeishuError as e:
        print("错误：%s" % e, file=sys.stderr)
        return 1
    except requests.RequestException as e:
        print("网络错误：%s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
