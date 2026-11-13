#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""移远软件资源中心（toolhub.quectel.com）命令行客户端。

纯 requests 实现，不依赖浏览器：
  1) 找 toolhub 要 SSO 授权地址 -> auth.quectel.com.cn -> openapi -> sso-web 登录页
  2) 用工作邮箱 + 密码走 SSO（密码前端是 RSA/PKCS#1 v1.5 加密的，这里纯 Python 复刻）
  3) 一路 302 拿到 toolhub 的 oauth code，换 qsc_at_ 开头的 accessToken
  4) 用 accessToken 查资源 / 查版本 / 要下载直链（预签名 S3，15 分钟有效）

用法：
    python toolhub.py login                 # 强制重新登录
    python toolhub.py whoami
    python toolhub.py cats                  # 分类
    python toolhub.py list QWinLog          # 按关键词搜资源
    python toolhub.py list --sort downloads --size 30
    python toolhub.py info QWinLog          # 资源详情 + 全部版本
    python toolhub.py versions QWinLog
    python toolhub.py download QWinLog      # 下最新版本到 ./
    python toolhub.py download QWinLog --version 2.3 -o D:\\tools
    python toolhub.py get-url QWinLog       # 只要直链，不下载
"""

import argparse
import base64
import getpass
import json
import os
import re
import sys
import time
from urllib.parse import parse_qs, quote, unquote, urlparse

try:
    import requests
except ImportError:  # pragma: no cover
    sys.exit('需要 requests：pip install requests')

BASE = os.environ.get('TOOLHUB_BASE', 'https://toolhub.quectel.com').rstrip('/')
AUTH = os.environ.get('TOOLHUB_AUTH', 'https://auth.quectel.com.cn').rstrip('/')
SSO = os.environ.get('TOOLHUB_SSO', 'https://sso-web.quectel.com').rstrip('/')
API = BASE + '/api/software-center'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

HOME = os.path.expanduser('~')
TOKEN_FILE = os.path.expanduser(os.environ.get('TOOLHUB_TOKEN_FILE', '~/.toolhub/token.json'))
CRED_FILES = [
    os.path.expanduser(os.environ['TOOLHUB_CREDENTIALS']) if os.environ.get('TOOLHUB_CREDENTIALS') else None,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', '.credentials.json'),
    os.path.join(HOME, '.toolhub', 'credentials.json'),
]


# --------------------------------------------------------------------------- #
# 控制台编码（Windows 管道常是 GBK，中文会乱码）
# --------------------------------------------------------------------------- #
def _init_stdout():
    enc = os.environ.get('TOOLHUB_ENCODING')
    if not enc and sys.platform == 'win32':
        try:
            import ctypes
            if ctypes.windll.kernel32.GetConsoleOutputCP() == 936:
                enc = 'gbk'
        except Exception:
            pass
    if enc:
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding=enc, errors='replace')
            except Exception:
                pass


_init_stdout()


class ToolhubError(Exception):
    pass


# --------------------------------------------------------------------------- #
# SSO 密码加密：登录页的 RSA 公钥 + PKCS#1 v1.5（纯 Python，不引入加密库）
# 公钥是登录页公开信息，不是任何人的凭证。
# --------------------------------------------------------------------------- #
SSO_RSA_PUBKEY = (
    'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAre5YnMJtO+gtwkeeq07f5UfywHM2LQ5T4jzV'
    'zYUYJOQN0AUAYkmoIt7rIfAN6q5nEby3zupXznBo/Y5SsRtXDoG53xHucpqE5SXD4J6kNnxj+JjecQ7ef'
    '0ev5MTOb+eREybymosgs7xr/eprv2O4GmipUwXVTWusbL/xjPzfP603JGz/r6xR94k5K8NXqHLQVBKURa5Q'
    'K3x9sUyX5ZxYop6llF3BdkIafB8aERw5iJa7i8fFK6UmIbhGQ8rLYYGj61229NayMgIuWJ3SGmUWWq0RyC'
    'Ejt96I6ZWwOqygkiEXj3PoQEmTUIxmEgrWQ5UxSHT/XDai5sbj7IueMqncPQIDAQAB')


def _der_tlv(buf, i=0):
    tag = buf[i]
    ln = buf[i + 1]
    i += 2
    if ln & 0x80:
        n = ln & 0x7F
        ln = int.from_bytes(buf[i:i + n], 'big')
        i += n
    return tag, buf[i:i + ln], i + ln


def _rsa_pub_from_spki(b64key):
    body = _der_tlv(base64.b64decode(b64key))[1]
    _, _, i = _der_tlv(body, 0)
    bitstr = _der_tlv(body, i)[1]
    if bitstr and bitstr[0] == 0:
        bitstr = bitstr[1:]
    seq = _der_tlv(bitstr)[1]
    _, nbytes, j = _der_tlv(seq, 0)
    _, ebytes, _ = _der_tlv(seq, j)
    return int.from_bytes(nbytes, 'big'), int.from_bytes(ebytes, 'big')


_RSA_N, _RSA_E = _rsa_pub_from_spki(SSO_RSA_PUBKEY)


def rsa_encrypt(text):
    msg = text.encode('utf-8')
    k = (_RSA_N.bit_length() + 7) // 8
    if len(msg) > k - 11:
        raise ToolhubError('密码过长，无法用 RSA 加密')
    ps = bytearray()
    while len(ps) < k - 3 - len(msg):
        b = os.urandom(1)[0]
        if b:
            ps.append(b)
    em = b'\x00\x02' + bytes(ps) + b'\x00' + msg
    c = pow(int.from_bytes(em, 'big'), _RSA_E, _RSA_N)
    return base64.b64encode(c.to_bytes(k, 'big')).decode()


# --------------------------------------------------------------------------- #
# 凭据 / token
# --------------------------------------------------------------------------- #
def load_credentials():
    u = os.environ.get('TOOLHUB_USERNAME')
    p = os.environ.get('TOOLHUB_PASSWORD')
    if u and p:
        return u, p
    for path in CRED_FILES:
        if not path or not os.path.exists(path):
            continue
        try:
            raw = open(path, encoding='utf-8').read()
            data = json.loads(raw)
        except Exception:
            continue
        cu = data.get('username') or data.get('user') or ''
        cp = data.get('password') or data.get('pwd') or ''
        if cu and cp:
            return cu, cp
    return None, None


def load_token():
    if not os.path.exists(TOKEN_FILE):
        return {}
    try:
        return json.load(open(TOKEN_FILE, encoding='utf-8'))
    except Exception:
        return {}


def save_token(tok):
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    tmp = TOKEN_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(tok, f, ensure_ascii=False, indent=2)
    os.replace(tmp, TOKEN_FILE)
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# 登录链路
# --------------------------------------------------------------------------- #
def sso_password_login(username, password):
    """sso-web 密码登录，返回 (access_token, refresh_token, expires_in)。"""
    enc = rsa_encrypt(password)
    try:
        chk = requests.post(SSO + '/api/uaa/mfa-open/check', timeout=30,
                            headers={'content-type': 'application/json', 'user-agent': UA},
                            json={'username': username, 'password': enc}).json()
        data = chk.get('data') or {}
        if data.get('isPass') is False:
            raise ToolhubError('账号或密码错误：%s' % (data.get('errorMessage') or chk.get('msg') or ''))
    except ToolhubError:
        raise
    except Exception:
        pass
    r = requests.post(SSO + '/api/uaa/oauth/token', timeout=30,
                      headers={'Content-Type': 'application/x-www-form-urlencoded',
                               'User-Agent': UA, 'terminal': 'web', 'devicesn': os.urandom(16).hex()},
                      data={'grant_type': 'password', 'username': username, 'password': enc,
                            'scope': 'ui', 'client_id': 'quectel', 'client_secret': 'quectel',
                            'auth_type': 'rsa_area'})
    try:
        j = r.json()
    except Exception:
        raise ToolhubError('SSO 登录返回异常：HTTP %s %s' % (r.status_code, r.text[:200]))
    if not j.get('access_token'):
        code = j.get('code')
        if code in (102, '102'):
            raise ToolhubError('该账号开了强制 MFA（短信/邮箱验证码），脚本密码登录走不通，'
                               '需要在浏览器里登录后手工导出 token。')
        raise ToolhubError('SSO 登录失败：%s' % (j.get('msg') or j))
    return j['access_token'], j.get('refresh_token'), int(j.get('expires_in') or 86000)


def login(force=False):
    tok = load_token()
    if not force and tok.get('access_token') and int(tok.get('expires_at') or 0) - 120 > time.time():
        return tok
    username, password = load_credentials()
    if not username or not password:
        if tok.get('access_token') and int(tok.get('expires_at') or 0) > time.time():
            return tok
        raise ToolhubError(
            '未找到账号密码。请任选一种方式提供：\n'
            '  1) 环境变量 TOOLHUB_USERNAME / TOOLHUB_PASSWORD\n'
            '  2) 凭据文件 skills/.credentials.json（.gitignore 里，不入库）\n'
            '     {"username": "你的工作邮箱", "password": "你的密码"}\n'
            '  3) ~/.toolhub/credentials.json（同上格式）')
    u, p = username, password
    s = requests.Session()
    s.headers['user-agent'] = UA

    r = s.get(API + '/auth/qauth/authorize-url', params={'client_type': 'WEB'}, timeout=30)
    d = (r.json() or {}).get('data') or {}
    if not d.get('authorizeUrl'):
        raise ToolhubError('取 SSO 授权地址失败：HTTP %s %s' % (r.status_code, r.text[:200]))
    q = parse_qs(urlparse(d['authorizeUrl']).query)
    client_id, code, callback = q['clientId'][0], q['code'][0], q['callback'][0]

    r = s.get(AUTH + '/api/v1/login/config', params={'code': code, 'clientId': client_id},
              headers={'System-Language': 'zh-cn', 'timeZone': 'Asia/Shanghai',
                       'no-check-user': 'true'}, timeout=30)
    srcs = (((r.json() or {}).get('data') or {}).get('loginSetting') or {}).get('identitySource') or []
    srcs = [x for x in srcs if x.get('status') in (None, 'Y')]
    if not srcs:
        raise ToolhubError('登录页没有可用的身份源（identitySource 为空）')

    r = s.post(AUTH + '/api/v1/login/identitySourceLogin',
               json={'code': code, 'clientId': client_id, 'identitySourceId': srcs[0]['id'],
                     'callback': quote(callback, safe='')},
               headers={'Origin': AUTH, 'Referer': AUTH + '/', 'no-check-user': 'true',
                        'System-Language': 'zh-cn', 'timeZone': 'Asia/Shanghai',
                        'content-type': 'application/json'}, timeout=30)
    openapi_url = (r.json() or {}).get('data')
    if not openapi_url:
        raise ToolhubError('取 SSO 登录地址失败：HTTP %s %s' % (r.status_code, r.text[:200]))

    r = s.get(openapi_url, timeout=30)
    oauth_callback = parse_qs(urlparse(r.url).query).get('oauth_callback', [None])[0]
    if not oauth_callback:
        raise ToolhubError('SSO 登录页没有返回 oauth_callback（%s）' % r.url[:200])
    oauth_callback = unquote(oauth_callback)

    at, rt, exp = sso_password_login(u, p)
    s.cookies.set('quectel_token', 'bearer' + at, domain=urlparse(SSO).hostname)
    s.cookies.set('quectel_refresh_token', rt or '', domain=urlparse(SSO).hostname)
    s.cookies.set('quectel_lang', 'cn', domain=urlparse(SSO).hostname)

    r = s.get(oauth_callback, allow_redirects=False, timeout=30)
    loc = r.headers.get('location')
    if not loc:
        raise ToolhubError('SSO 授权回调失败：HTTP %s %s' % (r.status_code, r.text[:200]))
    r = s.get(loc, allow_redirects=False, timeout=30)
    loc2 = r.headers.get('location')
    if not loc2:
        raise ToolhubError('SSO code 回调失败：HTTP %s %s' % (r.status_code, r.text[:200]))
    pq = parse_qs(urlparse(loc2).query)
    for k in ('code', 'clientId', 'ticket', 'callback'):
        if k not in pq:
            raise ToolhubError('回调参数缺少 %s：%s' % (k, loc2[:200]))

    r = s.post(AUTH + '/api/v1/login/ticket', timeout=30,
               files={'code': (None, pq['code'][0]), 'clientId': (None, pq['clientId'][0]),
                      'type': (None, 'IDENTITY_SOURCE'), 'ticket': (None, pq['ticket'][0])},
               headers={'Origin': AUTH, 'Referer': loc2, 'no-check-user': 'true',
                        'System-Language': 'zh-cn', 'timeZone': 'Asia/Shanghai'})
    if (r.json() or {}).get('code') not in (0, '0'):
        raise ToolhubError('SSO ticket 登录失败：%s' % r.text[:200])

    r = s.get(unquote(pq['callback'][0]), allow_redirects=False, timeout=30)
    loc3 = r.headers.get('location') or ''
    pq3 = parse_qs(urlparse(loc3).query)
    if 'code' not in pq3 or 'state' not in pq3:
        raise ToolhubError('没拿到 toolhub 的 oauth code：%s' % (loc3[:200] or r.text[:200]))

    r = s.post(API + '/auth/exchange', json={'code': pq3['code'][0], 'state': pq3['state'][0]},
               headers={'Origin': BASE, 'Referer': loc3, 'content-type': 'application/json'}, timeout=30)
    d = (r.json() or {}).get('data') or {}
    if not d.get('accessToken'):
        raise ToolhubError('换 token 失败：HTTP %s %s' % (r.status_code, r.text[:200]))
    tok = {
        'access_token': d['accessToken'],
        'refresh_token': d.get('refreshToken'),
        'expires_at': int(time.time()) + int(d.get('expiresIn') or 7200),
        'username': u,
        'sso_token': 'bearer' + at,
        'sso_refresh_token': rt,
    }
    save_token(tok)
    return tok


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
class Toolhub(object):
    def __init__(self):
        self.tok = load_token()

    def _headers(self, referer=None):
        return {
            'authorization': 'Bearer ' + self.tok['access_token'],
            'accept': 'application/json',
            'content-type': 'application/json',
            'origin': BASE,
            'referer': referer or (BASE + '/portal/resources'),
            'user-agent': UA,
        }

    def request(self, method, path, params=None, payload=None, _retry=True):
        if int(self.tok.get('expires_at') or 0) - 120 <= time.time():
            self.tok = login()
        url = path if path.startswith('http') else API + path
        r = requests.request(method, url, params=params, json=payload,
                             headers=self._headers(), timeout=60)
        if r.status_code in (401, 403) and _retry:
            self.tok = login(force=True)
            return self.request(method, path, params, payload, _retry=False)
        try:
            j = r.json()
        except Exception:
            raise ToolhubError('HTTP %s: %s' % (r.status_code, r.text[:300]))
        if r.status_code >= 400 or (isinstance(j, dict) and j.get('code') not in (0, '0', None)):
            raise ToolhubError('%s（HTTP %s / code %s）' % (j.get('msg') or '接口报错',
                                                          r.status_code, j.get('code')))
        return j.get('data')

    # -- 查询 ---------------------------------------------------------------
    def userinfo(self):
        return self.request('GET', '/auth/userinfo')

    def categories(self):
        return self.request('GET', '/portal/categories') or []

    def resources(self, keyword='', page=1, size=20, sort='downloads', field='all',
                  category_id='', os_name='', fetch_all=False):
        out, total = [], 0
        while True:
            params = {'pageNumber': page, 'pageSize': size, 'sort': sort}
            if keyword:
                params['keyword'] = keyword
                if field and field != 'all':
                    params['field'] = field
            if category_id:
                params['categoryId'] = category_id
            if os_name:
                params['os'] = os_name
            data = self.request('GET', '/portal/resources', params=params) or {}
            recs = data.get('records') or data.get('list') or []
            try:
                total = int(data.get('total') or 0)
            except Exception:
                total = 0
            out.extend(recs)
            if not fetch_all or len(recs) < size or len(out) >= total:
                break
            page += 1
        return out, total

    def resource(self, rid):
        return self.request('GET', '/portal/resources/%s' % rid)

    def versions(self, rid):
        return self.request('GET', '/portal/resources/%s/versions' % rid) or []

    def download_url(self, rid, vid, version, file_size):
        data = self.request('POST', '/portal/resources/%s/download' % rid,
                            payload={'versionId': vid, 'version': version,
                                     'fileSize': int(file_size or 0)},
                            ) or {}
        if not data.get('url'):
            raise ToolhubError('下载接口没返回 url：%s' % data)
        return data['url'], int(data.get('expiresIn') or 900)

    # -- 解析 ---------------------------------------------------------------
    def resolve(self, key):
        """资源 id 或名称/关键词 -> resource dict。"""
        key = str(key).strip()
        if key.isdigit():
            return self.resource(key)
        recs, total = self.resources(keyword=key, size=20, sort='downloads')
        if not recs:
            raise ToolhubError('没搜到 "%s" 相关资源' % key)
        exact = [x for x in recs if (x.get('name') or '').lower() == key.lower()]
        if exact:
            return exact[0]
        # 名字里包含关键词的优先，否则取下载量最高的
        hits = [x for x in recs if key.lower() in (x.get('name') or '').lower()]
        (hits or recs).sort(key=lambda x: x.get('downloads') or 0, reverse=True)
        return (hits or recs)[0]

    def pick_version(self, versions, want=None):
        if not versions:
            raise ToolhubError('该资源没有可用版本')
        if want:
            want = str(want).lstrip('vV')
            for v in versions:
                if str(v.get('version')).lstrip('vV') == want:
                    return v
            raise ToolhubError('没有版本 %s，可选：%s' % (
                want, ', '.join(str(v.get('version')) for v in versions)))
        ok = [v for v in versions if v.get('reviewStatus') in (None, 'APPROVED')]
        pool = ok or versions
        pool.sort(key=lambda v: (v.get('releaseDate') or ''), reverse=True)
        return pool[0]


# --------------------------------------------------------------------------- #
# 下载
# --------------------------------------------------------------------------- #
def human(n):
    try:
        n = float(n)
    except Exception:
        return '-'
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024 or unit == 'TB':
            return ('%.0f %s' % (n, unit)) if unit == 'B' else ('%.1f %s' % (n, unit))
        n /= 1024.0


def safe_name(name, default='download.bin'):
    name = (name or '').strip().replace('\\', '_').replace('/', '_')
    name = re.sub(r'[<>:"|?*\x00-\x1f]', '_', name)
    return name or default


def filename_from_url(url, fallback):
    q = parse_qs(urlparse(url).query)
    cd = q.get('response-content-disposition', [''])[0]
    m = re.search(r"filename\*=UTF-8''([^;]+)", cd) or re.search(r'filename="?([^";]+)"?', cd)
    if m:
        return safe_name(unquote(m.group(1)))
    return safe_name(fallback)


def http_download(url, dest, expect_size=None, quiet=False):
    try:
        expect_size = int(expect_size or 0)
    except Exception:
        expect_size = 0
    have = os.path.getsize(dest) if os.path.exists(dest) else 0
    headers = {'user-agent': UA}
    mode = 'wb'
    if have:
        headers['Range'] = 'bytes=%d-' % have
        mode = 'ab'
    r = requests.get(url, headers=headers, stream=True, timeout=120, allow_redirects=True)
    if have and r.status_code != 206:
        have, mode = 0, 'wb'
    if r.status_code not in (200, 206):
        raise ToolhubError('下载失败：HTTP %s' % r.status_code)
    total = expect_size or 0
    got = have
    os.makedirs(os.path.dirname(os.path.abspath(dest)) or '.', exist_ok=True)
    t0 = time.time()
    with open(dest, mode) as f:
        for chunk in r.iter_content(256 * 1024):
            if not chunk:
                continue
            f.write(chunk)
            got += len(chunk)
            if not quiet:
                pct = ('%5.1f%%' % (got * 100.0 / total)) if total else '  ...'
                sys.stdout.write('\r  %s  %s / %s  (%.1f MB/s)   ' % (
                    pct, human(got), human(total) if total else '?',
                    got / 1048576.0 / max(0.001, time.time() - t0)))
                sys.stdout.flush()
    if not quiet:
        sys.stdout.write('\n')
    size = os.path.getsize(dest)
    if expect_size and size != int(expect_size):
        raise ToolhubError('大小不符：期望 %d，实际 %d' % (int(expect_size), size))
    return size


def do_download(th, key, want_version=None, out_dir='.', dry_run=False, quiet=False):
    res = th.resolve(key)
    rid = res.get('id')
    name = res.get('name')
    versions = th.versions(rid)
    ver = th.pick_version(versions, want_version)
    vid = ver.get('id')
    fname = safe_name(ver.get('fileName'), '%s_%s.bin' % (safe_name(name), ver.get('version')))
    size = ver.get('fileSize')
    print('资源：%s（%s）' % (name, rid))
    print('版本：%s  发布：%s  大小：%s' % (ver.get('version'), ver.get('releaseDate'), human(size)))
    print('文件：%s' % fname)
    url, ttl = th.download_url(rid, vid, ver.get('version'), size)
    if dry_run:
        print('直链（%d 秒有效）：%s' % (ttl, url))
        return None
    dest = os.path.join(out_dir, filename_from_url(url, fname))
    print('保存：%s' % os.path.abspath(dest))
    got = http_download(url, dest, size, quiet=quiet)
    print('完成：%s（%s）' % (os.path.abspath(dest), human(got)))
    return dest


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def fmt_row(cols, widths):
    return '  '.join((str(c) if c is not None else '-')[:w].ljust(w) for c, w in zip(cols, widths))


def cmd_whoami(th, a):
    me = th.userinfo() or {}
    print('用户：%s' % me.get('username'))
    print('姓名：%s' % (me.get('fullName') or '-'))
    print('邮箱：%s' % (me.get('email') or '-'))
    print('类型：%s' % (me.get('userType') or '-'))
    tok = load_token()
    left = int(tok.get('expires_at') or 0) - int(time.time())
    print('token：%s…  剩余 %d 分钟' % ((tok.get('access_token') or '')[:22], max(0, left // 60)))


def cmd_cats(th, a):
    for c in th.categories():
        print('%-26s %s  (%s)' % (c.get('name'), c.get('id'), c.get('icon') or ''))


def cmd_list(th, a):
    cat_id = ''
    if a.cat:
        for c in th.categories():
            if a.cat.lower() in (c.get('name') or '').lower() or a.cat == c.get('id'):
                cat_id = c.get('id')
                break
        else:
            raise ToolhubError('没有分类 "%s"（用 `cats` 看全部）' % a.cat)
    recs, total = th.resources(keyword=a.keyword or '', page=a.page, size=a.size,
                               sort=a.sort, field=a.field, category_id=cat_id,
                               os_name=a.os, fetch_all=a.all)
    if not recs:
        print('没有匹配的资源')
        return
    print('共 %d 条%s' % (total or len(recs), '' if (total or 0) <= len(recs) else '，显示 %d 条' % len(recs)))
    print(fmt_row(['ID', 'NAME', 'VER', 'CAT', 'DL', 'PUBLISHED'], [21, 46, 9, 12, 5, 11]))
    for r in recs:
        print(fmt_row([r.get('id'), r.get('name'), r.get('latestVersion'),
                       r.get('categoryName'), r.get('downloads'), (r.get('publishedAt') or '')[:10]],
                      [21, 46, 9, 12, 5, 11]))


def cmd_info(th, a):
    res = th.resolve(a.key)
    print('ID      : %s' % res.get('id'))
    print('名称    : %s' % res.get('name'))
    print('编号    : %s' % res.get('code'))
    print('分类    : %s' % res.get('categoryName'))
    print('最新版  : %s' % res.get('latestVersion'))
    print('下载量  : %s   浏览 %s' % (res.get('downloads'), res.get('views')))
    print('发布    : %s' % res.get('publishedAt'))
    print('摘要    : %s' % (res.get('summary') or '-'))
    if res.get('installGuide'):
        print('安装    : %s' % res.get('installGuide'))
    print('页面    : %s/portal/resources/%s' % (BASE, res.get('id')))
    cmd_versions(th, a)


def cmd_versions(th, a):
    res = th.resolve(a.key)
    versions = th.versions(res.get('id'))
    print('\n版本 %d 个：' % len(versions))
    print(fmt_row(['VERSION', 'RELEASE', 'SIZE', 'REVIEW', 'SCAN', 'FILE'], [12, 11, 10, 9, 8, 48]))
    for v in versions:
        print(fmt_row([v.get('version'), v.get('releaseDate'), human(v.get('fileSize')),
                       v.get('reviewStatus'), v.get('scanStatus'), v.get('fileName')],
                      [12, 11, 10, 9, 8, 48]))


def cmd_download(th, a):
    if a.version:
        do_download(th, a.key, a.version, a.out, a.dry_run)
    elif a.all_versions:
        res = th.resolve(a.key)
        for v in th.versions(res.get('id')):
            if v.get('reviewStatus') not in (None, 'APPROVED'):
                continue
            do_download(th, res.get('id'), v.get('version'), a.out, a.dry_run)
    else:
        do_download(th, a.key, None, a.out, a.dry_run)


def cmd_url(th, a):
    res = th.resolve(a.key)
    ver = th.pick_version(th.versions(res.get('id')), a.version)
    url, ttl = th.download_url(res.get('id'), ver.get('id'), ver.get('version'), ver.get('fileSize'))
    print(url)
    print('# %s %s 直链，%d 秒有效' % (res.get('name'), ver.get('version'), ttl), file=sys.stderr)


def cmd_login(th, a):
    tok = login(force=True)
    me = Toolhub().userinfo() or {}
    print('登录成功：%s（%s）' % (me.get('username'), me.get('email')))
    print('token 缓存：%s' % TOKEN_FILE)


def cmd_token(th, a):
    tok = load_token()
    if a.force:
        tok = login(force=True)
    print(tok.get('access_token'))


def main(argv=None):
    ap = argparse.ArgumentParser(description='移远软件资源中心（toolhub）下载工具')
    sub = ap.add_subparsers(dest='cmd')

    p = sub.add_parser('login', help='强制重新登录')
    p.set_defaults(func=cmd_login)
    p = sub.add_parser('whoami', help='当前登录账号')
    p.set_defaults(func=cmd_whoami)
    p = sub.add_parser('token', help='打印 accessToken')
    p.add_argument('--force', action='store_true')
    p.set_defaults(func=cmd_token)
    p = sub.add_parser('cats', help='资源分类')
    p.set_defaults(func=cmd_cats)

    p = sub.add_parser('list', help='搜/列资源')
    p.add_argument('keyword', nargs='?', default='')
    p.add_argument('--page', type=int, default=1)
    p.add_argument('--size', type=int, default=20)
    p.add_argument('--sort', default='downloads', choices=['downloads', 'modifyTime', 'name'])
    p.add_argument('--field', default='all', choices=['all', 'name', 'description', 'tags', 'model'])
    p.add_argument('--cat', default='', help='分类名或分类 id')
    p.add_argument('--os', default='', help='Windows / Linux / Android ...')
    p.add_argument('--all', action='store_true', help='翻页取全部结果')
    p.set_defaults(func=cmd_list)

    p = sub.add_parser('info', help='资源详情 + 版本列表')
    p.add_argument('key')
    p.set_defaults(func=cmd_info)

    p = sub.add_parser('versions', help='只列版本')
    p.add_argument('key')
    p.set_defaults(func=cmd_versions)

    p = sub.add_parser('download', help='下载（默认最新版本）')
    p.add_argument('key', help='资源 id 或名称关键词')
    p.add_argument('--version', default=None, help='指定版本号，如 2.3')
    p.add_argument('--all-versions', action='store_true')
    p.add_argument('-o', '--out', default='.')
    p.add_argument('--dry-run', action='store_true', help='只打印直链，不下载')
    p.set_defaults(func=cmd_download)

    p = sub.add_parser('get-url', help='只取下载直链')
    p.add_argument('key')
    p.add_argument('--version', default=None)
    p.set_defaults(func=cmd_url)

    a = ap.parse_args(argv)
    if not getattr(a, 'func', None):
        ap.print_help()
        return 0
    try:
        a.func(Toolhub(), a)
    except ToolhubError as e:
        print('错误：%s' % e, file=sys.stderr)
        return 1
    except requests.RequestException as e:
        print('网络错误：%s' % e, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
