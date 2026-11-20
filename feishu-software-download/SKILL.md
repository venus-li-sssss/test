---
description: '免扫码（应用身份 bot）读写飞书云盘：云端实时搜索 + 递归遍历 + 下载常用软件与文档（QCOM、SSCOM、WindTerm、QFlash、QFIL、aboot、驱动、CAN 工具、升级版本包等），**以及建目录 / 上传文件（含 >20MB 分片断点续传）**，并可读取飞书文档/知识库正文。范围=云盘→软件测试部→软件测试二科 下的「基础软件存放」「项目环境搭建」两个根目录。只需 requests + 内置共享机器人凭据，不扫码、不依赖 lark-cli。触发词：下载QCOM、下载SSCOM、下载WindTerm、下载QFlash、下载QFIL、下载aboot、飞书软件下载、从飞书下载软件、串口工具下载、烧录工具下载、驱动下载、有哪些软件、搜索飞书云盘、云盘里有没有、同步软件目录、**上传到飞书云盘、传文件到云盘、上传安装包、建云盘目录、新建云盘文件夹、apk 传到云盘**、读飞书文档、飞书知识库、wiki 内容、tenant_access_token 访问云盘。'
name: feishu-software-download
---

# 飞书软件下载（应用身份，免扫码）

从飞书云盘 `云盘 → 软件测试部 → 软件测试二科` 下的**「基础软件存放」「项目环境搭建」**两个目录
下载常用测试工具/文档，并读取飞书文档 / 知识库正文。
**统一走应用身份 `tenant_access_token` + Python requests**：不扫码、不管用户登录态、换机器换账号都能用。
**优先用云端实时搜索**（`search`/`get`），catalog 只是离线兜底 + 补目录名。

> **分工（别用错）**：云盘**文件**（exe/zip/安装包/附件）下载 → 本 skill；
> **读云文档正文、知识库 wiki、多维表格 base、电子表格** → 用 `feishu-docs`（同一个机器人身份）。
> 本 skill 的 `doc` 只解析 wiki/docx，遇到 `base/` 链接会 JSONDecodeError，别硬试。

## 快速上手

脚本：`scripts/feishu_dl.py`（依赖 `requests`）。所有命令在 skill 目录下执行，或用绝对路径。

```bash
# 1) 云端实时搜索（推荐入口，不用 sync，永远是最新的）
python scripts\feishu_dl.py search 烧录
python scripts\feishu_dl.py search QDM562
python scripts\feishu_dl.py search 测试报告 --all   # 连 docx/sheet/bitable/slides 一起搜

# 1.5) 搜不到/不确定有没有 → find：先搜索，0 命中自动现场扫两个根目录（目录名也匹配）
python scripts\feishu_dl.py find 烧录            # → 烧录工具/ 及其下所有文件，带完整路径
python scripts\feishu_dl.py find 驱动 --depth 3  # 限制层数，少扫一层更快

# 2) 下载：先云端搜索，唯一命中直接下；多个命中会列候选，用 --pick 选
python scripts\feishu_dl.py get QCOM --out D:\tools
python scripts\feishu_dl.py get SerialTool --pick 2
python scripts\feishu_dl.py get 串口调试            # → SSCOM

# 3) 已知 file_token 直接下
python scripts\feishu_dl.py dl P5MRbbMa5onIDkx1u8aciFnanSf --out QCOM.exe

# 4) 目录视角（现扫，不依赖 catalog）
python scripts\feishu_dl.py tree                     # 默认遍历全部根目录（全量递归）
python scripts\feishu_dl.py tree --depth 2           # 只看两层，快
python scripts\feishu_dl.py tree --folder <folder_token>   # 只看某一个目录

# 5) 可选：生成/刷新离线快照 catalog（不是必须，只在这两种情况下用）
#    · 想离线 list 全量清单  · 反复查同一批文件想省网络
python scripts\feishu_dl.py sync
python scripts\feishu_dl.py list

# 5) 读飞书文档 / 知识库正文 → 存成 UTF-8 markdown 文件
python scripts\feishu_dl.py doc https://quectel.feishu.cn/wiki/RLOaw7nLQiwy06kEFsNcDNuEnid
```

