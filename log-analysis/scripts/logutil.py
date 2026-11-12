"""Shared helpers: stream big logs, parse timestamps, filter by time window."""
import io
import re
import sys

# [2026-11-06 10:52:04.112443] msg   |   [10:52:01.524] msg   |   2026-11-06 10:52:04,112 msg
TS_RE = re.compile(
    r'^\[?(?:(?P<date>\d{4}-\d\d-\d\d)[ T])?(?P<time>\d\d:\d\d:\d\d)(?:[.,](?P<frac>\d+))?\]?\s?(?P<msg>.*)')


def utf8_stdout():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def to_sec(t, frac=None):
    h, m, s = int(t[:2]), int(t[3:5]), int(t[6:8])
    return h * 3600 + m * 60 + s + (float('0.' + frac) if frac else 0.0)


def split_bound(text):
    """'2026-11-06 10:52:00' or '10:52:00' -> (date or None, 'HH:MM:SS')."""
    if text is None:
        return None, None
    parts = text.strip().split(' ')
    if len(parts) == 2:
        return parts[0], parts[1]
    return None, parts[0]


def iter_lines(path, start=None, end=None):
    """Yield (date, time, seconds_of_day, msg, raw) for timestamped lines inside [start, end].

    Logs are read sequentially and never loaded whole. Lines without a timestamp are skipped.
    Without dates in bounds the window is matched on time-of-day: it starts at the first line
    >= start and stops at the first later line > end (works for logs crossing midnight).
    """
    sd, st = split_bound(start)
    ed, et = split_bound(end)
    started = start is None
    with open(path, encoding='utf-8', errors='ignore') as fh:
        for raw in fh:
            m = TS_RE.match(raw)
            if not m:
                continue
            d, t = m.group('date'), m.group('time')
            sec = to_sec(t, m.group('frac'))
            key = (d + ' ' + t) if d else t
            lo = (sd + ' ' + st) if (sd and d) else st
            hi = (ed + ' ' + et) if (ed and d) else et
            if not started:
                if lo is None or (key if len(lo) > 8 and d else t) >= lo:
                    started = True
                else:
                    continue
            if hi is not None and (key if len(hi) > 8 and d else t) > hi:
                return
            yield d, t, sec, m.group('msg'), raw.rstrip('\n')


NUM_RE = re.compile(r'0x[0-9A-Fa-f]+|\b(?:[0-9A-Fa-f]{2} )+[0-9A-Fa-f]{2}\b|\d+')


def normalize(msg, width=110):
    """Replace numbers / hex dumps with '#', so repeated messages collapse to one pattern."""
    return NUM_RE.sub('#', msg)[:width]
