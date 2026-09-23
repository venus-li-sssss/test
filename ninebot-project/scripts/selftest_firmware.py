# -*- coding: utf-8 -*-
"""ninebot_ota.py 固件包管理 离线自测（不连内网、不产生任何平台写入）。

以 2026-09-17 的真实 HAR（新增固件包 + 查询固件包）为基准，用 mock session
校验脚本发出的每一个请求与 HAR 里的成功请求**结构一致**：
  * upload/init        body 字段 = {md5,name,size,totalBlock,clientKey}
  * upload/part (GET)  query 字段 = {bucketName,objectKey,uploadId,fileId,chunkNumber,totalChunks,size,md5}
  * upload/part (POST) multipart 字段 = {...,file}，其中 size 恒为 5242880、chunkNumber=1、totalChunks=1
  * s3-upload-by-path  body 字段 = HAR 完全一致（12 个字段）
  * add-firmware-new   body 字段 = HAR 完全一致（22 个字段）
  * 秒传(pass=true) 时不得再发二进制 POST
  * --dry-run 不得发出任何写请求
  * 版本从文件名推断、数组型查询参数、CJK 表格对齐 等纯本地逻辑

用法：
  python scripts/selftest_firmware.py                       # 用内置期望值
  python scripts/selftest_firmware.py --har <HAR文件>        # 直接以真实 HAR 为准
"""
import argparse
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ninebot_ota as N  # noqa: E402

# ---- HAR 实测基准（2026-09-17，成功新增 0242 的那次抓包） ----
HAR_INIT_KEYS = ["md5", "name", "size", "totalBlock", "clientKey"]
HAR_PART_GET_KEYS = ["bucketName", "objectKey", "uploadId", "fileId", "chunkNumber",
                     "totalChunks", "size", "md5"]
HAR_PART_POST_KEYS = ["bucketName", "objectKey", "uploadId", "fileId", "chunkNumber",
                      "totalChunks", "size", "md5", "file"]
HAR_S3_KEYS = ["fileId", "uploadId", "bucketName", "objectKey", "url", "name", "size",
               "md5", "pass", "partNumbers", "file_use_type", "productVehicleModelStringList"]
HAR_ADD_KEYS = ["productVehicleModelStringList", "part_code", "firmware_type",
                "firmware_version", "firmware_level", "file_id", "md5_verify_code",
                "descDraft", "big_file_url", "status", "description", "description_en",
                "relate_version", "operate_user", "encrypt_1", "is_milestone", "open_diff",
                "firmware_diff_data", "ui_extends", "skinName", "file_use_type",
                "estimate_time"]
# edit-firmware-new（替换固件包）实测 20 个字段（2026-09-23 HAR）
HAR_EDIT_KEYS = ["id", "firmware_version", "file_id", "md5_verify_code", "status", "descDraft",
                 "estimate_time", "description", "description_en", "relate_version",
                 "operate_user", "encrypt_1", "is_milestone", "open_diff",
                 "productVehicleModelStringList", "part_code", "firmware_diff_data",
                 "ui_extends", "osDescription", "osDescription_en"]
# firmware-info 响应样例（2026-09-23 HAR id=38706 / 0760），无 HAR 时作 fallback
INFO_SAMPLE = {
    "id": "38706", "firmware_id": "39173", "file_id": "121736",
    "md5_verify_code": "be18f33619141fcaae5292abaed6ef4a", "status": "1",
    "description_en": "安科联测试", "description": "安科联测试(0751--->0760)",
    "descDraft": "安科联测试(0751--->0760)", "encrypt_1": 2, "is_milestone": 0,
    "firmware_level": 1, "part_code": ["Z08A", "Z0DB", "XV"], "open_diff": 1,
    "ui_extends": [], "firmware_type": "ECU", "firmware_version": "0760",
    "file_name": "V0.7.6.0.bin", "unreal_file_url": "V0.7.6.0.bin",
    "estimate_time": 60, "osDescription": None, "osDescription_en": None,
    "productVehicleModelStringList": [["9YB5Vyi8", "K09603"], ["cLlkhxD9", "K05903"],
                                      ["cLlkhxD9", "K05905"], ["cLlkhxD9", "K05907"],
                                      ["cLlkhxD9", "K05908"], ["cLlkhxD9", "K05910"],
                                      ["cLlkhxD9", "K05912"], ["KkbeAhMy", "K02441"],
                                      ["KkbeAhMy", "K02442"], ["KkbeAhMy", "K02445"],
                                      ["KkbeAhMy", "K02446"]],
}
CHUNK = 5242880

