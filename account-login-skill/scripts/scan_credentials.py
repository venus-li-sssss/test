#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""交付前自检：扫一遍 skill 目录，看有没有把账号/凭证/真实数据带进仓库。

用法：
    python scan_credentials.py <skill目录> [--all]

退出码：0 干净 · 1 发现疑似凭证
"""
import argparse
import os
import re
import sys

def _init_stdout():
    """Windows 控制台是 GBK 时用 GBK 输出，避免中文乱码。"""
    enc = os.environ.get('OUTPUT_ENCODING')
    if not enc and sys.platform == 'win32':
        try:
            import ctypes
            if ctypes.windll.kernel32.GetConsoleOutputCP() == 936:
                enc = 'gbk'
        except Exception:
            pass
    if enc:
        for st in (sys.stdout, sys.stderr):
            try:
                st.reconfigure(encoding=enc, errors='replace')
            except Exception:
                pass


_init_stdout()

TEXT_EXT = {'.md', '.py', '.ps1', '.bat', '.sh', '.json', '.yaml', '.yml',
            '.txt', '.cfg', '.ini', '.toml', '.js', '.ts', '.html', '.xml', '.csv'}

# 占位符/示例白名单（整段命中才放过）—— 注意别把普通字母数字串当占位符，
# 否则真实 token / 手机号会被漏掉（踩过）。
PLACEHOLDERS = re.compile(
    r'^<[^>]*>$'                      # <userId>、<your-token>
    r'|example\.(com|org|net)'        # xxx@example.com
    r'|(XXXX|xxxx|\*\*\*|\.\.\.)'   # bearerXXXX、*** ...
    r'|^(demo|test|placeholder|your|change_?me)$',
    re.I)

PATTERNS = [
    # (名字, 正则, 置信度)
    ('邮箱地址', r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', 'med'),
    ('Bearer token', r'bearer[0-9a-fA-F\-]{16,}', 'high'),
    ('UUID token', r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', 'med'),
    ('GitHub token', r'gh[pousr]_[A-Za-z0-9]{20,}', 'high'),
    ('OpenAI/AK 风格 key', r'(sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})', 'high'),
    ('password 字面量', r'password\s*[:=]\s*[\'"][^\'"\s]{4,}[\'"]', 'high'),
    ('secret 字面量', r'\b(secret|api_?key|token|passwd)\s*[:=]\s*[\'"][^\'"\s]{8,}[\'"]', 'high'),
    ('Cookie 串', r'(quectel_token|sessionid|JSESSIONID|cf_clearance)\s*=\s*[A-Za-z0-9\-_.%]{8,}', 'high'),
    ('中国大陆手机号', r'(?<!\d)1[3-9]\d{9}(?!\d)', 'med'),
    ('userId 字面量', r'["\']?userId["\']?\s*:\s*["\']?\d+', 'med'),
    ('硬编码账号名', r'"username"\s*:\s*"(?!<)[^"]{2,}"', 'med'),
]


def iter_files(root, include_all=False):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in ('__pycache__', '.git', 'node_modules', '.venv')]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if not include_all and ext not in TEXT_EXT:
                continue
            yield os.path.join(dirpath, fn)


def scan(root, include_all=False):
    findings = []
    for path in iter_files(root, include_all):
        try:
            with open(path, encoding='utf-8', errors='ignore') as f:
                for lineno, line in enumerate(f, 1):
                    if len(line) > 4000:      # 压缩过的 JS/bundle 不扫
                        continue
                    for name, pat, level in PATTERNS:
                        for m in re.finditer(pat, line):
                            hit = m.group(0)
                            if PLACEHOLDERS.search(hit):
                                continue
                            findings.append((level, name, os.path.relpath(path, root),
                                             lineno, hit[:80]))
        except OSError as e:
            print('跳过 %s: %s' % (path, e), file=sys.stderr)
    return findings


def main():
    ap = argparse.ArgumentParser(description='交付前扫凭证')
    ap.add_argument('path', nargs='?', default='.')
    ap.add_argument('--all', action='store_true', help='连二进制一起扫（含大文件，慢）')
    a = ap.parse_args()
    if not os.path.isdir(a.path):
        sys.exit('目录不存在：%s' % a.path)

    fs = scan(a.path, a.all)
    if not fs:
        print('干净：没发现账号 / 凭证 / 真实数据。')
        return 0
    high = [f for f in fs if f[0] == 'high']
    med = [f for f in fs if f[0] == 'med']
    for tag, group in (('高危', high), ('待确认', med)):
        if not group:
            continue
        print('\n[%s] %d 处' % (tag, len(group)))
        for level, name, path, lineno, hit in group:
            print('  %-14s %s:%d  %s' % (name, path, lineno, hit))
    print('\n结论：%s' % ('有高危项，**不要上传**' if high else '只有待确认项，人工看一眼再传'))
    return 1 if high else 1


if __name__ == '__main__':
    sys.exit(main())
