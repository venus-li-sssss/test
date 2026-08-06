---
name: changelist2xlsx
description: 将 git changelist（修改点）txt 导入 SMOD 平台并自动新增测试用例。当用户提供 changelist/修改点 txt 并给出版本号（如 QDM559_STM32G0B0_APP_01.001.01.001_V19）时使用。触发场景：(1) 用户给了 changelist txt + 版本号，要"导入到平台"、"把修改点导入SMOD"、"生成测试用例"、"先导入再建用例"；(2) 用户说"按以前的逻辑先导入到平台，然后在以前的基础上面新增测试用例"。注意：本技能绝不输出"修改点测试报告"之类的文档，所有结果直接写入 SMOD 平台。
agent_created: true
---

# Changelist → SMOD 导入 + 测试用例工作流

把 git changelist（修改点）txt：**① 生成同名 Excel 清单 → ② 直接导入到 SMOD 平台 → ③ 导入完成后，基于修改点描述自动新增测试用例并设置测试结果。**

> ⚠️ **关键约束：本技能绝不输出「修改点测试报告」之类的文档。**
> 所有结果都**直接写入 SMOD 平台**（导入修改点、新建测试用例、设置测试结果）。
> 唯一落地的文件是第 1 步生成的同名 `.xlsx`（作为记录），**除此之外不再生成任何报告文件**。

## 触发 / 不触发

- ✅ 触发：用户给了 changelist txt + 版本号，要"导入平台、建用例"。
- ❌ 不触发：用户只想要「一份 Excel 或测试报告的文档」——本技能做的是平台写操作，不是文档生成。
  （若只想转 xlsx，可单独运行 `scripts/changelist_to_xlsx.py`。）

## 前置条件

- **登录凭证（二选一）**：
  - **推荐**：**SMOD/SSO 用户名 + 密码**，脚本会自动调用登录接口拿到 access_token。SSO 现在要求密码用 RSA（PKCS#1 v1.5）加密，脚本已内置公钥并会自动加密（无需手动操作）。
  - **备用**：浏览器 DevTools 复制的 `access_token`（去掉 `bearer` 前缀）。
- **依赖**：`pip install requests openpyxl pycryptodome`（优先使用受管 venv：`C:/Users/venus.li/.workbuddy/binaries/python/envs/default/Scripts/python.exe`）。`pycryptodome` 用于密码的 RSA 加密登录。

## 工作流程

### 步骤 0：确认输入
从用户消息取得：
- 修改点 **txt 路径**（绝对路径优先）
- **版本号**（用于提取项目名 + 匹配/新建版本）
- **用户名 + 密码**（优先）或 **access_token**（备用）

如果用户没给 txt、版本号或登录凭证，脚本会自动弹出输入框（tkinter，无图形环境时回退到命令行 `input`）让用户补全，无需手动重输完整命令。

### 步骤 1：运行工作流脚本
脚本 `scripts/smod_changelist_import.py` 已内联 txt→xlsx 转换（与 `changelist_to_xlsx.py` 一致），并串起完整 SMOD 流程。

**通过登录接口自动鉴权（推荐）：**
```bash
python scripts/smod_changelist_import.py ^
    "<输入.txt>" ^
    "<版本号>" ^
    --username "Venus.Li@ikotek.com" ^
    --password "你的SSO密码"
```

**或用浏览器 token 注入（备用）：**
```bash
python scripts/smod_changelist_import.py ^
    "<输入.txt>" ^
    "<版本号>" ^
    --token "<access_token>"
```

可选参数：
- `--platform odmm`：平台代码，默认 `odmm`
- `--xlsx <path>`：指定生成 xlsx 的位置（默认与 txt 同名同目录）
- `--no-create`：若版本不存在则不新建，直接退出

### 脚本内部 7 步流程
1. **生成 Excel**：解析 commit，输出「修改点」清单（10 列 + 分类推导），风格与 spliter_tool 一致。
2. **解析版本号**：`QDM559_STM32G0B0_APP_01.001.01.001_V19` → 项目名 `QDM559`。
3. **登录 SMOD**：调用 SSO 登录接口（`/api/uaa/oauth/token`）用【RSA 加密后的密码】换 SSO token，再写入 `quectel_token` 会话 cookie 并经 OAuth 重定向拿到 SMOD access_token；也支持直接注入浏览器 token。
4. **推断平台**：搜索项目历史，统计 `name_plat_ver`。
   - 全部一致 → 自动使用该平台（id_plat_ver）；
   - 不一致 → 列出选项让用户输序号选择。
