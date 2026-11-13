# -*- coding: utf-8 -*-
"""从飞书多维表格「GNSS的RTK账号信息」取 RTK 账号，输出给抓取工具 / AI 用。

用法:
    python rtk_accounts.py                 # 打印列表（TSV，人能看，exe 也能直接解析）
    python rtk_accounts.py --json          # 打印 JSON
    python rtk_accounts.py --out a.json    # 写缓存文件（GUI 的「从多维表格导入」读它）
    python rtk_accounts.py --out a.tsv --tsv
    python rtk_accounts.py --pick          # 挑一个可用账号，打印 user pass host port mount

账号表：资源 → GNSS的RTK账号信息
        app_token=HTqJbzD5TaCqjtsjxKGcAOvunwP table=tbl4AZDuMVwtfTSY
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.request

APP_TOKEN = "HTqJbzD5TaCqjtsjxKGcAOvunwP"
TABLE_ID = "tbl4AZDuMVwtfTSY"
FEISHU = "https://open.feishu.cn"
APP_ID = os.environ.get("FEISHU_APP_ID", "cli_a9bc97317fb89cc8")
_DEFAULT_SECRET = base64.b64decode("cnRUc0VaZnZOQWZsN3c3RFpBVklFZnJyUlNRZUZUZmg=").decode()
APP_SECRET = os.environ.get("FEISHU_APP_SECRET") or _DEFAULT_SECRET
CACHE = os.path.join(os.path.expanduser("~"), ".feishu_tat_cache.json")

F = {  # 列名 → 内部字段（表头是中英混排，按包含匹配，改列名也能用）
    "name": ("账号名称",),
    "user": ("Username", "账号"),
    "pass": ("Password", "密码"),
    "host": ("Adress", "地址"),
    "port": ("Port", "端口"),
    "mount": ("Mount", "挂载点"),
    "status": ("账号状态",),
    "note": ("备注",),
}


def log(msg):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        pass


def get_token(force=False):
    if not force and os.path.isfile(CACHE):
        try:
            c = json.load(open(CACHE, "r", encoding="utf-8"))
            if c.get("app_id") == APP_ID and c.get("expire_at", 0) > time.time() + 300:
                return c["token"]
        except Exception:
            pass
    req = urllib.request.Request(
        FEISHU + "/open-apis/auth/v3/tenant_access_token/internal",
        data=json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.load(r)
    if d.get("code") != 0:
        raise RuntimeError("取 token 失败: %s" % d.get("msg"))
    tok = d["tenant_access_token"]
    try:
        json.dump({"app_id": APP_ID, "token": tok, "expire_at": time.time() + d.get("expire", 7200)},
                  open(CACHE, "w", encoding="utf-8"))
    except Exception:
        pass
    return tok


def fetch(force=False):
    url = "%s/open-apis/bitable/v1/apps/%s/tables/%s/records?page_size=100" % (FEISHU, APP_TOKEN, TABLE_ID)
    tok = get_token(force)
    rows, page_token = [], None
    while True:
        u = url + ("&page_token=" + page_token if page_token else "")
        req = urllib.request.Request(u, headers={"Authorization": "Bearer " + tok})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.load(r)
        except Exception:
            tok = get_token(True)          # token 过期重试一次
            req = urllib.request.Request(u, headers={"Authorization": "Bearer " + tok})
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.load(r)
        if d.get("code") != 0:
            raise RuntimeError("读表失败: code=%s msg=%s" % (d.get("code"), d.get("msg")))
        data = d.get("data") or {}
        for it in data.get("items") or []:
            rows.append(normalize(it.get("fields") or {}))
        page_token = data.get("page_token")
        if not data.get("has_more") or not page_token:
            break
    return rows


def pick_field(fields, keys):
    for k, v in fields.items():
        for key in keys:
            if key.lower() in str(k).lower():
                if isinstance(v, list):
                    v = "".join([str(x.get("text", x)) if isinstance(x, dict) else str(x) for x in v])
                return str(v).strip()
    return ""


def normalize(fields):
    return {k: pick_field(fields, aliases) for k, aliases in F.items()}


TSV_HEAD = ["name", "user", "pass", "host", "port", "mount", "status", "note"]


def to_tsv(rows):
    out = ["\t".join(TSV_HEAD)]
    for r in rows:
        out.append("\t".join(str(r.get(k, "")).replace("\t", " ").replace("\n", " ")
                             for k in TSV_HEAD))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="从飞书多维表格取 RTK 账号（NTRIP）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--tsv", action="store_true", help="输出 TSV（默认也是 TSV）")
    ap.add_argument("--out", default="", help="写到文件（后缀 .json 写 JSON，否则写 TSV）")
    ap.add_argument("--pick", action="store_true", help="挑一个可用账号，打印 user pass host port mount")
    ap.add_argument("--only-available", action="store_true", help="只输出 账号状态=可用")
    ap.add_argument("--refresh", action="store_true", help="强制刷新 token")
    a = ap.parse_args()

    try:
        rows = fetch(force=a.refresh)
    except Exception as e:
        log("[rtk] ERROR: %s" % e)
        return 2

    if a.only_available:
        rows = [r for r in rows if "可用" in (r.get("status") or "")]
    if not rows:
        log("[rtk] 表里没有可用账号")
        return 3

    if a.out:
        path = os.path.abspath(a.out)
        if path.lower().endswith(".json"):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, indent=2)
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(to_tsv(rows))
        log("[rtk] 已写入 %s（%d 条）" % (path, len(rows)))

    if a.pick:
        r = rows[0]
        log("%s\t%s\t%s\t%s\t%s" % (r.get("user"), r.get("pass"), r.get("host"), r.get("port"), r.get("mount")))
    elif a.json:
        log(json.dumps(rows, ensure_ascii=False, indent=2))
    elif not a.out:
        log(to_tsv(rows))

    for r in rows:
        note = (r.get("note") or "").replace("\n", " ")
        log("[rtk] %s %s %s:%s/%s %s %s" % (r.get("name"), r.get("user"), r.get("host"),
                                            r.get("port"), r.get("mount"), r.get("status"), note[:40]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
