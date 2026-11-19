# -*- coding: utf-8 -*-
"""aboot 选择性烧录工具：列出 download.json 条目 / 生成跳过指定分区的固件包。

用法
    python aboot_skip.py list <固件包.zip>
    python aboot_skip.py make <固件包.zip> -o <输出.zip> --skip customer_fs,ext_flash [--dry-run]

说明
    · 只改 download.json（删掉指定分区的 flash 条目），镜像文件全部原样保留，
      避免烧录工具做文件校验时因缺文件失败。
    · 分区清单永远以这个包的 download.json 为准，脚本不内置任何机型/分区名。
    · 输入可以是内层包（根目录就有 download.json），也可以是双层包（自动挑里面那个 zip）。
"""
import argparse
import json
import os
import sys
import zipfile

LIST_CMDS = ("flash", "erase", "call", "partition")


def _find_pkg(zpath):
    """返回 (zipfile.ZipFile 对象, 说明)。双层包时返回内层 zip。"""
    z = zipfile.ZipFile(zpath)
    if "download.json" in z.namelist():
        return z, "内层包（根目录含 download.json）"
    inner = [n for n in z.namelist() if n.lower().endswith(".zip") and "/" not in n.strip("/")]
    if len(inner) != 1:
        sys.exit("包里找不到 download.json，也没找到唯一的内层 zip：%s" % z.namelist()[:10])
    data = z.read(inner[0])
    import io
    return zipfile.ZipFile(io.BytesIO(data)), "双层包 → 内层 %s" % inner[0]


def _load_cfg(z):
    raw = z.read("download.json")
    return json.loads(raw.decode("utf-8-sig"))


def _human(n):
    if n is None:
        return "—"
    if n >= 1024 * 1024:
        return "%.2f MB" % (n / 1048576.0)
    if n >= 1024:
        return "%.1f KB" % (n / 1024.0)
    return "%d B" % n


def cmd_list(args):
    z, note = _find_pkg(args.package)
    cfg = _load_cfg(z)
    sizes = {i.filename: i.file_size for i in z.infolist()}
    print("# 包：%s  （%s）" % (args.package, note))
    print("# download.json 共 %d 条（其中烧录动作 %d 条）\n"
          % (len(cfg), sum(1 for e in cfg if e.get("command") in LIST_CMDS)))
    print("| # | group | 动作 | 分区 | 镜像 | 镜像大小 | 标记 |")
    print("|---|---|---|---|---|---|---|")
    idx = 0
    for e in cfg:
        if e.get("command") not in LIST_CMDS:
            continue
        idx += 1
        img = e.get("image", "")
        print("| %d | %s | %s | %s | %s | %s | %s |" % (
            idx, e.get("group", ""), e.get("command"),
            e.get("partition", "") or "-", img or "-",
            _human(sizes.get(img)) if img else "—",
            "productionOnly" if e.get("productionOnly") else ""))
    print("\n提示：要跳过某些分区就 `make ... --skip <分区名,分区名>`。")


def cmd_make(args):
    z, note = _find_pkg(args.package)
    cfg = _load_cfg(z)
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}

    present = {e.get("partition") for e in cfg}
    missing = skip - present
    if missing:
        sys.exit("这些分区在 download.json 里不存在：%s\n现有分区：%s"
                 % (sorted(missing), sorted(p for p in present if p)))

    new, removed = [], []
    for e in cfg:
        # 跳过某分区 = 这个分区什么都不动（flash 和 erase 一起去掉）
        if e.get("command") in ("flash", "erase") and e.get("partition") in skip:
            removed.append("%s %s" % (e.get("command"), e.get("partition")))
            continue
        new.append(e)
    # 还有 call/partition 之类引用被跳过的分区 → 不是单纯"取消烧录"，拒绝自动处理
    conflict = [e for e in new if e.get("partition") in skip]
    if conflict:
        sys.exit("还有非 flash/erase 条目引用这些分区，需人工确认：%s" % conflict)

    print("包：%s（%s）" % (args.package, note))
    print("跳过：%s" % ", ".join(sorted(skip)))
    print("移除条目：%s" % removed)
    print("条目数：%d → %d ；flash %d → %d ；erase %d → %d"
          % (len(cfg), len(new),
             sum(1 for e in cfg if e.get("command") == "flash"),
             sum(1 for e in new if e.get("command") == "flash"),
             sum(1 for e in cfg if e.get("command") == "erase"),
             sum(1 for e in new if e.get("command") == "erase")))
    if not removed:
        sys.exit("没有任何条目被移除，检查 --skip 的分区名。")
    if args.dry_run:
        print("[dry-run] 未写文件。")
        return

    text = json.dumps(new, indent=3, ensure_ascii=False).replace("\n", "\r\n")
    with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED) as out:
        out.writestr("download.json", text.encode("utf-8"))
        for info in z.infolist():
            if info.filename == "download.json" or info.is_dir():
                continue
            out.writestr(info, z.read(info.filename))
    print("输出：%s (%d bytes)" % (os.path.abspath(args.output), os.path.getsize(args.output)))

    # 回读自检
    with zipfile.ZipFile(args.output) as chk:
        back = json.loads(chk.read("download.json").decode("utf-8"))
        left = [e.get("partition") for e in back if e.get("partition") in skip]
        print("自检：条目 %d ；仍引用被跳分区 %s ；文件数 %d"
              % (len(back), left or "无", len(chk.namelist())))


def main():
    ap = argparse.ArgumentParser(description="aboot 选择性烧录：列条目 / 生成跳过分区的包")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("list", help="列出 download.json 全部烧录动作")
    p1.add_argument("package")
    p1.set_defaults(func=cmd_list)

    p2 = sub.add_parser("make", help="生成跳过指定分区的固件包")
    p2.add_argument("package")
    p2.add_argument("-o", "--output", required=True)
    p2.add_argument("--skip", required=True, help="逗号分隔的分区名，如 customer_fs,ext_flash")
    p2.add_argument("--dry-run", action="store_true")
    p2.set_defaults(func=cmd_make)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
