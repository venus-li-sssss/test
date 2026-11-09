---
description: '免扫码（应用身份 bot）访问飞书云盘下载常用软件工具（QCOM、SSCOM、WindTerm、QFlash、QFIL、aboot 等），并可读取飞书文档/知识库正文。全程只需要 requests + 一个 app_id/app_secret，不需要用户登录、不需要扫码、不依赖 lark-cli。触发词：下载QCOM、下载SSCOM、下载WindTerm、下载QFlash、下载QFIL、下载aboot、飞书软件下载、从飞书下载软件、串口工具下载、烧录工具下载、有哪些软件、同步软件目录、读飞书文档、飞书知识库、wiki 内容、tenant_access_token 访问云盘。'
name: feishu-software-download
---

# 飞书软件下载（应用身份，免扫码）

从飞书云盘「基础软件存放」目录下载常用测试工具，并读取飞书文档 / 知识库正文。
**统一走应用身份 `tenant_access_token` + Python requests**：不扫码、不管用户登录态、换机器换账号都能用。

## 快速上手

脚本：`scripts/feishu_dl.py`（依赖 `requests`）。所有命令在 skill 目录下执行，或用绝对路径。

```bash
# 1) 看有哪些软件（读本地 catalog，不联网）
python scripts\feishu_dl.py list

# 2) 下载（按名称或关键词，模糊匹配；--out 不给就落到当前目录）
python scripts\feishu_dl.py get QCOM --out D:\tools
python scripts\feishu_dl.py get 串口调试            # → SSCOM
python scripts\feishu_dl.py get qfil                # → QPST/QFIL 安装包

# 3) 云端加了新文件后，重新拉目录（保留已有人工写的 name/说明/关键词）
python scripts\feishu_dl.py sync

# 4) 已知 file_token 直接下
python scripts\feishu_dl.py dl P5MRbbMa5onIDkx1u8aciFnanSf --out QCOM.exe

# 5) 云端目录树（排查"文件到底在哪"）
python scripts\feishu_dl.py tree

# 6) 读飞书文档 / 知识库正文 → 存成 UTF-8 markdown 文件
python scripts\feishu_dl.py doc https://quectel.feishu.cn/wiki/RLOaw7nLQiwy06kEFsNcDNuEnid
```

`doc` 的正文**只写文件、不打印到控制台**（Windows cp936 管道会把 UTF-8 中文打成乱码），
控制台只回 `OK saved: <绝对路径>`，然后用 `read_file` 读那个 md。

## 回答用户时的约定

- 下载完成必须报告：软件名、文件名、大小、**完整绝对路径**（markdown 链接形式）。
- 用户问"有哪些软件"→ 跑 `list`，把结果整理成表格（名称/所在目录/说明）。
- 用户要的软件不在目录里 → 先 `sync` 再匹配；仍没有就告知可用列表，并问是不是放到别的目录了。

## 鉴权与接口（已实测）

| 用途 | 接口 |
|---|---|
| 取 token（2h 有效，脚本自动缓存续期） | `POST /open-apis/auth/v3/tenant_access_token/internal` |
| 列目录 | `GET /open-apis/drive/v1/files?folder_token=<folder>` |
| **下载文件** | `GET /open-apis/drive/v1/medias/<file_token>/preview_download?preview_type=16` |
| Wiki 节点 → 文档 id | `GET /open-apis/wiki/v2/spaces/get_node?token=<node_token>` |
| 文档正文 | `GET /open-apis/docx/v1/documents/<obj_token>/blocks?page_size=500` |

⚠️ **三条踩过坑的结论**，不要改回去：

1. **不要用 `/medias/<token>/download`**：bot 身份没有 export 权限，直接 403（空响应）。
   `preview_download?preview_type=16` 才是源文件下载，实测 389,120 B 的 exe 正常落地。