_PASS = 0
_FAIL = 0


def check(title, ok, detail=""):
    global _PASS, _FAIL
    if ok:
        _PASS += 1
        print(f"  [PASS] {title}")
    else:
        _FAIL += 1
        print(f"  [FAIL] {title}  {detail}")


def load_har(path):
    """从真实 HAR 里抽出 4 个关键请求作为期望值。"""
    d = json.load(io.open(path, encoding="utf-8"))
    es = d["log"]["entries"]
    exp = {}
    for e in es:
        r = e["request"]
        u = r["url"]
        if u.endswith("/upload/init"):
            exp["init"] = json.loads(r["postData"]["text"])
        elif "/upload/part" in u and r["method"] == "POST" and "file" not in exp:
            txt = r["postData"]["text"]
            plain, fpart = [], []
            for ln in txt.splitlines():
                if 'name="' not in ln:
                    continue
                nm = ln.split('name="')[1].split('"')[0]
                (fpart if "filename=" in ln else plain).append(nm)
            exp["part_post_fields"] = plain + fpart
        elif u.endswith("/s3-upload-by-path"):
            exp["s3"] = json.loads(r["postData"]["text"])
        elif u.endswith("/add-firmware-new"):
            exp["add"] = json.loads(r["postData"]["text"])
        elif u.endswith("/edit-firmware-new"):
            exp["edit"] = json.loads(r["postData"]["text"])
        elif u.endswith("/firmware-info"):
            try:
                exp["info"] = json.loads(e["response"]["content"]["text"])
            except Exception:
                pass
    return exp


class FakeResp:
    def __init__(self, payload):
        self._p = payload
        self.status_code = 200
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self):
        return self._p


class FakeSession:
    """记录所有请求并返回预设响应；不做任何网络访问。"""

    def __init__(self, calls, fastpass=False, kind="api"):
        self.calls = calls
        self.fastpass = fastpass
        self.kind = kind
        self.cookies = {}
        self.proxies = {}
        # 复刻真实会话的请求头：API 会话带 JSON content-type；上传会话不带
        self.headers = {"user-agent": "fake", "origin": "https://iot-test.ninebot.com",
                        "referer": "https://iot-test.ninebot.com/"}
        if kind == "api":
            self.headers["content-type"] = "application/json;charset=UTF-8"

    def post(self, url, **kw):
        return self._route("POST", url, kw)

    def get(self, url, **kw):
        return self._route("GET", url, kw)

    def _route(self, method, url, kw):
        self.calls.append({"method": method, "url": url, "session": self.kind,
                           "session_headers": dict(self.headers), **kw})
        if url.endswith("/upload/init"):
            return FakeResp({"resultCode": "1000", "resultDesc": "success", "data": {
                "fileId": 23648,
                "uploadId": None if self.fastpass else "ENqy5zIPiB8fakeUploadId",
                "bucketName": "file-upload-test",
                "objectKey": "bigfile/2026-09-17/caa721d84cfe4df187f5206d4537cf84/V0.2.4.2.bin",
                "pass": self.fastpass}})
        if url.endswith("/upload/complete"):
            return FakeResp({"resultCode": "1000", "resultDesc": "success",
                             "data": "文件已完成上传"})
        if "/upload/part" in url:
            if method == "GET":
                return FakeResp({"resultCode": "1000", "data": {"pass": True}})
            return FakeResp({"resultCode": "1000", "data": {"partNumber": 1, "etag": "x"}})
        if url.endswith("/s3-upload-by-path"):
            return FakeResp({"resultCode": "1000", "resultDesc": "成功", "data": {
                "size": 260328, "file_id": "121495", "original_name": "V0.2.4.2.bin",
                "url": "V0.2.4.2.bin", "md5": "a0ccabf43229b450ec6978bd1d73c6b7"}})
        return FakeResp({"resultCode": "1000", "resultDesc": "成功", "data": True})