`doc` 的正文**只写文件、不打印到控制台**（Windows cp936 管道会把 UTF-8 中文打成乱码），
控制台只回 `OK saved: <绝对路径>`，然后用 `read_file` 读那个 md。

## 搜索接口的三个硬边界（2026-11-10 实测）

1. **只按文件名/标题命中，不按目录名命中**：搜 `QDM559` 搜不到 `QDM559/V0.2.4.0.bin`
   （文件名里没有 QDM559）。所以要"某目录下有什么"，得用 `tree`/`sync`，不能靠搜索。
2. **文件夹本身不进索引**：`doc_types=FOLDER` 永远返回 0 条，搜不到 folder。
3. **`page_size` 上限 20**，传 30 直接 `99992402 field validation failed`；
   `doc_filter.folder_tokens` 在租户实测**未生效**，搜索范围 = 应用可见的全部云盘。

结论：**搜索用来"按文件名捞文件"，遍历用来"回答某目录有啥"**，两条路都要。

## 回答用户时的约定

- 下载完成必须报告：软件名、文件名、大小、**完整绝对路径**（markdown 链接形式）。
- 用户问"有哪些软件 / 某个目录里有什么"→ 直接 `tree`（现扫，实时），不要拿 catalog 快照当唯一依据。
- 搜索没命中不代表没有：**`find` 会自动降级现场扫目录**（含目录名匹配），别只回一句"没有"。

## ④ 上传（写云盘）· `scripts/feishu_upload.py`

同一个机器人身份就有写权限（建目录 / 传文件都能），不用扫码、不用切个人账号：

```bash
# 建目录（父目录给 token 或直接贴 URL）
python scripts\feishu_upload.py mkdir 手机APP --under GiihfUC0tlDJGHdTriDcH4ljnUz

# 传文件（≤20MB 走 upload_all；>20MB 自动分片）
python scripts\feishu_upload.py upload "D:\x\九号出行APP_v6.10.12.apk" --folder OfccfrVr5lcFVBd6i58c336QnCc
python scripts\feishu_upload.py upload x.zip --folder https://quectel.feishu.cn/drive/folder/XXXX

# 分批续传（agent 单条命令有 ~60s 上限时必用；中断直接重跑同一条命令）
python scripts\feishu_upload.py upload big.zip --folder XXXX --budget 40 --workers 8
```

**分片协议踩坑（2026-11-20 实测，改错就会卡在 `block missing`）**：

1. 分片序号字段名是 **`seq`**，**从 0 开始**。写成 `seq_id` 服务端不报错、静默忽略 →
   `upload_finish` 必报 `1062010 block missing, please upload all blocks`；写成 1 起会报
   `1062009 actual size is inconsistent` / `1062011 block num out of bounds`。
2. 分片大小 4MB；**末片可以是短块**，`size` 传真实字节数即可，**不用补零**
   （补零会让 `upload_finish` 认不出那块）。
3. `checksum` 传 Adler-32 的**十进制**字符串；传十六进制报 `checksum param Invalid`。
4. `upload_finish` 的 `block_num` = `upload_prepare` 返回的 `block_num`（ceil(size/4MB)）。
5. `upload_all` 对 >20MB 会 TLS 直接断（`EOF occurred in violation of protocol`），别硬试。
6. bot 上传的新文件自动带 full_access；用 `--file-token` 覆盖老文件**不会**改权限。
7. 实测速率：8 线程分片约 1.8~3 MB/s；363MB 的 apk 约 2~3 分钟。

校验落地结果：`GET /open-apis/drive/v1/metas/batch_query` 拿 url；
下载侧 `preview_download` 的 `Content-Length` 必须等于本地 `os.path.getsize()`。

## 鉴权与接口（已实测）

| 用途 | 接口 | 所需 scope |
|---|---|---|
| 取 token（2h 有效，脚本自动缓存续期） | `POST /open-apis/auth/v3/tenant_access_token/internal` | — |
| **云端搜索** | `POST /open-apis/search/v2/doc_wiki/search`（返回 `data.res_units`，不是 items） | `search:docs:read` |
| 列目录 | `GET /open-apis/drive/v1/files?folder_token=<folder>` | `drive:drive:readonly` |
| **下载文件** | `GET /open-apis/drive/v1/medias/<file_token>/preview_download?preview_type=16` | `drive:drive:readonly` |
| Wiki 节点 → 文档 id | `GET /open-apis/wiki/v2/spaces/get_node?token=<node_token>` | `wiki:*` |
| 文档正文 | `GET /open-apis/docx/v1/documents/<obj_token>/blocks?page_size=500` | `docx:document:readonly` |