2. **不要用 `/drive/v1/files/<file_token>` 取元信息**：404。列目录只能用 `?folder_token=`。
3. **大文件必断流**：>100MB 的包（如 `aboot工具.rar` 131,760,852 B）实测在 ~120MB 处
   `IncompleteRead` 断掉。脚本已内置 `Range: bytes=<have>-` 断点续传 + 最多 5 次重试，
   落地前先比对 Content-Length，不完整就报错不冒充成功 —— 别把它简化回单次 `iter_content`。

**凭据不入库，需自备**（本仓库不含任何 app_id / app_secret）。脚本按下面顺序取：

1. 环境变量 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`
2. 本地文件 `~/.feishu_app.json`：`{"app_id": "cli_xxx", "app_secret": "xxx"}`

自建应用的准备步骤：

1. 在飞书开发者后台建一个**企业自建应用**，拿到 App ID / App Secret；
2. 开通应用身份权限 scope：`drive:drive:readonly`、`wiki:wiki:readonly`、`docx:document:readonly`；
3. 把该应用加为目标云盘目录的协作者（可阅读）——**共享给应用，不是共享给个人**；
4. 若目标目录不是下面的默认根目录，用 `FEISHU_ROOT_FOLDER=<folder_token>` 覆盖。

其它默认值：

- token 缓存：`~/.feishu_tat_cache.json`（提前 300s 续期，不用每次重取）
- 根目录：`GiihfUC0tlDJGHdTriDcH4ljnUz` = 基础软件存放（子目录：串口工具 / 烧录工具 / AI工具）；目录不同请 `sync` 或 `--folder` 指定

## 软件目录

`software_catalog.json`（与 SKILL.md 同目录）：

```json
{
  "root_folder": "GiihfUC0tlDJGHdTriDcH4ljnUz",
  "software": [
    {"name": "QCOM", "file_token": "P5MRbbMa5onIDkx1u8aciFnanSf",
     "filename": "QCOM_V1.6.exe", "folder": "串口工具",
     "description": "高通串口/诊断工具", "keywords": ["qcom", "高通", "串口工具"]}
  ]
}
```

匹配顺序：`name` 全等 → `keywords` 全等 → `name`/`keywords` 互为包含（不区分大小写）。
`sync` 后人工补的 `name`/`description`/`keywords` 会按 `file_token` 保留，不会被云端文件名冲掉。

当前目录（2026-10-14 实测）：

| 名称 | 目录 | 文件 |
|---|---|---|
| QCOM | 串口工具 | QCOM_V1.6.exe |
| SSCOM | 串口工具 | SSCOM.rar |
| WindTerm | 串口工具 | WindTerm_2.6.0_Windows_Portable_x86_64.zip |
| aboot | 烧录工具 | aboot工具.rar |
| QFIL | 烧录工具 | qpst.win.2.7_installer_00486.1_QFIL2.0.2.8.zip |
| QFlash | 烧录工具 | QFlash_V7.5_EN.zip |
| QuecAgent | AI工具 | QuecAgent-desktop.exe |

> 相关但不同职责的 skill：`flash-tools` / `qflash` 讲**怎么用**这些烧录工具，本 skill 只负责**把工具捞下来**。

## 错误处理

| 现象 | 原因 | 处理 |
|---|---|---|
| `1061004 forbidden` | 该云盘目录没共享给这个**应用**（不是共享给用户） | 让共享人把应用加为协作者（可阅读），搜索应用名而不是个人名 |
| `99991672 app_scope_not_applied` | 应用缺 scope（`drive:drive:readonly` / `wiki:*` / `docx:document:readonly`） | 开发者后台申请应用身份权限：`https://open.feishu.cn/app/<app_id>/auth` |
| 下载 403 / 空响应 | 用了 `/medias/.../download` | 换 `preview_download?preview_type=16`（脚本已内置） |
| token 401 / app_secret 无效 | Secret 被重置 | 后台重置 Secret 后更新环境变量 `FEISHU_APP_SECRET` 或 `~/.feishu_app.json` |
| `没找到 'xxx'` | 目录未同步 / 文件在别的目录 | `sync` → `tree` 确认 |
| 文档 blocks 为 0 | 传的是 wiki node 而不是 docx obj_token | 用 `doc <wiki链接>`，脚本会先 `get_node` 换 `obj_token` |
| 解压出来中文文件名是乱码（`├ⁿ┴ε.txt`） | 包里文件名是 GBK 存的、没打 UTF-8 标记，`zipfile` 按 cp437 解 | 见下面「落地之后」的还原一行代码，别用右键"全部解压缩" |

