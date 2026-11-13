#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「做升级包」工具集从飞书云盘拉到本地 ASCII 目录。

工具（adiff.exe / FBFMake / config 模板 / bat / 文档）不进 git 仓库，统一放飞书云盘：
    做升级包  https://quectel.feishu.cn/drive/folder/HVQwfjtCGlXh85dBLhmcIPtWnBf
    folder_token = HVQwfjtCGlXh85dBLhmcIPtWnBf

下载走 feishu-software-download skill 的 feishu_dl.py（应用身份 tenant_access_token，免扫码）。

用法：
    python fetch_tools.py                      # 默认落到 D:\\work\\package\\fota_tool
    python fetch_tools.py --dest D:\\fota_tool # 自定义落点（必须纯 ASCII）
    python fetch_tools.py --list               # 只列云盘里有哪些文件（含 file_token）
    python fetch_tools.py --check              # 只校验本地已有的工具是否齐/大小对得上
    python fetch_tools.py --force              # 大小对不上的也重下

⚠️ 落点必须纯 ASCII：FBFMake 是 ANSI 程序，路径含中文会弹模态框永久卡死（SKILL.md §1.1）。

feishu_dl.py 的定位顺序：
    1. 环境变量 FEISHU_DL_SCRIPT（feishu_dl.py 的绝对路径，或其所在目录）
    2. <本 skill>/../feishu-software-download/scripts/feishu_dl.py
    3. %USERPROFILE%\\.qwenpaw\\workspaces\\*\\skills\\feishu-software-download\\scripts\\feishu_dl.py
"""
import argparse
import importlib.util
import os
import pathlib
import re
import sys

FOLDER_TOKEN = "HVQwfjtCGlXh85dBLhmcIPtWnBf"
FOLDER_URL = "https://quectel.feishu.cn/drive/folder/HVQwfjtCGlXh85dBLhmcIPtWnBf"
DEFAULT_DEST = r"D:\work\package\fota_tool"

# (文件名, 预期字节数 | None)  —— 大小只做校验告警，不阻断
TOOLS = [
    ("adiff.exe", 248320),
    ("FBFMake_CF_V1.6-150.exe", 6467072),
    ("config", 578),
    ("config_app", 177),
    ("fbfmake.bat", None),
    ("fbfmake_fast.bat", None),
    ("fbfmake_full.bat", None),
    ("README.docx", None),
    ("升级包制作方法及模组FOTA升级说明.txt", None),
]

ASCII_RE = re.compile(r"^[\x20-\x7e]+$")


def need(fname):
    return fname in {n for n, _ in TOOLS}


def load_feishu_dl():
    cands = []
    env = os.environ.get("FEISHU_DL_SCRIPT")
    if env:
        p = pathlib.Path(env)
        cands.append(p if p.suffix == ".py" else p / "feishu_dl.py")
    here = pathlib.Path(__file__).resolve().parent
    cands.append(here.parent.parent / "feishu-software-download" / "scripts" / "feishu_dl.py")
    home = pathlib.Path.home()
    cands += list(home.glob(".qwenpaw/workspaces/*/skills/feishu-software-download/scripts/feishu_dl.py"))
    for c in cands:
        if c.is_file():
            spec = importlib.util.spec_from_file_location("feishu_dl", str(c))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            print("[feishu_dl] %s" % c)
            return mod
    sys.exit(
        "ERROR: 找不到 feishu_dl.py。\n"
        "  装好 feishu-software-download skill，或用环境变量指定：\n"
        "  set FEISHU_DL_SCRIPT=<...>/feishu-software-download/scripts/feishu_dl.py"
    )


def main():
    ap = argparse.ArgumentParser(description="从飞书云盘拉「做升级包」工具集")
    ap.add_argument("--dest", default=DEFAULT_DEST, help="落点目录（纯 ASCII），默认 %s" % DEFAULT_DEST)
    ap.add_argument("--list", action="store_true", help="只列云盘文件")
    ap.add_argument("--check", action="store_true", help="只校验本地工具")
    ap.add_argument("--force", action="store_true", help="大小对不上也重下")
    args = ap.parse_args()

    dest = pathlib.Path(args.dest)
    if not ASCII_RE.match(str(dest)):
        sys.exit("ERROR: 落点必须是纯 ASCII 路径（FBFMake 在中文路径下会弹模态框卡死）：%s" % dest)

    fd = load_feishu_dl()
    files = fd.list_folder(FOLDER_TOKEN)
    remote = {f["name"]: f for f in files}
    print("[云盘] %s  %d 项" % (FOLDER_URL, len(files)))

    if args.list:
        for f in sorted(files, key=lambda x: (x.get("type") != "folder", x["name"])):
            print("  %-40s %-7s %10s  %s" % (f["name"], f.get("type"), f.get("size", "-"), f["token"]))
        return

    if not remote:
        sys.exit("ERROR: 云盘目录为空（工具还没上传？）。先确认 %s 里有文件。" % FOLDER_URL)

    if args.check:
        bad = 0
        for name, size in TOOLS:
            p = dest / name
            if not p.exists():
                print("MISSING  %s" % name)
                bad += 1
                continue
            got = p.stat().st_size
            ok = (size is None) or (got == size) or str(got) == str(remote.get(name, {}).get("size"))
            print("%-8s %-40s %10d %s" % ("OK" if ok else "SIZE", name, got, "" if ok else "(预期 %s)" % size))
            bad += 0 if ok else 1
        sys.exit(0 if bad == 0 else 1)

    dest.mkdir(parents=True, exist_ok=True)
    got, skipped, failed = [], [], []
    for name, size in TOOLS:
        meta = remote.get(name)
        if not meta:
            failed.append((name, "云盘里没有这个文件"))
            continue
        p = dest / name
        if p.exists():
            local = p.stat().st_size
            rsize = int(meta.get("size") or 0)
            if local == rsize and local > 0 and not args.force:
                print("[skip] %s 已存在 %d B" % (name, local))
                skipped.append(name)
                continue
        try:
            n = fd.download(meta["token"], str(p))
        except SystemExit as e:
            failed.append((name, str(e)))
            continue
        got.append((name, n))
        print("[ok] %s  %d B" % (name, n))

    print("\n落点：%s" % dest)
    print("下载 %d / 跳过 %d / 失败 %d" % (len(got), len(skipped), len(failed)))
    for name, why in failed:
        print("  FAIL %s -- %s" % (name, why))

    if failed and len(failed) == len(TOOLS):
        sys.exit("ERROR: 一个都没下到，检查云盘权限（bot 需可阅读该文件夹）")

    print(
        "\n提醒：云盘里的 config / config_app 只是**参考模板**，"
        "正式做包必须用 scripts/make_config.py 依据版本包 partition.bin 重新生成（SKILL.md §1.2）。\n"
        "自检：python %s --check" % pathlib.Path(__file__).name
    )


if __name__ == "__main__":
    main()