## 已知边界（别踩）

1. **搜索命中结果的字段是 `res_units`**，每项在 `result_meta.token` / `title_highlighted`（标题带 `<h>` 高亮标签，要剥掉）。
2. **机器人应用没有云盘根目录**：`files list` 不带 `folder_token` 返回空列表，不能用它遍历全盘。
3. **搜索不给路径**：要显示"在哪个目录"，只能拿 `file_token` 去 catalog（`sync` 产物）反查。

⚠️ **三条踩过坑的结论**，不要改回去：

1. **不要用 `/medias/<token>/download`**：bot 身份没有 export 权限，直接 403（空响应）。
   `preview_download?preview_type=16` 才是源文件下载，实测 389,120 B 的 exe 正常落地。
2. **不要用 `/drive/v1/files/<file_token>` 取元信息**：404。列目录只能用 `?folder_token=`。
3. **大文件必断流**：>100MB 的包（如 `aboot工具.rar` 131,760,852 B）实测在 ~120MB 处
   `IncompleteRead` 断掉。脚本已内置 `Range: bytes=<have>-` 断点续传 + 最多 5 次重试，
   落地前先比对 Content-Length，不完整就报错不冒充成功 —— 别把它简化回单次 `iter_content`。

## 配置与搜索范围

**内置「团队共用只读机器人」凭据，开箱即用**（不是个人账号，可公开）：

- APP_ID `cli_a9bc97317fb89cc8`，租户 `quectel.feishu.cn`
- 想换成自己的应用时用环境变量覆盖：`FEISHU_APP_ID` / `FEISHU_APP_SECRET`

**搜索范围**：`云盘 → 软件测试部 → 软件测试二科` 下的两个根目录（多根，已内置）：

| 根目录 | folder_token | 内容 |
|---|---|---|
| 基础软件存放 | `GiihfUC0tlDJGHdTriDcH4ljnUz` | 串口/烧录/驱动/CAN/日志工具、九号上位机、升级版本包…（实测递归 84 项） |
| 项目环境搭建 | `F2T4fV4h1lzryvdGvc0cGxOHn1c` | 通用模组文档（EG915/BG95）、QDM562 |

- 换/加根目录：`FEISHU_ROOT_FOLDERS=<token1>,<token2>`（单个老写法 `FEISHU_ROOT_FOLDER=<token>` 仍兼容）
- `sync` 递归拉**所有根**写进 `software_catalog.json`（当前 52 个文件）
- `tree` 不给 `--folder` 就一次遍历所有根；`search`/`get` 走云端实时搜索，范围 = 应用可见云盘

若某个目录报 `1061004 forbidden`：让目录所有者把**这个应用**（搜索应用名，不是个人）加为可阅读协作者；
若报 `99991672 app_scope_not_applied`：开发者后台给应用补 scope（`drive:drive:readonly`、`wiki:wiki:readonly`、`docx:document:readonly`、`search:docs:read`）。

## 目录会变：现看就行，不用定期同步

两个目录是**活目录**（属主随时新增/替换/删除），所以本 skill 的设计前提是 **catalog 可有可无**：

| 你要做什么 | 用哪条 | 是否依赖 catalog |
|---|---|---|
| 找某个文件（知道名字） | `search <关键词>` → 云端实时 | ❌ 不依赖 |
| 搜索没命中，想确认"到底有没有" | `find <关键词>`（先搜索，0 命中自动现场扫两个根，**目录名也参与匹配**） | ❌ 不依赖 |
| 看目录结构 / 某目录下有什么 | `tree [--depth N]` 现扫 | ❌ 不依赖 |
| 下载 | `get <关键词>` → 搜索 → 现场扫目录 → catalog（三级兜底） | ❌ 基本不依赖 |
| 反复查询、想省点网络 | `sync` 生成 catalog（可选缓存） | ✅ 仅此场景 |

