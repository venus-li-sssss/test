#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试用例生成 OpenAPI 客户端（纯标准库，Windows/Linux 通用）

子命令：
  ping                                   验证 token
  create    --doc a.md --name "需求名"     创建任务（可带 --modules modules.json）
  status    <taskId> [--watch]            查状态（--watch 每 20s 轮询到完成/失败/超时）
  result    <taskId> [--out r.json] [--md r.md] [--cases-csv r.csv]
  cases     <taskId> --page 1 --pageSize 200   分页取用例（>2000 条时用）
  export    <taskId> [--dest docs]        下载 Excel
  run       --doc a.md --name "需求名"     一条龙：create → 轮询 → result → export
"""
import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

DEFAULT_BASE = "https://scnrhostplnc-app_4k5zy309bb5wx-1865305019607353.aiforce.run"
# 预览域名：官方文档给的 aiforce.run 主机在应用未发布前会返回
# 404 / 403「api key not allowed to access preview」，此时用这个域名 + 应用路径
PREVIEW_BASE = "https://scnrhostplnc.feishuapp.com/app/app_4k5zy309bb5wx"
APP_SUFFIX = "/app/app_4k5zy309bb5wx"
HERE = Path(__file__).resolve().parent
CFG_FILE = HERE / "config.local.json"


def cfg():
    data = {}
    if CFG_FILE.exists():
        try:
            data = json.loads(CFG_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            sys.exit(f"config.local.json 解析失败：{e}")
    base = os.environ.get("TEST_GEN_BASE") or data.get("base_url") or DEFAULT_BASE
    token = os.environ.get("TEST_GEN_TOKEN") or data.get("token") or ""
    return base.rstrip("/"), token


def _candidates():
    """按优先序给出候选 base：配置的 base → 预览域 → 官方域（去重）"""
    base, token = cfg()
    out = []
    for b in (base, PREVIEW_BASE, DEFAULT_BASE):
        b = b.rstrip("/")
        if b and b not in out:
            out.append(b)
    return out, token


def _once(method, base, path, token, body, timeout):
    import urllib.request
    import urllib.error

    headers = {"Authorization": "Bearer " + token}
    payload = None
    if body is not None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except urllib.error.URLError as e:
        reason = str(e)
        if "CERTIFICATE_VERIFY_FAILED" in reason or "Hostname mismatch" in reason:
            return 495, reason.encode()
        return 0, reason.encode()


def request(method, path, body=None, raw=False, timeout=180):
    bases, token = _candidates()
    if not token:
        sys.exit("缺少 token：设置环境变量 TEST_GEN_TOKEN，或写 scripts/config.local.json（参考 config.example.json）")
    tried, last = [], None
    for base in bases:
        code, data = _once(method, base, path, token, body, timeout)
        tried.append(f"{base} -> {code}")
        text = data.decode("utf-8", "replace") if isinstance(data, bytes) else str(data)
        # 预览闸门 / 证书不匹配 / 路径不存在 → 换下一个 base 再试
        if code in (404, 495) or "not allowed to access preview" in text:
            last = (code, text)
            continue
        if code == 409 and "/export" in path:
            sys.exit("任务未完成（HTTP 409），请先用 status --watch 轮询")
        if not (200 <= code < 300):
            sys.exit(f"HTTP {code} {method} {path}\n{text[:1200]}")
        if raw:
            return data
        return json.loads(text) if text else {}
    code, text = last or (0, "")
    sys.exit("所有 base 都失败：\n  " + "\n  ".join(tried) + f"\n最后响应：{text[:400]}")


def read_doc(path):
    p = Path(path)
    if not p.exists():
        sys.exit(f"文档不存在：{p}")
    text = p.read_text(encoding="utf-8", errors="replace")
    n = len(text)
    print(f"[doc] {p.name}  {n} 字符")
    if n > 200000:
        sys.exit("文档超过 20 万字符上限，请拆分后提交")
    return text


def load_modules(path):
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        sys.exit(f"modules 文件不存在：{p}")
    mods = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(mods, dict) and "modules" in mods:
        mods = mods["modules"]
    if not isinstance(mods, list):
        sys.exit("modules 必须是数组：[{path, description, type}, ...]")
    out = []
    for i, m in enumerate(mods, 1):
        path_ = m.get("path")
        if isinstance(path_, str):
            path_ = [path_]
        if not path_ or not isinstance(path_, list):
            sys.exit(f"第 {i} 个模块缺 path（字符串数组）")
        item = {
            "path": [str(x) for x in path_],
            "description": m.get("description", "") or "",
            "type": str(m.get("type", "1")),
        }
        out.append(item)
    print(f"[modules] {len(out)} 个模块：" + " / ".join(">".join(m["path"]) for m in out[:6])
          + (" ..." if len(out) > 6 else ""))
    return out


def cmd_ping(a):
    r = request("GET", "/openapi/test-generation/ping")
    print(json.dumps(r, ensure_ascii=False, indent=2))
    print("OK token 可用" if r else "返回为空，仍可能有权限问题")


def cmd_create(a):
    content = read_doc(a.doc) if a.doc else (a.content or "")
    if not content:
        sys.exit("必须给 --doc <文件> 或 --content <文本>")
    body = {"name": a.name, "content": content}
    mods = load_modules(a.modules)
    if mods:
        body["modules"] = mods
    if a.test_object:
        body["testObject"] = a.test_object
    if a.background:
        body["background"] = a.background
    if a.file_url:
        body["fileUrl"] = a.file_url
    r = request("POST", "/openapi/test-generation/tasks", body)
    tid = r.get("taskId") or r.get("data", {}).get("taskId") if isinstance(r, dict) else None
    print(json.dumps(r, ensure_ascii=False, indent=2))
    if not tid:
        sys.exit("返回里没有 taskId，请检查 payload")
    if a.save:
        Path(a.save).write_text(json.dumps({"taskId": tid, "name": a.name}, ensure_ascii=False), encoding="utf-8")
        print(f"[save] taskId 已写入 {a.save}")
    print(f"taskId={tid}")
    return tid


def cmd_status(a):
    if not a.watch:
        r = request("GET", f"/openapi/test-generation/tasks/{a.task_id}")
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return r
    start = time.time()
    interval = a.interval
    while True:
        r = request("GET", f"/openapi/test-generation/tasks/{a.task_id}")
        st = (r.get("status") or "").lower()
        el = int(time.time() - start)
        print(f"[{el:>5}s] status={st} {json.dumps({k: v for k, v in r.items() if k != 'status'}, ensure_ascii=False)[:400]}")
        if st in ("completed", "success", "done"):
            print("DONE 任务完成")
            return r
        if st in ("failed", "stopped", "error"):
            print("FAIL " + str(r.get("errorMsg") or r.get("msg") or "任务失败"))
            sys.exit(2)
        if el > a.timeout:
            print(f"TIMEOUT 已等 {el}s，任务仍在执行，可稍后用同一 taskId 再查")
            sys.exit(3)
        time.sleep(interval)


def fetch_all_cases(task_id):
    """超 2000 条时分页累积"""
    page, size, all_cases = 1, 200, []
    while True:
        r = request("GET", f"/openapi/test-generation/tasks/{task_id}/cases?page={page}&pageSize={size}")
        batch = r.get("cases") or r.get("data") or []
        if isinstance(batch, dict):
            batch = batch.get("cases") or []
        if not batch:
            break
        all_cases.extend(batch)
        total = r.get("total") or r.get("caseCount")
        print(f"[cases] page {page} +{len(batch)}（累计 {len(all_cases)}{'/' + str(total) if total else ''}）")
        if total and len(all_cases) >= int(total):
            break
        if len(batch) < size:
            break
        page += 1
    return all_cases


def clean_step(s):
    """接口返回的 testSteps 常自带 "1." 前缀，去掉避免渲染成 "1. 1. xxx\""""
    import re
    return re.sub(r"^\s*\d+\s*[\.、\)．]\s*", "", str(s).strip())


