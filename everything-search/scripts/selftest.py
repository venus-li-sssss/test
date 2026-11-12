#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
selftest.py - regression checks for everything-search.

Every case below maps to a bug that was actually hit while building this skill,
so a green run means those traps are still avoided:

  * quoted search text silently disables ext:/size:/dm:, | and space-AND
  * -r must immediately precede the search text
  * -name + -path-column CSVs have no "Filename" column
  * es.exe exits 0 on IPC failures and reports them on stderr only
  * a bogus -instance silently returns 0 results

Run:  python selftest.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "everything_search.py"

PASS, FAIL = [], []


def run(*argv: str) -> tuple[int, dict | list | None, str]:
    proc = subprocess.run([sys.executable, str(SCRIPT), *argv],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (proc.stdout or "").strip()
    try:
        payload = json.loads(out) if out.startswith(("{", "[")) else None
    except json.JSONDecodeError:
        payload = None
    return proc.returncode, payload, out


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASS.append(name)
        print(f"[PASS] {name}")
    else:
        FAIL.append(name)
        print(f"[FAIL] {name}  {detail}")


def main() -> int:
    # 1 - plain filename search returns structured rows
    rc, data, raw = run("partition.bin", "-n", "3")
    check("json schema", isinstance(data, dict) and data.get("ok") is True
          and isinstance(data.get("results"), list), raw[:200])
    if isinstance(data, dict) and data.get("results"):
        row = data["results"][0]
        check("row fields", {"path", "name", "size"} <= set(row), str(row))
        check("absolute path", len(row["path"]) > 2 and row["path"][1] == ":", row["path"])

    # 2 - search functions work (regression: quoted query killed them)
    rc, data, raw = run("ext:bin", "--count-only")
    check("ext: function", isinstance(data, dict) and data.get("count", 0) > 0, raw[:200])

    # 3 - space separated AND (regression: quoted query made it a literal phrase)
    rc, data, raw = run("partition bin", "-n", "2")
    check("space AND", isinstance(data, dict) and data.get("count", 0) > 0, raw[:200])

    # 4 - --ext shortcut
    rc, data, raw = run("customer_app", "--ext", "bin,mbn", "-n", "3")
    check("--ext shortcut", isinstance(data, dict) and data.get("count", 0) > 0, raw[:200])

    # 5 - regex (regression: -r must sit right before the query)
    rc, data, raw = run("QDM5[0-9][0-9]", "-r", "--count-only")
    check("regex via -r", isinstance(data, dict) and data.get("count", 0) > 0, raw[:200])

    # 6 - OR operator (regression: quoted query made | literal)
    rc, data, raw = run("ext:fbf|ext:mbn", "--count-only")
    check("OR operator", isinstance(data, dict) and data.get("count", 0) > 0, raw[:200])

    # 7 - size search function
    rc, data, raw = run("ext:zip size:>100mb", "--count-only")
    check("size: function", isinstance(data, dict) and data.get("count", 0) > 0, raw[:200])

    # 8 - -name + -path-column columns (regression: empty paths)
    rc, data, raw = run("QDM562", "--folders-only", "-n", "3", "--columns", "name,path")
    ok = (isinstance(data, dict) and data.get("results")
          and all(r["path"] for r in data["results"]))
    check("name+path columns", bool(ok), raw[:300])

    # 9 - path filter containing a space
    rc, data, raw = run("spliter", "--path", r"D:\QDM505 tool", "-n", "2")
    check("path with space", isinstance(data, dict) and data.get("count", 0) > 0, raw[:200])

    # 10 - sort by size descending
    rc, data, raw = run("ext:zip", "--files-only", "--sort", "size", "--desc", "-n", "5")
    sizes = [r.get("size") or 0 for r in (data or {}).get("results", [])]
    check("sort size desc", len(sizes) >= 2 and sizes == sorted(sizes, reverse=True), str(sizes))

    # 11 - paths output format
    rc, data, raw = run("partition.bin", "-n", "2", "--format", "paths")
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    check("paths format", data is None and lines and all(ln.strip() for ln in lines), raw[:200])

    # 12 - empty query is refused
    rc, data, raw = run("   ")
    check("empty query refused", isinstance(data, dict) and data.get("ok") is False, raw[:200])

    # 13 - bogus instance fails loudly (regression: silent 0 results)
    rc, data, raw = run("foo", "--instance", "definitely_not_an_instance", "--no-auto-start")
    check("bad instance errors", isinstance(data, dict) and data.get("ok") is False, raw[:200])

    # 14 - offset paging does not repeat the first page
    rc, d1, _ = run("ext:log", "-n", "3", "--sort", "size", "--desc")
    rc, d2, _ = run("ext:log", "-n", "3", "--offset", "3", "--sort", "size", "--desc")
    p1 = [r["path"] for r in (d1 or {}).get("results", [])]
    p2 = [r["path"] for r in (d2 or {}).get("results", [])]
    check("offset paging", p1 and p2 and not (set(p1) & set(p2)), f"{p1[:1]} vs {p2[:1]}")

    # 15 - zero-result query stays ok:true
    rc, data, raw = run("zzz_no_such_file_qqq123")
    check("zero results ok", isinstance(data, dict) and data.get("ok") is True
          and data.get("count") == 0, raw[:200])

    # 16 - --files-only must not return directories (regression: /a-d ignored)
    rc, data, raw = run("日志抓取", "--files-only", "-n", "5")
    paths = [r["path"] for r in (data or {}).get("results", [])]
    check("files-only has no dirs", bool(paths) and not any(p.endswith("\\") for p in paths),
          str(paths[:3]))

    # 17 - path column without name must still resolve full paths
    #      (regression: -path-column alone produced folder-looking rows)
    rc, data, raw = run("partition.bin", "-n", "3", "--columns", "path,size,dm")
    paths = [r["path"] for r in (data or {}).get("results", [])]
    check("path column resolves", bool(paths)
          and all(os.path.isfile(p) for p in paths if os.path.exists(p))
          and not any(p.endswith("\\") for p in paths), str(paths[:3]))

    # 18 - console code page mojibake is auto-repaired
    mojibake = "日志抓取".encode("utf-8").decode("gbk")  # what cmd.exe hands us
    rc, data, raw = run(mojibake, "--count-only")
    check("mojibake repaired", isinstance(data, dict) and data.get("count", 0) > 0, raw[:200])

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("failing: " + ", ".join(FAIL))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
