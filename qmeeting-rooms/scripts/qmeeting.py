#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Quectel 会议室（qmeeting.quectel.com）命令行客户端。

只依赖 requests。所有「查会议室 / 查我的会议 / 预订 / 取消」能力都在这里，
供 skill（qmeeting-rooms）调用。

用法示例：
    python qmeeting.py whoami
    python qmeeting.py areas
    python qmeeting.py rooms --date 2026-11-12 --start 14:00 --end 15:00 --min-capacity 8 --facility 飞书
    python qmeeting.py calendar --date 2026-11-12 --area 3F
    python qmeeting.py mine
    python qmeeting.py detail 599349
    python qmeeting.py book --room Malaga --date 2026-11-12 --start 14:00 --end 15:00 --theme "评审"
    python qmeeting.py cancel 645864 --remark "不需要了" --yes
"""

import argparse
import base64
import datetime
import getpass
import json
import os
import re
import sys
import time

try:
    import requests
except ImportError:  # pragma: no cover
    sys.exit('需要 requests：pip install requests')

def _init_stdout():
    """Windows 控制台是 GBK 时用 GBK 输出，避免中文乱码。
    重定向到文件/需要 UTF-8 时设 QMEETING_OUTPUT_ENCODING=utf-8。"""
    enc = os.environ.get('QMEETING_OUTPUT_ENCODING')
    if not enc and sys.platform == 'win32':
        try:
            import ctypes
            cp = ctypes.windll.kernel32.GetConsoleOutputCP()
            if cp == 936:
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

BASE = os.environ.get('QMEETING_BASE', 'https://qmeeting.quectel.com').rstrip('/')
SSO = os.environ.get('QMEETING_SSO', 'https://sso-web.quectel.com').rstrip('/')
TOKEN_FILE = os.path.expanduser(os.environ.get('QMEETING_TOKEN_FILE', '~/.qmeeting/token.json'))
TZ = datetime.timezone(datetime.timedelta(hours=8))

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')


# --------------------------------------------------------------------------- #
# 错误
# --------------------------------------------------------------------------- #
class ApiError(Exception):
    def __init__(self, msg, code=None, payload=None):
        super().__init__(msg)
        self.code = code
        self.payload = payload


# --------------------------------------------------------------------------- #
# 时间工具（统一按 GMT+8 处理，避免机器时区干扰）
# --------------------------------------------------------------------------- #
def today_str():
    return datetime.datetime.now(TZ).strftime('%Y-%m-%d')


def parse_day(s):
    if not s:
        return today_str()
    if s in ('today', '今天'):
        return today_str()
    if s in ('tomorrow', '明天'):
        return (datetime.datetime.now(TZ) + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    datetime.datetime.strptime(s, '%Y-%m-%d')
    return s


def to_ms(day, hhmm):
    """'2026-11-12' + '14:00' -> 毫秒时间戳（GMT+8）。"""
    hhmm = hhmm.strip()
    if hhmm == '24:00':
        hhmm = '23:59'
    fmt = '%Y-%m-%d %H:%M:%S' if hhmm.count(':') == 2 else '%Y-%m-%d %H:%M'
    return int(datetime.datetime.strptime('%s %s' % (day, hhmm), fmt)
               .replace(tzinfo=TZ).timestamp() * 1000)


def from_ms(ms, fmt='%m-%d %H:%M'):
    if ms in (None, '', 'null'):
        return '-'
    return datetime.datetime.fromtimestamp(int(ms) / 1000, TZ).strftime(fmt)


def ms_to_day(ms):
    return datetime.datetime.fromtimestamp(int(ms) / 1000, TZ).strftime('%Y-%m-%d')


# --------------------------------------------------------------------------- #
# Token 管理
# --------------------------------------------------------------------------- #
def _now():
    return int(time.time())


# --------------------------------------------------------------------------- #
# SSO 账号登录
# 前端 sso_login_shared.js 里用 RSA 公钥做 PKCS#1 v1.5 加密再 base64，
# 这里用纯 Python 复刻（pow + 手工 DER 解析），不引入加密库依赖。
# 公钥是 SSO 登录页的公开信息，不是任何人的凭证。
# --------------------------------------------------------------------------- #
SSO_RSA_PUBKEY = (
    'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAre5YnMJtO+gtwkeeq07f5UfywHM2LQ5T4jzV'
    'zYUYJOQN0AUAYkmoIt7rIfAN6q5nEby3zupXznBo/Y5SsRtXDoG53xHucpqE5SXD4J6kNnxj+JjecQ7ef'
    '0ev5MTOb+eREybymosgs7xr/eprv2O4GmipUwXVTWusbL/xjPzfP603JGz/r6xR94k5K8NXqHLQVBKURa5Q'
    'K3x9sUyX5ZxYop6llF3BdkIafB8aERw5iJa7i8fFK6UmIbhGQ8rLYYGj61229NayMgIuWJ3SGmUWWq0RyC'
    'Ejt96I6ZWwOqygkiEXj3PoQEmTUIxmEgrWQ5UxSHT/XDai5sbj7IueMqncPQIDAQAB')


def _der_tlv(buf, i=0):
    """极简 DER TLV 解析：返回 (tag, value, next_index)。"""
    tag = buf[i]
    ln = buf[i + 1]
    i += 2
    if ln & 0x80:
        n = ln & 0x7F
        ln = int.from_bytes(buf[i:i + n], 'big')
        i += n
    return tag, buf[i:i + ln], i + ln


def _rsa_pub_from_spki(b64key):
    body = _der_tlv(base64.b64decode(b64key))[1]      # SubjectPublicKeyInfo
    _, _, i = _der_tlv(body, 0)                       # AlgorithmIdentifier
    bitstr = _der_tlv(body, i)[1]                     # BIT STRING
    if bitstr and bitstr[0] == 0:                     # 未用位数
        bitstr = bitstr[1:]
    tlv = _der_tlv(bitstr)                            # RSAPublicKey SEQUENCE
    seq = tlv[1]
    _, nbytes, j = _der_tlv(seq, 0)
    _, ebytes, _ = _der_tlv(seq, j)
    return int.from_bytes(nbytes, 'big'), int.from_bytes(ebytes, 'big')


_RSA_N, _RSA_E = _rsa_pub_from_spki(SSO_RSA_PUBKEY)


def rsa_encrypt(text):
    """等价于前端 encrypt(text, "base64", "utf8")：PKCS#1 v1.5 → base64。"""
    msg = text.encode('utf-8')
    k = (_RSA_N.bit_length() + 7) // 8
    if len(msg) > k - 11:
        raise ValueError('密码过长')
    ps = bytearray()
    while len(ps) < k - 3 - len(msg):
        b = os.urandom(1)[0]
        if b:                       # PKCS#1 v1.5 要求 PS 非零
            ps.append(b)
    em = b'\x00\x02' + bytes(ps) + b'\x00' + msg
    c = pow(int.from_bytes(em, 'big'), _RSA_E, _RSA_N)
    return base64.b64encode(c.to_bytes(k, 'big')).decode()