**不做定期维护**：不要求每周 sync，也不建议挂定时任务。目录变了，`find` / `tree` 现看一遍就够
（52 个文件全量扫一遍约 2~5 秒，比维护快照便宜）。

### 什么时候才需要 `sync`

- 想离线看全量清单（`list`）、或短时间内反复查同一批文件；
- `find`/`tree` 都因为网络抖动失败时的降级手段。

`sync` 会做增量对比，方便判断"最近云端动了什么"：

- `🆕 新增 N 个` / `♻️ 内容变过 N 个`（同 `file_token`、`modified_time` 变了）/ `🗑 上次有这次没了 N 个`
- 若距上次 `sync` 超过 `FEISHU_CATALOG_MAX_AGE_DAYS`（默认 7 天），`list` 会提示"已 N 天没更新"，**提示只是提醒你快照旧了，不代表要立刻同步**

其它规则：

1. 人工补的 `description` / `keywords` 按 `file_token` 保留；文件删了条目自动消失。
2. 根目录本身变了（部门重组/新增根）→ 改 `FEISHU_ROOT_FOLDERS` + `ROOT_LABELS` 两处，逻辑不用动。
3. 新加的子目录不用管，`walk` 递归自动发现。

其它默认值：

- token 缓存：`~/.feishu_tat_cache.json`（提前 300s 续期，不用每次重取）

## 软件目录

`software_catalog.json`（与 SKILL.md 同目录）由 `sync` 生成，结构：

```json
{
  "root_folders": ["GiihfUC0tlDJGHdTriDcH4ljnUz", "F2T4fV4h1lzryvdGvc0cGxOHn1c"],
  "last_sync": "2026-11-10T16:18:06+08:00",
  "software": [
    {"name": "QCOM", "file_token": "P5MRbbMa5onIDkx1u8aciFnanSf",
     "filename": "QCOM_V1.6.exe", "folder": "基础软件存放/串口工具",
     "description": "高通串口/诊断工具", "keywords": ["qcom", "高通", "基础软件存放/串口工具"]}
  ]
}
```

`folder` 是「根目录名/相对路径」，用来给搜索结果补目录、回答"某目录下有什么"。
`sync` 后人工补的 `name`/`description`/`keywords` 会按 `file_token` 保留，不会被云端文件名冲掉。

> 别再手工维护这张表：`list` 打全量、`tree` 打目录树、`search` 打云端命中。三者任一都比手写表格准。
> 相关但不同职责的 skill：`flash-tools` / `qflash` 讲**怎么用**这些烧录工具，本 skill 只负责**把工具捞下来**。

## 错误处理

| 现象 | 原因 | 处理 |
|---|---|---|
| `1061004 forbidden` | 该云盘目录没共享给这个**应用**（不是共享给用户） | 让共享人把应用加为协作者（可阅读），搜索应用名而不是个人名 |
| `99991672 app_scope_not_applied` | 应用缺 scope（`drive:drive:readonly` / `wiki:*` / `docx:document:readonly`） | 开发者后台申请应用身份权限：`https://open.feishu.cn/app/<app_id>/auth` |
| 下载 403 / 空响应 | 用了 `/medias/.../download` | 换 `preview_download?preview_type=16`（脚本已内置） |
| token 401 / app_secret 无效 | Secret 被重置 | 后台重置 Secret 后更新环境变量 `FEISHU_APP_SECRET` 或 `~/.feishu_app.json` |
| 搜不到文件 | 关键词太长 / 目标在别的目录 / 文件名里没有该词 | 换更短关键词再 `search` → 仍没有就 `tree` 人工看 |
| `99992402 field validation failed` | `page_size` > 20 | 脚本已限制 20，别调大 |
| 搜索 0 条但目录里明明有 | 搜的是目录名（目录不进索引） | 用 `tree`/`sync`，别用 `search` |
| 列根目录返回空 | 机器人应用没有云盘根目录 | 必须给 `folder_token`（`tree --folder`） |
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

## 上传文件到云盘（2026-11-20 实测）

机器人身份可以上传文件到云盘文件夹，**不需要额外开权限**（只要有 `drive:drive` scope）。

### 上传接口

