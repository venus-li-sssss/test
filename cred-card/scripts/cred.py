#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一凭据卡片 (cred-card)
====================================
集中管理各内部/外部系统的账号密码，按账号身份分两层存储：

  1) 受保护层（DPAPI 加密）
     - 账号后缀命中 policy.json 里 protected_domains 的（默认 @ikotek.com / @quecagent.com / @quectel.com）
     - 存 ~/.cred-card/vault.dpapi.json，用 Windows DPAPI 加密，仅本机 + 当前 Windows 用户可解
     - 禁止明文落盘，也禁止写进 SKILL.md / 任何可同步目录
  2) 明文层
     - 其余账号（客户邮箱、测试账号、临时账号等）
     - 存 ~/.cred-card/accounts.json，直接明文，方便复用

Feishu 场景不走本工具：飞书内（云文档/云盘/IM/妙搭内嵌页）直接用飞书身份，不需要密码。

常用用法:
  python cred.py set --id qdisk --username venus.li@ikotek.com        # 交互输入密码，自动判定加密
  python cred.py set --id ninebot --username xxx@ninebot.com --password 123456 --plain
  python cred.py get --id qdisk --field password
  python cred.py get --id qdisk --json
  python cred.py list
  python cred.py remove --id ninebot
  python cred.py classify --username venus.li@ikotek.com