def cases_to_rows(cases):
    rows = []
    for c in cases:
        steps = c.get("testSteps") or []
        if isinstance(steps, list):
            steps = "\n".join(f"{i}. {clean_step(s)}" for i, s in enumerate(steps, 1))
        rows.append([
            c.get("caseId", ""), c.get("moduleName", ""), c.get("name", ""),
            c.get("precondition", ""), steps, c.get("expectedResult", ""),
            c.get("priority", ""), c.get("testContent", ""),
        ])
    return rows


HEADER = ["用例编号", "所属模块", "用例名称", "前置条件", "测试步骤", "预期结果", "优先级", "测试内容"]


def write_csv(rows, path):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)
    print(f"[csv] {path}  {len(rows)} 条")


def render_md(payload, flat_cases=None, task_name=""):
    lines = [f"# {task_name or payload.get('name') or '测试用例结果'}", ""]
    if payload.get("caseCount") is not None:
        lines.append(f"- 用例总数：{payload.get('caseCount')}")
    if payload.get("truncated"):
        lines.append("- 注意：结果被截断（>2000 条），完整数据请用 cases/export 接口")
    lines.append("")
    if flat_cases is not None:
        groups = {}
        for c in flat_cases:
            groups.setdefault(c.get("moduleName") or "-", []).append(c)
        sections = [{"modulePath": [k], "cases": v} for k, v in groups.items()]
    else:
        sections = payload.get("modules") or []
    idx = 0
    for m in sections:
        mp = m.get("modulePath") or []
        title = " / ".join(mp) if isinstance(mp, list) else str(mp)
        lines.append(f"## {title}（{m.get('caseCount', len(m.get('cases') or []))} 条）")
        if m.get("description"):
            lines.append("")
            lines.append(f"> {str(m['description'])[:300]}")
        for c in m.get("cases") or []:
            idx += 1
            lines.append("")
            lines.append(f"### {c.get('caseId') or idx} {c.get('name', '')}")
            if c.get("priority"):
                lines.append(f"- 优先级：{c['priority']}")
            if c.get("precondition"):
                lines.append(f"- 前置条件：{c['precondition']}")
            steps = c.get("testSteps") or []
            if steps:
                lines.append("- 测试步骤：")
                if isinstance(steps, str):
                    lines.append(f"  1. {clean_step(steps)}")
                else:
                    for i, s in enumerate(steps, 1):
                        lines.append(f"  {i}. {clean_step(s)}")
            if c.get("expectedResult"):
                lines.append(f"- 预期结果：{c['expectedResult']}")
        lines.append("")
    return "\n".join(lines)


