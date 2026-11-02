# -*- coding: utf-8 -*-
"""NMEA 解析核心（自包含）。

支持：
  1) 纯 NMEA 文本（可带机头信息行，如 Unicore LC29HBA/UC6228、Quectel QDM559 输出）
  2) 带本地时间戳前缀的 NMEA，形如 [2026-09-24_16:03:16:623]$GNRMC,...

对外：
  parse(path)        -> (rmc, gga)
  build_epochs(rmc, gga) -> [ {utc, local, wall, lat, lon, alt, sats, hdop, fix, sog_kn, sog_kmh} ]
  haversine(lat1,lon1,lat2,lon2) -> 米
"""
import datetime
import math
import re

RMC_RE = re.compile(
    r"\$G[NPLEABQ]?RMC,(\d{6}(?:\.\d+)?),([AV]),"
    r"(\d{2})(\d{2}\.\d+),([NS]),"
    r"(\d{3})(\d{2}\.\d+),([EW]),"
    r"([\d.]*),([\d.]*),(\d{6})"
)
GGA_RE = re.compile(
    r"\$G[NPLEABQ]?GGA,(\d{6}(?:\.\d+)?),"
    r"(\d{2})(\d{2}\.\d+),([NS]),"
    r"(\d{3})(\d{2}\.\d+),([EW]),"
    r"(\d),(\d*),([\d.]*),(-?[\d.]*),M"
)
TS_RE = re.compile(r"^\[(\d{4})-(\d{2})-(\d{2})_(\d{2}):(\d{2}):(\d{2})[:.](\d{3})\]")

FIXQ = {0: "无效", 1: "单点定位(GPS)", 2: "差分(DGPS)", 3: "PPS", 4: "RTK固定",
        5: "RTK浮动", 6: "估测", 7: "手动", 8: "模拟"}


def dm_to_deg(dm, hemi):
    v = float(dm)
    deg = int(v // 100)
    val = deg + (v - deg * 100) / 60.0
    return -val if hemi in ("S", "W") else val


def haversine(lat1, lon1, lat2, lon2):
    R = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def parse(path):
    rmc, gga = [], {}
    with open(path, "rb") as f:
        data = f.read()
    text = data.decode("utf-8", errors="ignore")
    if text.count("$") < 10:
        text = data.decode("gbk", errors="ignore")

    cur_local = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = TS_RE.match(line)
        if m:
            try:
                cur_local = datetime.datetime(
                    int(m.group(1)), int(m.group(2)), int(m.group(3)),
                    int(m.group(4)), int(m.group(5)), int(m.group(6)), int(m.group(7)) * 1000)
            except ValueError:
                cur_local = None
            line = line[m.end():].strip()
        if not line.startswith("$"):
            continue
        m = RMC_RE.match(line)
        if m:
            rmc.append({
                "time": m.group(1), "status": m.group(2),
                "lat": dm_to_deg(m.group(3) + m.group(4), m.group(5)),
                "lon": dm_to_deg(m.group(6) + m.group(7), m.group(8)),
                "sog": float(m.group(9)) if m.group(9) else 0.0,
                "date": m.group(11), "local": cur_local,
            })
            continue
        m = GGA_RE.match(line)
        if m:
            gga[m.group(1)] = {
                "lat": dm_to_deg(m.group(2) + m.group(3), m.group(4)),
                "lon": dm_to_deg(m.group(5) + m.group(6), m.group(7)),
                "fix": int(m.group(8)),
                "sats": int(m.group(9)) if m.group(9) else 0,
                "hdop": float(m.group(10)) if m.group(10) else 0.0,
                "alt": float(m.group(11)) if m.group(11) not in ("", "-") else 0.0,
            }
    return rmc, gga


def build_epochs(rmc, gga):
    eps, seen = [], set()
    for r in rmc:
        if r["status"] != "A" or r["time"] in seen:
            continue
        seen.add(r["time"])
        g = gga.get(r["time"], {})
        lat, lon = r["lat"], r["lon"]
        if abs(lat) < 1e-9 and abs(lon) < 1e-9:
            lat, lon = g.get("lat"), g.get("lon")
        if lat is None or lon is None:
            continue
        hh, mm = int(r["time"][0:2]), int(r["time"][2:4])
        ss = float(r["time"][4:])
        d = r["date"]
        try:
            dt_utc = datetime.datetime(2000 + int(d[4:6]), int(d[2:4]), int(d[0:2]),
                                       hh, mm, int(ss), int(round((ss - int(ss)) * 1e6)))
        except ValueError:
            dt_utc = None
        eps.append({
            "utc": dt_utc,
            "local": dt_utc + datetime.timedelta(hours=8) if dt_utc else None,
            "wall": r.get("local"),
            "lat": lat, "lon": lon,
            "alt": g.get("alt", 0.0), "sats": g.get("sats", 0),
            "hdop": g.get("hdop", 0.0), "fix": g.get("fix", 0),
            "sog_kn": r["sog"], "sog_kmh": r["sog"] * 1.852,
        })
    eps.sort(key=lambda e: (e["utc"] or e["wall"] or datetime.datetime.min))
    return eps


if __name__ == "__main__":
    import sys
    eps = build_epochs(*parse(sys.argv[1]))
    print("点数", len(eps))
    if eps:
        print("起", eps[0]["local"], "止", eps[-1]["local"])