## 兜底：lark-cli

机器上装了 lark-cli 且 `.env` 配的是同一个应用（`strict-mode=bot`）时，可以用它做等价验证：

```bash
lark-cli auth status --json
lark-cli drive +preview --file-token <file_token> --type source_file --output <path> --as bot
```

`+download` 会报没有 export 权限，`+preview --type source_file` 才是能用的那条路。
但**默认别用 lark-cli**——脚本自带 token 管理，少一个外部依赖。

## 自测记录（2026-10-14 / 10-15，本机实测通过）

| 用例 | 结果 |
|---|---|
| `sync` 递归拉目录 | ✅ 7 个文件 / 3 个子目录，人工 name-说明-关键词保留 |
| `list` | ✅ 表格输出 |
| `get QCOM`（精确名） | ✅ 389,120 B exe |
| `get 串口调试`（关键词） | ✅ → SSCOM.rar 478,848 B |
| `get 9008`（关键词） | ✅ → QPST/QFIL zip 40,742,358 B |
| `get aboot`（131MB 大文件） | ✅ 断流 1 次后续传完成，头 8 字节 `Rar!\x1a\x07\x01\x00` 校验为真压缩包 |
| `get QFlash`（285MB 大文件，2026-10-15） | ✅ 298,851,687 B，断流 2 次（138MB / 281MB）均自动续传补齐，`testzip()` 无损坏，1379 条目 |
| `dl <file_token>` | ✅ |
| `tree` | ✅ |
| `doc <wiki URL>` | ✅ 节点→obj_token→70 blocks，落地 UTF-8 md |

下载中途产物写在 `<目标名>.part`，成功后才 rename，失败不留半成品。

## 落地之后：解压与查重（2026-10-15 实测补的）

**1. 中文文件名要按 GBK 还原再解压。** 这些工具包（QFlash、aboot 等）里常有 GBK 命名却没打 UTF-8
标记的条目，`zipfile` 默认按 cp437 解码 → `命令.txt` 变成 `├ⁿ┴ε.txt`，Windows 资源管理器直接解会出乱码名：

```python
fixed = name.encode('cp437', 'replace').decode('gbk', 'replace')   # 仅对 info.flag_bits & 0x800 == 0 的条目
```

**2. 下载前先想清楚是不是已经有。** 285MB 的包下到 `Downloads` 结果和本地已装的一模一样，等于白跑一趟带宽。
比对不用全量 hash，拿 zip 里存好的 CRC 和本地文件算出来的 `zlib.crc32` 对一遍就够：

```python
import zipfile, zlib, os
z = zipfile.ZipFile(r'QFlash_V7.5_EN.zip')
for i in z.infolist():
    if i.is_dir(): continue
    lp = os.path.join(local_root, i.filename.replace('/', os.sep))
    ok = os.path.exists(lp) and os.path.getsize(lp) == i.file_size and crc32(lp) == i.CRC
```

对不上时先分清两类：**运行时被工具改写的配置**（`MainConfig.ini`、`EFlashTool/1/config.ini`、
`cfg.digest` —— 存的是 COM 口、上次选的镜像路径，本地和包里不一样是正常的，别当版本差异）
和 **真的版本差异**。QFlash 那次实测：1088 个文件 1079 个一致，3 个是上述配置，6 个"缺失"其实是 GBK 文件名。
结论 = 云端包和本地已装同版本，没必要重复解压。
