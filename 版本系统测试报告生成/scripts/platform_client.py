# -*- coding: utf-8 -*-
"""妙搭报告平台（app_4jxgwzvqczpd2）服务端调用客户端。

覆盖 8 个 OpenAPI：
  1. POST /openapi/report-export/summary-report      摘要报告 -> downloadUrl
  2. POST /openapi/report-export/test-plan           测试计划 -> downloadUrl
  3. POST /openapi/report-export/function-report     常规功能 -> downloadUrl
  4. POST /openapi/report-export/pressure-report     常规压力 -> downloadUrl
  5. POST /openapi/road-test-report/generate         路测报告(base64图) -> downloadUrl
  6. GET  /openapi/road-test-report/{id}/download-url 路测报告重取链接
  7. POST /openapi/reports/generate                  JIRA 报告（异步）-> reportId
  8. GET  /openapi/reports/{id}/status               JIRA 报告轮询 -> downloadUrl

只在服务端跑（CLI / 后端 / 脚本），不要放进浏览器：接口不放 CORS，且 Key 会随前端产物泄露。

API Key 解析顺序：api_key 参数 > 环境变量 REPORT_PLATFORM_API_KEY > ~/.report_platform_key
                 > ~/.roadtest_key（本机路测 skill 已用的那份，同一个 App 的凭证）。
**不要把 Key 硬编码进源码**，也不要提交进 git。

环境：
  prod = https://scnrhostplnc.feishu.link  默认。2026-10-21 平台发布后 8 个路由全部在线；
           实测偶发 500 "fetch failed"（服务端调文件服务超时），重试一次就过，_send 已兜住
  dev  = https://scnrhostplnc-app_4jxgwzvqczpd2-1862314647902395.aiforce.run
           联调用；证书 hostname 不匹配 -> 自动 verify=False，凭证还需开「可访问开发环境」

用法：
    from client import ReportPlatformClient
    c = ReportPlatformClient()                       # 默认 env="prod"
    print(c.summary_report({...}))
    print(c.test_plan(version="V01", plan_items=[{...}]))
    rid = c.jira_generate("me@x.com", "token", "https://jira/.../issues/?jql=project%3DQDM565", "…_V01")
    done = c.jira_wait(rid, timeout=600)            # success 时带 downloadUrl
    c.download(done["downloadUrl"], out="JIRA.xlsx")

CLI：
    python client.py summary --data summary.json [--env dev]
    python client.py test-plan --data plan.json
    python client.py function --data function.json
    python client.py pressure --data pressure.json
    python client.py road-test --dir <三件套目录> --version V01 --result PASS
    python client.py jira --account u --password p --jira-url "https://..." --version V01 [--wait]
    python client.py status <reportId>
    python client.py download-url <reportId>
    python client.py download <url> --out x.xlsx
所有子命令支持 --env prod|dev（默认 dev，因为生产还没发布 report-export/reports 路由）、
--insecure（默认 dev 自动关校验）、--timeout。
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional

import requests

APP_ID = "app_4jxgwzvqczpd2"
ENVS = {
    "prod": "https://scnrhostplnc.feishu.link",
    "dev": "https://scnrhostplnc-app_4jxgwzvqczpd2-1862314647902395.aiforce.run",
}
# 2026-10-21 平台发布后：8 个路由在 prod 全部在线（prod 偶发 500 "fetch failed"，由 _send 重试兜住）。
# 真遇到未发布，接口会回 404 "Cannot POST/GET ..."，ApiError 原文带出来，不再做本地预判。
PAYLOAD_LIMIT = 12 * 1024 * 1024      # 网关硬上限：请求体 ≤12MB（超了回 200 + code）
PAYLOAD_TARGET = 6 * 1024 * 1024      # 实测 >6MB 服务端传桶易超时，路测图按这个预算降档
B64_LIMIT = 15_000_000                # 单张图 base64 字符上限
MAX_SCENES = 50                       # scenes 数组元素上限（实测校验文案）
MAX_IMG_PER_SCENE = 20
RESULT_ENUM = {"PASS", "FAIL", "PASS WITH COMMAND", "PASS WITH COMMANDS"}
# 内部报告的「测试结果」口径和平台 H 列不一样（报告写 Pass with comments），先归一化
RESULT_ALIAS = {
    "PASS WITH COMMENTS": "PASS WITH COMMAND",
    "PASS WITH COMMENT": "PASS WITH COMMAND",
    "PASS": "PASS",
    "FAIL": "FAIL",
}


def normalize_result(value: str) -> str:
    """报告口径 -> 平台口径；认不出来的返回 ""（不写 H 列），调用方自己决定要不要提示。"""
    key = (value or "").strip().upper()
    if key in RESULT_ENUM:
        return "PASS WITH COMMAND" if key == "PASS WITH COMMANDS" else key
    return RESULT_ALIAS.get(key, "")


class ApiError(RuntimeError):
    """接口非 2xx，或 2xx 但 body 里有业务 code。原文一律带出来，方便转告用户。"""

    def __init__(self, status: int, text: str, url: str = ""):
        self.status, self.text, self.url = status, text, url
        msg = text[:800]
        try:
            j = json.loads(text)
            err = j.get("error")
            if isinstance(err, dict):
                msg = "%s | %s" % (err.get("message"), str(err.get("details"))[:400])
            elif j.get("code"):
                msg = "业务失败 code=%s | %s" % (j["code"], j.get("message") or text[:400])
            elif j.get("message"):
                msg = str(j["message"])[:600]
        except (ValueError, AttributeError):
            pass
        super().__init__("HTTP %s %s -> %s" % (status, url, msg))


def resolve_api_key(cli: str = "") -> str:
    if cli:
        return cli.strip()
    for name in ("REPORT_PLATFORM_API_KEY", "ROAD_TEST_API_KEY"):
        if os.environ.get(name):
            return os.environ[name].strip()
    for fn in (".report_platform_key", ".roadtest_key"):     # inline 路径，别先存变量
        try:
            return open(os.path.join(os.path.expanduser("~"), fn), encoding="utf-8").read().strip()
        except OSError:
            continue
    return ""


class ReportPlatformClient:
    def __init__(self, env: str = "prod", api_key: str = "", app_id: str = APP_ID,
                 verify: Optional[bool] = None, timeout: float = 120.0, retries: int = 3):
        if env not in ENVS:
            raise ValueError("env 只能是 prod / dev")
        self.base, self.app_id, self.timeout, self.retries = ENVS[env], app_id, timeout, retries
        self.env = env
        key = resolve_api_key(api_key)
        if not key:
            raise ApiError(0, "缺 API Key：传 api_key / 设环境变量 REPORT_PLATFORM_API_KEY "
                              "/ 写 ~/.report_platform_key", "")
        self.hdr = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
        # dev 域名证书 hostname 不匹配；prod 正常校验
        self.verify = (env == "prod") if verify is None else verify
        if not self.verify:
            try:
                import urllib3
                urllib3.disable_warnings()
            except ImportError:
                pass

    # ---------- 底层 ----------
    def _url(self, path: str, **kw: str) -> str:
        return self.base + "/app/" + self.app_id + path.format(app_id=self.app_id, **kw)

    def _send(self, method: str, path: str, body: Any = None, raw_body: bytes = None,
              wall: Optional[float] = None) -> Dict[str, Any]:
        url = self._url(path)
        data = raw_body if raw_body is not None else (
            json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None)
        if data is not None and len(data) > PAYLOAD_LIMIT:
            raise ApiError(0, "请求体 %.1f MB 超网关硬上限 12MB，请减少图片/条目"
                           % (len(data) / 1048576), url)
        last: Optional[BaseException] = None
        for attempt in range(self.retries):
            try:
                r = self._post_hard(method, url, data, wall)
            except Exception as e:                                  # 网络/超时
                last = e
                print("  第%d次网络异常 %s: %s" % (attempt + 1, type(e).__name__, str(e)[:150]),
                      file=sys.stderr, flush=True)
                time.sleep(5 * (attempt + 1))
                continue
            if r is None:
                last = ApiError(0, "wall %ss 超时（发送或读取阻塞）" % wall, url)
                print("  第%d次%s" % (attempt + 1, last), file=sys.stderr, flush=True)
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code in (200, 201):
                try:
                    j = r.json()
                except ValueError:
                    raise ApiError(r.status_code, "响应不是 JSON：" + r.text[:400], url)
                if isinstance(j, dict) and j.get("code") and str(j["code"]) not in ("0", "200"):
                    raise ApiError(r.status_code, r.text, url)       # 网关 200 + 业务 code
                return j
            if r.status_code in (400, 401, 403, 404, 422):            # 参数/鉴权/路由错，重试无意义
                raise ApiError(r.status_code, r.text, url)
            print("  第%d次 %s %s" % (attempt + 1, r.status_code, r.text[:200]),
                  file=sys.stderr, flush=True)
            last = ApiError(r.status_code, r.text, url)
            time.sleep(5 * (attempt + 1))
        raise last if last else ApiError(0, "未知失败", url)

    def _post_hard(self, method: str, url: str, data: Optional[bytes],
                   wall: Optional[float]) -> Optional[requests.Response]:
        """requests 的 timeout 管不到"发送大请求体"阶段，body 卡住会永不超时 -> 子线程强杀。"""
        box: Dict[str, Any] = {}

        def work():
            try:
                box["r"] = requests.request(method, url, headers=self.hdr, data=data,
                                            timeout=(20, self.timeout), verify=self.verify)
            except Exception as e:
                box["e"] = e

        t = threading.Thread(target=work, daemon=True)
        t.start()
        t.join(wall if wall is not None else self.timeout + 30)
        if t.is_alive():
            return None
        if "e" in box:
            raise box["e"]
        return box["r"]

    # ---------- 1~4 报告导出（同步，直接回 downloadUrl）----------
    def summary_report(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._send("POST", "/openapi/report-export/summary-report", payload)

    def test_plan(self, plan_items: List[Dict[str, Any]], version: str = "") -> Dict[str, Any]:
        p: Dict[str, Any] = {"planItems": plan_items}
        if version:
            p["version"] = version
        return self._send("POST", "/openapi/report-export/test-plan", p)

    def function_report(self, report_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self._send("POST", "/openapi/report-export/function-report",
                          {"reportItems": report_items})

    def pressure_report(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self._send("POST", "/openapi/report-export/pressure-report", {"items": items})

    # ---------- 5~6 路测 ----------
    def road_test_report(self, version: str, scenes: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self._send("POST", "/openapi/road-test-report/generate",
                          {"version": version, "scenes": scenes}, wall=300)

    ROAD_LADDER = [(1200, 80), (1000, 78), (800, 75), (640, 72)]

    def road_test_from_dir(self, root: str, version: str, result: str = "", remark: str = "",
                           max_images: int = 4, include_overall: bool = True,
                           max_edge: int = 0, quality: int = 0) -> Dict[str, Any]:
        """三件套目录（<场景>/区域整体.jpg、整体.jpg、NN_HHMMSS.jpg）-> 路测报告 Excel。

        自动降档：请求体预算 ≤6MB（实测 >6MB 服务端传桶易超时/500），网关硬上限 12MB；
        还失败就继续降画质、减每场景图数，最多 6 次尝试。"""
        res = normalize_result(result)
        if (result or "").strip() and not res:
            raise ApiError(0, "测试结果 %r 平台 H 列不接受（只能 PASS / FAIL / PASS WITH COMMAND，"
                              "其余细节写 remark）" % result, "")
        plan = self._scene_files(root, include_overall)
        if not plan:
            raise ApiError(0, "目录里没找到截图：%s" % root, "")
        ladder = [(max_edge, quality or 85)] if max_edge else list(self.ROAD_LADDER)
        caps = sorted({max_images or 4, 2, 1}, reverse=True)
        err: Optional[ApiError] = None
        for attempt in range(len(ladder) + len(caps)):
            edge, q = ladder[min(attempt, len(ladder) - 1)]
            cap = max_images if attempt < len(ladder) else caps[min(
                attempt - len(ladder), len(caps) - 1)]
            scenes = self._encode_scenes(plan, cap, edge, q, res, remark)
            size = len(json.dumps({"version": version, "scenes": scenes}).encode("utf-8"))
            print("  [road] 第%d档 长边%d 质量%d 每场景≤%d张 -> 请求体 %.1f MB"
                  % (attempt + 1, edge, q, cap, size / 1048576), flush=True)
            if size > PAYLOAD_LIMIT and (edge, q) != ladder[-1]:
                continue
            try:
                return self.road_test_report(version[:100], scenes)
            except ApiError as e:
                err = e
                if e.status in (400, 401, 403, 404, 422):
                    raise
        raise err if err else ApiError(0, "路测接口始终失败", "")

    @staticmethod
    def _scene_files(root: str, include_overall: bool) -> List[Any]:
        out = []
        for d in sorted(x for x in os.listdir(root) if os.path.isdir(os.path.join(root, x))):
            if d == "整体" and not include_overall:
                continue
            p = os.path.join(root, d)
            files = [os.path.join(p, w) for w in ("区域整体.jpg", "整体.jpg")
                     if os.path.exists(os.path.join(p, w))]
            files += [os.path.join(p, f) for f in sorted(os.listdir(p))
                      if f.lower().endswith((".jpg", ".jpeg", ".png"))]
            if files:
                out.append((d, files))
        return out

    def _encode_scenes(self, plan: List[Any], cap: int, edge: int, q: int,
                       res: str, remark: str) -> List[Dict[str, Any]]:
        scenes: List[Dict[str, Any]] = []
        for d, files in plan[:MAX_SCENES]:
            imgs = []
            for f in files[:max(cap, 1)]:
                b = self._img_b64(f, edge, q)
                if len(b) > B64_LIMIT:
                    print("  !! 跳过超尺寸图 %s" % f, file=sys.stderr, flush=True)
                    continue
                imgs.append({"base64": b,
                             "fileName": "%s %s" % (d, os.path.splitext(os.path.basename(f))[0])[:255]})
            if not imgs:
                continue
            s: Dict[str, Any] = {"name": d[:255], "images": imgs}
            if res:
                s["result"] = res[:1000]
            if remark:
                s["remark"] = remark[:1000]
            scenes.append(s)
        return scenes

    @staticmethod
    def _img_b64(path: str, max_edge: int = 1600, quality: int = 85) -> str:
        from PIL import Image
        with Image.open(path) as im:
            w, h = im.size
            if max_edge and max(w, h) > max_edge:
                s = max_edge / max(w, h)
                im = im.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)
            buf = io.BytesIO()
            im.convert("RGB").save(buf, "JPEG", quality=quality)
        return base64.b64encode(buf.getvalue()).decode()

    def road_test_download_url(self, report_id: str) -> Dict[str, Any]:
        return self._send("GET", "/openapi/road-test-report/{reportId}/download-url"
                          .replace("{reportId}", report_id))

    # ---------- 7~8 JIRA（异步）----------
    def jira_generate(self, account: str, password: str, jira_url: str,
                      version: str) -> Dict[str, Any]:
        return self._send("POST", "/openapi/reports/generate",
                          {"account": account, "password": password,
                           "jiraUrl": jira_url, "version": version})

    def jira_status(self, report_id: str) -> Dict[str, Any]:
        return self._send("GET", "/openapi/reports/{reportId}/status".replace("{reportId}", report_id))

    def jira_wait(self, report_id: str, timeout: float = 600.0, interval: float = 10.0,
                  verbose: bool = True) -> Dict[str, Any]:
        """轮询到 success/failed。failed 时抛 ApiError（含 errorMsg 原文）。"""
        deadline = time.time() + timeout
        while True:
            j = self.jira_status(report_id)
            st = j.get("status")
            if verbose:
                print("  [%s] status=%s" % (time.strftime("%H:%M:%S"), st), flush=True)
            if st == "success":
                return j
            if st == "failed":
                raise ApiError(0, j.get("errorMsg") or json.dumps(j, ensure_ascii=False), self._url("x"))
            if time.time() > deadline:
                raise ApiError(0, "轮询超时（%.0fs），最后状态 %s，reportId=%s 可稍后再查"
                               % (timeout, st, report_id), "")
            time.sleep(interval)

    # ---------- 下载 ----------
    def download(self, url: str, out: str = "") -> str:
        """签名链接 7 天有效，拿到就下载。out 不给就用响应/URL 里的文件名。"""
        r = requests.get(url, timeout=(20, max(self.timeout, 300)), verify=self.verify)
        if r.status_code != 200 or len(r.content) < 2000:
            raise ApiError(r.status_code, "下载失败 %d bytes：%s" % (len(r.content), r.text[:200]), url)
        out = out or os.path.basename(url.split("?")[0]) or "report_%s.xlsx" % time.strftime("%Y%m%d%H%M%S")
        d = os.path.dirname(os.path.abspath(out))
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)          # --out 指到不存在的目录就先建
        try:
            open(out, "wb").write(r.content)
        except (PermissionError, OSError):                 # 文件正被 Excel 打开
            alt = "%s_%s.xlsx" % (os.path.splitext(out)[0], time.strftime("%H%M%S"))
            open(alt, "wb").write(r.content)
            out = alt
        return os.path.abspath(out)

    @staticmethod
    def unwrap(j: Dict[str, Any]) -> Dict[str, Any]:
        """统一取 downloadUrl / fileName，不同接口字段名一致，这里只兜一层。"""
        return {"downloadUrl": j.get("downloadUrl", ""), "fileName": j.get("fileName", ""),
                "reportId": j.get("reportId", ""), "status": j.get("status", "")}


# ---------------- 载荷辅助（对齐内部报告/摘要的字段口径） ----------------
def plan_item(seq_no: int, version: str, test_date: str, function_item: str, case_count: int,
              manpower: float, status: str, plan_end_date: str,
              actual_end_date: Optional[str] = None, remark: str = "",
              id_: str = "") -> Dict[str, Any]:
    """测试计划一行（/test-plan 的 planItems；/summary-report 的 testPlanData 同结构）。"""
    return {"id": id_ or ("t_%03d" % seq_no), "seqNo": seq_no, "version": version,
            "testDate": test_date, "functionItem": function_item, "caseCount": case_count,
            "manpower": manpower, "status": status, "planEndDate": plan_end_date,
            "actualEndDate": actual_end_date, "remark": remark}


def state(name: str, main_checked: bool = False, main_result: str = "",
          v_checked: bool = False, v_result: str = "") -> Dict[str, Any]:
    """basicFunctionStates / functionItems 的一项：主版本 + V 版本勾选与结果。"""
    return {"name": name,
            "mainVersion": {"checked": main_checked, "result": main_result},
            "vVersion": {"checked": v_checked, "result": v_result}}


def summary_payload(**kw: Any) -> Dict[str, Any]:
    """摘要报告必填字段脚手架，缺哪个就报错，避免发出去被服务端默默出个空表
    （实测 dev 环境传 {} 也会 201 出表，所以必填校验要在本地做）。"""
    required = ["confidentialityLevel", "documentType", "reviewer", "approver", "implementationTime",
                "testPlatform", "versionNumber", "projectIndustry", "mainVersionNumber",
                "testType", "testLevel", "testContent", "tester", "testDate", "reportPath",
                "submissionPath", "baselinesVersion", "baselinesProjectPath", "forWindows",
                "forLinux", "testSummary"]
    p = dict(kw)
    p.setdefault("testContent", {"functionTest": True, "modificationPoint": False,
                                 "routinePressure": True, "bugVerification": False,
                                 "citTest": False})
    p.setdefault("forWindows", "")
    p.setdefault("forLinux", "")
    missing = [k for k in required
               if k not in p or p[k] is None
               or (isinstance(p[k], (dict, list)) and not p[k])]
    if missing:
        raise ApiError(0, "摘要报告缺必填字段：%s" % "、".join(missing), "")
    return p


# ---------------- CLI ----------------
def _load_data(args: argparse.Namespace) -> Any:
    if getattr(args, "data", ""):
        return json.load(open(args.data, encoding="utf-8"))
    txt = sys.stdin.read()
    if not txt.strip():
        raise SystemExit("没给数据：--data <file.json> 或从 stdin 传 JSON")
    return json.loads(txt)


def main() -> int:
    ap = argparse.ArgumentParser(description="妙搭报告平台 OpenAPI 客户端（服务端用）")
    ap.add_argument("--env", default="prod", choices=["prod", "dev"],
                    help="默认 prod（2026-10-21 发布后 8 个路由都在）；dev 为联调域名，会自动关证书校验")
    ap.add_argument("--api-key", default="", help="不给就找环境变量 / ~/.report_platform_key / ~/.roadtest_key")
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--verify", action="store_true", help="强制校验 TLS 证书（dev 域名证书 hostname 不匹配）")
    ap.add_argument("--out", default="", help="下载落盘路径")
    ap.add_argument("--quiet", action="store_true", help="只打最终 JSON，别打过程")
    sp = ap.add_subparsers(dest="cmd", required=True)

    for name, help_ in [("summary", "摘要报告 Excel（body=整个请求体 JSON）"),
                        ("test-plan", "测试计划 Excel（body={version?,planItems:[...]}）"),
                        ("function", "常规功能 Excel（body={reportItems:[...]}）"),
                        ("pressure", "常规压力 Excel（body={items:[...]}）")]:
        s = sp.add_parser(name, help=help_)
        s.add_argument("--data", default="", help="请求体 JSON 文件；不给就读 stdin")

    s = sp.add_parser("road-test", help="路测报告 Excel（从三件套目录出图）")
    s.add_argument("--dir", required=True)
    s.add_argument("--version", required=True)
    s.add_argument("--result", default="")
    s.add_argument("--remark", default="")
    s.add_argument("--max-images", type=int, default=6)
    s.add_argument("--no-overall", action="store_true")

    s = sp.add_parser("jira", help="JIRA 报告（异步）")
    s.add_argument("--account", required=True)
    s.add_argument("--password", required=True)
    s.add_argument("--jira-url", required=True, help="含 JQL 的过滤器链接")
    s.add_argument("--version", required=True)
    s.add_argument("--wait", action="store_true", help="提交后直接轮询到 success 并下载")
    s.add_argument("--poll-timeout", type=float, default=600.0)

    s = sp.add_parser("status", help="查 JIRA 报告状态")
    s.add_argument("report_id")
    s = sp.add_parser("download-url", help="重取路测报告链接")
    s.add_argument("report_id")
    s = sp.add_parser("download", help="下载签名链接")
    s.add_argument("url")

    args = ap.parse_args()
    c = ReportPlatformClient(env=args.env, api_key=args.api_key, timeout=args.timeout,
                             verify=True if args.verify else None)
    if args.cmd == "summary":
        j = c.summary_report(_load_data(args))
    elif args.cmd == "test-plan":
        d = _load_data(args)
        j = c.test_plan(d["planItems"], d.get("version", "")) if isinstance(d, dict) else c.test_plan(d)
    elif args.cmd == "function":
        d = _load_data(args)
        j = c.function_report(d["reportItems"] if isinstance(d, dict) else d)
    elif args.cmd == "pressure":
        d = _load_data(args)
        j = c.pressure_report(d["items"] if isinstance(d, dict) else d)
    elif args.cmd == "road-test":
        j = c.road_test_from_dir(args.dir, args.version, args.result, args.remark,
                                 args.max_images, not args.no_overall)
    elif args.cmd == "jira":
        j = c.jira_generate(args.account, args.password, args.jira_url, args.version)
        if args.wait:
            j = c.jira_wait(j["reportId"], args.poll_timeout, verbose=not args.quiet)
    elif args.cmd == "status":
        j = c.jira_status(args.report_id)
    elif args.cmd == "download-url":
        j = c.road_test_download_url(args.report_id)
    else:
        out = c.download(args.url, args.out)
        print(json.dumps({"saved": out}, ensure_ascii=False))
        return 0

    u = ReportPlatformClient.unwrap(j)
    if not args.quiet:
        print(json.dumps(j, ensure_ascii=False)[:600])
    if u["downloadUrl"]:
        out = c.download(u["downloadUrl"], args.out) if args.out or u["status"] != "generating" else ""
        print("downloadUrl=%s" % u["downloadUrl"])
        if out:
            print("SAVED=%s" % out)
    elif u["reportId"]:
        print("reportId=%s status=%s" % (u["reportId"], u["status"]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ApiError as e:
        print("接口失败：%s" % e, file=sys.stderr)
        sys.exit(1)
