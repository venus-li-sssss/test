#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""账号登录型 skill 的可复用骨架。

只依赖标准库（urllib），复制到你的 skill 里改几处常量就能用：

    BASE      = 'https://your.site.com'
    TOKEN_URL = BASE + '/oauth/token'

用法见 SKILL.md；本文件可直接跑自检：

    python account_auth.py --selftest
"""

import argparse
import base64
import getpass
import json
import os
import sys
import time
import urllib.error
import urllib.request

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

USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')


# --------------------------------------------------------------------------- #
# 1. token 存储：只存 token，不存密码
# --------------------------------------------------------------------------- #
class TokenStore(object):
    """token 落在用户目录（~/.<app>/token.json），**永远不放进 skill 目录**。

    - 一个 Windows/macOS 用户一份 → 多人共用同一份 skill 互不影响
    - 文件权限 600（仅本人可读）
    - 密码永不写入
    """

    def __init__(self, app, path=None):
        self.app = app
        self.path = path or os.path.expanduser(os.path.join('~', '.' + app, 'token.json'))

    def load(self):
        try:
            with open(self.path, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def save(self, data):
        d = os.path.dirname(self.path)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)
        try:
            os.chmod(self.path, 0o600)
        except Exception:
            pass

    def clear(self):
        try:
            os.remove(self.path)
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# 2. 询问账号：有就用，没有就问；非交互环境给指引而不是死等
# --------------------------------------------------------------------------- #
def ask_credentials(env_user='APP_USERNAME', env_pass='APP_PASSWORD',
                    user=None, password=None, hint='账号（邮箱或工号）'):
    u = user or os.environ.get(env_user)
    p = password or os.environ.get(env_pass)
    if u and p:
        return u, p
    if not sys.stdin or not sys.stdin.isatty():
        raise SystemExit(
            '未登录。三种方式任选：\n'
            '  1) 交互式登录：  <cmd> login --ask\n'
            '  2) 浏览器导出的 HAR：  <cmd> login --devtools <文件>\n'
            '  3) 直接给 token：  <cmd> login --token "bearerXXXX"\n'
            '（非交互环境不会卡住等你输密码，请用上面任一方式）')
    if not u:
        u = input('%s: ' % hint).strip()
    if not p:
        p = getpass.getpass('密码（只用于换 token，不会保存）: ')
    if not u or not p:
        raise SystemExit('账号或密码为空，已取消。')
    return u, p


# --------------------------------------------------------------------------- #
# 3. HTTP：失败信息要能看懂，别把 500 原样甩给用户
# --------------------------------------------------------------------------- #
def post_json(url, payload, token=None, timeout=30):
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                 method='POST',
                                 headers={'Content-Type': 'application/json',
                                          'Accept': 'application/json',
                                          'User-Agent': USER_AGENT,
                                          **({'Authorization': token} if token else {})})
    return _do(req, timeout)


def post_form(url, fields, timeout=30):
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=body, method='POST',
                                 headers={'Content-Type': 'application/x-www-form-urlencoded',
                                          'User-Agent': USER_AGENT})
    return _do(req, timeout)


def _do(req, timeout):
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8', 'replace'))
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return json.loads(raw)
        except Exception:
            raise SystemExit('HTTP %s: %s' % (e.code, raw[:300]))
    except Exception as e:
        raise SystemExit('请求失败：%s' % e)


import urllib.parse  # noqa: E402  （放在这里避免和上面 _do 的顺序混淆）


# --------------------------------------------------------------------------- #
# 4. 状态机：有效就用 → 快过期就续 → 续不了才问人
# --------------------------------------------------------------------------- #
class AuthGuard(object):
    """把「有 token 就用，没 token 就问」这套逻辑集中在一处。

    login_fn(username, password) -> dict：返回
        {'access_token': ..., 'refresh_token': ..., 'expires_in': 86399}
    refresh_fn(refresh_token) -> dict：同上（没有 refresh 就传 None）
    """

    def __init__(self, store, login_fn, refresh_fn=None,
                 refresh_ahead=120, app='app'):
        self.store = store
        self.login_fn = login_fn
        self.refresh_fn = refresh_fn
        self.refresh_ahead = refresh_ahead
        self.app = app
        self.tok = store.load()

    # -- 对外 -------------------------------------------------------------
    def token(self, force_refresh=False):
        if force_refresh:
            self._refresh_or_login()
        elif not self._valid():
            self._refresh_or_login()
        return self.tok.get('access_token')

    def login(self, username=None, password=None):
        u, p = ask_credentials(env_user=(self.app.upper() + '_USERNAME'),
                               env_pass=(self.app.upper() + '_PASSWORD'),
                               user=username, password=password)
        data = self.login_fn(u, p)
        self._absorb(data, username=u)

    # -- 内部 -------------------------------------------------------------
    def _valid(self):
        return bool(self.tok.get('access_token')) and \
            int(self.tok.get('expires_at') or 0) - self.refresh_ahead > time.time()

    def _refresh_or_login(self):
        if self.tok.get('refresh_token') and self.refresh_fn:
            try:
                data = self.refresh_fn(self.tok['refresh_token'])
                if data and data.get('access_token'):
                    self._absorb(data)
                    return
            except (SystemExit, Exception):
                pass  # 续期失败就落到询问账号
        if self.tok.get('access_token') and int(self.tok.get('expires_at') or 0) > time.time():
            return  # 还有效，别多事
        self.login()

    def _absorb(self, data, username=None):
        self.tok['access_token'] = data['access_token']
        if data.get('refresh_token'):
            self.tok['refresh_token'] = data['refresh_token']
        self.tok['expires_at'] = int(time.time()) + int(data.get('expires_in') or 86000)
        if username:
            self.tok['username'] = username   # 只记账号名，不记密码
        self.store.save(self.tok)


# --------------------------------------------------------------------------- #
# 5. 可选：前端把密码 RSA/AES 加密后再提交时的通用工具
# --------------------------------------------------------------------------- #
def _der_tlv(buf, i=0):
    tag = buf[i]
    ln = buf[i + 1]
    i += 2
    if ln & 0x80:
        n = ln & 0x7F
        ln = int.from_bytes(buf[i:i + n], 'big')
        i += n
    return tag, buf[i:i + ln], i + ln


def rsa_pub_from_spki(b64key):
    """'MIIBIjANBgkq...' → (n, e)。公钥从登录页 JS 里抄，不是凭证。"""
    body = _der_tlv(base64.b64decode(b64key))[1]
    _, _, i = _der_tlv(body, 0)
    bitstr = _der_tlv(body, i)[1]
    if bitstr and bitstr[0] == 0:
        bitstr = bitstr[1:]
    seq = _der_tlv(bitstr)[1]
    _, nbytes, j = _der_tlv(seq, 0)
    _, ebytes, _ = _der_tlv(seq, j)
    return int.from_bytes(nbytes, 'big'), int.from_bytes(ebytes, 'big')


def rsa_encrypt_pkcs1v15(text, b64key):
    """等价前端 encrypt(text,'base64','utf8') + pkcs1 padding。"""
    n, e = rsa_pub_from_spki(b64key)
    msg = text.encode('utf-8')
    k = (n.bit_length() + 7) // 8
    if len(msg) > k - 11:
        raise ValueError('密码过长')
    ps = bytearray()
    while len(ps) < k - 3 - len(msg):
        b = os.urandom(1)[0]
        if b:
            ps.append(b)
    em = b'\x00\x02' + bytes(ps) + b'\x00' + msg
    return base64.b64encode(pow(int.from_bytes(em, 'big'), e, n).to_bytes(k, 'big')).decode()


# --------------------------------------------------------------------------- #
# 6. 自检
# --------------------------------------------------------------------------- #
def _selftest():
    print('== TokenStore 往返 ==')
    store = TokenStore('demo_auth_selftest', path=os.path.join(os.getcwd(), '.selftest_token.json'))
    store.save({'access_token': 'bearer-abc', 'refresh_token': 'r-1',
                'expires_at': int(time.time()) + 3600, 'username': 'demo'})
    t = store.load()
    print('  写入/读回:', '成功' if t.get('access_token') == 'bearer-abc' else '失败')
    print('  文件权限(仅 unix 有意义):', oct(os.stat(store.path).st_mode & 0o777))
    os.remove(store.path)

    print('\n== 状态机 ==')
    calls = []

    def login_fn(u, p):
        calls.append(('login', u))
        return {'access_token': 'T-new', 'refresh_token': 'R-new', 'expires_in': 100}

    def refresh_fn(rt):
        calls.append(('refresh', rt))
        return {'access_token': 'T-refreshed', 'refresh_token': 'R-2', 'expires_in': 100}

    s2 = TokenStore('demo2', path=os.path.join(os.getcwd(), '.selftest2.json'))
    g = AuthGuard(s2, login_fn, refresh_fn)
    g.tok = {'access_token': 'T-ok', 'refresh_token': 'R-ok',
             'expires_at': int(time.time()) + 3600}
    print('  有效 token → 直接用:', g.token() == 'T-ok', calls == [])
    g.tok['expires_at'] = int(time.time()) - 1
    print('  过期 + 有 refresh → 自动续:', g.token() == 'T-refreshed', calls == [('refresh', 'R-ok')])
    g.tok = {}
    calls.clear()
    print('  非交互环境无账号 → 给指引不卡住:', end=' ')
    try:
        g.token()
        print('失败（居然没报错）')
    except SystemExit as e:
        print('正确 ->', str(e).splitlines()[0])
    s2.clear()

    print('\n== RSA PKCS#1 v1.5 ==')
    try:
        from cryptography.hazmat.primitives.asymmetric import rsa, padding
        from cryptography.hazmat.primitives import serialization
        priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        b64 = base64.b64encode(priv.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo)).decode()
        ok = True
        for msg in ('Hello@123', '中文密码#1', 'x' * 180):
            c = base64.b64decode(rsa_encrypt_pkcs1v15(msg, b64))
            ok = ok and priv.decrypt(c, padding.PKCS1v15()).decode('utf-8') == msg
        print('  往返一致:', ok)
    except ImportError:
        print('  跳过（未安装 cryptography，仅自检需要）')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='账号登录型 skill 骨架自检')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        _selftest()
    else:
        ap.print_help()