def load_token_file():
    if not os.path.exists(TOKEN_FILE):
        return {}
    try:
        with open(TOKEN_FILE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_token(tok):
    d = os.path.dirname(TOKEN_FILE)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
        json.dump(tok, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except Exception:
        pass


def norm_bearer(t):
    t = t.strip().strip('"').strip("'")
    if not t:
        return ''
    return t if t.lower().startswith('bearer') else 'bearer' + t


def strip_bearer(t):
    t = (t or '').strip().strip('"').strip("'")
    return t[6:].strip() if t.lower().startswith('bearer') else t


def parse_cookie_string(s):
    out = {}
    for part in s.split(';'):
        if '=' not in part:
            continue
        k, v = part.split('=', 1)
        out[k.strip()] = v.strip()
    return out


def token_from_devtools(path):
    """从浏览器导出的 HAR / .devtools 文件里提取 token（cookie 或 oauth 响应）。"""
    with open(path, encoding='utf-8', errors='replace') as f:
        raw = f.read()
    # 1) oauth 响应里的 access_token / refresh_token（取最后一个成功的）
    acc = ref = None
    for m in re.finditer(r'"access_token"\s*:\s*"([^"]+)"', raw):
        acc = m.group(1)
    for m in re.finditer(r'"refresh_token"\s*:\s*"([^"]+)"', raw):
        ref = m.group(1)
    if acc:
        return norm_bearer(acc), (strip_bearer(ref) if ref else '')
    # 2) cookie 里的 quectel_token
    m = re.search(r'quectel_token=([^;\s"]+)', raw)
    if m:
        r = re.search(r'quectel_refresh_token=([^;\s"]+)', raw)
        return norm_bearer(m.group(1)), (strip_bearer(r.group(1)) if r else '')
    raise SystemExit('没能从 %s 里找到 token（既没有 access_token 也没有 quectel_token）' % path)


# --------------------------------------------------------------------------- #
# 客户端
# --------------------------------------------------------------------------- #
class QMeeting(object):
    def __init__(self):
        self.tok = load_token_file()
        env_tok = os.environ.get('QMEETING_TOKEN')
        if env_tok:
            self.tok['access_token'] = norm_bearer(env_tok)
            if os.environ.get('QMEETING_REFRESH_TOKEN'):
                self.tok['refresh_token'] = strip_bearer(os.environ['QMEETING_REFRESH_TOKEN'])
        self._me = self.tok.get('me') or {}

    # -- token ---------------------------------------------------------------
    def _has_token(self):
        return bool(self.tok.get('access_token'))

    def _ensure(self, force=False):
        exp = int(self.tok.get('expires_at') or 0)
        need = force or not self._has_token() or (exp and exp - 120 <= _now())
        if not need:
            return
        if self.tok.get('refresh_token'):
            try:
                self._refresh()
                return
            except SystemExit:
                if not self._has_token():
                    raise
                # 刷新失败但有旧 token：继续用（可能还没真过期）
                return
        if not self._has_token():
            # 没 token 也没 refresh_token → 有账号就用，没账号就问
            self.login_with_account()
        elif exp and exp <= _now():
            self.login_with_account()

    def login_with_account(self, username=None, password=None):
        """账号登录：参数 > 环境变量 > 交互式询问。密码不落盘、不上传。"""
        u = username or os.environ.get('QMEETING_USERNAME')
        p = password or os.environ.get('QMEETING_PASSWORD')
        if not (u and p):
            if not sys.stdin or not sys.stdin.isatty():
                raise SystemExit(
                    '未登录。可以任选一种方式：\n'
                    '  1) 账号登录：python qmeeting.py login --ask\n'
                    '  2) HAR 文件：python qmeeting.py login --devtools <导出的文件>\n'
                    '  3) 直接给 token：python qmeeting.py login --token "bearerXXXX"')
            if not u:
                u = input('移远账号（邮箱或工号）: ').strip()
            if not p:
                p = getpass.getpass('密码（只用于换 token，不会保存）: ')
        if not u or not p:
            raise SystemExit('账号或密码为空，已取消。')
        self.password_login(u, p)

    def password_login(self, username, password):
        enc = rsa_encrypt(password)
        # 1) 登录前的 MFA 预检（前端必调，顺带能拿到更准确的错误信息）
        try:
            chk = requests.post(SSO + '/api/uaa/mfa-open/check', timeout=30,
                                headers={'content-type': 'application/json', 'user-agent': UA},
                                json={'username': username, 'password': enc}).json()
            data = chk.get('data') or {}
            if data.get('isPass') is False:
                raise SystemExit('账号或密码错误：%s' % (data.get('errorMessage') or chk.get('msg') or ''))
            if chk.get('success') is False and not data:
                raise SystemExit('账号或密码错误：%s' % (chk.get('msg') or 'mfa-open/check 失败'))
        except SystemExit:
            raise
        except Exception:
            pass  # 预检接口异常不影响主流程
        # 2) 换 token
        form = {
            'grant_type': 'password',
            'username': username,
            'password': enc,
            'scope': 'ui',
            'client_id': 'quectel',
            'client_secret': 'quectel',
            'auth_type': 'rsa_area',
        }
        try:
            j = requests.post(SSO + '/api/uaa/oauth/token', data=form, timeout=30,
                              headers={'Content-Type': 'application/x-www-form-urlencoded',
                                       'User-Agent': UA}).json()
        except Exception as e:
            raise SystemExit('登录请求失败：%s' % e)
        if not j.get('access_token'):
            code = j.get('code')
            if code in (102, '102'):
                raise SystemExit('这个账号开了 MFA（短信/邮件验证码），密码登录走不通。\n'
                                 '请改用浏览器登录后：qmeeting.py login --devtools <HAR文件>')
            raise SystemExit('登录失败：%s' % (j.get('msg') or j))
        self.tok['access_token'] = norm_bearer(j['access_token'])
        if j.get('refresh_token'):
            self.tok['refresh_token'] = strip_bearer(j['refresh_token'])
        self.tok['expires_at'] = _now() + int(j.get('expires_in') or 86000)
        self.tok['username'] = username          # 只记账号，不记密码
        self.tok.pop('me', None)
        save_token(self.tok)
        self._me = {}
        return self.me(refresh=True)

    def _refresh(self):
        url = SSO + '/api/uaa/oauth/token'
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': strip_bearer(self.tok['refresh_token']),
            'scope': 'ui',
            'client_id': 'quectel',
            'client_secret': 'quectel',
        }
        try:
            r = requests.post(url, data=data, timeout=30,
                              headers={'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': UA})
            j = r.json()
        except Exception as e:
            raise SystemExit('刷新 token 失败：%s' % e)
        if j.get('access_token'):
            self.tok['access_token'] = norm_bearer(j['access_token'])
            if j.get('refresh_token'):
                self.tok['refresh_token'] = strip_bearer(j['refresh_token'])
            self.tok['expires_at'] = _now() + int(j.get('expires_in') or 86000)
            save_token(self.tok)
            return
        raise SystemExit('刷新 token 失败：%s' % (j.get('msg') or j))

    # -- http ----------------------------------------------------------------
    def headers(self):
        return {
            'authorization': self.tok['access_token'],
            'content-type': 'application/json',
            'accept': 'application/json, text/plain, */*',
            'origin': BASE,
            'referer': BASE + '/scheduled',
            'user-agent': UA,
        }

    def request(self, method, path, payload=None, _retry=True):
        self._ensure()
        url = path if path.startswith('http') else BASE + path
        r = requests.request(method, url, headers=self.headers(), json=payload, timeout=40)
        if r.status_code == 401 and _retry:
            self._ensure(force=True)
            return self.request(method, path, payload, _retry=False)
        try:
            data = r.json()
        except Exception:
            raise ApiError('HTTP %s: %s' % (r.status_code, r.text[:300]))
        if isinstance(data, dict) and data.get('code') not in (0, '0', None):
            raise ApiError(data.get('msg') or '接口返回错误', data.get('code'), data)
        if r.status_code >= 400:
            raise ApiError('HTTP %s: %s' % (r.status_code, data), r.status_code, data)
        return data.get('data') if isinstance(data, dict) else data

    def get(self, path):
        return self.request('GET', path)

    def post(self, path, payload=None):
        return self.request('POST', path, payload if payload is not None else {})

    # -- 我的信息 -------------------------------------------------------------
    def me(self, refresh=False):
        if self._me and not refresh:
            return self._me
        data = self.get('/api/org/employee/getMyInfo?fileId=')
        emp = (data or {}).get('employeeVo') or {}
        self._me = {
            'userId': emp.get('userId'),
            'fullName': ('%s %s' % (emp.get('enName') or '', emp.get('legalName') or '')).strip(),
            'legalName': emp.get('legalName'),
            'enName': emp.get('enName'),
            'deptName': emp.get('deptName'),
            'workEmail': emp.get('workEmail'),
        }
        self.tok['me'] = self._me
        save_token(self.tok)
        return self._me

    # -- 办公区域 -------------------------------------------------------------
    def area_tree(self):
        return self.post('/api/meet/office-area/list-treeByUser', {}) or []

    @staticmethod
    def flatten_areas(tree):
        out = []

        def walk(nodes, parents):
            for n in nodes or []:
                path = parents + [n.get('name') or '']
                out.append({
                    'id': str(n.get('id')),
                    'name': n.get('name') or '',
                    'path': '-'.join([p for p in path if p]),
                    'level': n.get('level'),
                    'leaf': n.get('leaf'),
                })
                walk(n.get('children'), path)

        walk(tree, [])
        return out

    def area_ids(self, keyword=None):
        areas = self.flatten_areas(self.area_tree())
        if not keyword:
            return [a['id'] for a in areas], areas
        kw = keyword.lower()
        hit = [a for a in areas if kw in a['path'].lower()]
        if not hit:
            raise SystemExit('没有匹配「%s」的办公区域。可用区域：\n%s' % (
                keyword, '\n'.join('  %s  %s' % (a['id'], a['path']) for a in areas)))
        # 命中的区域 + 其子区域（path 以命中 path 开头）
        ids = {a['id'] for a in hit}
        for a in areas:
            for h in hit:
                if a['path'].startswith(h['path'] + '-'):
                    ids.add(a['id'])
        return sorted(ids, key=lambda x: int(x) if x.isdigit() else 0), areas

    def my_site(self):
        """我所在的办公园区（system/area，如 FoShan）。"""
        try:
            a = self.get('/api/meet/system/area') or {}
            return a.get('name') or ''
        except Exception:
            return ''

    def default_area_ids(self, keyword=None, all_sites=False):
        """--area 优先；否则默认限定在我自己的园区；all_sites 时返回全部区域。"""
        if keyword:
            return self.area_ids(keyword)
        if all_sites:
            return self.area_ids()
        site = self.my_site()
        if site:
            try:
                ids, areas = self.area_ids(site)
                if ids:
                    return ids, areas
            except SystemExit:
                pass
        return self.area_ids()

    # -- 会议室 ---------------------------------------------------------------
    def recommend_rooms(self, office_ids, start_ms, end_ms):
        """指定时间段空闲/占用会议室。"""
        data = self.post('/api/meet/recommend/listByUser', {
            'officeAreaIds': [str(i) for i in office_ids],
            'startStamp': start_ms,
            'endStamp': end_ms,
        }) or {}
        return data.get('ableRooms') or [], data.get('unableRooms') or []

    def room_ids_in_scope(self, day, office_ids):
        """某个区域下的会议室 roomId 集合。
        recommend/listByUser 不按 officeAreaIds 过滤，只有 calendarView 才是区域级的，
        所以用日历视图反查本区域有哪些会议室。"""
        try:
            rooms = self.calendar(day, office_ids)
        except Exception:
            return set()
        return {str(r.get('roomId')) for r in rooms if r.get('roomId')}

    def calendar(self, day, office_ids=None, room_name='', facility_ids=None,
                 start='07:00', end='23:59'):
        """会议室日历（每个会议室当天的占用/空闲时段）。"""
        if office_ids is None:
            office_ids, _ = self.area_ids()
        return self.post('/api/meet/room/calendarView', {
            'officeAreaIds': [str(i) for i in office_ids],
            'facilityIds': facility_ids or [],
            'periodOfTimeStart': '',
            'periodOfTimeEnd': '',
            'roomName': room_name or '',
            'dateStr': day,
            'fountTimeStart': start,
            'fountTimeEnd': end,
        }) or []

    # -- 会议室详情 / 图片 -----------------------------------------------------
    def room_detail(self, room_id):
        """单个会议室详情：名称/容量/类型/区域/设施/照片/位置导航图/门口屏编号。"""
        return self.get('/api/meet/room/detail/%s' % str(room_id))

    def find_room(self, key, day=None):
        """roomId 原样返回；否则按名称关键词在会议室日历里找（唯一即返回）。"""
        key = str(key).strip()
        if key.isdigit():
            return key
        day = day or today_str()
        rooms = self.calendar(day, self.area_ids()[0])
        kw = key.lower()
        hit = [r for r in rooms if kw in (r.get('name') or '').lower()
               or kw in (r.get('cnName') or '').lower()]
        if not hit:
            raise SystemExit('没有匹配「%s」的会议室' % key)
        exact = [r for r in hit if (r.get('name') or '').lower() == kw]
        if len(exact) == 1:
            return str(exact[0]['roomId'])
        if len(hit) == 1:
            return str(hit[0]['roomId'])
        raise SystemExit('「%s」匹配到多个会议室，请用 roomId 或更完整的名称：\n%s' % (
            key, '\n'.join('  %s  %s' % (r.get('roomId'), r.get('name')) for r in hit[:20])))

    def room_media(self, room_id):
        """会议室信息 + 照片 + 位置导航图（图片是公网 URL，无需 token）。"""
        d = self.room_detail(room_id) or {}
        base = d.get('roomBase') or {}
        head = d.get('roomHeard') or {}
        fac = d.get('roomFacility') or {}
        info = {
            'roomId': str(room_id),
            'name': head.get('name') or '',
            'cnName': head.get('cnName') or '',
            'capacity': base.get('seatingCapacity'),
            'roomType': (base.get('typeDimensionDto') or {}).get('name') or '',
            'area': (base.get('officeAreaDto') or {}).get('name') or '',
            'facilities': [f.get('name') for f in (fac.get('facilityList') or []) if f.get('name')],
            'teleconference': fac.get('teleconferenceType') or '',
            'zoomAccount': fac.get('zoomAccount') or '',
            'zoomLink': fac.get('zoomLink') or '',
            'platform': ((fac.get('meetingRoomResourceReserveVo') or {}).get('platformTypeName') or ''),
            'panels': [p.get('exhibitionPanelCode') for p in (fac.get('panelInfoList') or [])
                       if p.get('exhibitionPanelCode')],
            'photos': [],
            'guide': None,
        }
        for f in base.get('imageFiles') or []:
            if f.get('link'):
                info['photos'].append({'name': f.get('originalName') or f.get('name') or 'photo.jpg',
                                       'url': f.get('link')})
        g = base.get('locationGuideImageFile') or {}
        if g.get('link'):
            info['guide'] = {'name': g.get('originalName') or g.get('name') or 'guide.jpg',
                             'url': g.get('link')}
        return info

    def booking_step(self):
        cfg = self.get('/api/meet/system/config') or {}
        slot = cfg.get('bookingTimeSlotConfig') or {}
        return {
            'step': slot.get('step') or 5,
            'open': cfg.get('openBookingConfig') or {},
            'max_future_days': (cfg.get('dateRangeConfig') or {}).get('restrictFutureBookingDay'),
            'timezone': cfg.get('timeZone'),
        }

    # -- 我的会议 -------------------------------------------------------------
    def my_bookings(self, status='MY_BOOKING', is_filter_end='Y', extra=None):
        body = {'meetingBookingTimeStatus': status, 'isFilterEnd': is_filter_end}
        if extra:
            body.update(extra)
        return self.post('/api/meet/booking-user/list', body) or []

    def booking_detail(self, booking_id):
        return self.get('/api/meet/appointed/detail/%s' % booking_id)

    def booking_participants(self, booking_id):
        return self.get('/api/meet/appointed/participant/%s' % booking_id) or []

    # -- 人员 -----------------------------------------------------------------
    def search_user(self, keyword, size=10):
        data = self.post('/api/org/employee/page', {
            'workStatus': 'IN_SERVICE',
            'pageNumber': 1,
            'pageSize': size,
            'name': keyword,
            'key': keyword,
        }) or {}
        return data.get('records') or []

    def users_by_ids(self, ids):
        """按 userId 精确查员工（不要用姓名搜索，userId 会被当成名字匹配到别人）。"""
        ids = [str(i) for i in ids if i]
        if not ids:
            return {}
        try:
            recs = self.post('/api/org/employee/selectEmpBaseInfoByUserIds', ids) or []
        except ApiError:
            recs = []
        out = {}
        for r in recs:
            name = ('%s %s' % (r.get('enName') or '', r.get('legalName') or '')).strip()
            out[str(r.get('userId'))] = name or str(r.get('userId'))
        return out

    def resolve_users(self, tokens):
        """邮箱 / 姓名 / userId -> [{userId, name}]；同名多人时报错要求更精确。"""
        out = []
        for t in tokens or []:
            t = t.strip()
            if not t:
                continue
            if t.isdigit():
                hit = self.users_by_ids([t]).get(t)
                out.append({'userId': t, 'name': hit or t})
                continue
            recs = self.search_user(t)
            picked = [r for r in recs
                      if t.lower() in (r.get('workEmail') or '').lower()
                      or t.lower() == (r.get('loginName') or '').lower()
                      or t in (r.get('legalName') or '')
                      or t.lower() in (r.get('enName') or '').lower()]
            recs = picked or recs
            if not recs:
                raise SystemExit('找不到员工「%s」' % t)
            if len(recs) > 1 and t.lower() not in [(r.get('workEmail') or '').lower() for r in recs]:
                names = '\n'.join('  %s  %s  %s' % (r.get('userId'), r.get('enName'),
                                                    r.get('workEmail')) for r in recs[:10])
                raise SystemExit('「%s」匹配到多人，请用邮箱或 userId 指定：\n%s' % (t, names))
            r = recs[0]
            out.append({'userId': r['userId'],
                        'name': '%s %s' % (r.get('enName') or '', r.get('legalName') or '')})
        # 去重 + 自动包含自己
        me = self.me()
        dedup = {}
        if me.get('userId'):
            dedup[me['userId']] = me.get('fullName') or 'me'
        for u in out:
            dedup[u['userId']] = u['name']
        return [{'userId': k, 'name': v} for k, v in dedup.items()]

    # -- 预订 / 取消 -----------------------------------------------------------
    PLATFORM_MAP = {'飞书': 'LARK', 'Lark': 'LARK', 'Teams': 'TEAMS', 'Zoom': 'ZOOM',
                    '腾讯会议': 'TENCENT', 'Tencent': 'TENCENT'}

    def build_booking(self, room, participants, day, start, end, theme=None,
                      explanation='', reminder=15, platform=None):
        me = self.me()
        uid = me['userId']
        start_ms, end_ms = to_ms(day, start), to_ms(day, end)
        if end_ms <= start_ms:
            raise SystemExit('结束时间必须晚于开始时间')
        plat = platform or self.PLATFORM_MAP.get(room.get('teleconferenceType') or '', '')
        # participants 既可以传原始 token（邮箱/姓名），也可以传已解析的 [{userId,name}]
        if participants and isinstance(participants[0], dict):
            users = participants
        elif participants:
            users = self.resolve_users(participants)
        else:
            users = [{'userId': uid, 'name': me['fullName']}]
        return {
            'id': '',
            'isSingle': False,
            'theme': (theme or '%s发起的会议' % me['fullName']).strip(),
            'meetingDate': day,
            'startTime': start_ms,
            'endTime': end_ms,
            'enableMeetingRoomZoom': 'Y',
            'zoomMeetingRoomId': '',
            'zoomLink': '',
            'chooseZoomMeetingRoomId': str(room.get('roomId')),
            'ruleType': 'SINGLE',
            'isRecurrenceMeeting': 'N',
            'recurrenceRule': None,
            'recurrenceMeetingCode': '',
            'reminderTimeBeforeStart': int(reminder),
            'explanation': explanation or '',
            'fileIdList': [],
            'bookingUser': {'userId': uid, 'userFullName': me['fullName'], 'deptNameList': None},
            'bookingUserId': uid,
            'isPublicConference': 'N',
            'enableParticipantManagement': 'N',
            'enableCheckInNoAuthWithExhibitionPanel': 'Y',
            'enableEndInAdvanceNoAuthWithExhibitionPanel': 'Y',
            'cancellationReason': '',
            'participantsNum': len(users),
            'participants': [u['userId'] for u in users],
            'roomIds': [str(room.get('roomId'))],
            'meetingPassword': '',
            'muteEnableJoin': 'Y',
            'autoCloudRecord': 'N',
            'useRoomMeetingCode': False,
            'platformType': plat,
            'enablePassword': 'N',
            'visibleToParticipants': 'N',
            'roomRequired': 'Y',
            'bookingSource': 'USER',
            'hasRoom': 'Y',
            'useOnlineMeeting': 'Y',
            'simplerBooking': 'N',
        }

    def create_booking(self, payload):
        return self.post('/api/meet/appointed/create', payload)

    def cancel_booking(self, booking_id, remark='', flag=False):
        return self.post('/api/meet/appointed/cancelBooking', {
            'bookingId': str(booking_id),
            'remark': remark or '',
            'flag': bool(flag),
        })


# --------------------------------------------------------------------------- #
# 选择会议室
# --------------------------------------------------------------------------- #
def pick_room(qm, key, day, start, end, area=None):
    """按 roomId 或名称关键词，在指定时间段挑一个空闲会议室。"""
    office_ids, _ = qm.default_area_ids(area)
    able, _unable = qm.recommend_rooms(office_ids, to_ms(day, start), to_ms(day, end))
    scope = qm.room_ids_in_scope(day, office_ids)
    if scope:
        able = [r for r in able if str(r.get('roomId')) in scope]
    if not able:
        raise SystemExit('该时间段没有空闲会议室')
    key = str(key).strip()
    if key.isdigit():
        hit = [r for r in able if str(r.get('roomId')) == key]
    else:
        kw = key.lower()
        hit = [r for r in able if kw in (r.get('name') or '').lower()
               or kw in (r.get('cnName') or '').lower()]
    if not hit and not key.isdigit():
        # 也许被占了 -> 给占用信息
        raise SystemExit('时间段内没有匹配「%s」的空闲会议室。\n可选：\n%s' % (
            key, '\n'.join('  %s  %s  (%s人)' % (r.get('roomId'), r.get('name'),
                                                r.get('seatingCapacity')) for r in able[:25])))
    if len(hit) > 1:
        raise SystemExit('「%s」匹配到多个会议室，请用 roomId 或更完整的名称：\n%s' % (
            key, '\n'.join('  %s  %s  (%s人)' % (r.get('roomId'), r.get('name'),
                                                r.get('seatingCapacity')) for r in hit[:25])))
    return hit[0]


def room_label(r):
    return '%s  %s  %s' % (
        from_ms(r.get('startTime'), '%m-%d %H:%M') if r.get('startTime') else '',
        r.get('theme') or '',
        ','.join((x.get('roomName') or '') for x in (r.get('roomBaseInfoVos') or [])))


# --------------------------------------------------------------------------- #
# 输出
# --------------------------------------------------------------------------- #
def print_rooms(rooms):
    if not rooms:
        print('（无）')
        return
    rows = [('roomId', '会议室', '容量', '设施', '平台', '区域', '当前状态')]
    for r in rooms:
        rows.append((
            str(r.get('roomId')),
            r.get('name') or '',
            str(r.get('seatingCapacity') or ''),
            ','.join(r.get('facilities') or []),
            r.get('teleconferenceType') or '',
            r.get('officeName') or '',
            '占用' if r.get('_busy') else '空闲',
        ))
    print_table(rows)


def print_table(rows):
    widths = [max(_w(r[i]) for r in rows) for i in range(len(rows[0]))]
    for idx, r in enumerate(rows):
        line = '  '.join(_pad(c, widths[i]) for i, c in enumerate(r)).rstrip()
        print(line)
        if idx == 0:
            print('  '.join('-' * w for w in widths))


def _w(s):
    s = str(s)
    return sum(2 if ord(ch) > 127 else 1 for ch in s)


def _pad(s, width):
    s = str(s)
    return s + ' ' * max(0, width - _w(s))


def safe_name(name, default='file'):
    """把 originalName 变成安全的本地文件名（保留扩展名）。"""
    name = (name or default).strip().replace('\\', '_').replace('/', '_')
    name = re.sub(r'[<>:"|?*\x00-\x1f]', '_', name)
    name = re.sub(r'\s+', ' ', name).strip(' .')
    return name or default


def download_file(url, dest):
    """下载图片到本地（qos.quectel.com 的图片是公开 URL，不需要 token）。"""
    r = requests.get(url, timeout=90, headers={'user-agent': UA})
    if r.status_code >= 400:
        raise ApiError('下载失败 HTTP %s: %s' % (r.status_code, url))
    d = os.path.dirname(dest)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    with open(dest, 'wb') as f:
        f.write(r.content)
    return len(r.content)


# --------------------------------------------------------------------------- #
# 命令
# --------------------------------------------------------------------------- #
def cmd_login(a):
    tok = load_token_file()
    if a.devtools:
        acc, ref = token_from_devtools(a.devtools)
    elif a.cookie:
        c = parse_cookie_string(a.cookie)
        acc = norm_bearer(c.get('quectel_token', ''))
        ref = strip_bearer(c.get('quectel_refresh_token', ''))
    elif a.token:
        acc, ref = norm_bearer(a.token), strip_bearer(a.refresh_token or '')
    else:
        # 没有任何凭证来源 → 账号登录（有账号就用，没账号就问）
        qm = QMeeting()
        me = qm.login_with_account(a.username, a.password)
        print('登录成功：%s (userId=%s, %s)' % (me['fullName'], me['userId'], me['deptName']))
        print('token 文件：%s（只存 token，不存密码）' % TOKEN_FILE)
        return me
    if not acc:
        raise SystemExit('没解析到 access_token')
    tok.update({'access_token': acc, 'refresh_token': ref or tok.get('refresh_token', ''),
                'expires_at': _now() + 86000,
                'saved_at': datetime.datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')})
    save_token(tok)
    qm = QMeeting()
    me = qm.me(refresh=True)
    print('登录成功：%s (userId=%s, %s)' % (me['fullName'], me['userId'], me['deptName']))
    print('token 文件：%s' % TOKEN_FILE)
    if not tok.get('refresh_token'):
        print('提示：没有 refresh_token，24 小时后需要重新 login。')
    return me


def cmd_whoami(a):
    qm = QMeeting()
    me = qm.me(refresh=True)
    print(json.dumps(me, ensure_ascii=False, indent=2) if a.json else
          '%s (userId=%s)\n部门: %s\n邮箱: %s' % (me['fullName'], me['userId'],
                                              me['deptName'], me['workEmail']))
    return me


def cmd_areas(a):
    qm = QMeeting()
    areas = qm.flatten_areas(qm.area_tree())
    if a.json:
        print(json.dumps(areas, ensure_ascii=False, indent=2))
        return areas
    rows = [('areaId', '层级', '路径')]
    for x in areas:
        rows.append((x['id'], str(x['level']), x['path'] + ('  *' if x['leaf'] == 'Y' else '')))
    print_table(rows)
    print('\n* = 叶子节点（可直接预订的楼层/区域）')
    return areas


def cmd_rooms(a):
    qm = QMeeting()
    day = parse_day(a.date)
    office_ids, _ = qm.default_area_ids(a.area, all_sites=a.sites)
    able, unable = qm.recommend_rooms(office_ids, to_ms(day, a.start), to_ms(day, a.end))
    for r in unable:
        r['_busy'] = True
    rooms = able + (unable if a.all else [])
    if not a.sites:
        scope = qm.room_ids_in_scope(day, office_ids)
        if scope:
            rooms = [r for r in rooms if str(r.get('roomId')) in scope]
            able = [r for r in able if str(r.get('roomId')) in scope]
            unable = [r for r in unable if str(r.get('roomId')) in scope]
    if a.room:
        kw = a.room.lower()
        rooms = [r for r in rooms if kw in (r.get('name') or '').lower()
                 or kw in (r.get('cnName') or '').lower()]
    if a.min_capacity:
        rooms = [r for r in rooms if int(r.get('seatingCapacity') or 0) >= a.min_capacity]
    if a.facility:
        rooms = [r for r in rooms if any(a.facility in (f or '') for f in (r.get('facilities') or []))]
    if a.platform:
        rooms = [r for r in rooms if a.platform in (r.get('teleconferenceType') or '')]
    rooms.sort(key=lambda r: (r.get('_busy') or False, r.get('name') or ''))
    if a.json:
        print(json.dumps(rooms, ensure_ascii=False, indent=2))
        return rooms
    print('# %s %s-%s  空闲 %d / 占用 %d（%s）' % (day, a.start, a.end, len(able), len(unable),
                                                 '含占用' if a.all else '仅空闲'))
    print_rooms(rooms[:a.limit] if a.limit else rooms)
    return rooms


def cmd_calendar(a):
    qm = QMeeting()
    day = parse_day(a.date)
    office_ids, _ = qm.default_area_ids(a.area, all_sites=a.sites)
    rooms = qm.calendar(day, office_ids, room_name=a.room or '')
    if a.room:
        kw = a.room.lower()
        rooms = [r for r in rooms if kw in (r.get('name') or '').lower()]
    if a.json:
        print(json.dumps(rooms, ensure_ascii=False, indent=2))
        return rooms
    print('# %s 会议室日历（%d 间）' % (day, len(rooms)))
    for r in rooms:
        busy = r.get('using') or []
        if busy:
            slots = '; '.join('%s-%s %s' % (b.get('start'), b.get('end'),
                                            b.get('bookingName') or '') for b in busy)
        else:
            slots = '全天空闲'
        print('%s\t%s\t%s人\t%s' % (r.get('roomId'), r.get('name'),
                                   r.get('seatingCapacity'), slots))
    return rooms


def cmd_mine(a):
    qm = QMeeting()
    rows = qm.my_bookings(a.status, 'N' if a.include_finished else 'Y')
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return rows
    if not rows:
        print('（没有会议）')
        return rows
    table = [('bookingId', '主题', '开始', '结束', '会议室', '状态', '可取消')]
    for x in rows:
        table.append((
            str(x.get('id')),
            (x.get('theme') or '')[:28],
            from_ms(x.get('startTime')),
            from_ms(x.get('endTime'), '%H:%M'),
            ','.join(i.get('roomName') or '' for i in (x.get('roomBaseInfoVos') or [])),
            x.get('responseStateName') or ('已结束' if int(x.get('endTime') or 0) < time.time() * 1000 else ''),
            x.get('cancelButton') or '',
        ))
    print_table(table)
    return rows


def cmd_detail(a):
    qm = QMeeting()
    d = qm.booking_detail(a.booking_id)
    parts = qm.booking_participants(a.booking_id)
    if a.json:
        print(json.dumps({'detail': d, 'participants': parts}, ensure_ascii=False, indent=2))
        return d
    rooms = d.get('roomBaseInfoVos') or []
    print('会议编号 : %s' % d.get('code'))
    print('bookingId: %s' % d.get('id'))
    print('主题     : %s' % d.get('theme'))
    print('时间     : %s ~ %s' % (from_ms(d.get('startTime'), '%Y-%m-%d %H:%M'),
                                 from_ms(d.get('endTime'), '%H:%M')))
    print('会议室   : %s' % ','.join(r.get('commonName') or r.get('roomName') or '' for r in rooms))
    for r in rooms:
        if r.get('zoomLink'):
            print('线上会议 : %s (ID %s)' % (r.get('zoomLink'), r.get('zoomCode')))
    print('说明     : %s' % (d.get('explanation') or ''))
    print('状态     : %s' % (d.get('cancellationReason') and ('已取消:' + d['cancellationReason']) or '正常'))
    print('参会人   : %s' % ', '.join(p.get('partUserName') or '' for p in parts))
    if getattr(a, 'save', None):
        files = []
        for r in rooms:
            rid = r.get('roomId')
            if not rid:
                continue
            try:
                files += _save_media(qm, qm.room_media(rid),
                                     os.path.join(a.save, str(rid)), guide_only=False)
            except Exception as e:
                print('  会议室 %s 图片下载失败：%s' % (rid, e), file=sys.stderr)
        if files:
            print('\n图片已保存 %d 个：' % len(files))
            for f in files:
                print('  ' + f)
        else:
            print('\n（该会议没有可下载的会议室照片/导航图）')
    return d


def cmd_room(a):
    """会议室详情 + 照片 + 位置导航图。"""
    qm = QMeeting()
    rid = qm.find_room(a.room)
    info = qm.room_media(rid)
    if a.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print('会议室 : %s (roomId=%s)' % (info['name'], info['roomId']))
        print('区域   : %s   类型: %s   容量: %s 人' % (info['area'], info['roomType'],
                                                  info['capacity']))
        if info['facilities']:
            print('设施   : %s' % ', '.join(info['facilities']))
        if info['platform']:
            print('资源平台: %s' % info['platform'])
        if info['teleconference'] or info['zoomAccount']:
            print('房间会议: %s %s %s' % (info['teleconference'] or '-',
                                        info['zoomAccount'] or '',
                                        info['zoomLink'] or ''))
        if info['panels']:
            print('门口屏 : %s' % ', '.join(info['panels']))
        print('照片   : %d 张' % len(info['photos']))
        for i, p in enumerate(info['photos'], 1):
            print('  %d. %-28s %s' % (i, p['name'], p['url']))
        if info['guide']:
            print('导航图 : %-28s %s' % (info['guide']['name'], info['guide']['url']))
        else:
            print('导航图 : （没有配置）')
    if a.save:
        files = _save_media(qm, info, a.save, guide_only=False)
        print('\n已保存 %d 个文件：' % len(files))
        for f in files:
            print('  ' + f)
    return info


def _save_media(qm, info, out_dir, guide_only=False):
    """把照片/导航图下载到 out_dir，返回本地绝对路径列表。"""
    targets = []
    if not guide_only:
        targets += [(p['name'], p['url']) for p in info['photos']]
    if info.get('guide'):
        targets.append((info['guide']['name'], info['guide']['url']))
    files = []
    room_tag = '%s-%s' % (info['roomId'], safe_name(info.get('name') or 'room', 'room'))
    for idx, (name, url) in enumerate(targets, 1):
        dest = os.path.join(out_dir, '%s_%02d-%s' % (room_tag, idx, safe_name(name)))
        download_file(url, dest)
        files.append(os.path.abspath(dest))
    return files


def cmd_images(a):
    """批量下载会议室照片 + 位置导航图。"""
    qm = QMeeting()
    out_dir = a.out or os.path.join(os.getcwd(), 'room-images')
    all_files = []
    for key in a.rooms:
        rid = qm.find_room(key)
        info = qm.room_media(rid)
        sub = os.path.join(out_dir, '%s-%s' % (rid, safe_name(info['name'], 'room')))
        files = _save_media(qm, info, sub, guide_only=a.guide_only)
        all_files += files
        print('%-6s %-30s 照片 %d 张%s → %s' % (
            rid, info['name'], len(info['photos']),
            '（跳过）' if a.guide_only else '', os.path.abspath(sub)))
        for f in files:
            print('   ' + f)
    if not all_files:
        print('没有可下载的图片（该会议室没配照片/导航图）')
    return all_files


def cmd_book(a):
    qm = QMeeting()
    day = parse_day(a.date)
    # 1) 校验时间片
    cfg = qm.booking_step()
    step = cfg.get('step') or 5
    for t in (a.start, a.end):
        h, m = [int(x) for x in t.split(':')]
        if (h * 60 + m) % step:
            print('警告：开始/结束时间不在 %d 分钟刻度上（平台步长 %d 分钟）' % (step, step), file=sys.stderr)
    # 2) 选会议室（确认空闲）
    room = pick_room(qm, a.room, day, a.start, a.end, area=a.area)
    # 3) 组包
    users = qm.resolve_users(a.participant)  # 无 --participant 时只有自己
    payload = qm.build_booking(room, users, day, a.start, a.end,
                               theme=a.theme, explanation=a.explain or '',
                               reminder=a.reminder, platform=a.platform)
    print('# 会议室 : %s (roomId=%s, %s人, %s)' % (room.get('name'), room.get('roomId'),
                                                 room.get('seatingCapacity'),
                                                 room.get('teleconferenceType') or '无线上会议'))
    print('# 时间   : %s %s-%s   主题: %s' % (day, a.start, a.end, payload['theme']))
    print('# 参会人 : %s' % ', '.join('%s(%s)' % (u['name'], u['userId']) for u in users))
    if a.dry_run:
        print('\n--- payload (dry-run，未提交) ---')
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return payload
    # 4) 提交
    data = qm.create_booking(payload) or {}
    booking_id = data.get('bookingId')
    errors = data.get('error') or []
    if not booking_id:
        print('\n预订失败，平台没有返回 bookingId。返回：%s' % json.dumps(data, ensure_ascii=False)[:500])
        return data
    # 平台的 error 字段不可靠（实测会返回“xx冲突”但会议实际已创建），以详情接口为准
    ok_rooms = []
    try:
        d = qm.booking_detail(booking_id) or {}
        ok_rooms = [r.get('commonName') or r.get('roomName') or '' for r in (d.get('roomBaseInfoVos') or [])]
    except Exception:
        pass
    if errors:
        print('\n注意：平台返回提示 %s' % '; '.join(errors))
    if ok_rooms:
        print('预订成功 bookingId=%s，会议室 %s，%s %s-%s' % (
            booking_id, ','.join(ok_rooms), day, a.start, a.end))
        print('撤销：python qmeeting.py cancel %s --remark "..." --yes' % booking_id)
    else:
        print('bookingId=%s 已生成，但没查到会议室信息，请用 detail %s 核实' % (booking_id, booking_id))
    return data


def cmd_cancel(a):
    qm = QMeeting()
    d = qm.booking_detail(a.booking_id) if a.show else None
    if d and not a.yes:
        print('即将取消：%s | %s ~ %s | %s' % (
            d.get('theme'), from_ms(d.get('startTime'), '%Y-%m-%d %H:%M'),
            from_ms(d.get('endTime'), '%H:%M'),
            ','.join(r.get('commonName') or '' for r in (d.get('roomBaseInfoVos') or []))))
    if not a.yes:
        print('未执行。确认要取消请加 --yes')
        return None
    ok = qm.cancel_booking(a.booking_id, a.remark or '')
    print('已取消 %s' % a.booking_id if ok else '取消结果：%s' % ok)
    return ok


def cmd_config(a):
    qm = QMeeting()
    print(json.dumps(qm.booking_step(), ensure_ascii=False, indent=2))


# --------------------------------------------------------------------------- #
def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if '--json' in argv:  # 允许 --json 写在子命令之后
        argv = ['--json'] + [x for x in argv if x != '--json']
    p = argparse.ArgumentParser(prog='qmeeting', description='Quectel 会议室 CLI')
    p.add_argument('--json', action='store_true', help='输出原始 JSON')
    sub = p.add_subparsers(dest='cmd', required=True)

    s = sub.add_parser('login', help='登录：账号 / token / cookie / HAR 文件')
    s.add_argument('-u', '--username', help='移远账号（邮箱或工号）；不传则询问')
    s.add_argument('-p', '--password', help='密码；不传则交互式询问（推荐，避免留在命令历史）')
    s.add_argument('--ask', action='store_true', help='强制用账号密码登录（交互式询问）')
    s.add_argument('--token')
    s.add_argument('--refresh-token')
    s.add_argument('--cookie', help='形如 "quectel_token=bearer...; quectel_refresh_token=..."')
    s.add_argument('--devtools', help='浏览器导出的 HAR/.devtools 文件')
    s.set_defaults(func=cmd_login)

    s = sub.add_parser('whoami', help='当前登录人与 userId')
    s.set_defaults(func=cmd_whoami)

    s = sub.add_parser('areas', help='我可用的办公区域/楼层（拿 areaId）')
    s.set_defaults(func=cmd_areas)

    s = sub.add_parser('rooms', help='某时间段可用会议室')
    s.add_argument('--date', default='today')
    s.add_argument('--start', default='09:00')
    s.add_argument('--end', default='10:00')
    s.add_argument('--area', help='办公区域关键词（如 3F / B10 / FoShan）')
    s.add_argument('--room', help='会议室名称关键词')
    s.add_argument('--min-capacity', type=int)
    s.add_argument('--facility', help='设施关键词（飞书/TV/Projector/Zoom）')
    s.add_argument('--platform', help='线上会议平台关键词（飞书/Teams/Zoom）')
    s.add_argument('--all', action='store_true', help='同时列出被占用的')
    s.add_argument('--sites', action='store_true', help='不限本园区，查全部园区')
    s.add_argument('--limit', type=int, default=40)
    s.set_defaults(func=cmd_rooms)

    s = sub.add_parser('calendar', help='会议室当天日历（谁占了哪段）')
    s.add_argument('--date', default='today')
    s.add_argument('--area')
    s.add_argument('--room')
    s.add_argument('--sites', action='store_true', help='不限本园区，查全部园区')
    s.set_defaults(func=cmd_calendar)

    s = sub.add_parser('mine', help='我的会议列表')
    s.add_argument('--status', default='MY_BOOKING',
                   choices=['MY_BOOKING', 'MY_INVITED', 'WEEK', 'DAY', 'MONTHLY',
                            'ALL_MEETING', 'DEFAULT_MONTH'])
    s.add_argument('--include-finished', action='store_true')
    s.set_defaults(func=cmd_mine)

    s = sub.add_parser('detail', help='会议详情')
    s.add_argument('booking_id')
    s.add_argument('--save', help='顺带把这个会议的会议室照片/导航图下载到这里')
    s.set_defaults(func=cmd_detail)

    s = sub.add_parser('room', help='会议室详情：照片 + 位置导航图')
    s.add_argument('room', help='roomId 或名称关键词（如 Malaga / 306-FS-B10-3F-Male）')
    s.add_argument('--save', help='把照片和导航图下载到这个目录')
    s.set_defaults(func=cmd_room)

    s = sub.add_parser('images', help='批量下载会议室照片和位置导航图')
    s.add_argument('rooms', nargs='+', help='roomId 或名称关键词，可多个')
    s.add_argument('--out', help='输出目录（默认 ./room-images）')
    s.add_argument('--guide-only', action='store_true', help='只下位置导航图')
    s.set_defaults(func=cmd_images)

    s = sub.add_parser('book', help='预订会议室')
    s.add_argument('--room', required=True, help='roomId 或名称关键词')
    s.add_argument('--date', default='today')
    s.add_argument('--start', required=True)
    s.add_argument('--end', required=True)
    s.add_argument('--theme')
    s.add_argument('--explain', default='')
    s.add_argument('--participant', action='append', default=[], help='姓名/邮箱/userId，可重复')
    s.add_argument('--reminder', type=int, default=15, help='提前提醒分钟数')
    s.add_argument('--platform', help='LARK/TEAMS/ZOOM/TENCENT，默认按会议室推断')
    s.add_argument('--area')
    s.add_argument('--dry-run', action='store_true', help='只打印 payload，不提交')
    s.set_defaults(func=cmd_book)

    s = sub.add_parser('cancel', help='取消会议')
    s.add_argument('booking_id')
    s.add_argument('--remark', default='')
    s.add_argument('--yes', action='store_true', help='确认执行')
    s.add_argument('--show', action='store_true', default=True)
    s.set_defaults(func=cmd_cancel)

    s = sub.add_parser('config', help='平台预订规则（步长/开放时间/可预订天数）')
    s.set_defaults(func=cmd_config)

    a = p.parse_args(argv)
    try:
        a.func(a)
    except ApiError as e:
        print('接口错误：%s' % e, file=sys.stderr)
        if e.payload:
            print(json.dumps(e.payload, ensure_ascii=False)[:800], file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