def run_s3(monkeypatch_calls, file_path, fastpass=False, pvm=(("kBwCVBq4", "K21101"),)):
    calls = []
    fake = FakeSession(calls, fastpass=fastpass, kind="api")
    fake_up = FakeSession(calls, fastpass=fastpass, kind="upload")
    orig, orig_up = N._session, N._upload_session
    N._session = lambda: fake
    N._upload_session = lambda: fake_up
    try:
        up, md5 = N.s3_upload(file_path, [list(pvm[0])], "0242",
                              display_name="V0.2.4.2.bin", verbose=False)
    finally:
        N._session, N._upload_session = orig, orig_up
    return calls, up, md5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--har", default="")
    ap.add_argument("--file", default=r"D:\work\QDM559\version\QDM559_STM32G0B0_APP_01.001.01.001_V22\V0.2.4.2.bin")
    args = ap.parse_args()

    exp_s3, exp_add, exp_init = HAR_S3_KEYS, HAR_ADD_KEYS, HAR_INIT_KEYS
    exp_part_post = HAR_PART_POST_KEYS
    exp_edit, exp_info = HAR_EDIT_KEYS, dict(INFO_SAMPLE)
    if args.har and os.path.isfile(args.har):
        har = load_har(args.har)
        exp_s3 = list(har.get("s3", {}).keys()) or HAR_S3_KEYS
        exp_add = list(har.get("add", {}).keys()) or HAR_ADD_KEYS
        exp_init = list(har.get("init", {}).keys()) or HAR_INIT_KEYS
        exp_part_post = har.get("part_post_fields", exp_part_post)
        exp_edit = list(har.get("edit", {}).keys()) or HAR_EDIT_KEYS
        exp_info = (har.get("info") or {}).get("data") or dict(INFO_SAMPLE)
        print(f"[基准] 使用真实 HAR: {args.har}"
              f"（edit 字段 {len(exp_edit)} 个）")
    else:
        print("[基准] 使用内置期望字段（HAR 实测记录）")

    # 找一个真实固件文件；找不到就用临时文件（只影响 md5/size，不影响结构断言）
    fw = args.file
    tmp = None
    if not os.path.isfile(fw):
        import tempfile
        fd, tmp = tempfile.mkstemp(suffix=".bin")
        os.write(fd, b"\x00" * 260328)
        os.close(fd)
        fw = tmp
        print(f"[注意] 未找到 {args.file}，改用临时文件 {fw}")

    print("\n=== 1. 纯本地逻辑 ===")
    check("version_from_filename V0.2.4.2.bin -> 0242",
          N.version_from_filename("V0.2.4.2.bin") == "0242")
    check("version_from_filename ECU_IMG_V4.4.4.bin -> 0444",
          N.version_from_filename("ECU_IMG_V4.4.4.bin") == "0444")
    check("version_from_filename SteelDustApp_ota_V2.3.C.bin -> 023C",
          N.version_from_filename("SteelDustApp_ota_V2.3.C.bin") == "023C")
    check("normalize_version 0.2.4.2 -> (0242, V0.2.4.2)",
          N.normalize_version("0.2.4.2") == ("0242", "V0.2.4.2"))
    p = [t for t in N._fw_params(1, 100, "", "K21101,K02430", "ECU,HEP", "", "kBwCVBq4")
         if "[]" in t[0]]
    check("数组型查询参数 key[] 形式",
          p == [("product_key[]", "kBwCVBq4"), ("vehicle_model_code[]", "K21101"),
                ("vehicle_model_code[]", "K02430"), ("firmware_type[]", "ECU"),
                ("firmware_type[]", "HEP")], f"实际={p}")
    check("normalize_version 3 段自动补 0: 4.4.4 -> (0444, V0.4.4.4)",
          N.normalize_version("4.4.4") == ("0444", "V0.4.4.4"))
    check("normalize_version 容忍 V 前缀: V0.3.2.E -> (032E, V0.3.2.E)",
          N.normalize_version("V0.3.2.E") == ("032E", "V0.3.2.E"))
    check("_disp_width 中文按 2 列", N._disp_width("中文ab") == 6)
    check("FW_STATUS_NAMES 状态映射",
          N.FW_STATUS_NAMES["1"].startswith("测试") and N.FW_STATUS_NAMES["3"].startswith("工厂"))

    print("\n=== 2. 真实二进制上传（pass=false 全流程） ===")
    calls, up, md5 = run_s3(None, fw)
    urls = [c["url"] for c in calls]
    init_c = next((c for c in calls if c["url"].endswith("/upload/init")), None)
    get_c = next((c for c in calls if "/upload/part" in c["url"] and c["method"] == "GET"), None)
    post_c = next((c for c in calls if "/upload/part" in c["url"] and c["method"] == "POST"), None)
    comp_c = next((c for c in calls if c["url"].endswith("/upload/complete")), None)
    s3_c = next((c for c in calls if c["url"].endswith("/s3-upload-by-path")), None)
    check("请求顺序 init->part(GET)->part(POST)->complete->s3-upload-by-path",
          [i for i, u in enumerate(urls) if "upload" in u] ==
          sorted([i for i, u in enumerate(urls) if "upload" in u]) and
          urls[0].endswith("/upload/init") and urls[-1].endswith("/s3-upload-by-path"), urls)
    check("upload/init body 字段与 HAR 一致",
          sorted(init_c["json"]) == sorted(exp_init), f"实际={sorted(init_c['json'])}")
    check("upload/init totalBlock=1（<5MB 单分片）", init_c["json"]["totalBlock"] == 1)
    check("upload/part GET query 字段与 HAR 一致",
          sorted(get_c["params"]) == sorted(HAR_PART_GET_KEYS), f"实际={sorted(get_c['params'])}")
    check("upload/part POST multipart 字段与 HAR 一致",
          sorted(f[0] for f in post_c["files"]) == sorted(exp_part_post),
          f"实际={sorted(f[0] for f in post_c['files'])}")
    mp = {f[0]: f[1] for f in post_c["files"]}
    check("multipart size 恒为 5242880（与浏览器一致）", mp["size"][1] == str(CHUNK),
          f"实际={mp['size'][1]}")
    check("multipart chunkNumber/totalChunks = 1/1",
          mp["chunkNumber"][1] == "1" and mp["totalChunks"][1] == "1")
    check("multipart 带二进制 file 字段", mp["file"][0] == "V0.2.4.2.bin")
    check("上传分片走「上传专用会话」（不带 cookie / 不带 JSON content-type）",
          post_c.get("session") == "upload" and get_c.get("session") == "upload",
          f"post={post_c.get('session')} get={get_c.get('session')}")
    check("上传会话请求头里没有 content-type（否则 requests 不会补 multipart，服务端 500）",
          "content-type" not in post_c.get("session_headers", {}),
          post_c.get("session_headers"))
    check("API 会话确实带 JSON content-type（这就是必须分离两个会话的原因）",
          "content-type" in init_c.get("session_headers", {}))
    check("upload/complete body = {fileId}", comp_c["json"] == {"fileId": 23648})
    check("s3-upload-by-path body 字段与 HAR 一致",
          sorted(s3_c["json"]) == sorted(exp_s3), f"实际={sorted(s3_c['json'])}")
    check("s3-upload-by-path 返回 file_id=121495 被解析",
          up["data"]["file_id"] == "121495")
    if os.path.isfile(args.file) and os.path.basename(args.file) == "V0.2.4.2.bin":
        check("md5 与 HAR 一致（a0ccabf4...）",
              md5 == "a0ccabf43229b450ec6978bd1d73c6b7", md5)

    print("\n=== 3. 秒传（pass=true 跳过二进制） ===")
    calls2, _, _ = run_s3(None, fw, fastpass=True)
    check("秒传时不再发 POST /upload/part",
          not any("/upload/part" in c["url"] and c["method"] == "POST" for c in calls2),
          [c["url"] for c in calls2])
    check("秒传仍会 complete + s3-upload-by-path",
          any(c["url"].endswith("/upload/complete") for c in calls2)
          and any(c["url"].endswith("/s3-upload-by-path") for c in calls2))

    print("\n=== 4. add_firmware 提交 payload（mock 网络） ===")
    recorded = {}

    def fake_api_post(path, payload, request_code, timeout=30):
        recorded[path] = {"payload": payload, "code": request_code}
        if path.endswith("/add-firmware-new"):
            return FakeResp({"resultCode": "1000", "resultDesc": "成功", "data": None})
        if path.endswith("/firmware-relate-version-new"):
            return FakeResp({"resultCode": "1000", "data": {"total": 1, "list": [
                {"firmware_version": "023E", "file_name": "V0.2.3.E.bin"}]}})
        return FakeResp({"resultCode": "1000", "data": True, "desc": "ok"})

    orig_post, orig_iter, orig_sess = N.api_post, N.iter_firmware, N._session
    orig_up = N._upload_session
    add_calls = []
    N.api_post = fake_api_post
    N.iter_firmware = lambda *a, **kw: ([], 0)   # 查重返回空 -> 允许提交
    N._session = lambda: FakeSession(add_calls)             # 上传链路也必须 mock，禁止真连平台
    N._upload_session = lambda: FakeSession(add_calls, kind="upload")
    try:
        res = N.add_firmware(fw, version="0242", part_code="Z0DK", model="kBwCVBq4,K21101",
                             firmware_type="ECU", desc="selftest", desc_en="selftest",
                             force=False)
    finally:
        N.api_post, N.iter_firmware, N._session = orig_post, orig_iter, orig_sess
        N._upload_session = orig_up
    check("add 全链路未真正联网（上传请求被 mock）",
          any(c["url"].endswith("/upload/init") for c in add_calls), add_calls)
    add_payload = recorded.get("/hardware/firmware/add-firmware-new", {}).get("payload", {})
    check("add-firmware-new body 字段与 HAR 完全一致",
          sorted(add_payload) == sorted(exp_add),
          f"多={sorted(set(add_payload) - set(exp_add))} 少={sorted(set(exp_add) - set(add_payload))}")
    check("part_code 传 [Z0DK]", add_payload.get("part_code") == ["Z0DK"])
    check("firmware_version=0242 file_id=121495",
          add_payload.get("firmware_version") == "0242" and add_payload.get("file_id") == "121495")
    check("productVehicleModelStringList=[[kBwCVBq4,K21101]]",
          add_payload.get("productVehicleModelStringList") == [["kBwCVBq4", "K21101"]])
    check("permission-new 也走 firmware:add",
          recorded.get("/hardware/firmware/permission-new", {}).get("code") == "firmware:add")
    check("add_firmware 返回 ok=True", res.get("ok") is True)

    print("\n=== 5. dry-run 不产生任何写请求 ===")
    writes = []

    def watch_post(path, payload, request_code, timeout=30):
        writes.append(path)
        return FakeResp({"resultCode": "1000", "data": {}})

    calls_dry = []
    fake = FakeSession(calls_dry)
    N.api_post = watch_post
    N._session = lambda: fake
    N._upload_session = lambda: FakeSession(calls_dry, kind="upload")
    N.iter_firmware = lambda *a, **kw: ([{"firmware_version": "0242", "id": "38795",
                                          "status": "1", "part_code": ["Z0DK"],
                                          "file_name": "V0.2.4.2.bin"}], 1)
    try:
        res_dry = N.add_firmware(fw, version="0242", part_code="Z0DK",
                                 model="kBwCVBq4,K21101", dry_run=True)
    finally:
        N.api_post, N._session, N.iter_firmware = orig_post, orig_session, orig_iter
        N._upload_session = orig_upload_session
    check("dry-run 未发任何 api_post", writes == [], writes)
    check("dry-run 未发任何上传请求", calls_dry == [], [c["url"] for c in calls_dry])
    check("dry-run 返回 duplicate=True（检测到已存在同版本）",
          res_dry.get("duplicate") is True)
    check("dry-run 给出 payload 预览", "payload_preview" in res_dry)

    print("\n=== 6. description 必填（提前拦截，不白传二进制） ===")
    calls_nod = []
    N.api_post = lambda *a, **kw: FakeResp({"resultCode": "1000", "data": {}})
    N._session = lambda: FakeSession(calls_nod)
    N._upload_session = lambda: FakeSession(calls_nod, kind="upload")
    N.iter_firmware = lambda *a, **kw: ([], 0)
    err = None
    try:
        try:
            N.add_firmware(fw, version="0243", part_code="Z0DK",
                           model="kBwCVBq4,K21101")   # 不给 desc / desc_en
        except RuntimeError as e:
            err = str(e)
    finally:
        N.api_post, N._session, N.iter_firmware = orig_post, orig_session, orig_iter
        N._upload_session = orig_upload_session
    check("缺 description 时抛出明确错误（平台 1009 descriptionmust not be blank）",
          err is not None and "description" in (err or ""), err)
    check("且在发任何上传/写请求之前就拦下", calls_nod == [],
          [c["url"] for c in calls_nod])

    print("\n=== 7. 替换固件包 edit-firmware-new（mock 网络，HAR 基准） ===")
    rec7, calls7 = {"gets": []}, []

    def fake_get(path, params, request_code, timeout=30):
        rec7["gets"].append({"path": path, "params": params, "code": request_code})
        if path.endswith("/firmware-info"):
            data = json.loads(json.dumps(exp_info))
            if str(params.get("id")) == "38896":      # 模拟真实场景：把 0751 包替换 + 扩车型
                data.update({"id": "38896", "firmware_version": "0751", "file_id": "121737",
                             "md5_verify_code": "4abcf3898c3a3743882b1fae0ac27367",
                             "file_name": "V0.7.5.1.bin", "unreal_file_url": "V0.7.5.1.bin",
                             "part_code": ["XV"], "description": "移远测试固件，请勿升级！！！",
                             "description_en": "Quectel internal test firmware. DO NOT UPGRADE!!!",
                             "productVehicleModelStringList": [["KkbeAhMy", "K02445"]]})
            return FakeResp({"resultCode": "1000", "resultDesc": "成功", "data": data})
        return FakeResp({"resultCode": "1000", "data": {}})

    def fake_post7(path, payload, request_code, timeout=30):
        rec7[path] = {"payload": payload, "code": request_code}
        return FakeResp({"resultCode": "1000", "resultDesc": "成功", "data": None})

    N.api_get, N.api_post = fake_get, fake_post7
    N._session = lambda: FakeSession(calls7)
    N._upload_session = lambda: FakeSession(calls7, kind="upload")
    try:
        res_edit = N.edit_firmware("38896", fw, version="0751", part_code="Z08A,Z0DB,XV",
                                   pvm=[["KkbeAhMy", "K02445"], ["cLlkhxD9", "K05910"]])
    finally:
        N.api_get, N.api_post, N._session = orig_get, orig_post, orig_session
        N._upload_session = orig_upload_session

    ep = rec7.get("/hardware/firmware/edit-firmware-new", {}).get("payload", {})
    check("edit-firmware-new url-request-code = firmware:edit（不是 firmware:add）",
          rec7.get("/hardware/firmware/edit-firmware-new", {}).get("code") == "firmware:edit")
    check("edit-firmware-new body 字段与 HAR 完全一致",
          sorted(ep) == sorted(exp_edit),
          f"多={sorted(set(ep) - set(exp_edit))} 少={sorted(set(exp_edit) - set(ep))}")
    check("先 GET firmware-info?id=<id> 读原记录",
          bool(rec7["gets"]) and rec7["gets"][0]["path"].endswith("/firmware-info")
          and rec7["gets"][0]["params"].get("id") == "38896")
    check("file_id 指向新上传文件 121495", ep.get("file_id") == "121495")
    check("md5_verify_code = 新文件 md5", ep.get("md5_verify_code") == N.file_md5(fw))
    check("version=0751", ep.get("firmware_version") == "0751")
    check("part_code 覆盖为 [Z08A,Z0DB,XV]", ep.get("part_code") == ["Z08A", "Z0DB", "XV"])
    check("车型 = 原有 K02445 + 追加 K05910",
          ep.get("productVehicleModelStringList") == [["KkbeAhMy", "K02445"],
                                                      ["cLlkhxD9", "K05910"]])
    check("open_diff/status/description 未指定则沿用原记录",
          ep.get("open_diff") == exp_info.get("open_diff")
          and ep.get("status") == str(exp_info.get("status"))
          and ep.get("description") == "移远测试固件，请勿升级！！！")
    init_c7 = next((c for c in calls7 if c["url"].endswith("/upload/init")), None)
    check("上传名沿用原 file_name（V0.7.5.1.bin，改名会改版本）",
          bool(init_c7) and init_c7["json"]["name"] == "V0.7.5.1.bin",
          init_c7 and init_c7["json"]["name"])
    check("edit 全链路未真正联网（仅 mock 请求）", bool(ep) and res_edit.get("ok") is True)

    print("\n=== 8. 替换 dry-run / 不换文件 两条路径 ===")
    rec8, calls8 = {"writes": 0}, []

    def fake_get8(path, params, request_code, timeout=30):
        data = json.loads(json.dumps(exp_info))
        data.update({"id": "38896", "firmware_version": "0751", "file_id": "121737",
                     "file_name": "V0.7.5.1.bin", "part_code": ["XV"],
                     "productVehicleModelStringList": [["KkbeAhMy", "K02445"]]})
        return FakeResp({"resultCode": "1000", "data": data})

    def fake_post8(path, payload, request_code, timeout=30):
        rec8["writes"] += 1
        rec8[path] = payload
        return FakeResp({"resultCode": "1000", "data": None})

    N.api_get, N.api_post = fake_get8, fake_post8
    N._session = lambda: FakeSession(calls8)
    N._upload_session = lambda: FakeSession(calls8, kind="upload")
    try:
        dry = N.edit_firmware("38896", fw, version="0751", dry_run=True)
        only_attr = N.edit_firmware("38896", None,
                                    pvm=[["KkbeAhMy", "K02445"], ["cLlkhxD9", "K05910"]])
    finally:
        N.api_get, N.api_post, N._session = orig_get, orig_post, orig_session
        N._upload_session = orig_upload_session
    check("dry-run 不发任何写请求、不上传", rec8["writes"] == 1 and calls8 == [],
          f"writes={rec8['writes']} uploads={len(calls8)}")
    check("dry-run 返回 payload 预览（file_id 占位）",
          dry.get("payload_preview", {}).get("file_id") == "<上传后返回>")
    check("不换文件时沿用原 file_id=121737",
          rec8.get("/hardware/firmware/edit-firmware-new", {}).get("file_id") == "121737")

    if tmp:
        os.remove(tmp)

    print(f"\n===== 结果: {_PASS} passed, {_FAIL} failed =====")
    return 1 if _FAIL else 0


orig_session = N._session
orig_upload_session = N._upload_session
orig_get = N.api_get

if __name__ == "__main__":
    sys.exit(main())