"""

import argparse
import base64
import getpass
import json
import os
import sys
import time

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 运行期状态一律放用户目录，不放 skill 目录（skill 目录会被同步/上传/打包）
CRED_DIR = os.path.join(os.path.expanduser("~"), ".cred-card")
VAULT_FILE = os.path.join(CRED_DIR, "vault.dpapi.json")
PLAIN_FILE = os.path.join(CRED_DIR, "accounts.json")
POLICY_FILE = os.path.join(SKILL_DIR, "policy.json")
ENTROPY = b"cred-card-vault-v1"

DEFAULT_POLICY = {
    "protected_domains": ["ikotek.com", "quecagent.com", "quectel.com"],
    "note": "命中这里的公司邮箱账号必须 DPAPI 加密；其他账号可明文保存",
}


# --------------------------------------------------------------------------
# 策略
# --------------------------------------------------------------------------
def load_policy():
    if os.path.exists(POLICY_FILE):
        try:
            with open(POLICY_FILE, "r", encoding="utf-8") as f:
                p = json.load(f)
            if isinstance(p.get("protected_domains"), list) and p["protected_domains"]:
                return p
        except Exception as e:
            sys.stderr.write("读取 policy.json 失败，使用默认策略: %s\n" % e)
    return DEFAULT_POLICY


def classify(username):
    """返回 'protected' 或 'plain'。"""
    domains = [d.lower().lstrip("@") for d in load_policy()["protected_domains"]]
    u = (username or "").strip().lower()
    for d in domains:
        if u.endswith("@" + d):
            return "protected"
    return "plain"


# --------------------------------------------------------------------------
# DPAPI
# --------------------------------------------------------------------------
def _dpapi(data, protect):
    if not sys.platform.startswith("win"):
        raise RuntimeError("当前系统不支持 DPAPI，只能在 Windows 上保存受保护凭据")
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    ent = ctypes.create_string_buffer(ENTROPY, len(ENTROPY))
    blob_ent = DATA_BLOB(len(ENTROPY), ctypes.cast(ent, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()

    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if not fn(ctypes.byref(blob_in), None, ctypes.byref(blob_ent),
              None, None, 0, ctypes.byref(blob_out)):
        raise RuntimeError("DPAPI 调用失败，错误码 %s" % kernel32.GetLastError())
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _read_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            sys.stderr.write("读取 %s 失败: %s\n" % (os.path.basename(path), e))
    return default


def _write_json(path, obj, private=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    if private:
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass


# --------------------------------------------------------------------------
# 存储
# --------------------------------------------------------------------------
def load_vault():
    """返回受保护凭据字典；解密失败返回空。"""
    rec = _read_json(VAULT_FILE, None)
    if not rec or not rec.get("enc"):
        return {}
    try:
        raw = _dpapi(base64.b64decode(rec["enc"]), False)
        return json.loads(raw.decode("utf-8"))
    except Exception as e:
        sys.stderr.write("受保护凭据解密失败（需重新 set）: %s\n" % e)
        return {}


def save_vault(v):
    payload = json.dumps(v, ensure_ascii=False).encode("utf-8")
    enc = base64.b64encode(_dpapi(payload, True)).decode("ascii")
    _write_json(VAULT_FILE, {"v": 1, "enc": enc,
                             "updated": time.strftime("%Y-%m-%d %H:%M:%S")}, private=True)


def load_plain():
    return _read_json(PLAIN_FILE, {})


def save_plain(p):
    _write_json(PLAIN_FILE, p)


def find_entry(entry_id):
    """跨两层查找，返回 (entry, tier)。"""
    v = load_vault()
    if entry_id in v:
        return v[entry_id], "protected"
    p = load_plain()
    if entry_id in p:
        return p[entry_id], "plain"
    return None, None


# --------------------------------------------------------------------------
# 命令
# --------------------------------------------------------------------------
def cmd_classify(args):
    tier = classify(args.username)
    domains = load_policy()["protected_domains"]
    print("账号: %s" % args.username)
    print("判定: %s" % ("受保护（DPAPI 加密）" if tier == "protected" else "明文保存即可"))
    print("受保护域名: %s" % ", ".join("@" + d for d in domains))


def cmd_set(args):
    username = args.username
    password = args.password
    try:
        if not username:
            username = input("账号: ").strip()
        if not password:
            password = getpass.getpass("密码: ")
    except (EOFError, KeyboardInterrupt):
        sys.stderr.write("当前环境不支持交互输入，请改用 --username/--password 传参。\n")
        sys.exit(2)
    if not username or not password:
        sys.stderr.write("账号或密码为空，已取消。\n")
        sys.exit(2)

    tier = classify(username)
    if args.plain and tier == "protected":
        sys.stderr.write(
            "拒绝明文保存：%s 属于公司邮箱账号，必须加密存储（去掉 --plain 即可）。\n" % username)
        sys.exit(2)
    if tier == "protected":
        tier = "protected"

    entry = {"username": username, "password": password,
             "updated": time.strftime("%Y-%m-%d %H:%M:%S")}
    if args.note:
        entry["note"] = args.note

    if tier == "protected":
        v = load_vault()
        v[args.id] = entry
        save_vault(v)
        # 从明文层清掉同名条目，避免两处不一致
        p = load_plain()
        if args.id in p:
            p.pop(args.id)
            save_plain(p)
        print("已用 DPAPI 加密保存: id=%s  账号=%s  文件=%s" % (args.id, username, VAULT_FILE))
    else:
        p = load_plain()
        p[args.id] = entry
        save_plain(p)
        v = load_vault()
        if args.id in v:
            v.pop(args.id)
            save_vault(v)
        print("已明文保存: id=%s  账号=%s  文件=%s" % (args.id, username, PLAIN_FILE))


def cmd_get(args):
    entry, tier = find_entry(args.id)
    if not entry:
        if args.missing_ok:
            print("")
            return
        sys.stderr.write("没有找到 id=%s 的凭据，先用: python cred.py set --id %s\n" % (args.id, args.id))
        sys.exit(3)
    if args.json:
        print(json.dumps({"id": args.id, "tier": tier, "username": entry.get("username"),
                          "password": entry.get("password"), "note": entry.get("note")},
                         ensure_ascii=False))
        return
    field = args.field or "password"
    val = entry.get(field)
    if val is None:
        sys.stderr.write("id=%s 没有字段 %s\n" % (args.id, field))
        sys.exit(3)
    print(val)


def cmd_list(args):
    v = load_vault()
    p = load_plain()
    rows = [(k, e.get("username", ""), "DPAPI加密") for k, e in v.items()]
    rows += [(k, e.get("username", ""), "明文") for k, e in p.items()]
    if not rows:
        print("暂无保存的凭据。")
        return
    print("共 %d 条  (受保护 %d / 明文 %d)" % (len(rows), len(v), len(p)))
    for k, u, tier in sorted(rows):
        print("  %-18s %-32s %s" % (k, u, tier))


def cmd_remove(args):
    hit = False
    v = load_vault()
    if args.id in v:
        v.pop(args.id)
        save_vault(v)
        hit = True
    p = load_plain()
    if args.id in p:
        p.pop(args.id)
        save_plain(p)
        hit = True
    print("已删除 id=%s" % args.id if hit else "没有找到 id=%s" % args.id)


def cmd_where(args):
    """给其他 skill 用：告诉它某 id 存在哪一层（不输出密码）。"""
    entry, tier = find_entry(args.id)
    if not entry:
        print("missing")
        sys.exit(3)
    print(tier)


def build_parser():
    p = argparse.ArgumentParser(description="统一凭据卡片：账号密码集中管理（公司邮箱走 DPAPI，其余明文）")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("set", help="新增/更新一条凭据")
    s.add_argument("--id", required=True, help="凭据标识，如 qdisk / jira / ninebot")
    s.add_argument("--username", help="账号（不给则交互输入）")
    s.add_argument("--password", help="密码（不建议写在命令行，交互输入更安全）")
    s.add_argument("--note", help="备注，如所属系统/用途")
    s.add_argument("--plain", action="store_true", help="强制明文（仅非公司邮箱账号可用）")
    s.set_defaults(func=cmd_set)

    g = sub.add_parser("get", help="取出某条凭据的字段")
    g.add_argument("--id", required=True)
    g.add_argument("--field", default="password", help="默认 password，可选 username / note")
    g.add_argument("--json", action="store_true", help="输出整条 JSON")
    g.add_argument("--missing-ok", action="store_true", help="不存在时返回空串而不报错")
    g.set_defaults(func=cmd_get)

    l = sub.add_parser("list", help="列出已保存凭据（不显示密码）")
    l.set_defaults(func=cmd_list)

    r = sub.add_parser("remove", help="删除一条凭据")
    r.add_argument("--id", required=True)
    r.set_defaults(func=cmd_remove)

    c = sub.add_parser("classify", help="判断某账号该加密还是可明文")
    c.add_argument("--username", required=True)
    c.set_defaults(func=cmd_classify)

    w = sub.add_parser("where", help="输出某 id 的存储层（protected/plain），不输出密码")
    w.add_argument("--id", required=True)
    w.set_defaults(func=cmd_where)

    return p


def main():
    args = build_parser().parse_args()
    if not args.cmd:
        build_parser().print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
