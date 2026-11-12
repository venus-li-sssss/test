"""Histogram of normalized message patterns inside a time window (count, first-last time, one sample).

Use it on a normal window and an abnormal window, then diff the two outputs.
Counts are only comparable after dividing by window length - pass --rate to print per-second rates.

Usage:
  python -X utf8 window_patterns.py LOG --from 10:52:00 --to 11:02:30 -o normal.txt --rate
  # error scan over the whole log, most frequent first
  python -X utf8 window_patterns.py LOG --grep "ERROR|FAIL|Exception|Traceback|failed|timeout|超时|失败|错误" --top 40
Options: --grep REGEX keep only matching messages, --exclude REGEX drop matching messages.
"""
import argparse
import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from logutil import iter_lines, normalize, utf8_stdout  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('log')
    ap.add_argument('--from', dest='start')
    ap.add_argument('--to', dest='end')
    ap.add_argument('--rate', action='store_true')
    ap.add_argument('--top', type=int, default=0, help='only print the N most frequent patterns')
    ap.add_argument('--grep')
    ap.add_argument('--exclude')
    ap.add_argument('-o')
    a = ap.parse_args()
    if a.o:
        sys.stdout = open(a.o, 'w', encoding='utf-8')
    else:
        utf8_stdout()

    keep = re.compile(a.grep) if a.grep else None
    drop = re.compile(a.exclude) if a.exclude else None
    pats = collections.OrderedDict()
    first = last = None
    total = 0
    day, prev = 0, None
    for _, t, sec, msg, _raw in iter_lines(a.log, a.start, a.end):
        if prev is not None and sec < prev - 3600:
            day += 1
        prev = sec
        sec += 86400 * day
        if (keep and not keep.search(msg)) or (drop and drop.search(msg)):
            continue
        total += 1
        first = sec if first is None else first
        last = sec
        k = normalize(msg)
        e = pats.get(k)
        if e is None:
            pats[k] = [1, t, t, msg.strip()[:200]]
        else:
            e[0] += 1
            e[2] = t
    span = max((last or 0) - (first or 0), 1)
    print('lines=%d patterns=%d span=%.0fs' % (total, len(pats), span))
    items = list(pats.values())
    if a.top:
        items = sorted(items, key=lambda e: -e[0])[:a.top]
    for c, t1, t2, sample in items:
        rate = ' %.3f/s' % (c / span) if a.rate else ''
        print('%7d%s %s-%s %s' % (c, rate, t1, t2, sample))


if __name__ == '__main__':
    main()
