#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
九号(Ninebot) IoT OTA 固件平台 操作 helper（一体化版本）
配合 SKILL.md 使用。使用前必须连内网（SOCKS5 127.0.0.1:1080）。

子命令:
  connect            安装依赖 + 测试内网连通
  login             用 ACCOUNT/PASSWORD 账号密码登录，刷新并持久化会话 Cookie
  part-types         获取零部件类型列表
  models             获取车型列表（用于拿 产品码,车型码）
  query              查询固件包列表
  add                新增固件包（自动 命名+MD5+真实二进制上传+提交；可用 --imei 自动解析车型/零部件）
  query-device       按 IMEI/SN 查询设备 + 当前各零部件版本（自动解析车型/零部件编码）
  resolve-part       解析某车型某零部件的可用 part_code
  upgrade            下发一次升级任务并轮询+校验
  rollback           下发一次回滚（= 向更低版本再发一次升级任务）
  status             查看设备当前版本 + 最近升级历史
  fota               一站式：注册缺失包 -> 升级链路 -> 回滚（一次跑完，最少对话轮次）
  ble-upgrade        平台下发蓝牙升级指令(c:ota/actual_ota_type=2)，需 APP 经 BLE 开始刷写
  commands           查看平台下发到设备的指令（链路核验：是否下发/设备是否回应）
                     --watch N 用于 APP 设置后一键核验平台下发与设备回应

用法示例:
  python ninebot_ota.py connect
  python ninebot_ota.py query-device 869004070113552
  python ninebot_ota.py add --imei 869004070113552 --file fw.bin --version 032E
  python ninebot_ota.py upgrade 869004070113552 032E
  python ninebot_ota.py rollback 869004070113552 022f
  python ninebot_ota.py fota 869004070113552 --files 032e.bin,032f.bin --versions 032E,032F --rollback-to 022f
  python ninebot_ota.py commands 869004070113552 --minutes 10
  python ninebot_ota.py commands 869004070113552 --watch 30   # APP设置后调用，等平台下发并跟踪回应
  python ninebot_ota.py ble-upgrade 869004070113552 032E       # 平台下发蓝牙升级指令(需APP经BLE刷写)
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
import urllib.parse
from datetime import date, datetime

import requests

# ---------- 基础配置 ----------
BASE = "https://iot-test.ninebot.com/service/iot-ota-console-api"
CONSOLE_BASE = "https://iot-test.ninebot.com/service/iot-console-api"

# 内网 SOCKS5 代理（需本机已建立隧道）
PROXY = "socks5h://127.0.0.1:1080"
PROXIES = {"http": PROXY, "https": PROXY}

# 认证 Cookie（会话级，会过期；从浏览器/抓包刷新。下面一组来自 2026-07-23 抓包，较新）
COOKIES = {
    "SESSION": "04bf66fe-ad05-44df-8af1-b71ed3c9d669",
    "titan-test-tgc": "TGT-2c75bc13b1034d73b77cea7b2c9d5194",
    "auth-test": "NDBiMDM5NDItMjE0OS00NmVjLThhMTktNzQ2OTc5MGJlMDhi",
}

# S3 上传参数
S3_REGION = "cn-northwest-1"
S3_BUCKET = "file-upload-test"
FILE_API = "https://iot-test.ninebot.com/service/file-upload"
UPLOAD_HOST = "https://file-upload-test.ninebot.com"
CHUNK_SIZE = 5242880  # 分片大小常量（5MB）

OPERATE_USER = "dehao.zhang"

# 平台登录账号 / 密码（登录用邮箱格式；OPERATE_USER 是操作回填用的短工号）
# 改账号/密码只改这里即可，所有命令自动重新登录。
ACCOUNT = "dehao.zhang@ninebot.com"
PASSWORD = "1003070394ssXX!"
# 登录成功后把会话 Cookie 持久化到本地，跨进程复用（默认 30min 过期后再自动重登）
COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ninebot_cookies.json")
_AUTH_VALID_UNTIL = 0  # 鉴权有效截止时间戳；0=未知，强制首次校验


def _parse_ts(ts):
    """解析平台时间字段为 epoch 秒。支持 ISO8601 字符串(如 2026-08-05 16:36:10)或 epoch 数字/字符串；失败返回 0。"""
    if not ts:
        return 0
    try:
        if isinstance(ts, (int, float)):
            v = float(ts)
            return v / 1000.0 if v > 1e12 else v
        s = str(ts).strip().replace("/", "-")
        s19 = s[:19]
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
            try:
                return datetime.strptime(s19, fmt).timestamp()
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(s.replace("Z", "")).timestamp()
        except ValueError:
            return 0
    except Exception:
        return 0


