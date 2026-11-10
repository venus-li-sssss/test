---
description: Use this skill when 用户要操作妙搭平台的 skill 仓库（scnrhostplnc.aiforce.cloud）：妙搭仓库、上传到妙搭、妙搭下载skill、平台仓库同步、user-skills
  仓库、CPE 仓库、列平台仓库、看仓库提交、删仓库文件、aiforce 仓库读写。GitHub 仓库请用 skill仓库同步。
name: 妙搭仓库同步
---

# 妙搭仓库同步（`scnrhostplnc.aiforce.cloud` 上的 skill 仓库）

妙搭平台上有一批**仓库**（`user-skills`、`CPE`、`QDM121`、`丢包率测试`…），每个仓库带分支和 commit 历史。这个 skill 负责**从这些仓库下载 skill / 把本地 skill 传上去 / 看仓库里有什么 / 删远端文件**。

内置 apikey，开箱即用，不用登录网页。

> 这是**平台仓库**，跟 GitHub `venus-li-sssss/test` 是两套东西。GitHub 那份用 `/skill仓库同步`，别混。

## 执行

```bat
set MS=python "<此 SKILL.md 所在目录>\scripts\miaoda_repo.py"

:: 平台上有哪些仓库
%MS% repos

:: 当前仓库（默认 user-skills）概况 / 分支 / 最近提交
%MS% info
%MS% branches
%MS% log -n 10

:: 有哪些 skill、各多少文件
%MS% list
%MS% tree 抓取串口日志

:: 下载
%MS% pull 抓取串口日志 --dest skills\抓取串口日志
%MS% get README.md --out README.md

:: 上传（新增/更新/删除一次提交）
%MS% push skills\某skill -m "说明"
%MS% push skills\某skill --dry-run          :: 只算差异，不提交
%MS% rm 旧目录/旧文件.md -m "删掉"

:: 换仓库 / 换分支
%MS% --repo CPE list
%MS% --repo 丢包率测试 --branch main log -n 5
```

`--repo` 和 `--branch` 是**全局参数**，要写在子命令前面。

退出码：`0` 成功 · `1` 一般错误 · `2` 鉴权失败 · `3` 没有变化、未提交。

## apikey 与坐标

| 项 | 值 |
|---|---|
| 平台 | `https://scnrhostplnc.aiforce.cloud/app/app_17b0ap920df` |
| 默认仓库 | `user-skills`（`61615b55-39a2-4ad9-9583-a41b839f3f81`） |
| 默认分支 | 仓库的默认分支（`user-skills` 是 `main`） |
| apikey | 内置在脚本里，hex 存放，运行时还原 |

覆盖方式（不改脚本）：

```bat
set MIAODA_API_KEY=xxx
set MIAODA_USER=某邮箱
set MIAODA_REPO=CPE
set MIAODA_BASE=https://scnrhostplnc.aiforce.cloud/app/app_17b0ap920df
```

请求头两个都要：`Authorization: Bearer <apikey>` 和 **`x-user-name: <邮箱>`**（少了后者直接失败）。平台按 `x-user-name` 记账，所以换人用要改 `MIAODA_USER`。

## 接口（踩清楚了再用）

| 用途 | 接口 |
|---|---|
| 列仓库 | `GET /openapi/repos` |
| 列分支 | `GET /openapi/repos/{repoId}/branches`（要 headCommitId 只能走这个，`/repos` 里那个 branches 数组不含） |
| 文件树 | `GET /openapi/files/tree?branchId=` → 嵌套 `children`，要自己递归展平 |
| 读单文件 | `GET /openapi/files?branchId=&path=` → `content`（404 = 不存在） |
| 提交列表 | `GET /openapi/repos/{repoId}/commits?branchId=&pageSize=` |
| 提交 | `POST /openapi/repos/{repoId}/commits`，body: `{branchId, message, changes:[{path, action, content}], userName}`，`action` = `create` / `update` / `delete`，成功返回 201 |

## 和 GitHub 那份最大的区别（非常重要）

**这个平台每次 `POST commits` 都会产生一个 commit，哪怕内容一个字都没变。** 它没有"内容 sha"可比，所以脚本 push 前会**逐个文件 `GET` 读回来比对内容**，只把真正变了的放进 `changes`；全都没变就返回 3、不提交。

别为了省事跳过这个 diff —— 之前用 `sync_upload.py` 全量推的时候，同一个文件推几次就是几个 commit，历史会变垃圾。

文件树里也有 `status` 字段（`clean` / `created` / `updated`），但它反映的是 working 状态，不保证能替代内容比对，别拿它当 diff 依据。

## 平台限制

1. **只收 UTF-8 文本**。二进制（zip / docx / png / exe）传上去没意义，脚本遇到非 UTF-8 文件会跳过并提示。
2. 单个 commit 的 `changes` 不要太大（网络请求会超时）；几百 KB 的 skill 目录没问题，几十 MB 的先别传。
3. 中文目录名、路径都正常（走 JSON body，不用 URL 编码）。
4. `user-skills` 里有 `skill-repo-backup/`、`.disable_to_model_invocation_migration.json`、`skill.json` 这类系统文件，**push 时别用 `--prefix ""` 往仓库根灌**，那会把不相关的基础设施文件也卷进来。

## 常见流程

**把本地 skill 传到妙搭**（已有同名目录会就地更新，多余文件默认删掉）：

```bat
%MS% push skills\抓取串口日志 --dry-run     :: 先看 A/M/D
%MS% push skills\抓取串口日志 -m "更新说明"
```

**把妙搭上的 skill 拉到本地**：

```bat
%MS% pull 抓取串口日志 --dest skills\抓取串口日志
```

`--no-prune` 可以保留"远端有、本地没有"的文件；默认是删掉（同步语义），所以先 dry-run。

## 依赖

`requests`。