"""Per-round summary of a controller/script log (one line per round), or the de-duplicated flow of one round.

Usage:
  python -X utf8 run_summary.py LOG                      # one line per round
  python -X utf8 run_summary.py LOG --detail 34          # flow of round 34, polling lines collapsed
Options:
  --marker  regex whose 1st group is the round number      (default: run_times:(\\d+))
  --poll    regex for polling lines; groups joined = state (default: 等待[^,]*,当前状态为(\\S+))
  --result  regex marking verdict lines shown in summary   (default: 成功|失败|超时|fail|FAIL|timeout|异常|错误|重试)
  -o FILE   write output (UTF-8) to FILE instead of stdout
"""
import argparse
import collections
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from logutil import TS_RE, utf8_stdout  # noqa: E402


def parse_dt(date, time, frac):
    return datetime.strptime('%s %s.%s' % (date, time, frac or '0'), '%Y-%m-%d %H:%M:%S.%f')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('log')
    ap.add_argument('--marker', default=r'run_times:(\d+)')
    ap.add_argument('--poll', default=r'等待[^,]*,当前状态为(\S+)')
    ap.add_argument('--result', default=r'成功|失败|超时|fail|FAIL|timeout|异常|错误|重试')
    ap.add_argument('--detail', type=int)
    ap.add_argument('-o')
    a = ap.parse_args()
    if a.o:
        sys.stdout = open(a.o, 'w', encoding='utf-8')
    else:
        utf8_stdout()
    marker, poll, result = re.compile(a.marker), re.compile(a.poll), re.compile(a.result)

    runs = collections.OrderedDict()
    cur = None
    with open(a.log, encoding='utf-8', errors='ignore') as fh:
        for raw in fh:
            m = TS_RE.match(raw)
            if not m or not m.group('date'):
                continue
            ts = parse_dt(m.group('date'), m.group('time'), m.group('frac'))
            msg = m.group('msg').strip()
            mk = marker.search(msg)
            if mk:
                cur = int(mk.group(1))
                runs[cur] = {'start': ts, 'end': ts, 'poll': collections.Counter(), 'lines': []}
                continue
            if cur is None:
                continue
            r = runs[cur]
            r['end'] = ts
            p = poll.search(msg)
            if p:
                state = p.group(1) if p.groups() else p.group(0)
                r['poll'][state] += 1
                r['lines'].append(('P', ts, state, msg[:60]))
            else:
                r['lines'].append(('L', ts, msg[:220], ''))

    if a.detail is not None:
        prev = None
        for kind, ts, x, y in runs[a.detail]['lines']:
            if kind == 'P':
                if x == prev:
                    continue
                prev = x
                print(ts.strftime('%H:%M:%S.%f')[:-3], '[poll]', y)
            else:
                prev = None
                print(ts.strftime('%H:%M:%S.%f')[:-3], x)
        return

    print('rounds:', len(runs))
    for k, r in runs.items():
        dur = (r['end'] - r['start']).total_seconds()
        verdicts = [x for kd, _, x, _ in r['lines'] if kd == 'L' and result.search(x)]
        print('%s start=%s dur=%ds polls=%s | %s' % (
            k, r['start'].strftime('%m-%d %H:%M:%S'), dur, dict(r['poll']),
            ' || '.join(v[:80] for v in verdicts[-3:])))


if __name__ == '__main__':
    main()
