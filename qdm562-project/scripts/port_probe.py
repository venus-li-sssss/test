# -*- coding: utf-8 -*-
"""QDM562 上位机升级压测 · 端口自检

用途：换 USB 口 / 换机器 / 换治具后，自动认一遍：
  1) AT 口、DIAG 口、设备日志口（MI05）、上位机口（FTDI）
  2) 上位机口发送方向是否通（设备日志里出现 "_5AA5 Receive"）
  3) 上位机口接收方向是否通（能否读到 5A A5 应答）

打印结论后按提示改 device.yaml 的 COM / gnss_com / gnss_capture_port。
只写一帧版本查询指令，不会触发升级。
"""
import sys
import io
import time
import threading

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import serial
import serial.tools.list_ports

VERSION_FRAME = bytes([0x5A, 0xA5, 0x01, 0x3E, 0x09, 0x01, 0x02, 0x02, 0xB2, 0xFF])


def list_ports():
    return list(serial.tools.list_ports.comports())


def classify(port):
    desc = (port.description or "").lower()
    hwid = (port.hwid or "").upper()
    if "diag" in desc:
        return "DIAG"
    if "at port" in desc or " quectel usb at" in desc:
        return "AT"
    if "mi05" in desc or "mi_05" in hwid:
        return "LOG"
    if "0403" in hwid and "6001" in hwid:
        return "FTDI"
    if "quectel" in desc:
        return "OTHER-QUECTEL"
    return "OTHER"


def log_watcher(port_name, result, stop_flag, seconds=12):
    """被动监听设备日志口，看是否出现 5AA5 Receive（证明上位机口发出去的帧到设备了）"""
    try:
        ser = serial.Serial(port_name, 115200, timeout=0.2)
    except Exception as error:
        result["error"] = "打不开 {}: {}".format(port_name, error)
        return
    t0 = time.time()
    buf = ""
    while time.time() - t0 < seconds and not stop_flag.is_set():
        data = ser.read(1024)
        if data:
            buf += data.decode("utf-8", "replace")
            if "5AA5 Receive" in buf or "5aa5 receive" in buf.lower():
                result["seen"] = True
                idx = buf.lower().find("5aa5 receive")
                result["line"] = buf[max(0, idx - 40):idx + 120].replace("\r", "").replace("\n", " ")
                break
    ser.close()


def probe_upper(port_name):
    """向上位机候选口写一帧，同时监听日志口 + 自己读应答"""
    out = {"send_ok": False, "recv_ok": False, "recv_bytes": 0,
           "log_seen": False, "log_line": "", "error": ""}
    log_port = PROBE.get("LOG")
    stop_flag = threading.Event()
    log_res = {}
    th = None
    if log_port and log_port != port_name:
        th = threading.Thread(target=log_watcher, args=(log_port, log_res, stop_flag, 14), daemon=True)
        th.start()
        time.sleep(1.5)
    try:
        ser = serial.Serial(port_name, 115200, timeout=0.2)
    except Exception as error:
        out["error"] = "打不开 {}: {}".format(port_name, error)
        stop_flag.set()
        return out
    try:
        ser.reset_input_buffer()
        for _ in range(2):
            ser.write(VERSION_FRAME)
            ser.flush()
            time.sleep(1.0)
        t0 = time.time()
        while time.time() - t0 < 12:
            data = ser.read(256)
            if data:
                out["recv_bytes"] += len(data)
                if data[:2] == b"\x5a\xa5":
                    out["recv_ok"] = True
                    break
    except Exception as error:
        out["error"] = "读写异常: {}".format(error)
    finally:
        ser.close()
    if th:
        th.join(timeout=16)
    out["log_seen"] = bool(log_res.get("seen"))
    out["log_line"] = log_res.get("line", "")
    if log_res.get("error"):
        out["error"] = out["error"] or log_res["error"]
    out["send_ok"] = out["log_seen"]
    return out


def main():
    ports = list_ports()
    print("=== 本机串口 ===")
    if not ports:
        print("没有检测到任何串口，先查 USB 线 / 驱动")
        return 1
    kinds = {}
    for p in ports:
        kind = classify(p)
        kinds.setdefault(kind, []).append(p.device)
        print("  {:<8} {:<45} {}".format(p.device, (p.description or "")[:45], p.hwid or ""))
    print()

    PROBE.update({k: (v[0] if v else None) for k, v in kinds.items()})
    print("识别结果: AT={AT} DIAG={DIAG} LOG={LOG} FTDI={FTDI} 其它={OTHER}".format(
        AT=PROBE.get("AT"), DIAG=PROBE.get("DIAG"), LOG=PROBE.get("LOG"),
        FTDI=PROBE.get("FTDI"), OTHER=PROBE.get("OTHER")))
    print()

    candidates = [c for c in (PROBE.get("FTDI"), PROBE.get("OTHER")) if c]
    if not candidates:
        print("没找到上位机口候选（FTDI / 其它）")
        return 1

    best = None
    for cand in candidates:
        print("--- 探测上位机候选 {} ---".format(cand))
        res = probe_upper(cand)
        print("  发送方向(设备日志收到 5AA5): {}".format("通" if res["send_ok"] else "未确认"))
        if res["log_line"]:
            print("    设备侧: {}".format(res["log_line"][:130]))
        print("  接收方向(读到应答)      : {} ({} 字节)".format(
            "通" if res["recv_ok"] else "未通", res["recv_bytes"]))
        if res["error"]:
            print("    异常: {}".format(res["error"]))
        if res["send_ok"] and (best is None or res["recv_ok"]):
            best = cand
        if res["send_ok"] and res["recv_ok"]:
            break
        print()

    print("=== 结论 ===")
    if best:
        print("上位机口 = {}".format(best))
        print("改 device.yaml:  COM: {}".format(best))
    else:
        print("没有找到能确认发送方向的上位机口；请检查 FTDI 接线（TX/RX/GND）")
    if PROBE.get("LOG"):
        print("GNSS 日志口 = {}（改 device.yaml: gnss_com / gnss_capture_port）".format(PROBE["LOG"]))
    else:
        print("没认出设备日志口（Quectel USB MI05），GNSS 版本会读不到")
    print()
    print("提示: 接收方向不通时，先用上位机 GUI 手动开串口发一次版本帧，")
    print("     看 GUI「传输记录」里有没有 Rx；有 Rx 说明是脚本侧问题，没有就是接线问题。")
    return 0


if __name__ == "__main__":
    PROBE = {}
    sys.exit(main())