def cmd_result(a):
    r = request("GET", f"/openapi/test-generation/tasks/{a.task_id}/result")
    flat = None
    if r.get("truncated"):
        print("[warn] truncated=true，改走分页接口取全量")
        flat = fetch_all_cases(a.task_id)
    payload = r
    mods = r.get("modules") or []
    total = r.get("caseCount") or sum(len(m.get("cases") or []) for m in mods)
    print(f"[result] completed={r.get('completed')} caseCount={total} modules={len(mods)} truncated={r.get('truncated')}")
    if a.out:
        Path(a.out).write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[json] {a.out}")
    all_cases = flat if flat is not None else [c for m in mods for c in (m.get("cases") or [])]
    if a.cases_csv:
        write_csv(cases_to_rows(all_cases), a.cases_csv)
    if a.md:
        Path(a.md).write_text(render_md(payload, flat, a.task_name or ""), encoding="utf-8")
        print(f"[md] {a.md}")
    return r


def cmd_cases(a):
    r = request("GET", f"/openapi/test-generation/tasks/{a.task_id}/cases?page={a.page}&pageSize={a.pageSize}")
    print(json.dumps(r, ensure_ascii=False, indent=2)[:8000])


def cmd_export(a):
    try:
        r = request("GET", f"/openapi/test-generation/tasks/{a.task_id}/export")
    except SystemExit as e:
        if "409" in str(e):
            sys.exit("任务未完成（HTTP 409），请先用 status --watch 轮询")
        raise
    fn = r.get("fileName") or f"{a.task_id}.xlsx"
    url = r.get("downloadUrl")
    print(f"[export] {fn}  {r.get('size')} B  用例 {r.get('caseCount')} 条  truncated={r.get('truncated')}")
    if not url:
        sys.exit("返回里没有 downloadUrl")
    dest_dir = Path(a.dest or ".")
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / fn
    data = request("GET", url, raw=True) if url.startswith("/") else _download(url)
    out.write_bytes(data)
    print(f"[saved] {out.resolve()}  {len(data)} B")
    return out


