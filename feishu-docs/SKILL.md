---
name: feishu-docs
description: Use this skill when 用户要把**飞书云文档 / 知识库 wiki / 多维表格 base / 电子表格 sheets** 的内容读出来或导出：读飞书文档正文、看知识库某一篇、查/导多维表格（样机管理库、团队架构、物资管理、压测脚本记录、GNSS RTK账号表）、把表格导成 CSV/JSON、按字段过滤记录、看表有哪些字段。免扫码走团队只读机器人身份。触发词：飞书文档、飞书 wiki、知识库内容、读飞书文档、多维表格、base 表、bitable、查表格、导出多维表格、样机管理库、团队架构、物资管理、压测脚本记录、RTK账号、表格转CSV、字段列表、feishu doc、wiki 正文。**下载云盘里的文件请用 feishu-software-download**。
---

# 飞书文档体系读写（云文档 / 知识库 / 多维表格 / 电子表格）

一个脚本 `scripts/feishu_docs.py`，统一走**团队只读机器人**（应用身份 `tenant_access_token`），不扫码、不依赖个人登录态。

> 分工：**读内容** 用本 skill；**下载云盘文件**（exe/zip/安装包）用 `feishu-software-download`。
> 两者是**同一个机器人身份**，所以权限模型一致：谁能读，取决于机器人有没有被加成协作者。

## 快速开始

```bat
set FD=python "<此 SKILL.md 所在目录>\scripts\feishu_docs.py"

%FD% info   <url>                     :: 先看是什么类型（docx/wiki/base/sheet）+ 表清单
%FD% read   <url> -o out.md           :: 读正文/内容（docx、wiki 都行）
%FD% read   <url> --table 样机登记     :: base：读某个表（默认第一个表）
%FD% read   <url> -o out.csv          :: base/sheet：导成 CSV（UTF-8-BOM，Excel 直接开）

%FD% base tables  <url>               :: 这个多维表格有哪些数据表、各多少字段
%FD% base fields  <url> --table 样机登记
%FD% base records <url> --table RTK账号表 --limit 5
%FD% base records <url> --where "账号状态=可用" --json
%FD% base export  <url> --table RTK账号表 -o rtk.csv
%FD% wiki tree    <wiki url>          :: 知识库顶层节点
%FD% token                            :: 排查用，打印 tenant_access_token
```

认的链接形式：`/wiki/<token>`、`/docx/<token>`、`/sheets/<token>?sheet=`、`/base/<token>?table=tbl…`、`/docs/<token>`，也接受裸 token。

## 典型用法（AI 侧）

- “RTK 还有哪些账号可用” → `base records <RTK base 链接> --table RTK账号表 --where "账号状态=可用"`
- “把样机管理库导给我” → `base export <链接> --table <表名> -o 样机.csv`
- “这两轮车知识库写了啥” → `read <wiki 链接> -o kb.md`（正文写文件，别直接打印，cp936 管道会乱码）
- “团队架构里谁负责 X” → `wiki tree` 找到节点 → `read` 子节点

## 权限模型（最重要的坑）

同一个机器人身份，**能读哪些 wiki/base 取决于有没有被加成协作者**。实测状态（2026-11-13，授权后复测）：

| 资源 | 状态 |
|---|---|
| GNSS 的 RTK 账号信息（独立 base） | ✅ 可读（RTK账号表 3 行、预约记录表） |
| 软测知识库（space `7572883271840088068`）下的全部节点 | ✅ 可读 |
| ├ 两轮车 / 新人培训 / 日常工作流程 / GNSS资料 / 标准模板 / 远程服务器工具 | ✅ docx 正文 578 / 3209 / 190 / 15 / 16 / 237 字 |
| ├ 样机管理库 / 团队架构 / 物资管理（wiki 里的多维表格） | ✅ 各 3 张表（样机清单、团队主要负责人、物资清单…） |
| ├ 标准模板的子页面（含 sheet） | ✅ 子页 docx 4215 字；TFT 测试标准 sheet 200 行 × 26 列 |
| AI方案知识库 / FWA / Tracker | ✅ 可读 |
| 压测脚本记录（独立 base `NknpbHSoTaoQNlseKm5cRwpqnUh`） | ✅ 4 张表（2026/2025/2024 非FWA脚本需求、FWA脚本） |
| 知识库里其它多维表格 | ✅ 任务大厅（9 表）、JIRA缺陷库（28 字段）、客户问题库（17 字段）、SMOD、器件资料 |

