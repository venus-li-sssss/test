# -*- coding: utf-8 -*-
"""飞书云盘「写」能力：建目录 / 上传文件（应用身份 bot，免扫码，支持断点续传）。

配套 feishu_dl.py（只读：搜/列/下载），这里补上写：

    python feishu_upload.py mkdir 手机APP --under GiihfUC0tlDJGHdTriDcH4ljnUz
    python feishu_upload.py upload "D:\\x\\九号出行APP_v6.10.12.apk" --folder OfccfrVr5lcFVBd6i58c336QnCc
    python feishu_upload.py upload x.zip --folder https://quectel.feishu.cn/drive/folder/XXXX
    python feishu_upload.py upload x.apk --folder-json      # 只输出 file_token / url（给脚本用）

协议要点（实测踩坑，别改回去）：
  1. ≤20MB 用 upload_all；>20MB 必须 upload_prepare → upload_part → upload_finish 分片。
  2. **分片序号字段名是 `seq`（不是 seq_id），并且从 0 开始**：
     写成 seq_id 服务端不报错、静默忽略 → 最后 upload_finish 报 `1062010 block missing`。
     写成 1 起 → 1062009 actual size inconsistent / 1062011 block num out of bounds。
  3. 分片大小固定 4MB；**末片可以是短块**（size 传真实字节数），不需要补零。
  4. checksum 传 Adler-32 **十进制**字符串；传十六进制报 `checksum param Invalid`。
  5. upload_finish 的 block_num = upload_prepare 返回的 block_num（ceil(size/4MB)）。
  6. bot 身份可建目录/传文件，但**自动授权只对新上传的文件生效**，覆盖已有文件不改进权限。
  7. 单条命令跑太久会被外面（agent/终端）掐断：给 --budget 分批跑，脚本按状态文件续传。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import feishu_dl as fd          # noqa: E402  复用 token / 配置

BASE = 'https://open.feishu.cn'
BLOCK = 4 * 1024 * 1024
UPLOAD_ALL_MAX = 20 * 1024 * 1024


def norm_token(s: str) -> str:
    """支持直接贴 URL：https://quectel.feishu.cn/drive/folder/<token>"""
    s = (s or '').strip()
    if s.startswith('http'):
        if '/folder/' in s:
            return s.split('/folder/')[1].split('?')[0]
        if '/file/' in s:
            return s.split('/file/')[1].split('?')[0]
        return s.rstrip('/').split('/')[-1].split('?')[0]
    return s


def headers():
    return {'Authorization': 'Bearer ' + fd.get_token()}


# ------------------------------------------------------------------ 建目录
def mkdir(name, parent):
    H = dict(headers(), **{'Content-Type': 'application/json; charset=utf-8'})
    r = requests.post(BASE + '/open-apis/drive/v1/files/create_folder', headers=H,
                      json={'folder_token': norm_token(parent), 'name': name}, timeout=60)
    j = r.json()
    if j.get('code') == 0:
        print(json.dumps({'ok': True, 'folder_token': j['data']['token'],
                          'url': j['data']['url']}, ensure_ascii=False))
        return 0
    print(json.dumps({'ok': False, 'code': j.get('code'), 'msg': j.get('msg')}, ensure_ascii=False))
    return 1


# ------------------------------------------------------------------ 小文件
def upload_all(local: Path, folder: str, name: str):
    H = headers()
    size = local.stat().st_size
    with open(local, 'rb') as f:
        r = requests.post(BASE + '/open-apis/drive/v1/files/upload_all', headers=H,
                          data={'file_name': name, 'parent_type': 'explorer',
                                'parent_node': folder, 'size': str(size)},
                          files={'file': (name, f, 'application/octet-stream')}, timeout=600)
    return r.json()


# ------------------------------------------------------------------ 分片
def state_file(local: Path) -> Path:
    d = Path(os.environ.get('TEMP') or os.environ.get('TMP') or '.') / 'feishu_upload_state'
    d.mkdir(parents=True, exist_ok=True)
    key = '%s_%d' % (local.name, local.stat().st_size)
    return d / (key.replace(os.sep, '_') + '.json')