```python
import requests

url = "https://open.feishu.cn/open-apis/drive/v1/medias/upload_all"
headers = {"Authorization": f"Bearer {token}"}

with open(file_path, "rb") as f:
    files = {
        "file_name": (None, os.path.basename(file_path)),
        "parent_type": (None, "explorer"),
        "parent_node": (None, folder_token),
        "size": (None, str(os.path.getsize(file_path))),
        "file": (os.path.basename(file_path), f, "application/octet-stream"),
    }
    resp = requests.post(url, headers=headers, files=files)

data = resp.json()
if data.get("code") == 0:
    file_token = data["data"]["file_token"]
```

### 创建子文件夹

```python
url = "https://open.feishu.cn/open-apis/drive/v1/files/create_folder"
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
body = {"name": "QDM562", "folder_token": parent_folder_token}
resp = requests.post(url, headers=headers, json=body)
```

### 踩过的坑（2026-11-20）

1. **云盘权限 ≠ 多维表格权限**：机器人能上传到云盘文件夹，但不一定能写入多维表格。
   - 云盘上传：`drive:drive` scope，机器人默认有
   - 多维表格写入：需要单独在多维表格里给机器人开"可编辑"权限（91403 Forbidden 就是没开）
   - **不要混淆**："压测脚本记录"是多维表格（bitable），"压测脚本云盘"是文件夹（folder），两个东西

2. **用户说"放脚本的地方"通常指云盘文件夹**：导航页面里的"压测脚本记录"是多维表格，但实际脚本文件放在云盘 `BTmtfevlhlORjVdyeWscINqEnBd` 文件夹下。上传脚本时直接传到云盘文件夹，不要往多维表格里加记录（除非用户明确要求）。

3. **上传大文件会断流**：和下载一样，>100MB 的文件可能断流，需要断点续传（`Range: bytes=<have>-`）。脚本已内置重试逻辑。

4. **导航是纯文本渲染，desc 里不要写 markdown `**`**：会原样显示成星号。

### 凭据脱敏规则（2026-11-20 用户确认，重要）

上传 `device.yaml` / 配置类文件到云盘时，判断账号类型决定脱不脱敏：

| 账号域名 | 处理 |
|---|---|
| `@ikotek.com`、`@quectel.com`（公司邮箱） | **必须脱敏**：密码换成占位符 |
| 其他（客户邮箱，如 `@ninebot.com` 等） | **不要脱敏**：账号密码原样保留 |

理由：客户平台的账号是测试必需的凭据，脱敏了别人拿到配置也连不上；公司邮箱属于员工个人账号，需要遮。

所以「一律脱敏」和「一律不脱敏」都是错的，**按域名判断**。


### 实测案例

2026-11-20 上传 QDM562 上位机升级脚本：
- 目标文件夹：`BTmtfevlhlORjVdyeWscINqEnBd`（压测脚本云盘）
- 创建子文件夹：`QDM562`（token: `UF4FfLsLbldKWDdFktncm6NPnye`）
- 再创建子文件夹：`上位机升级压测`（token: `Wjymf8saclFGdqdm9Zxc7GLTnsg`）
- 上传文件：`QDM562上位机升级_V3.1_gnss可选.py`（505 KB）、`device.yaml`
- 结果：✅ 成功，文件夹链接 https://quectel.feishu.cn/drive/folder/Wjymf8saclFGdqdm9Zxc7GLTnsg

### 上传脚本的组织结构（2026-11-20 经验）

**不要把脚本文件直接散放在项目文件夹根目录**，应该按脚本类型分子文件夹：

```
QDM562/                          ← 项目文件夹
  上位机升级压测/                  ← 按脚本类型分
    QDM562上位机升级_V3.1_gnss可选.py
    device.yaml
  开关机压测/                      ← 以后加别的脚本
    xxx.py
  OTA压测/
    yyy.py
```

**原因**：一个项目可能有多种压测脚本（上位机升级、开关机、OTA、FCT 等），直接散放会混乱，按类型分子文件夹便于管理和查找。

**删除文件接口**：
```python
url = f"https://open.feishu.cn/open-apis/drive/v1/files/{file_token}?type=file"
headers = {"Authorization": f"Bearer {token}"}
resp = requests.delete(url, headers=headers)
```
