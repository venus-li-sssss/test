"""Count regex matches per time bucket across a whole log -> find the change point (step vs gradual, persistent vs intermittent).

Usage:
  python -X utf8 bucket_count.py LOG --step 600 \
      --pat "write=IAP write" --pat "resend=uart_reSend_iapData" -o buckets.txt
  # derived ratio column: --ratio "write/resend"
Options:
  --step   bucket size in seconds (default 60)
  --pat    NAME=REGEX, repeatable (searched in message text)
  --ratio  A/B, adds A/B column
  --from/--to   optional window; omit to scan everything
Time-only logs that cross midnight are bucketed with a day counter (d0, d1, ...).
"""
import argparse
import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from logutil import iter_lines, utf8_stdout  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('log')
    ap.add_argument('--step', type=int, default=60)
    ap.add_argument('--pat', action='append', required=True)
    ap.add_argument('--ratio')
    ap.add_argument('--from', dest='start')
    ap.add_argument('--to', dest='end')
    ap.add_argument('-o')
    a = ap.parse_args()
    if a.o:
        sys.stdout = open(a.o, 'w', encoding='utf-8')
    else:
        utf8_stdout()

    pats = []
    for p in a.pat:
        name, _, rx = p.partition('=')
        pats.append((name, re.compile(rx)))
    names = [n for n, _ in pats]

    buckets = collections.OrderedDict()
    day, prev = 0, -1.0
    for d, t, sec, msg, _raw in iter_lines(a.log, a.start, a.end):
        if sec < prev - 3600:
            day += 1
        prev = sec
        k = (d or 'd%d' % day, int(sec // a.step) * a.step)
        row = buckets.setdefault(k, collections.Counter())
        for n, rx in pats:
            if rx.search(msg):
                row[n] += 1

    for (d, s), row in buckets.items():
        line = '%s %02d:%02d:%02d ' % (d, s // 3600, s // 60 % 60, s % 60) + ' '.join('%s=%d' % (n, row[n]) for n in names)
        if a.ratio:
            x, y = a.ratio.split('/')
            line += ' %s/%s=%.2f' % (x, y, row[x] / row[y] if row[y] else 0.0)
        print(line)


if __name__ == '__main__':
    main()
