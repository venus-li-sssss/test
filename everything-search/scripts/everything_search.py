#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
everything_search.py - Fast whole-disk file search on Windows via Everything.

Talks to the running Everything index through es.exe (the official IPC command
line client). No GUI is opened, clicked or scraped: es.exe speaks the native
Everything IPC protocol, so results come back in milliseconds.

Output is structured (JSON by default) so an AI agent can consume it directly.

Examples
--------
    # find files by name
    python everything_search.py "partition.bin" -n 10

    # only .fbf firmware packages under D:\\work, newest first
    python everything_search.py "ext:fbf" --path "D:\\work" --sort date-modified --desc

    # folders whose name contains 测试
    python everything_search.py "测试" --folders-only -n 20

    # regex, match against the whole path
    python everything_search.py -r "QDM5\\d\\d.*\\.xlsx" --match-path -n 5

    # how many matches exist (no listing)
    python everything_search.py "ext:log" --path "D:\\work" --count-only

    # plain path list, one per line (easy to pipe into other tools)
    python everything_search.py "*.dll" --format paths
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
BIN_DIR = SKILL_DIR / "bin"
ES_LOCAL = BIN_DIR / "es.exe"
ES_DOWNLOAD_URL = "https://www.voidtools.com/ES-1.1.0.27.zip"

EVERYTHING_CANDIDATES = [
    r"C:\Program Files\Everything\Everything.exe",
    r"C:\Program Files (x86)\Everything\Everything.exe",
]

# es.exe column flag -> normalized key used in our output
COLUMN_FLAGS = {
    "name": "-name",
    "path": "-path-column",
    "fullpath": "-full-path-and-name",
    "size": "-size",
    "extension": "-extension",
    "date_created": "-date-created",
    "date_modified": "-date-modified",
    "date_accessed": "-date-accessed",
    "attributes": "-attributes",
    "run_count": "-run-count",
}

HEADER_MAP = {
    "Filename": "filename",
    "Name": "name",
    "Path": "path",
    "Size": "size",
    "Extension": "extension",
    "Date Created": "date_created",
    "Date Modified": "date_modified",
    "Date Accessed": "date_accessed",
    "Attributes": "attributes",
    "Run Count": "run_count",
}

SORT_NAMES = [
    "name", "path", "size", "extension", "date-created", "date-modified",
    "date-accessed", "attributes", "run-count", "date-recently-changed", "date-run",
]


# --------------------------------------------------------------------------- #
# Chinese / non-ASCII argument repair
# --------------------------------------------------------------------------- #
def repair_mojibake(text: str) -> str:
    """
    Undo "UTF-8 bytes read as a legacy code page" mangling.

    Passing a Chinese query through cmd.exe (code page 936) can hand Python
    mojibake such as '鏃ュ織鎶撳彇' instead of '日志抓取'. Genuine Chinese almost
    never survives the reverse round trip (encode cp936 -> decode utf-8), so a
    *successful* round trip is strong evidence that the text was mangled.
    Correct text fails the round trip and is returned unchanged.
    """
    if not text or not any(ord(c) > 0x7F for c in text):
        return text
    for enc in ("gbk", "cp936", "cp950", "cp932", "latin-1"):
        try:
            fixed = text.encode(enc).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if fixed and fixed != text:
            return fixed
    return text


# --------------------------------------------------------------------------- #
# es.exe acquisition
# --------------------------------------------------------------------------- #
def find_es() -> Path | None:
    """Locate es.exe: skill bin dir first, then PATH."""
    if ES_LOCAL.is_file():
        return ES_LOCAL
    which = shutil_which("es.exe")
    if which:
        return Path(which)
    return None


def shutil_which(name: str) -> str | None:
    from shutil import which
    return which(name)


