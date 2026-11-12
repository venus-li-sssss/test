"""Dump raw lines of a time window (optionally dropping noisy lines) to a small UTF-8 file for reading.

Usage:
  python -X utf8 raw_window.py LOG --from 17:30:00 --to 17:30:05 --exclude "IAP size|IAP write" -o w.txt
Options:
  --exclude  regex of lines to drop     --include  regex of lines to keep
  --width    truncate each line (default 240)
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from logutil import iter_lines, utf8_stdout  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('log')
    ap.add_argument('--from', dest='start')
    ap.add_argument('--to', dest='end')
    ap.add_argument('--exclude')
    ap.add_argument('--include')
    ap.add_argument('--width', type=int, default=240)
    ap.add_argument('-o')
    a = ap.parse_args()
    if a.o:
        sys.stdout = open(a.o, 'w', encoding='utf-8')
    else:
        utf8_stdout()
    ex = re.compile(a.exclude) if a.exclude else None
    inc = re.compile(a.include) if a.include else None
    for _d, _t, _s, _msg, raw in iter_lines(a.log, a.start, a.end):
        if ex and ex.search(raw):
            continue
        if inc and not inc.search(raw):
            continue
        print(raw[:a.width])


if __name__ == '__main__':
    main()
