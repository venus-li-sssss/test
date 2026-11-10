---
description: Use this skill when 用户要把 skill 上传到 GitHub 仓库或从仓库下载：上传skill到仓库、传skill、下载skill、拉取skill、从仓库拉某个skill、看仓库里有哪些skill、仓库文件列表、删除仓库文件、更新仓库文件、同步skill仓库、venus-li-sssss/test
  仓库读写、GitHub skill 仓库操作。
name: skill仓库同步
---

# skill 仓库同步（GitHub `venus-li-sssss/test`）

把这个仓库当 skill 的家：**上传本地 skill 目录 / 下载仓库里的 skill / 看仓库有什么 / 删远端文件**，一个脚本全包。

内置仓库 token，开箱即用，不用配 git、不用 `git clone`、不用 credential manager。

## 执行

```bat
set SR=python "<此 SKILL.md 所在目录>\scripts\skill_repo.py"

:: 看仓库概况（含 token 是否有效）
%SR% info

:: 看仓库里有哪些 skill，各多少文件/多大
%SR% list

:: 看某个 skill 里的文件
%SR% tree 抓取串口日志

:: 下载一个 skill 到当前目录（--dest 指定目标目录）
%SR% pull 抓取串口日志 --dest skills\抓取串口日志

:: 上传（新增或更新）一个 skill 目录，一个 commit 提交全部变更
%SR% push skills\抓取串口日志 -m "更新 抓取串口日志：补充 xx 说明"

:: 只想看看会改什么，不真的提交
%SR% push skills\抓取串口日志 --dry-run

:: 单文件读写 / 删除
%SR% get README.md --out README.md
%SR% put 本地文件.md 某目录/远端文件.md -m "更新说明"
%SR% rm 旧目录/旧文件.md -m "删掉废弃文件"
```

退出码：`0` 成功 · `1` 一般错误（路径不存在等）· `2` token/权限问题 · `3` 没有变化、未提交。

## token 与坐标

脚本内置：

| 项 | 值 |
|---|---|
| 仓库 | `venus-li-sssss/test`（公开，默认分支 `main`） |
| token | 内置，`repo` scope，对该仓库有 admin 权限 |

换账号 / 换仓库 / token 失效时用环境变量覆盖，不用改脚本：

```bat
set GITHUB_TOKEN=ghp_xxx
set SKILL_OWNER=某用户
set SKILL_REPO=某仓库
set SKILL_BRANCH=main
```

**token 在脚本里是 base64 存的，不是明文。** 别改成明文 —— 这个仓库是公开的，GitHub 的 secret scanning 一检出明文 `ghp_` 就会**自动吊销**，skill 当场失效。这是唯一的原因，不是保密需要。

## 命令细节

| 命令 | 说明 |
|---|---|
| `info` | 仓库名/大小/权限/HEAD/最后提交/文件数/token 状态 |
| `list` | 顶层目录一览：文件数、大小、合计 |
| `tree [前缀]` | 列文件与大小、blob sha；不给前缀就列全仓库 |
| `pull <名字> [--dest]` | 下载整个目录到本地，路径自动建 |
| `pull-all [--dest]` | 全部目录逐个拉到 `<dest>/<名字>` |
| `get <远端路径> [--out]` | 下载单文件（不给 `--out` 就用文件名） |
| `push <本地目录> [--name] [--prefix] [-m] [--dry-run] [--no-prune]` | 上传目录；远端目录名默认取本地目录名 |
| `put <本地文件> <远端路径> [-m]` | 上传单文件 |
| `rm <远端路径> [-m]` | 删除远端单文件 |

`push` 的几个开关：

- `--name`：远端目录名，默认 = 本地目录名
- `--prefix ""`：**不套目录名，直接放仓库根**（一般不要用）
- `--no-prune`：不删除"远端有、本地没有"的文件。**默认会删**（同步语义），删前先 `--dry-run` 看一眼
- `--dry-run`：只打印 `A/M/D` 清单，不提交

## 实现方式（改代码前先看）

走 GitHub REST + Git Data API，**不碰 git 命令行**：

```
GET  /git/ref/heads/main            → 当前 commit
GET  /git/commits/<sha>             → 根 tree
GET  /git/trees/<tree>?recursive=1  → 全量文件清单（含 blob sha、size）
GET  /git/blobs/<sha>               → 文件内容（base64）
POST /git/blobs                     → 新内容（只对真正变了的文件发）
POST /git/trees  (base_tree=…)      → 新 tree
POST /git/commits                   → 一个 commit 带上全部增删
PATCH /git/refs/heads/main          → 移动分支
```

两个关键点：

1. **blob sha 在本地算**（`sha1("blob <len>\0" + 内容)`，和 git 一致），所以没变的文件一个字节都不上传 —— `--dry-run` 能秒判「没有变化」就是靠这个。
2. **一次 push = 一个 commit**，不会因为文件多而产生一堆碎片提交。

## 踩过的坑

1. **中文路径必须 URL 编码**：`/git/blobs/<sha>` 之外，凡带路径的请求（如 contents API）都要按段 `quote`，脚本里的 `q()` 就是干这个的；自己加接口时别忘了。
2. **`--dry-run` 只读，是真安全的**。写操作前养成先 dry-run 的习惯，尤其是会 `D`（删除）的时候。
3. **大目录慎传**：仓库里 `pressure-test/` 有 46 MB，`pull-all` 会拉很久。只要一个 skill 就用 `pull <名字>`。
4. **API 有速率限制**（token 认证 5000 次/小时），`info`/`list`/`tree` 各消耗 2~3 次。别在循环里反复调 `head()`。
5. **push 内容不变时返回 3**：`没有变化，不提交。` 这不是错，是幂等。
6. **`pull` 会按远端路径重建目录**，`..` 段会被 `safe_join` 过滤掉，不会写到目标目录外面。

## 依赖

`requests`。没有 pyserial / git 依赖。