5. **查/建版本**：版本已存在 → 取 `id_beta_ver` 直接导入；不存在 → 用推断平台新建再导入（除非 `--no-create`）。
6. **导入 Excel**：`POST .../pointsImport?access_token=...` 上传 xlsx（**token 走 URL query 参数，非 Authorization 头**）。
7. **逐修改点建用例 + 设结果**（基于导入后的修改点）：
   - **有需求**（描述含 `<Change Type>/<Solution>/<Change Reason>/<RN description>/<Test-Proposal>` 等字段，或 `<项目><功能>:描述` 标题）→ 按描述用规则化 AI 生成测试用例，用例 `test_result=Test-in-Process`；该修改点测试结果设为 `Test-in-Process (ti)`。
     - 生成逻辑会解析标题中的功能模块（如 `运输功能/日志功能`），结合 `Solution` / `RN description` 等字段生成具体可执行的摘要、前置条件、测试步骤、期望结果，不再简单拼接「测试xxx / 1.xxx正常」。
     - 识别到关键字（`运输`、`日志`、`100k`、`缓冲区`、`post`、`锁`、`AT` 等）会生成针对性用例；标记 `Stress-Test=y` 会追加压力/并发用例；标记 `HW-Test=y` 会追加硬件检查用例。
   - **无需求**（描述只有版本号、无 `<>` 标签）→ **不建用例**，修改点测试结果设为 `Blocked-NoRun (bnr)`，备注设为「无需测试」。

### 步骤 2：反馈结果（不生成报告文件）
向用户**简洁汇报**：xlsx 路径、登录用户、推断平台、版本匹配/新建情况、导入成功、有/无需求修改点各自处理数量。
**不要**再生成独立的测试报告文档。可用 `present_files` 仅呈现第 1 步的 xlsx 作为记录。

## 关键接口（来自 HAR 抓包，已实测）

- SSO 登录：`POST https://sso-web.quectel.com/api/uaa/oauth/token`（`grant_type=password`，密码须 RSA/PKCS#1 v1.5 加密，请求体带 `auth_type=rsa_area`；公钥见 `smod_client.py` 的 `SSO_RSA_PUBLIC_KEY`，必要时可调用 `_fetch_sso_public_key()` 从前端动态拉取）
- OAuth 授权：`GET https://st-oauth.quectel.com/login/oss?next_url=...` → 重定向返回 `code`
- 换 SMOD token：`GET /api/login/authorizeToken?code=xxx`
- 鉴权头：`Authorization: bearer<token>`（**bearer 与 token 之间无空格**）
- 搜索项目：`GET /api/projects/{platform}/betavers?platform_code=&page=&size=&keyword=`
- 硬件平台：`GET /api/simpleHardwarePlatforms` → `[{id,name}]`
- 新建版本：`POST /api/projects/{platform}/betavers` 体 `{"id_plat_ver":..., "code":...}`
- 导入 Excel：`POST /api/projects/{platform}/betavers/{id_beta_ver}/pointsImport?access_token=xxx`，multipart 字段 `file`（xlsx）
- 取用例编号：`GET /api/newCaseCode`
- 测试结论字典：`GET /api/dict/test_result`（`ti`=Test-in-Process，`bnr`=Blocked-NoRun）
- 列修改点：`GET /api/projects/{platform}/betavers/{id}/points`（含 `description`）
- 新建用例：`POST /api/projects/{platform}/cases`
- 改点结果：`PATCH /api/projects/{platform}/points/{id}/test_result` 体 `{"value":"ti"|"bnr"}`
- 改点备注：`PATCH /api/projects/{platform}/points/{id}/remark` 体 `{"value":"无需测试"}`
- 列某修改点用例：`GET /api/projects/{platform}/points/{id}/cases` → `[{id,code,summary,test_result,...}]`
- **删除用例**：`DELETE /api/projects/{platform}/cases`，请求体 `{"ids":[id1,id2,...]}`（ids 在 **JSON 体**里，不在 URL；用 GET/POST 探测会返回 405/500）

## 删除用例用法（新增）
`smod_changelist_import.py` 支持「仅删除用例」模式，登录后直接删除指定用例 id 并退出：

```bash
python scripts/smod_changelist_import.py --delete-cases 1851245,1821972 ^
    --username "Venus.Li@ikotek.com" --password "你的SSO密码"
# 或
python scripts/smod_changelist_import.py --delete-cases 1851245,1821972 --token "<access_token>"
```

> 提示：先用 `GET .../points/{id}/cases`（或直接看 SMOD 网页）确认要删的用例 id，再批量删除。

## 注意事项
- 登录已实现全自动：`--username` + `--password` 即可，脚本内部走 SSO → OAuth → SMOD token 完整链路。
- `--token` 仅作为备用（例如 SSO 登录策略临时变更、密码无法提供时）。
- 若想接入真正 LLM 生成用例，只需改 `smod_changelist_import.py` 中的 `ai_generate_test_cases()`，其余流程不动。
- Excel 结构保持 10 列（修改点编号/描述/分类/执行人/测试结果/评审状态/备注/Test-Proposal/Stress-Test/HW-Test），分类推导规则与原转换一致。
- 平台代码默认 `odmm`；如需其他平台请通过 `--platform` 指定。
- 健壮性增强（已内置）：① 新建用例遇到瞬时 5xx/网络错误会自动重试（业务错误如 `30001` 重复用例不重试）；② 重跑脚本时若修改点下**已有用例会自动跳过新建**（幂等），避免重复建用例 / 触发 `30001`。
