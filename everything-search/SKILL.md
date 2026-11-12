---
description: 'Use this skill when the user wants to search/locate files on Windows fast, without opening any GUI: 搜文件、找文件、查文件在哪、全盘搜索、按扩展名找、最近改过的文件、最大的文件、某个型号的固件包在哪、Everything、es.exe、locate/find a file, where is X, list files matching a pattern. Backed by the Everything index through the official es.exe IPC client.'
name: everything-search
---

# everything-search

让 AI 直接调用 **Everything 的索引**做全盘文件搜索，毫秒级返回。全程走 Everything 原生 IPC（官方 `es.exe` 客户端），**不打开、不点击、不截屏任何 GUI**。

- `bin/es.exe` —— voidtools 官方命令行客户端（ES 1.1.0.27）。**不随仓库分发**（第三方二进制，受其许可约束）；本机已有就在 `bin\`，没有时脚本首次运行会自动从 voidtools 下载
- `scripts/everything_search.py` —— 封装层：结构化 JSON 输出、Everything 语法、自动兜底
- `scripts/selftest.py` —— 20 条回归用例，改脚本后必跑

本机情况：Everything **1.4.1.1017 (x86)**，装在 `C:\Program Files (x86)\Everything`，索引服务常驻（`*.dll` 约 6.3 万条，`*.zip` 约 6600 条）。

## 用法

```bat
:: 在 skill 的 scripts 目录下执行
python everything_search.py <query> [选项]
```

```bat
:: 按文件名找
python everything_search.py "partition.bin" -n 10

:: 找固件包，按大小降序
python everything_search.py "ext:fbf" --sort size --desc -n 5

:: 限定目录 + 只要最新的 Excel
python everything_search.py "ext:xlsx" --path "D:\work\QDM562" --sort date-modified --desc -n 5

:: 文件夹，名字含「测试」
python everything_search.py "测试" --folders-only -n 20 --columns "name,path"

:: 正则 + 全路径匹配
python everything_search.py "QDM5[0-9][0-9].*\.xlsx" -r --match-path -n 5

:: 只要数量，不要列表
python everything_search.py "ext:log" --path "D:\work" --count-only

:: 纯路径列表，方便管道给别的工具
python everything_search.py "*.dll" --format paths