**关键经验：在知识库里给「最上层的那个节点」加机器人协作者 + 勾「所有子页面可用」，整个子树（docx / 多维表格 / 电子表格都算）一次性全开**，不用逐个页面加。但它**只覆盖同一知识库空间**；独立的 base（如压测脚本记录、GNSS RTK）要单独加协作者。

修法（一次性）：在飞书里打开那个知识库节点 / 多维表格 →「···」→ 添加协作者 → 加上**只读机器人应用**（共享对话框里显示为「识别图片 latex 的结果」`cli_a9bc97317fb89cc8`），给可阅读/可管理权限。

脚本对这两类错误已经翻译成人话（`131006` 提示加协作者、`91403` 提示加多维表格协作者、`99991672` 提示缺 scope），**别硬试第二次，直接把提示转述给用户**。

## 接口备忘

| 用途 | 接口 |
|---|---|
| 换 token | `POST /open-apis/auth/v3/tenant_access_token/internal` |
| wiki 节点 → 真实对象 | `GET /open-apis/wiki/v2/spaces/get_node?token=&obj_type=wiki` → `obj_type/obj_token` |
| 知识库节点列表 | `GET /open-apis/wiki/v2/spaces/{space_id}/nodes` |
| 云文档正文 | `GET /open-apis/docx/v1/documents/{id}/raw_content` |
| 云文档标题 | `GET /open-apis/docx/v1/documents/{id}` |
| 表格工作表 | `GET /open-apis/sheets/v3/spreadsheets/{token}/sheets/query` |
| 表格数据 | `GET /open-apis/sheets/v2/spreadsheets/{token}/values/{range}`（range 写 `Sheet1!A1:Z200`） |
| 多维表格 | `GET /open-apis/bitable/v1/apps/{app}/tables`、`…/tables/{t}/fields`、`…/tables/{t}/records`（`page_size≤200`、`has_more`+`page_token` 翻页） |

## 踩过的坑

1. **wiki 链接不能直接当 docx 用**：必须先 `get_node` 拿到 `obj_token`；wiki 节点还可能是 `bitable`/`sheets`/`file`，所以先 `info` 再读。脚本已把 wiki 的 `bitable` 归一成 `base`。
2. **多维表格字段值是嵌套结构**（人员是 `[{name}]`、多选是 list、日期是毫秒时间戳），脚本统一扁平化成字符串；自己写代码时别直接 `print(fields)`。
3. **`/base/<token>` 里的 token 是 app_token，不是 table_id**；`table=tbl…` 才是表。
4. **读电子表格要传 `sheet_id` 不是表名**：`range` 写成 `<sheet_id>!A1:Z200`，传 name 会报 `90215 not found sheetId`。
5. **导出 CSV 一定要 `utf-8-sig`**，否则 Excel 打开中文乱码。
6. **敏感数据**：RTK 账号表里有账号/密码，导出后别贴到外部或写进公开仓库。
7. 正文**只写文件不打印**（`-o out.md`），Windows 控制台是 cp936，直接打印 UTF-8 中文会花。
8. `docx` 的 `raw_content` 是纯文本（丢样式；容器页可能只有十几个字，真正的正文在子页），要块级结构（表格/图片）得走 `/docx/v1/documents/{id}/blocks`，本脚本暂不展开。