def upload_multipart(local: Path, folder: str, name: str, workers=6, budget=0.0, out_json=False):
    H = headers()
    size = local.stat().st_size
    sf = state_file(local)
    st = json.loads(sf.read_text(encoding='utf-8')) if sf.is_file() else {}
    if st and (st.get('size') != size or st.get('folder') != folder or st.get('name') != name):
        st = {}

    if not st:
        r = requests.post(BASE + '/open-apis/drive/v1/files/upload_prepare', headers=H, json={
            'file_name': name, 'parent_type': 'explorer', 'parent_node': folder, 'size': size},
            timeout=60)
        j = r.json()
        if j.get('code') != 0:
            print(json.dumps({'ok': False, 'stage': 'prepare', **j}, ensure_ascii=False))
            return 1
        st = {'size': size, 'folder': folder, 'name': name, 'upload_id': j['data']['upload_id'],
              'block_num': int(j['data'].get('block_num') or ((size + BLOCK - 1) // BLOCK)),
              'done': []}
        sf.write_text(json.dumps(st), encoding='utf-8')
        if not out_json:
            print('prepare ok: upload_id=%s block_num=%s size=%.1fMB'
                  % (st['upload_id'], st['block_num'], size / 1024 / 1024), flush=True)

    total, done = st['block_num'], set(st['done'])

    def send(seq):                     # seq 从 0 开始，字段名 seq
        with open(local, 'rb') as f:
            f.seek(seq * BLOCK)
            chunk = f.read(BLOCK)
        for attempt in range(1, 4):
            try:
                rr = requests.post(BASE + '/open-apis/drive/v1/files/upload_part', headers=H,
                                   data={'upload_id': st['upload_id'], 'seq': str(seq),
                                         'size': str(len(chunk)),
                                         'checksum': str(zlib.adler32(chunk) & 0xffffffff)},
                                   files={'file': ('part', chunk, 'application/octet-stream')},
                                   timeout=300)
                jj = rr.json()
                if jj.get('code') == 0:
                    return seq, None
                err = '%s(%s)' % (jj.get('msg'), jj.get('code'))
            except Exception as e:
                err = repr(e)
            time.sleep(1.5 * attempt)
        return seq, err

    t0 = time.time()
    todo = [s for s in range(total) if s not in done]
    pending, i = [], 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {}
        while i < len(todo) and (not budget or time.time() - t0 < budget):
            for _ in range(workers):
                if i >= len(todo):
                    break
                futs[ex.submit(send, todo[i])] = todo[i]
                i += 1
            for fut in as_completed(list(futs)):
                seq, err = fut.result()
                futs.pop(fut, None)
                (pending.append((seq, err)) if err else done.add(seq))
            st['done'] = sorted(done)
            sf.write_text(json.dumps(st), encoding='utf-8')
            if not out_json:
                print('  %d/%d 片 (%.0f%%)' % (len(done), total, 100.0 * len(done) / total), flush=True)
            if i >= len(todo) and not futs:
                break

    st['done'] = sorted(done)
    sf.write_text(json.dumps(st), encoding='utf-8')

    if len(done) < total:
        print(json.dumps({'ok': False, 'incomplete': total - len(done), 'pending': pending[:3],
                          'hint': '重跑同一条命令继续（状态文件已保存）'}, ensure_ascii=False))
        return 9

    r = requests.post(BASE + '/open-apis/drive/v1/files/upload_finish', headers=H, json={
        'upload_id': st['upload_id'], 'block_num': total}, timeout=180)
    j = r.json()
    if j.get('code') != 0:
        print(json.dumps({'ok': False, 'stage': 'finish', **j}, ensure_ascii=False))
        return 3
    token = j['data'].get('file_token')
    sf.unlink(missing_ok=True)
    print(json.dumps({'ok': True, 'file_token': token, 'size': size,
                      'url': 'https://quectel.feishu.cn/file/%s' % token,
                      'folder': 'https://quectel.feishu.cn/drive/folder/%s' % folder},
                     ensure_ascii=False))
    return 0


def upload(local: str, folder: str, name=None, workers=6, budget=0.0, out_json=False):
    p = Path(local).resolve()
    if not p.is_file():
        print(json.dumps({'ok': False, 'msg': 'not a file: %s' % p}, ensure_ascii=False))
        return 1
    folder = norm_token(folder)
    name = name or p.name
    if p.stat().st_size <= UPLOAD_ALL_MAX:
        j = upload_all(p, folder, name)
        if j.get('code') == 0:
            token = j['data'].get('file_token')
            print(json.dumps({'ok': True, 'mode': 'all', 'file_token': token,
                              'url': 'https://quectel.feishu.cn/file/%s' % token,
                              'folder': 'https://quectel.feishu.cn/drive/folder/%s' % folder},
                             ensure_ascii=False))
            return 0
        if not out_json:
            print('upload_all 失败（%s），改分片' % j.get('msg'), flush=True)
    return upload_multipart(p, folder, name, workers=workers, budget=budget, out_json=out_json)


def main():
    ap = argparse.ArgumentParser(description='飞书云盘写入：mkdir / upload')
    sub = ap.add_subparsers(dest='cmd', required=True)
    m = sub.add_parser('mkdir')
    m.add_argument('name')
    m.add_argument('--under', required=True, help='父目录 token 或 URL')
    u = sub.add_parser('upload')
    u.add_argument('local')
    u.add_argument('--folder', required=True, help='目标目录 token 或 URL')
    u.add_argument('--name', default=None)
    u.add_argument('--workers', type=int, default=6)
    u.add_argument('--budget', type=float, default=0.0, help='单次运行秒数上限，0=不限（分批续传用）')
    u.add_argument('--json', action='store_true', help='只输出 JSON')
    a = ap.parse_args()
    if a.cmd == 'mkdir':
        return mkdir(a.name, a.under)
    return upload(a.local, a.folder, a.name, a.workers, a.budget, a.json)


if __name__ == '__main__':
    sys.exit(main())