def download_es(dest: Path = ES_LOCAL, url: str = ES_DOWNLOAD_URL) -> Path:
    """Download the official ES zip from voidtools and extract es.exe."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_zip = Path(tempfile.mkstemp(suffix=".zip")[1])
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "everything-search-skill"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp_zip, "wb") as fh:
            fh.write(resp.read())
        with zipfile.ZipFile(tmp_zip) as zf:
            member = next((n for n in zf.namelist() if n.lower().endswith("es.exe")), None)
            if not member:
                raise RuntimeError(f"es.exe not found inside {url}")
            with zf.open(member) as src, open(dest, "wb") as out:
                out.write(src.read())
    finally:
        try:
            tmp_zip.unlink()
        except OSError:
            pass
    if not dest.is_file():
        raise RuntimeError("es.exe extraction failed")
    return dest


def ensure_es(auto_download: bool = True) -> Path:
    es = find_es()
    if es:
        return es
    if not auto_download:
        raise SystemExit(
            "es.exe (Everything command line client) is missing.\n"
            f"Put es.exe in {BIN_DIR} or run with --auto-download."
        )
    print("[everything-search] es.exe missing, downloading from voidtools...", file=sys.stderr)
    return download_es()


# --------------------------------------------------------------------------- #
# Everything instance handling
# --------------------------------------------------------------------------- #
def find_everything_exe() -> str | None:
    for cand in EVERYTHING_CANDIDATES:
        if os.path.isfile(cand):
            return cand
    return None


def everything_running() -> bool:
    try:
        out = subprocess.run(
            ["tasklist", "/fi", "imagename eq Everything.exe", "/nh"],
            capture_output=True, text=True, timeout=15,
        ).stdout or ""
    except Exception:
        return False
    return "Everything.exe" in out


def start_everything(wait: float = 6.0) -> bool:
    """Fallback: bring the Everything index process up (minimised, never driven)."""
    if everything_running():
        return True
    exe = find_everything_exe()
    if not exe:
        return False
    try:
        subprocess.Popen([exe], cwd=os.path.dirname(exe),
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        return False
    deadline = time.time() + wait
    while time.time() < deadline:
        if everything_running():
            time.sleep(1.5)  # let the index finish loading
            return True
        time.sleep(0.3)
    return False


# --------------------------------------------------------------------------- #
# Query building / execution
# --------------------------------------------------------------------------- #
def _quote(tok: str) -> str:
    """Quote only for values that need it (paths). The query itself is never quoted."""
    if not tok:
        return '""'
    if any(c in tok for c in " \t"):
        return f'"{tok}"'
    return tok


def build_command(es: Path, args, export_path: Path) -> str:
    """
    Build the es.exe command line as a STRING.

    Why a string instead of an argv list: es.exe forwards the quoting of the
    search argument straight through to Everything, and Everything treats a
    quoted search as a literal phrase - which silently disables search
    functions (ext:, size:, dm:), the | operator and space-separated AND.
    Passing the query unquoted keeps the full Everything syntax working.
    Nothing goes through cmd.exe, so | & ^ need no escaping.
    """
    cmd: list[str] = [str(es)]

    if args.instance:
        cmd += ["-instance", _quote(args.instance)]
    if args.timeout:
        cmd += ["-timeout", str(args.timeout)]

    # NOTE: -r/-regex takes the search string as its own argument, so it must be
    # emitted immediately before the query - never in the middle of the switches.
    if args.case:
        cmd.append("-i")
    if args.whole_word:
        cmd.append("-w")
    if args.match_path:
        cmd.append("-p")

    if args.offset:
        cmd += ["-offset", str(args.offset)]
    if args.limit is not None:
        cmd += ["-n", str(args.limit)]

    if args.path:
        cmd += ["-path", _quote(args.path)]
    if args.parent:
        cmd += ["-parent", _quote(args.parent)]

    if args.folders_only:
        cmd.append("/ad")
    elif args.files_only:
        cmd.append("/a-d")

    if args.sort:
        cmd += ["-sort", args.sort]
        cmd.append("-sort-descending" if args.desc else "-sort-ascending")
    elif args.desc:
        cmd.append("-sort-descending")

    # Display columns
    if args.columns:
        wanted = [c.strip().lower().replace("-", "_") for c in args.columns.split(",") if c.strip()]
        # A "path" column only carries the *directory*; without the filename the
        # rows cannot be resolved into full paths (silently yields folder-looking
        # garbage), so pull the name column in as well.
        if "path" in wanted and not ({"name", "fullpath"} & set(wanted)):
            cmd.append("-name")
        for key in wanted:
            if key in COLUMN_FLAGS:
                cmd.append(COLUMN_FLAGS[key])
            elif key in ("dm",):
                cmd.append("-date-modified")
            elif key in ("dc",):
                cmd.append("-date-created")
    else:
        cmd += ["-full-path-and-name", "-size", "-date-modified"]

    cmd += [
        "-date-format", "1",       # ISO-8601
        "-size-format", "1",       # raw bytes
        "-no-digit-grouping",
        "-export-csv", _quote(str(export_path)),
        "-utf8-bom",
    ]

    query = args.query.strip()
    if args.ext:
        exts = ";".join(e.strip().lstrip(".") for e in args.ext.split(",") if e.strip())
        query = f"{query} ext:{exts}".strip()
    if args.raw:
        cmd.append(args.raw)
    if args.regex:
        cmd.append("-r")   # must directly precede the search text
    # query appended verbatim: the user keeps control over Everything syntax
    cmd.append(query)
    return " ".join(cmd)


def parse_export(path: Path, columns_requested: str | None) -> list[dict]:
    if not path.is_file():
        return []
    raw = path.read_bytes()
    if not raw.strip():
        return []
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []
    header = [HEADER_MAP.get(h.strip(), h.strip().lower().replace(" ", "_")) for h in rows[0]]

    def _is_abs(p: str) -> bool:
        return bool(p) and (p[0] in "\\/" or (len(p) > 1 and p[1] == ":"))

    out: list[dict] = []
    for row in rows[1:]:
        if not row or all(not c for c in row):
            continue
        rec = {header[i] if i < len(header) else f"col{i}": (row[i] if i < len(row) else "")
               for i in range(max(len(header), len(row)))}
        item: dict = {}
        # -full-path-and-name puts the whole path under "Filename";
        # -name + -path-column splits it into two columns.
        raw_name = rec.get("filename") or rec.get("name") or ""
        dirpath = rec.get("path") or ""

        if _is_abs(raw_name) or not dirpath:
            full = raw_name
        else:
            full = os.path.join(dirpath, raw_name)
        item["path"] = full
        item["name"] = os.path.basename(full.rstrip("\\/")) if full else ""

        size = rec.get("size", "")
        if size:
            try:
                item["size"] = int(size)
            except ValueError:
                item["size_text"] = size
        else:
            item["size"] = None

        for key in ("date_modified", "date_created", "date_accessed", "attributes",
                    "extension", "run_count"):
            val = rec.get(key)
            if val:
                item[key] = val
        out.append(item)
    return out


def run_es(cmd: str, timeout: float) -> tuple[int, str, str]:
    """Run a pre-built command line string (shell=False -> CreateProcess, no cmd.exe)."""
    proc = subprocess.run(cmd, shell=False, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


# es.exe reports IPC problems on stderr while still exiting 0, so the exit code
# alone is not a reliable failure signal.
IPC_MARKERS = ("ipc window not found", "everything ipc", "is not running",
               "not running", "error 8")


def is_ipc_failure(out: str, err: str) -> bool:
    blob = f"{out} {err}".lower()
    return any(m in blob for m in IPC_MARKERS)


def run_with_autostart(cmd: str, no_autostart: bool, timeout: float = 180) -> tuple[int, str, str]:
    code, out, err = run_es(cmd, timeout)
    if is_ipc_failure(out, err) and not no_autostart:
        if start_everything():
            code, out, err = run_es(cmd, timeout)
    return code, out, err


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Search files on Windows through Everything (IPC, no GUI interaction).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("query", nargs="?", default="",
                   help="Everything search syntax, e.g. 'ext:fbf' or 'partition.bin'")
    p.add_argument("--query-file", help="read the query from a UTF-8 file instead of the "
                                        "command line (immune to console code page mangling)")
    p.add_argument("-n", "--limit", type=int, default=20,
                   help="max results (default 20, use 0 for unlimited)")
    p.add_argument("--offset", type=int, default=0, help="skip first N results")
    p.add_argument("--path", help="only search inside this folder (recursive)")
    p.add_argument("--parent", help="only results whose parent folder is exactly this")
    p.add_argument("--ext", help="comma separated extensions, appended as ext:a;b")

    p.add_argument("-r", "--regex", action="store_true", help="treat query as regex")
    p.add_argument("--case", action="store_true", help="match case")
    p.add_argument("--whole-word", action="store_true", help="match whole words")
    p.add_argument("--match-path", action="store_true", help="match against full path")

    g = p.add_mutually_exclusive_group()
    g.add_argument("--folders-only", action="store_true", help="directories only (/ad)")
    g.add_argument("--files-only", action="store_true", help="files only (/a-d)")

    p.add_argument("--sort", choices=SORT_NAMES, help="sort results")
    p.add_argument("--desc", action="store_true", help="descending order (with --sort)")
    p.add_argument("--columns", help="comma list: name,path,fullpath,size,extension,"
                                    "date_created,date_modified,date_accessed,attributes,run_count")

    p.add_argument("--format", choices=["json", "paths", "tsv", "csv"], default="json",
                   help="output format (default json)")
    p.add_argument("--count-only", action="store_true", help="print only the match count")
    p.add_argument("--timeout", type=int, default=15000,
                   help="wait up to N ms for the Everything database (default 15000)")
    p.add_argument("--instance", help="Everything instance name, if not the default one")
    p.add_argument("--raw", help="extra raw es.exe switches to append verbatim")
    p.add_argument("--auto-download", action="store_true", default=True,
                   help="download es.exe if missing (default on)")
    p.add_argument("--no-auto-start", action="store_true",
                   help="do not try to start Everything.exe when the index is down")
    p.add_argument("--allow-empty", action="store_true",
                   help="allow an empty query (lists the whole index - usually a mistake)")
    p.add_argument("--no-repair", action="store_true",
                   help="do not auto-repair console-code-page mojibake in the query")
    p.add_argument("--debug-command", action="store_true",
                   help="print the exact es.exe command line to stderr")

    args = p.parse_args(argv)

    # Console code page mangling: repair mojibake picked up from cmd.exe.
    if not args.no_repair:
        if args.query_file:
            args.query = Path(args.query_file).read_text(encoding="utf-8-sig").strip()
        args.query = repair_mojibake(args.query)
        args.path = repair_mojibake(args.path) if args.path else args.path
        args.parent = repair_mojibake(args.parent) if args.parent else args.parent
        args.ext = repair_mojibake(args.ext) if args.ext else args.ext

    if not args.query.strip() and not args.allow_empty:
        print(json.dumps({"ok": False, "error": "empty query refused; pass --allow-empty to search everything"},
                         ensure_ascii=False))
        return 2
    if args.limit == 0:
        args.limit = None

    try:
        es = ensure_es(args.auto_download)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"es.exe unavailable: {exc}"}, ensure_ascii=False))
        return 3

    # Pre-flight when a non-default instance is requested: es.exe silently falls
    # back (or returns junk) for a name that does not exist, so verify it first.
    if args.instance:
        vcmd = f"{es} -instance {_quote(args.instance)} -get-everything-version"
        vout, verr = "", ""
        _, vout, verr = run_es(vcmd, 60)
        if (is_ipc_failure(vout, verr) or not vout.strip()) and not args.no_auto_start:
            if start_everything():
                _, vout, verr = run_es(vcmd, 60)
        if is_ipc_failure(vout, verr) or not vout.strip():
            print(json.dumps(
                {"ok": False, "error": f"Everything instance '{args.instance}' is not reachable",
                 "detail": (verr or vout).strip(),
                 "hint": "Check the instance name, or omit --instance <name> to use the default one."},
                ensure_ascii=False))
            return 1

    tmp_dir = tempfile.mkdtemp(prefix="es_q_")
    export_path = Path(tmp_dir) / "out.csv"
    try:
        # count-only uses Everything's native counter (exact, cheap)
        if args.count_only:
            cmd: list[str] = [str(es), "-get-result-count"]
            if args.path:
                cmd += ["-path", _quote(args.path)]
            if args.parent:
                cmd += ["-parent", _quote(args.parent)]
            if args.case:
                cmd.append("-i")
            if args.match_path:
                cmd.append("-p")
            if args.folders_only:
                cmd.append("/ad")
            elif args.files_only:
                cmd.append("/a-d")
            query = args.query.strip()
            if args.ext:
                exts = ";".join(e.strip().lstrip(".") for e in args.ext.split(",") if e.strip())
                query = f"{query} ext:{exts}".strip()
            if args.raw:
                cmd.append(args.raw)
            if args.regex:
                cmd.append("-r")   # must directly precede the search text
            cmd.append(query)
            code, out, err = run_with_autostart(" ".join(cmd), args.no_auto_start, 120)
            if is_ipc_failure(out, err) or (code != 0 and not "".join(ch for ch in out if ch.isdigit())):
                print(json.dumps(
                    {"ok": False, "code": code, "error": (err or out).strip() or "es.exe failed",
                     "hint": "Everything is not reachable. Start it (or drop --no-auto-start) "
                             "and check the instance name."},
                    ensure_ascii=False))
                return 1
            digits = "".join(ch for ch in out if ch.isdigit())
            print(json.dumps({"ok": True, "query": args.query, "count": int(digits or 0)},
                             ensure_ascii=False))
            return 0

        cmd = build_command(es, args, export_path)
        if args.debug_command:
            print(f"[es] {cmd}", file=sys.stderr)
        code, out, err = run_with_autostart(cmd, args.no_auto_start)

        if (is_ipc_failure(out, err) or code != 0) and not export_path.exists():
            print(json.dumps(
                {"ok": False, "code": code, "error": (err or out).strip() or "es.exe failed",
                 "hint": "Make sure Everything is running and its index is loaded."},
                ensure_ascii=False))
            return 1

        results = parse_export(export_path, args.columns)

        if args.format == "paths":
            for item in results:
                print(item["path"])
            return 0
        if args.format == "tsv":
            cols = ["path", "size", "date_modified"]
            print("\t".join(cols))
            for item in results:
                print("\t".join(str(item.get(c) or "") for c in cols))
            return 0
        if args.format == "csv":
            cols = ["path", "size", "date_modified"]
            w = csv.writer(sys.stdout, lineterminator="\n")
            w.writerow(cols)
            for item in results:
                w.writerow([item.get(c) or "" for c in cols])
            return 0

        payload = {
            "ok": True,
            "query": args.query,
            "count": len(results),
            "limited": args.limit is not None and len(results) >= (args.limit or 0),
            "results": results,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    finally:
        try:
            export_path.unlink()
        except OSError:
            pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