def _download(url):
    import urllib.request
    with urllib.request.urlopen(url, timeout=300) as resp:
        return resp.read()


def cmd_run(a):
    tid = a.task_id
    if not tid:
        tid = cmd_create(a)
    print(f"--- 轮询任务 {tid}（间隔 {a.interval}s，最长 {a.timeout}s）")
    a.task_id = tid
    cmd_status(a)
    print("--- 取结果")
    cmd_result(a)
    if a.export:
        print("--- 下载 Excel")
        cmd_export(a)


def main():
    p = argparse.ArgumentParser(description="测试用例生成 OpenAPI 客户端")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("ping", help="验证 token")
    sp.set_defaults(func=cmd_ping)

    common_create = argparse.ArgumentParser(add_help=False)
    common_create.add_argument("--doc", help="需求文档路径（txt/md）")
    common_create.add_argument("--content", help="直接给需求文本")
    common_create.add_argument("--name", required=False, default=None, help="需求名称")
    common_create.add_argument("--modules", help="模块拆分 JSON 文件")
    common_create.add_argument("--test-object", dest="test_object", help="测试对象，如 QDM562")
    common_create.add_argument("--background", help="测试背景")
    common_create.add_argument("--file-url", dest="file_url", help="需求文件链接（与 content 二选一）")
    common_create.add_argument("--save", help="把 taskId 存到该 json 路径")

    sp = sub.add_parser("create", parents=[common_create], help="创建任务")
    sp.set_defaults(func=cmd_create)

    sp = sub.add_parser("status", help="查状态")
    sp.add_argument("task_id")
    sp.add_argument("--watch", action="store_true", help="轮询到完成")
    sp.add_argument("--interval", type=int, default=20)
    sp.add_argument("--timeout", type=int, default=2400)
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("result", help="取用例结果")
    sp.add_argument("task_id")
    sp.add_argument("--out", help="原始 JSON 落盘")
    sp.add_argument("--md", help="渲染成 markdown")
    sp.add_argument("--cases-csv", dest="cases_csv", help="导出 CSV（Excel 可直接打开）")
    sp.add_argument("--task-name", dest="task_name", help="markdown 标题")
    sp.set_defaults(func=cmd_result)

    sp = sub.add_parser("cases", help="分页取用例（>2000 条）")
    sp.add_argument("task_id")
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--pageSize", type=int, default=200)
    sp.set_defaults(func=cmd_cases)

    sp = sub.add_parser("export", help="下载 Excel")
    sp.add_argument("task_id")
    sp.add_argument("--dest", help="保存目录，默认当前目录")
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("run", parents=[common_create], help="create+轮询+结果(+Excel)")
    sp.add_argument("--task-id", dest="task_id", help="复用已有 taskId，跳过创建")
    sp.add_argument("--interval", type=int, default=20)
    sp.add_argument("--timeout", type=int, default=2400)
    sp.add_argument("--export", action="store_true", help="顺带下载 Excel")
    sp.add_argument("--md")
    sp.add_argument("--out")
    sp.add_argument("--cases-csv", dest="cases_csv")
    sp.add_argument("--dest")
    sp.set_defaults(func=cmd_run, task_name=None)

    a = p.parse_args()
    if getattr(a, "func", None) in (cmd_create, cmd_run) and not a.name:
        a.name = Path(a.doc).stem if a.doc else "未命名需求"
    a.func(a)


if __name__ == "__main__":
    main()