def _load_saved_cookies():
    """启动时从本地文件恢复上次会话 Cookie，避免每次运行都重新登录。"""
    global _AUTH_VALID_UNTIL
    try:
        if os.path.exists(COOKIE_FILE):
            with open(COOKIE_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            COOKIES.update({k: v for k, v in saved.items() if k in COOKIES})
            _AUTH_VALID_UNTIL = time.time() + 1800  # 信任本地 cookie 30 分钟
    except Exception:
        pass


def _save_cookies():
    """把当前 COOKIES 持久化到本地文件。"""
    try:
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            json.dump(dict(COOKIES), f, ensure_ascii=False)
    except Exception:
        pass


_load_saved_cookies()


HEADERS_JSON = {
    "content-type": "application/json;charset=UTF-8",
    "accept": "application/json, text/plain, */*",
}
HDR_SSE = {"accept": "application/json, text/plain, */*", "url-request-code": "firmware:add"}


# ---------- 工具函数 ----------
def normalize_version(version):
    """版本号命名规则: '032E' -> ['0','3','2','E']; '0.3.2.E' -> 同上
    返回 (firmware_version 大写拼接, package_name='V'+点连接)
    ⚠️ 平台按【上传文件名】提取固件版本：V0.3.2.E.bin -> 032E；裸名 032e.bin -> null -> 4025
    """
    version = version.strip()
    parts = [p for p in re.split(r"[.\s]+", version) if p]
    if len(parts) == 1 and len(parts[0]) == 4:
        parts = list(parts[0])
    firmware_version = "".join(parts).upper()
    package_name = "V" + ".".join(parts)
    return firmware_version, package_name


def file_md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _session():
    ensure_authenticated()
    s = requests.Session()
    s.proxies.update(PROXIES)
    s.cookies.update(COOKIES)
    s.headers.update({
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://iot-test.ninebot.com",
        "referer": "https://iot-test.ninebot.com/",
    })
    return s


# ---------- 鉴权：账号密码自动登录 + 失效自刷新 ----------
def login():
    """账号密码登录 iot-test 平台，刷新 SESSION/titan-test-tgc/auth-test 会话 Cookie 并持久化。
    流程: (1) GET /service/oauth2/authorization/iot 拿前置 SESSION；
          (2) POST https://auth-test.ninebot.com/login 提交 username/password。"""
    global _AUTH_VALID_UNTIL
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0")
    s = requests.Session()
    s.proxies.update(PROXIES)
    s.headers.update({"user-agent": ua, "accept": "text/html,application/xhtml+xml,*/*;q=0.8"})
    # 步骤1：前置 cookie（SESSION）
    r1 = s.get("https://iot-test.ninebot.com/service/oauth2/authorization/iot"
               "?redirect_uri=https%3A%2F%2Fiot-test.ninebot.com%2F%23%2F", timeout=20)
    if r1.status_code not in (200, 302):
        raise RuntimeError(f"获取前置 cookie 失败: HTTP {r1.status_code}")
    # 步骤2：提交账号密码
    payload = "username={0}&password={1}&isRemember=true".format(
        urllib.parse.quote(ACCOUNT), urllib.parse.quote(PASSWORD))
    h = {
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://auth-test.ninebot.com",
        "referer": "https://auth-test.ninebot.com/login",
        "user-agent": ua,
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,*/*;q=0.8",
    }
    r2 = s.post("https://auth-test.ninebot.com/login", data=payload,
                headers=h, timeout=20)
    if r2.status_code not in (200, 302):
        raise RuntimeError(f"登录失败: HTTP {r2.status_code} {r2.text[:200]}")
    # 收割需要的 cookie
    needed = ("SESSION", "titan-test-tgc", "auth-test")
    got = {k: v for k, v in s.cookies.items() if k in needed}
    if "SESSION" not in got:
        raise RuntimeError("登录成功但未取到 SESSION cookie，可能账号/密码错误")
    COOKIES.update(got)
    _save_cookies()
    _AUTH_VALID_UNTIL = time.time() + 1800
    return got


def _probe_auth():
    """用一次轻量接口探测当前 cookie 是否有效（resultCode 1000 = 有效）。"""
    s = requests.Session()
    s.proxies.update(PROXIES)
    s.cookies.update(COOKIES)
    s.headers.update({
        "user-agent": "Mozilla/5.0",
        "origin": "https://iot-test.ninebot.com",
        "referer": "https://iot-test.ninebot.com/",
    })
    try:
        r = s.get(BASE + "/basic/products-vehicle-models",
                  params={"partType": "ECU"}, headers=HDR_SSE, timeout=15)
        if r.status_code == 200:
            return r.json().get("resultCode") == "1000"
    except Exception:
        pass
    return False


def ensure_authenticated():
    """按需鉴权：缓存有效期内直接放行；否则先探测、失效则自动登录。"""
    global _AUTH_VALID_UNTIL
    now = time.time()
    if now < _AUTH_VALID_UNTIL:
        return
    if _probe_auth():
        _AUTH_VALID_UNTIL = now + 1800
        return
    login()  # 失败抛异常，由调用方处理


def api_post(path, payload, request_code):
    s = _session()
    h = dict(HEADERS_JSON)
    h["url-request-code"] = request_code
    r = s.post(BASE + path, json=payload, headers=h, timeout=30)
    return r


def api_get(path, params, request_code):
    s = _session()
    r = s.get(BASE + path, params=params, headers={"accept": "application/json, text/plain, */*", "url-request-code": request_code}, timeout=30)
    return r


# ---------- 业务函数：查询/车型 ----------
def connect():
    print("[1/3] 安装依赖 requests[socks] ...", flush=True)
    os.system(f'{sys.executable} -m pip install "requests[socks]" -q')
    print("[2/3] 测试内网代理连通性 ...", flush=True)
    try:
        s = _session()
        r = s.get(BASE + "/basic/products-vehicle-models", params={"partType": "ECU"}, headers=HDR_SSE, timeout=15)
        ok = r.status_code == 200
        print(f"    状态码: {r.status_code}, 连通: {'是' if ok else '否'}", flush=True)
        if not ok:
            print("    ⚠️ 未连通：请确认本机已建立到内网的 SOCKS5 隧道(127.0.0.1:1080)。")
    except Exception as e:
        print(f"    ⚠️ 连通测试失败: {e}", flush=True)
    print("[3/3] 完成。", flush=True)


def get_part_types():
    return api_post("/api/iot/get-part-type-list", {}, "firmware:add").json()


def get_models(part_type="ECU"):
    return api_get("/basic/products-vehicle-models", {"partType": part_type}, "firmware:add").json()


def query_firmware(page=1, num=10, level="", vehicle_model_code="",
                   firmware_type="", firmware_version=""):
    params = {
        "page": page, "num": num,
        "firmware_level": level,
        "vehicle_model_code": vehicle_model_code,
        "firmware_type": firmware_type,
        "firmware_version": firmware_version,
    }
    return api_get("/hardware/firmware/firmware-list", params, "firmwareList:info").json()


# ---------- 业务函数：设备解析（关键：避免加错车型） ----------
def resolve_device(imei_or_sn):
    """按 IMEI/SN 查设备，并返回 (device_dict, parts_dict[part_type]=info)
    自动解析出 product_key / vehicle_model_code / 各零部件当前版本与 pn。"""
    s = _session()
    url = CONSOLE_BASE + "/device/list"
    payload = {"pageNumber": 1, "pageSize": 10, "snVin": imei_or_sn,
               "activeStatus": "", "onlineStatus": "", "sort": "desc",
               "productIds": [], "modelCodes": []}
    r = s.post(url, json=payload, timeout=30)
    j = r.json()
    if j.get("resultCode") != "1000" or not j.get("data", {}).get("list"):
        raise RuntimeError(f"设备查询失败或无结果: {j}")
    dev = j["data"]["list"][0]
    # 兼容字段命名：设备列表接口返回 camelCase，但本脚本其余逻辑用 snake_case
    dev.setdefault("product_key", dev.get("productKey"))
    dev.setdefault("vehicle_model_code", dev.get("vehicleModelCode"))
    dev.setdefault("device_id", dev.get("deviceId") or dev.get("id"))
    sn = dev.get("sn")
    rp = s.post(BASE + "/api/iot/get-parts-version", data=json.dumps({"sn": sn}), timeout=30)
    pj = rp.json()
    parts = {i["part_type"]: i for i in pj.get("data", [])} if pj.get("resultCode") == "1000" else {}
    return dev, parts


# ---------- 实时数据 / 设备详情查询（补充接口，来自 iot-console-api） ----------
def _device_ids(sn):
    """解析设备三元组，供 realTimeData / historyData / ai 系列接口使用。"""
    dev, _ = resolve_device(sn)
    return {
        "deviceId":   dev.get("deviceId") or dev.get("device_id"),
        "deviceName": dev.get("deviceName"),
        "productId":  dev.get("productId"),
        "productKey": dev.get("productKey") or dev.get("product_key"),
        "sn":         sn,
    }


def rt_query(sn, endpoint, method="GET", extra=None, json_body=None,
             base="realTimeData", raw=False):
    """调用 iot-console-api 实时/历史数据接口。
    endpoint: 'alarm' / 'bms' / 'vehicleStatus' / 'warning'(base='ai/vehicle') 等。
    base: api 路径前缀段（默认 realTimeData；historyData / ai/vehicle）。
    返回 data 段（raw=True 返回整包）。"""
    ids = _device_ids(sn)
    s = _session()
    url = f"{CONSOLE_BASE}/{base}/{endpoint}"
    params = {"productId": ids["productId"], "deviceName": ids["deviceName"],
              "deviceId": ids["deviceId"]}
    if extra:
        params.update(extra)
    if method.upper() == "GET":
        r = s.get(url, params=params, timeout=30)
    else:
        r = s.post(url, params=params, json=json_body, timeout=30)
    j = r.json()
    if str(j.get("resultCode")) != "1000":
        raise RuntimeError(f"{base}/{endpoint} 查询失败: {j}")
    return j if raw else j.get("data")


def device_overview(sn):
    """聚合查询设备全部实时数据（整车/状态/报警/故障/事件/电池/电池日志/字段/天气/近期在线）。"""
    ids = _device_ids(sn)
    sections = {
        "vehicle(整车实时)": ("realTimeData", "vehicle", {}),
        "vehicleStatus(车辆状态)": ("realTimeData", "vehicleStatus", {}),
        "alarm(报警)": ("realTimeData", "alarm", {}),
        "warning(故障告警)": ("ai/vehicle", "warning",
                              {"sn": sn, "pageNo": 1, "pageSize": 20}),
        "event(事件)": ("realTimeData", "event", {}),
        "bms(电池)": ("realTimeData", "bms", {}),
        "bmsLog(电池日志)": ("realTimeData", "bmsLog", {}),
        "field(字段)": ("realTimeData", "field", {"productKey": ids["productKey"]}),
        "weather(天气)": ("realTimeData", "weather", {}),
    }
    out = {}
    for title, (base, ep, extra) in sections.items():
        try:
            out[title] = rt_query(sn, ep, base=base, extra=extra)
        except Exception as e:
            out[title] = {"_error": str(e)}
    try:
        now = int(time.time() * 1000)
        out["onlineStatusHistory(最近24h)"] = rt_query(
            sn, "onlineStatus", base="historyData",
            extra={"startTime": now - 24 * 3600 * 1000, "endTime": now})
    except Exception as e:
        out["onlineStatusHistory(最近24h)"] = {"_error": str(e)}
    return out


def device_dataflow(sn, fields=None):
    """POST 数据流接口（需指定想看的字段映射）。默认查 SOC/车速/总电流/总电压。"""
    ids = _device_ids(sn)
    default_fields = {"soc": "SOC", "speed": "车速",
                      "total_electric_current": "总电流", "total_voltage": "总电压"}
    body = {"productId": ids["productId"], "deviceName": ids["deviceName"],
            "fields": fields or default_fields, "deviceId": ids["deviceId"]}
    return rt_query(sn, "dataFlow", method="POST", json_body=body)


def download_tasks():
    """查询当前账号下的固件下载任务列表（与具体设备无关）。"""
    s = _session()
    r = s.get(CONSOLE_BASE + "/downloadTask/get", timeout=30)
    return r.json()


def require_attribute(pvm, part_type="ECU"):
    r = api_post("/hardware/firmware/require-attribute",
                 {"productVehicleModelList": pvm, "partType": part_type}, "firmware:add")
    j = r.json()
    return [c["code"] for c in j.get("data", {}).get("partCodes", [])]


def resolve_part_code(pvm, part_type, device_pn):
    """从 require-attribute 返回的候选 part_code 中选最匹配设备 ECU pn 的。
    规则：优先选 device_pn 前缀匹配的；否则选最长的（最具体）。"""
    codes = require_attribute(pvm, part_type)
    if not codes:
        return None
    if device_pn:
        pn = device_pn.upper()
        matched = [c for c in codes if pn.startswith(c.upper())]
        if matched:
            return max(matched, key=len)
    return max(codes, key=len)


# ---------- 业务函数：新增固件包（完整真实上传流程） ----------
def s3_upload(file_path, product_vehicle_model, firmware_version, display_name=None):
    """完整上传流程（按 HAR 真实顺序）：
        file-upload/upload/init -> upload/part(GET预检+POST二进制) -> upload/complete
        -> hardware/firmware/s3-upload-by-path (拿 file_id)
    ⚠️ 平台按【文件名】提取版本：必须用 V<x1>.<x2>.<x3>.<x4>.bin，否则版本=null -> 4025。"""
    name = display_name or (normalize_version(firmware_version)[1] + ".bin")
    size = os.path.getsize(file_path)
    md5 = file_md5(file_path)
    s = _session()
    h = dict(HEADERS_JSON); h["url-request-code"] = "firmware:add"

    r = s.post(FILE_API + "/upload/init",
               json={"md5": md5, "name": name, "size": size,
                     "totalBlock": 1, "clientKey": "iot-console-api"},
               headers=h, timeout=30).json()
    d = r["data"]
    file_id = d["fileId"]; upload_id = d.get("uploadId"); object_key = d["objectKey"]
    bucket = d.get("bucketName", S3_BUCKET)

    if not d.get("pass"):
        s.get(UPLOAD_HOST + "/upload/part",
              params={"bucketName": bucket, "objectKey": object_key, "uploadId": upload_id,
                      "fileId": file_id, "chunkNumber": 1, "totalChunks": 1,
                      "size": CHUNK_SIZE, "md5": md5}, timeout=30)
        files = [
            ("bucketName", (None, bucket)), ("objectKey", (None, object_key)),
            ("uploadId", (None, str(upload_id))), ("fileId", (None, str(file_id))),
            ("chunkNumber", (None, "1")), ("totalChunks", (None, "1")),
            ("size", (None, str(CHUNK_SIZE))), ("md5", (None, md5)),
            ("file", (name, open(file_path, "rb"), "application/octet-stream")),
        ]
        s.post(UPLOAD_HOST + "/upload/part", files=files, timeout=120)

    s.post(FILE_API + "/upload/complete", json={"fileId": file_id}, headers=h, timeout=30)

    payload = {"region": S3_REGION, "bucketName": bucket, "objectKey": object_key, "url": None,
               "name": name, "size": size, "md5": md5, "file_use_type": 0,
               "productVehicleModelStringList": product_vehicle_model}
    r = s.post(BASE + "/hardware/firmware/s3-upload-by-path", json=payload, headers=h, timeout=30)
    return r.json(), md5


def add_firmware(file_path, version, part_code=None, model=None, imei=None,
                 firmware_type="ECU", desc="", desc_en="", level=1):
    """新增固件包。两种用法：
       A) 显式: --model kBwCVBq4,K21101 --part-code Z0DK
       B) 自动: --imei <IMEI>  -> 自动解析 车型/零部件编码（推荐，避免加错车型）
    """
    if imei:
        dev, parts = resolve_device(imei)
        pk = dev["product_key"]; vmc = dev["vehicle_model_code"]
        pvm = [[pk, vmc]]
        if part_code is None:
            pn = parts.get(firmware_type, {}).get("pn")
            part_code = resolve_part_code(pvm, firmware_type, pn)
            if part_code is None:
                raise RuntimeError("无法自动解析 part_code，请显式传 --part-code")
        print(f"[车型] PK={pk} VMC={vmc} part_code={part_code}", flush=True)
    else:
        if not model:
            raise RuntimeError("需提供 --model 或 --imei")
        pvm = [[m.strip() for m in model.split(",")]]

    if not os.path.isfile(file_path):
        raise RuntimeError(f"文件不存在: {file_path}")

    firmware_version, package_name = normalize_version(version)
    print(f"[新增固件] 版本={firmware_version} 包名={package_name}.bin", flush=True)

    up, md5 = s3_upload(file_path, pvm, firmware_version, display_name=package_name + ".bin")
    if up.get("resultCode") != "1000":
        return {"ok": False, "step": "s3-upload", "resp": up}
    file_id = up["data"]["file_id"]
    print(f"[1/3] s3-upload OK file_id={file_id} md5={md5}", flush=True)

    perm = api_post("/hardware/firmware/permission-new",
                    {"productVehicleModelStringList": pvm, "firmware_type": firmware_type,
                     "part_code": [part_code]}, "firmware:add").json()
    print(f"[2/3] permission-new {perm.get('resultCode')}", flush=True)

    rel = api_post("/hardware/firmware/firmware-relate-version-new",
                   {"productKeys": [], "vehicle_model_codes": [],
                    "productVehicleModelStringList": pvm, "firmware_type": firmware_type,
                    "firmware_version": firmware_version, "firmware_level": level,
                    "pageSize": 10, "pageNumber": 1}, "firmware:add").json()
    print(f"[3/4] relate-version {rel.get('resultCode')}", flush=True)

    payload = {"productVehicleModelStringList": pvm, "part_code": [part_code],
               "firmware_type": firmware_type, "firmware_version": firmware_version,
               "firmware_level": level, "file_id": file_id, "md5_verify_code": md5,
               "descDraft": desc or desc_en, "big_file_url": "", "status": 1,
               "description": desc or desc_en, "description_en": desc_en or desc,
               "relate_version": "", "operate_user": OPERATE_USER, "encrypt_1": 2,
               "is_milestone": 0, "open_diff": 0, "firmware_diff_data": [],
               "ui_extends": [], "skinName": "", "file_use_type": 0, "estimate_time": 60}
    add = api_post("/hardware/firmware/add-firmware-new", payload, "firmware:add").json()
    print(f"[4/4] add-firmware-new {add.get('resultCode')} {add.get('resultDesc')}", flush=True)
    return {"ok": add.get("resultCode") == "1000", "firmware_version": firmware_version,
            "file_id": file_id, "add_response": add}


# ---------- 业务函数：FOTA 升级 / 回滚 / 状态 ----------
def send_upgrade(sn, pk, vmc, part_type, target, current):
    """下发升级任务: POST /api/iot/auto-group-send
    注意 otaCurrentVersion 传【设备真实上报版本】(来自 get-parts-version)，
    otaTargetVersion 传【包版本标签】(如 032E)。"""
    s = _session()
    payload = {"sn": sn, "product_key": pk,
               "partTypes": [{"partType": part_type, "otaTargetVersion": target,
                              "otaCurrentVersion": current, "buttonDisplay": False}],
               "vehicle_model_code": vmc, "encrypt_2": 2, "times": "1",
               "intervalTime": 15, "verification": False}
    return s.post(BASE + "/api/iot/auto-group-send", data=json.dumps(payload), timeout=30)


def send_ble_upgrade(sn, pk, vmc, part_type, target, user_name=OPERATE_USER):
    """平台下发蓝牙升级指令: POST /api/iot/send
    与普通静默 FOTA(auto-group-send) 不同，这是 cmdCode=c:ota + actual_ota_type:2 的单部件指令；
    平台下发后**必须由手机 APP 经蓝牙开始刷写(app.fota_begin)**才会真正传输固件。
    参考 QDM551 压力脚本 fota_bluetooth_download_api / fota_update(ota_type="app")。"""
    s = _session()
    payload = {"user_name": user_name, "sn": sn, "product_key": pk,
               "cmdCode": "c:ota", "qos": 0, "timeout": 0,
               "part_type": part_type, "part_firmware_version": target,
               "vehicle_model_code": vmc, "actual_ota_type": 2, "verification": False}
    return s.post(BASE + "/api/iot/send", data=json.dumps(payload), timeout=30)


def get_upgrade_history(sn, pk, part_type="", target="", upgrade_status="null", size=30):
    """OTA 升级历史/任务列表 = 页面 OTA管理→单元升级→升级详情 背后的接口。
    包含：① 静默 FOTA 任务 (actual_ota_type=1)；
          ② 蓝牙升级任务 (actual_ota_type=2) —— 下发后 status=-1 即「待升级」(等 APP 经蓝牙开始)。
    注意 BLE 任务刚下发时 get-upgrade-history 有 ~1min 异步延迟；commands 走的是蜂窝指令日志，查不到 BLE 任务。"""
    s = _session()
    payload = {"page": 1, "size": size, "product_key": pk, "sn": sn,
               "part_type": part_type or "",
               "upgrade_status": upgrade_status if upgrade_status != "" else "null",
               "ota_target_version": target or ""}
    return s.post(BASE + "/api/iot/get-upgrade-history", data=json.dumps(payload), timeout=30).json()


def get_parts_version(sn):
    s = _session()
    r = s.post(BASE + "/api/iot/get-parts-version", data=json.dumps({"sn": sn}), timeout=30)
    j = r.json()
    return {i["part_type"]: i.get("part_firmware_version") for i in j.get("data", [])}


# ---------- 业务函数：查看平台下发到设备的指令（链路核验） ----------
# 对应 HAR: GET /service/iot-console-api/device/command
# 字段含义（基于抓包推断，status 为字符串）:
#   req_time   平台下发指令的时间戳
#   resp_time  设备回应的时间戳（为空=设备尚未回应/超时）
#   resp_code  设备回应码（"01"=已回应；空=未回应）
#   status     指令状态: "0"/"1"=已下发 "2"=已送达 "3"=设备已回应(完成) "4"=失败/超时
#   cmd_body   平台下发的指令体(sourceId/tragetId/cmdId/data/index...)
#   resp_data  设备回执体
HDR_CMD = {"accept": "application/json, text/plain, */*", "url-request-code": "data:raw"}
CMD_STATUS_DESC = {
    "0": "已下发", "1": "已下发", "2": "已送达设备",
    "3": "设备已回应(完成)", "4": "失败/超时",
}

def get_device_commands(sn, pk, device_id, start, end):
    """查询平台下发到某设备的指令列表（时间窗 start~end 为 epoch 秒）。
    返回平台原始 JSON（data 为指令数组）。"""
    s = _session()
    params = {"productKey": pk, "sn": sn, "deviceId": device_id,
              "startTime": start, "endTime": end}
    r = s.get(CONSOLE_BASE + "/device/command", params=params,
              headers=HDR_CMD, timeout=30)
    return r.json()


def _summarize_commands(data):
    out = []
    for c in data:
        req = c.get("req_time"); resp = c.get("resp_time")
        st = str(c.get("status")); rcode = c.get("resp_code")
        out.append({
            "cmd_num": c.get("cmd_num"),
            "cmd_code": c.get("cmd_code"),
            "req_time": req,
            "resp_time": resp,
            "status": st,
            "status_desc": CMD_STATUS_DESC.get(st, st),
            "resp_code": rcode,
            "device_responded": bool(rcode),
            "latency_s": (int(resp) - int(req)) if (req and resp) else None,
            "cmd_body": c.get("cmd_body"),
            "resp_data": c.get("resp_data"),
        })
    return out


def do_commands(imei, minutes=10, since=None, until=None, watch=None):
    """查看平台下发指令。两种模式:
       - 列表模式(默认): 列出时间窗内的下发指令并做链路核验。
       - watch 模式(--watch N): 用于【APP 设置之后】调用，轮询等待平台下发的新指令，
         并持续跟踪到设备回应，直接给出'平台是否下发+设备是否回应'的判定。
    """
    dev, parts = resolve_device(imei)
    sn = dev["sn"]
    pk = dev.get("product_key") or dev.get("productKey")
    device_id = dev.get("device_id") or dev.get("deviceId") or dev.get("id")
    if not device_id:
        raise RuntimeError(f"无法获取 deviceId（device 字段: {list(dev.keys())}）")
    now = int(time.time())

    if watch:
        base = now
        deadline = now + int(watch)
        print(f"[watch] 等待平台下发新指令（最多 {watch}s，用于 APP 设置后核验）...", flush=True)
        target = None
        while time.time() < deadline:
            j = get_device_commands(sn, pk, device_id, base, int(time.time()) + 5)
            if j.get("resultCode") == "1000":
                new = [c for c in (j.get("data") or []) if int(c.get("req_time", 0)) >= base]
                if new:
                    target = new[-1]
                    break
            time.sleep(3)
        if not target:
            print("[watch] 超时: 窗口内未检测到平台下发的新指令（可能 APP 未真正触发，或指令未落库）", flush=True)
            return []
        # 等待设备回应
        print(f"[watch] 已检测到下发指令 cmd_num={target.get('cmd_num')} req_time={target.get('req_time')}", flush=True)
        for _ in range(int(watch // 3) + 2):
            j2 = get_device_commands(sn, pk, device_id, base, int(time.time()) + 5)
            if j2.get("resultCode") == "1000":
                cur = next((x for x in (j2.get("data") or []) if x.get("cmd_num") == target.get("cmd_num")), None)
                if cur and cur.get("resp_code"):
                    target = cur
                    break
            time.sleep(3)
        return _print_cmd_result([target], sn, pk, device_id)

    end = until or now
    start = since or (end - int(minutes) * 60)
    j = get_device_commands(sn, pk, device_id, start, end)
    if j.get("resultCode") != "1000":
        print(f"[FAIL] 查询失败: {j.get('resultDesc')} code={j.get('resultCode')}", flush=True)
        return []
    data = j.get("data") or []
    return _print_cmd_result(data, sn, pk, device_id, start, end)


def _print_cmd_result(data, sn, pk, device_id, start=None, end=None):
    if start is not None and end is not None:
        print(f"[设备] SN={sn} PK={pk} deviceId={device_id}")
        print(f"[时间窗] {start}~{end} ({(end-start)//60}分钟), 共 {len(data)} 条指令\n")
    elif data:
        print(f"[设备] SN={sn} PK={pk} deviceId={device_id}, 命中 {len(data)} 条\n")
    responded = 0
    for c in data:
        req = c.get("req_time"); resp = c.get("resp_time")
        st = str(c.get("status")); rcode = c.get("resp_code")
        flag = "✅ 设备已回应" if rcode else "⏳ 未回应/超时"
        print(f"- {flag} | cmd={c.get('cmd_code')} | req={req} resp={resp} | status={st}({CMD_STATUS_DESC.get(st, st)}) resp_code={rcode}")
        if c.get("cmd_body"):
            print(f"    cmd_body : {c['cmd_body']}")
        if c.get("resp_data"):
            print(f"    resp_data: {c['resp_data']}")
        if rcode:
            responded += 1
    print(f"\n[链路核验] 平台下发 {len(data)} 条, 设备已回应 {responded} 条", flush=True)
    if data and responded == len(data):
        print("[结论] 平台已下发且设备全部回应 —— 即便 APP 显示超时，实际链路已成功。", flush=True)
    elif data and responded == 0:
        print("[结论] 平台已下发但设备均无回应 —— 可能真超时/设备离线，需结合 APP 判断。", flush=True)
    return _summarize_commands(data)



def poll_upgrade(sn, pk, part_type, target, timeout=480, interval=10):
    """轮询升级历史；历史接口偶发'服务器异常'时最多重试3次即转设备版本回退校验。
    返回 (ok, entry): ok=True成功 / False失败 / None超时或历史不可用。"""
    deadline = time.time() + timeout
    last = None
    err_cnt = 0
    while time.time() < deadline:
        try:
            j = get_upgrade_history(sn, pk, part_type, target)
            err_cnt = 0
            lst = (j.get("data") or {}).get("list", []) or []
        except Exception as e:
            err_cnt += 1
            print(f"  [poll] history 异常: {e}", flush=True)
            if err_cnt >= 3:
                print("  [poll] history 持续不可用，等待设备刷写后转版本回退校验...", flush=True)
                time.sleep(90)
                return None, last
            time.sleep(interval)
            continue
        if j.get("resultCode") != "1000":
            err_cnt += 1
            if err_cnt >= 3:
                print("  [poll] history 持续不可用，等待设备刷写后转版本回退校验...", flush=True)
                time.sleep(90)
                return None, last
            time.sleep(interval)
            continue
        matches = [x for x in lst if x.get("part_type") == part_type and x.get("ota_target_version") == target]
        if matches:
            e = matches[0]; st = str(e.get("upgrade_status"))
            print(f"  [poll] {part_type}->{target} status={st} reason={e.get('status_reason')} progress={e.get('progress')}", flush=True)
            last = e
            if st == "1":
                return True, e
            if st == "2":
                return False, e
        else:
            print("  [poll] 任务尚未生成...", flush=True)
        time.sleep(interval)
    return None, last


def do_upgrade(imei, target, current=None, part_type="ECU", rollback=False, timeout=480):
    """执行一次升级/回滚并校验。校验以【平台任务状态】为主；
    设备真实版本可能与包标签不同(如 032E 标签 -> 设备报 023e)，故不强制相等，
    仅用'版本是否发生变化'作为历史不可用时的回退判据。"""
    dev, parts = resolve_device(imei)
    sn = dev["sn"]; pk = dev["product_key"]; vmc = dev["vehicle_model_code"]
    if current is None:
        current = parts.get(part_type, {}).get("part_firmware_version")
    tag = "回滚" if rollback else "升级"
    print(f"\n=== {tag} {part_type}: {current} -> {target} (IMEI {imei}) ===", flush=True)

    r = send_upgrade(sn, pk, vmc, part_type, target, current)
    try:
        j = r.json()
    except Exception:
        print(f"[FAIL] 下发响应非 JSON: {r.text[:200]}", flush=True); return False
    if j.get("resultCode") != "1000":
        print(f"[FAIL] 下发失败: {j.get('resultDesc')} code={j.get('resultCode')}", flush=True); return False
    print("[OK] 任务已创建，轮询中...", flush=True)

    ok, e = poll_upgrade(sn, pk, part_type, target, timeout)
    time.sleep(3)
    new_ver = get_parts_version(sn).get(part_type)
    print(f"[设备实际版本] {part_type} = {new_ver} (操作前 {current})", flush=True)
    if ok is True:
        print(f"[SUCCESS] {tag}成功 (target={target})", flush=True); return True
    if ok is False:
        print(f"[FAIL] {tag}失败: {e.get('status_reason') if e else '未知'}", flush=True); return False
    if new_ver != current:
        print(f"[SUCCESS?] 平台状态未知，但设备版本已变化 {current} -> {new_ver}，推断{tag}生效", flush=True); return True
    print(f"[UNKNOWN] 平台状态未知且设备版本未变({new_ver})，请稍后复查", flush=True); return None


def do_ble_upgrade(imei, target, current=None, part_type="ECU", verify_timeout=120):
    """平台下发蓝牙升级指令（cmdCode=c:ota, actual_ota_type=2）。
    注意：本命令只完成「平台下发」这一步；之后必须由手机 APP 经 BLE 真正开始刷写
    （device_control.py 在 APP 固件详情/升级页点「开始升级」），平台侧才算完成。

    核验路径（**用 get-upgrade-history，不要用 commands**）：
      commands 查的是「平台→车机(蜂窝)指令日志」，BLE 的 c:ota 走「平台→手机APP」通道，不会落进那里。
      真正的 BLE 任务在 OTA管理→单元升级→升级详情 页面，对应 API 即 get-upgrade-history，
      任务特征 `actual_ota_type=2`，刚下发后 `upgrade_status=-1` 表示「待升级」(等 APP 开始)。"""
    dev, parts = resolve_device(imei)
    sn = dev["sn"]; pk = dev["product_key"]; vmc = dev["vehicle_model_code"]
    if current is None:
        current = parts.get(part_type, {}).get("part_firmware_version")
    print(f"\n=== 平台下发蓝牙升级 {part_type}: {current} -> {target} (IMEI {imei}) ===", flush=True)
    r = send_ble_upgrade(sn, pk, vmc, part_type, target)
    try:
        j = r.json()
    except Exception:
        print(f"[FAIL] 下发响应非 JSON: {r.text[:200]}", flush=True); return False
    if j.get("resultCode") != "1000":
        print(f"[FAIL] 平台下发蓝牙升级失败: {j.get('resultDesc')} code={j.get('resultCode')}", flush=True); return False
    print("[OK] 平台已下发蓝牙升级指令 (cmdCode=c:ota, actual_ota_type=2)", flush=True)

    # 核验：轮询 get-upgrade-history 等 BLE 任务(actual_ota_type=2)出现
    # 注意：待升级态 ota_target_version 字段返回 null，因此匹配按 (actual_ota_type=2 + part_type) + 最新创建 判定
    print(f"[核验] 等待 get-upgrade-history 出现 actual_ota_type=2 的 {part_type} 任务(BLE 任务有 ~1min 异步延迟)...", flush=True)
    send_ts = time.time()
    deadline = send_ts + verify_timeout
    found = None
    while time.time() < deadline:
        h = get_upgrade_history(sn, pk, part_type=part_type, size=15)
        lst = h.get("data", {}).get("list", []) or []
        # 候选: actual_ota_type=2 且 part_type 匹配；按 create_time desc 排序后取首条>=send_ts 的
        cands = [t for t in lst if str(t.get("actual_ota_type")) == "2" and t.get("part_type") == part_type]
        if cands:
            # 优先选 create_time 晚于 send_ts 的（避免与历史 BLE 任务混淆）
            fresh = [t for t in cands if _parse_ts(t.get("create_time") or t.get("createTime") or 0) >= send_ts - 5]
            if fresh:
                found = fresh[0]
            else:
                found = cands[0]  # 兜底：最新 BLE 任务
            break
        time.sleep(5)
    if found:
        st = str(found.get("upgrade_status"))
        st_desc = {-1: "待升级(等APP开始)", 0: "升级中", 1: "升级成功", 2: "升级失败"}.get(int(st) if str(st).lstrip("-").isdigit() else -9, st)
        tv = found.get("ota_target_version") or "?"
        print(f"[OK] 已确认 BLE 升级任务(taskid={found.get('ota_task_result_id')}, target={tv}, status={st}={st_desc}, actual_ota_type=2)", flush=True)
    else:
        print(f"[WARN] {verify_timeout}s 内未在 get-upgrade-history 找到任务（异步延迟可能更长）；可在 OTA管理→单元升级→升级详情 页面手动确认。", flush=True)

    print("[下一步] 平台仅下发指令；需手机 APP 经蓝牙开始刷写：", flush=True)
    print(f"  1) 在 APP 固件详情/升级页点「开始升级」(BLE 推送固件)", flush=True)
    print(f"  2) 任务在 OTA管理→单元升级→升级详情 可见；APP 发起后 status 会从 -1(待升级) 流转", flush=True)
    return True


def do_fota(imei, files, versions, rollback_to=None, part_type="ECU"):
    """一站式工作流：注册缺失包 -> 升级链路 -> 回滚。一次跑完，最少对话轮次。"""
    dev, parts = resolve_device(imei)
    pk = dev["product_key"]; vmc = dev["vehicle_model_code"]; sn = dev["sn"]
    pvm = [[pk, vmc]]
    pn = parts.get(part_type, {}).get("pn")
    part_code = resolve_part_code(pvm, part_type, pn)
    cur = parts.get(part_type, {}).get("part_firmware_version")
    print(f"[设备] SN={sn} PK={pk} 车型={vmc} {part_type}当前={cur} part_code={part_code}", flush=True)

    # 1) 注册缺失的包（已存在则继续，不阻断）
    if files and versions:
        for f, v in zip(files, versions):
            if not os.path.isfile(f):
                print(f"[WARN] 文件不存在跳过: {f}", flush=True); continue
            print(f"\n--- 注册固件包 {v} ({os.path.basename(f)}) ---", flush=True)
            res = add_firmware(f, v, part_code=part_code, model=pvm, firmware_type=part_type,
                               desc=f"自动注册 {v}", desc_en=f"auto {v}")
            if not res.get("ok"):
                print(f"  [INFO] 注册未成功(可能已存在): {res.get('add_response', {}).get('resultDesc')}", flush=True)

    # 2) 升级链路：当前 -> v1 -> v2 ...
    seq = [cur] + list(versions)
    print(f"\n[升级链路] {' -> '.join(seq)}", flush=True)
    for i in range(1, len(seq)):
        do_upgrade(imei, seq[i], seq[i - 1], part_type)

    # 3) 回滚
    if rollback_to:
        print(f"\n[回滚] 回退到 {rollback_to}", flush=True)
        do_upgrade(imei, rollback_to, seq[-1], part_type, rollback=True)
    print("\n=== fota 流程结束 ===", flush=True)


# ---------- CLI ----------
def main():
    p = argparse.ArgumentParser(description="九号 IoT OTA 固件平台 helper")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("connect")
    sub.add_parser("login", help="用 ACCOUNT/PASSWORD 账号密码登录平台，刷新会话 Cookie 并持久化")
    sub.add_parser("part-types")
    m = sub.add_parser("models"); m.add_argument("--part-type", default="ECU")
    q = sub.add_parser("query")
    q.add_argument("--page", type=int, default=1); q.add_argument("--num", type=int, default=10)
    q.add_argument("--level", default=""); q.add_argument("--vehicle-model-code", default="")
    q.add_argument("--type", dest="firmware_type", default=""); q.add_argument("--version", dest="firmware_version", default="")

    a = sub.add_parser("add", help="新增固件包（--imei 可自动解析车型/零部件）")
    a.add_argument("--file", required=True)
    a.add_argument("--version", required=True)
    a.add_argument("--part-code", default=None)
    a.add_argument("--model", default=None)
    a.add_argument("--imei", default=None)
    a.add_argument("--type", dest="firmware_type", default="ECU")
    a.add_argument("--desc", default=""); a.add_argument("--desc-en", dest="desc_en", default="")
    a.add_argument("--level", type=int, default=1)

    qd = sub.add_parser("query-device", help="按 IMEI/SN 查设备+当前版本")
    qd.add_argument("imei")

    dd = sub.add_parser("device-data", help="聚合查询设备全部实时数据(整车/状态/报警/故障/事件/电池/天气/近期在线)")
    dd.add_argument("sn")
    da = sub.add_parser("device-alarm", help="查询报警信息"); da.add_argument("sn")
    dw = sub.add_parser("device-warning", help="查询故障/告警信息(ai/vehicle/warning)"); dw.add_argument("sn")
    de = sub.add_parser("device-event", help="查询事件信息"); de.add_argument("sn")
    db = sub.add_parser("device-bms", help="查询电池(BMS)实时数据"); db.add_argument("sn")
    dbs = sub.add_parser("device-bmslog", help="查询电池日志"); dbs.add_argument("sn")
    dvs = sub.add_parser("device-status", help="查询车辆状态(vehicleStatus)"); dvs.add_argument("sn")
    df = sub.add_parser("device-dataflow", help="查询数据流(默认SOC/车速/电流/电压，--fields覆盖)"); df.add_argument("sn"); df.add_argument("--fields", default="")
    doh = sub.add_parser("device-online-history", help="查询在线状态历史"); doh.add_argument("sn"); doh.add_argument("--hours", type=int, default=24)
    sub.add_parser("download-tasks", help="查询固件下载任务列表(与设备无关)")

    rp = sub.add_parser("resolve-part", help="解析车型零部件的 part_code")
    rp.add_argument("model", help="pk,vmc"); rp.add_argument("--part-type", default="ECU"); rp.add_argument("--pn", default="")

    up = sub.add_parser("upgrade", help="下发升级并轮询校验")
    up.add_argument("imei"); up.add_argument("target"); up.add_argument("current", nargs="?", default=None)
    up.add_argument("--type", dest="part_type", default="ECU")
    rb = sub.add_parser("rollback", help="下发回滚(向更低版本再升级一次)")
    rb.add_argument("imei"); rb.add_argument("target"); rb.add_argument("current", nargs="?", default=None)
    rb.add_argument("--type", dest="part_type", default="ECU")

    st = sub.add_parser("status", help="设备当前版本+最近升级历史")
    st.add_argument("imei"); st.add_argument("--type", dest="part_type", default="ECU")

    cm = sub.add_parser("commands", help="查看平台下发到设备的指令（链路核验）")
    cm.add_argument("imei")
    cm.add_argument("--minutes", type=int, default=10, help="时间窗长度(分钟)，默认10")
    cm.add_argument("--since", type=int, default=None, help="起始 epoch 秒（覆盖 --minutes）")
    cm.add_argument("--until", type=int, default=None, help="结束 epoch 秒")
    cm.add_argument("--watch", type=int, default=None, help="APP设置后用: 轮询等待新指令并跟踪回应, 单位秒")

    fo = sub.add_parser("fota", help="一站式: 注册缺失包+升级链路+回滚")
    fo.add_argument("imei")
    fo.add_argument("--files", default="", help="固件bin路径,逗号分隔(与--versions对应)")
    fo.add_argument("--versions", default="", help="版本号,逗号分隔,如 032E,032F")
    fo.add_argument("--rollback-to", default="", help="回滚目标版本,如 022f")
    fo.add_argument("--type", dest="part_type", default="ECU")

    be = sub.add_parser("ble-upgrade", help="平台下发蓝牙升级指令(c:ota/actual_ota_type=2)，需APP经BLE开始刷写")
    be.add_argument("imei"); be.add_argument("target"); be.add_argument("current", nargs="?", default=None)
    be.add_argument("--type", dest="part_type", default="ECU")

    args = p.parse_args()

    if args.cmd == "connect":
        connect()
    elif args.cmd == "login":
        got = login()
        print(json.dumps({"ok": True, "account": ACCOUNT,
                          "cookies": {k: "***" for k in got}},
                         ensure_ascii=False, indent=2))
    elif args.cmd == "part-types":
        print(json.dumps(get_part_types(), ensure_ascii=False, indent=2))
    elif args.cmd == "models":
        print(json.dumps(get_models(args.part_type), ensure_ascii=False, indent=2))
    elif args.cmd == "query":
        print(json.dumps(query_firmware(args.page, args.num, args.level, args.vehicle_model_code, args.firmware_type, args.firmware_version), ensure_ascii=False, indent=2))
    elif args.cmd == "add":
        if not args.imei and not args.model:
            print("需提供 --model 或 --imei"); sys.exit(1)
        res = add_firmware(args.file, args.version, args.part_code, args.model, args.imei, args.firmware_type, args.desc, args.desc_en, args.level)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif args.cmd == "query-device":
        dev, parts = resolve_device(args.imei)
        print(json.dumps({"device": dev, "parts": parts}, ensure_ascii=False, indent=2))
    elif args.cmd == "device-data":
        print(json.dumps(device_overview(args.sn), ensure_ascii=False, indent=2))
    elif args.cmd == "device-alarm":
        print(json.dumps(rt_query(args.sn, "alarm"), ensure_ascii=False, indent=2))
    elif args.cmd == "device-warning":
        print(json.dumps(rt_query(args.sn, "warning", base="ai/vehicle",
                                 extra={"sn": args.sn, "pageNo": 1, "pageSize": 20}),
                         ensure_ascii=False, indent=2))
    elif args.cmd == "device-event":
        print(json.dumps(rt_query(args.sn, "event"), ensure_ascii=False, indent=2))
    elif args.cmd == "device-bms":
        print(json.dumps(rt_query(args.sn, "bms"), ensure_ascii=False, indent=2))
    elif args.cmd == "device-bmslog":
        print(json.dumps(rt_query(args.sn, "bmsLog"), ensure_ascii=False, indent=2))
    elif args.cmd == "device-status":
        print(json.dumps(rt_query(args.sn, "vehicleStatus"), ensure_ascii=False, indent=2))
    elif args.cmd == "device-dataflow":
        fields = json.loads(args.fields) if args.fields else None
        print(json.dumps(device_dataflow(args.sn, fields), ensure_ascii=False, indent=2))
    elif args.cmd == "device-online-history":
        now = int(time.time() * 1000)
        print(json.dumps(rt_query(args.sn, "onlineStatus", base="historyData",
                                 extra={"startTime": now - args.hours * 3600 * 1000,
                                        "endTime": now}),
                         ensure_ascii=False, indent=2))
    elif args.cmd == "download-tasks":
        print(json.dumps(download_tasks(), ensure_ascii=False, indent=2))
    elif args.cmd == "resolve-part":
        pvm = [[x.strip() for x in args.model.split(",")]]
        codes = require_attribute(pvm, args.part_type)
        pick = resolve_part_code(pvm, args.part_type, args.pn) if args.pn else (max(codes, key=len) if codes else None)
        print(json.dumps({"candidates": codes, "picked": pick}, ensure_ascii=False, indent=2))
    elif args.cmd == "upgrade":
        do_upgrade(args.imei, args.target, args.current, args.part_type)
    elif args.cmd == "rollback":
        do_upgrade(args.imei, args.target, args.current, args.part_type, rollback=True)
    elif args.cmd == "status":
        dev, parts = resolve_device(args.imei)
        print("[当前版本]", json.dumps(get_parts_version(dev["sn"]), ensure_ascii=False))
        try:
            h = get_upgrade_history(dev["product_key"], dev["sn"], args.part_type)
            print("[最近历史]", json.dumps(h.get("data", {}).get("list", [])[:5], ensure_ascii=False))
        except Exception as e:
            print(f"[历史获取失败] {e}")
    elif args.cmd == "fota":
        files = [x.strip() for x in args.files.split(",") if x.strip()]
        versions = [x.strip() for x in args.versions.split(",") if x.strip()]
        do_fota(args.imei, files, versions, args.rollback_to or None, args.part_type)
    elif args.cmd == "ble-upgrade":
        do_ble_upgrade(args.imei, args.target, args.current, args.part_type)
    elif args.cmd == "commands":
        do_commands(args.imei, minutes=args.minutes, since=args.since,
                    until=args.until, watch=args.watch)


if __name__ == "__main__":
    main()