:: 最近一天内改过的 bin
python everything_search.py "ext:bin dm:today" -n 10
```

## 参数

| 参数 | 说明 |
|---|---|
| `query` | Everything 搜索语法（见下），空格分隔即 AND |
| `-n/--limit` | 最多返回条数，默认 20，`0` = 不限 |
| `--offset` | 跳过前 N 条（翻页） |
| `--path` | 只搜这个目录（递归） |
| `--parent` | 只搜直接父目录等于该路径的结果 |
| `--ext` | 简写，逗号分隔扩展名 → `ext:a;b` |
| `-r/--regex` | query 按正则解释 |
| `--case` / `--whole-word` / `--match-path` | 区分大小写 / 全词 / 匹配完整路径 |
| `--folders-only` / `--files-only` | 只要目录 / 只要文件 |
| `--sort` | `name,path,size,extension,date-created,date-modified,date-accessed,run-count` |
| `--desc` | 降序（配 `--sort`） |
| `--columns` | `name,path,fullpath,size,extension,date_created,date_modified,date_accessed,attributes,run_count`；默认 `fullpath,size,dm` |
| `--format` | `json`（默认）/`paths`/`tsv`/`csv` |
| `--count-only` | 只输出匹配总数 |
| `--instance` | 非默认 Everything 实例名（多实例场景，会先预检） |
| `--query-file` | 从 UTF-8 文件读 query，彻底避开控制台代码页乱码 |
| `--debug-command` | 把实际下发的 es.exe 命令行打到 stderr（排查用） |
| `--no-repair` | 关闭中文乱码自动修复 |
| `--raw` | 原样透传额外 es.exe 开关 |
| `--no-auto-start` | 索引没起来时不要尝试拉起 Everything |
| `--allow-empty` | 允许空 query（会列出整个索引，一般别用） |

## Everything 语法速查（已在本机实测有效）

| 写法 | 含义 |
|---|---|
| `foo bar` | 同时包含 foo 和 bar（AND，顺序无关） |
| `foo|bar` | OR |
| `!foo` | 排除 |
| `*.fbf` / `?.txt` | 通配符 |
| `ext:bin` / `ext:bin;fbf` | 按扩展名 |
| `size:>100mb` `size:1mb..10mb` | 按大小 |
| `dm:today` `dm:2026-09-01` `dm:last7days` | 按修改时间 |
| `dc:` `da:` | 创建 / 访问时间 |
| `path:D:\work` | 路径包含 |
| `parent:D:\work\x` | 直接父目录 |
| `\work\QDM` | 含路径分隔符自动匹配全路径 |
| `case:foo` | 区分大小写 |
| `"foo bar"` | 字面短语（**会关掉函数和运算符**，慎用） |
| `attrib:H` `/ad` `/a-d` | 属性 / 只要目录 / 只要文件 |

## 输出格式

```json
{
  "ok": true,
  "query": "partition.bin",
  "count": 3,
  "limited": true,
  "results": [
    {"path": "C:\\...\\partition.bin", "name": "partition.bin",
     "size": 2188, "date_modified": "2026-09-23T21:20:34"}
  ]
}
```

失败时 `{"ok": false, "error": "...", "hint": "..."}`，退出码非 0。`count` 是**本页**条数，`limited: true` 表示被 `-n` 截断，需要总数请用 `--count-only`。

## 坑（都是实测踩出来的，改脚本前先读）

1. **搜索串不能被引号包住。** ES 会把命令行里的双引号原样透传给 Everything，而 Everything 把带引号的搜索当「字面短语」——于是 `ext:` `size:` `dm:` 全部失效、`|` 变成普通字符、空格不再表示 AND。表现极其反直觉：`ext:bin` 返回 0，但 `*.bin` 正常。
   → 封装层因此**自己拼命令行为字符串**（`shell=False` 直接走 CreateProcess，不经 cmd.exe，所以 `|` `&` 也不用转义），query 永远不加引号，只对 `-path` 这类值按需加引号。
2. **`-r` 是带参选项**，必须紧贴在搜索串前面。放在开关中间会让它把下一个开关当成正则。
3. **CSV 里没有 `Filename` 列的情况**：用 `-name`+`-path-column` 导出时表头是 `Name,Path`，必须两列拼回全路径；用 `-full-path-and-name` 才是整行全路径（表头仍叫 `Filename`）。
4. **IPC 失败时 es.exe 退出码是 0**，错误只写在 stderr（`Error 8: Everything IPC window not found`）。只判退出码会把故障当「0 结果」。封装层按关键词识别并可选自动拉起 Everything。
5. **`-instance` 传不存在的实例名会静默回落**，返回看似正常的空结果。封装层先用 `-get-everything-version` 预检。
6. 导出统一走 `-export-csv ... -utf8-bom` + `utf-8-sig` 读文件，避开控制台代码页把中文路径搞成乱码。
7. 空结果不报错（退出码 0，CSV 只有表头），属正常，`ok:true, count:0`。
8. **中文 query 会被 cmd.exe 的代码页搞坏。** 命令以 UTF-8 交给 cmd（代码页 936）时，cmd 按 GBK 解一遍再交给 Python，于是 `日志抓取.exe` 变成 `鏃ュ織鎶撳彇.exe`，搜出来全是空。封装层用「encode(cp936) → decode(utf-8) 往返成功即判定为乱码」自动修复（真中文过不了这个往返，不会被误改）；要完全杜绝就用 `--query-file` 把查询写进 UTF-8 文件。
9. **`--columns` 只要 `path`（目录列）而不要 `name` 时**，CSV 里根本没有文件名，解析回来就会变成一条条"目录"、大小还错位。封装层检测到这种组合会自动补 `-name`。

## es.exe 缺失 / 换版本

刚 pull 下来时 `bin\` 是空的（仓库不存第三方二进制），**首次运行会自动下载**（`--auto-download` 默认开）。手动补：

```bat
curl -L -o "%TEMP%\es.zip" https://www.voidtools.com/ES-1.1.0.27.zip
powershell -Command "Expand-Archive '%TEMP%\es.zip' -DestinationPath '<skill>\bin' -Force"
```

## 自检

```bat
python scripts\selftest.py
```

20 条用例覆盖上面每个坑（含中文乱码修复、files-only、path 列解析）；全绿才算没退化。
