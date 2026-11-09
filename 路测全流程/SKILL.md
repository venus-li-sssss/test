---
description: 'Use this skill when the user wants the whole GNSS road-test chain from
  NMEA logs to deliverables: 输入设备+高精度NMEA → 出三件套测试数据(对比KML/截图/CEP表Excel) → 再出 Word(docx)路测报告
  和 调接口生成 Excel路测报告。Triggers: 路测, 路测报告, 生成路测报告, NMEA出报告, 轨迹对比报告, CEP报告, 三件套, 定位精度报告,
  docx报告, excel报告, 从日志一路出到报告。'
name: 路测全流程
---

# 路测全流程（NMEA → 测试数据 → docx + Excel 报告）

一条链把路测做完：**设备 NMEA + 高精度 NMEA + 区域划分** → ① 三件套测试数据 → ② Word 报告 → ③ 接口出的 Excel 报告。
本 skill 自包含（QGIS 出图脚本 + 两个报告脚本 + batch），不再依赖其它 skill。

## 执行：batch 出三件套+docx，Excel 报告单独跑一条 shell

**步骤①②用 `run_tool_batch` 加载 `scripts/路测全流程.json`，不要用 inline actions 自己拼。**
**步骤③（Excel/接口）刻意不在 batch 里**：大请求体会把 batch kernel 挂死（实测），batch 跑完后
用 `execute_shell_command` 单条跑：

```
python "<skill目录>/scripts/excel_report.py" --dir "<out_root>" --version "01.001.01.001_V0" --result "PASS" --remark "细节写这里" --max-images 6
```

**上传前必须向用户要两个输入（用户明确要求，不许默默上传、更不许自己编）**：
1. **测试版本**（--version，≤100 字符）；
2. **测试结果**（--result，**只能三选一：`PASS` / `FAIL` / `PASS WITH COMMAND`**——H 列要保持干净，
   统计、细节一律放 --remark，别塞进 result）。
用户不回或明确留空才允许加 `--allow-blank`（脚本会拦下缺参上传，输出提示让你去问用户）。
脚本任何接口报错都打响应原文并终止——**报错原文必须转告用户**。

已经有三件套、只缺报告时，跑 `scripts/报告生成.json`（同一套 args，跳过 QGIS），Excel 同样单条 shell。

```
run_tool_batch(
  file_path="<skill目录>/scripts/路测全流程.json",
  args={
    "cfg": "D:\\work\\路测工具\\区域划分.json",
    "out_root": "D:\\work\\路测工具\\gps_kml\\_标注测试\\三件套",
    "version": "01.001.01.001_V0",
    "skill_dir": "<skill目录>"
  }
)
```

### Batch Parameters

| 参数 | 含义 | 怎么填 |
|---|---|---|
| `cfg` | `区域划分.json` 的绝对路径（喂给 QGIS 出数） | 由 agent 按下方"准备配置"写好再传；跑 `报告生成.json` 时随便填个值（该 batch 不读它） |
| `out_root` | 三件套输出根目录，也是两个报告的输入目录 | 必须与 `cfg` 里的 `out_root` **一致**，否则报告找不到图 |
| `version` | 被测版本号，写进两份报告（docx 封面 + Excel 的"测试版本"列/文件名） | 例 `01.001.01.001_V0`；不要带 `/ \ : * ?` 等文件名非法字符 |
| `skill_dir` | 本 skill 的绝对目录 | 用来拼 `scripts/*.py` |

Excel 报告的 API Key **不作为 batch 参数**（避免落进对话/日志）：`excel_report.py` 依次找 `--api-key` → 环境变量 `ROAD_TEST_API_KEY` → `~\.roadtest_key` 文件。本机已写好 `C:\Users\<你>\.roadtest_key`，缺了再问用户要。

## 第 0 步（唯一需要判断的地方）：准备 `区域划分.json`

batch 前 agent 必须先把配置写好，其余全自动。契约：

- 必填 `hi_log`（高精度 NMEA，UTC）、`dev_txt`（设备日志，北京时间）、`out_root`。
- 区域划分三选一，**优先级 KML > 时间 > 帧编号**，由脚本自动判定：
  - `kml_dir` 目录里有 `.kml` → 按多边形划分；区域名取 Placemark name 或文件名；落不进多边形的帧进 `其他\`
  - `"mode":"time"` + `regions_time:[{name, ranges:[[起,止],…]}]`
  - `"mode":"image"` + `regions_image:[{name, from, to}]`；留空则先只出 `0_全部帧\` + `帧清单.txt`，拿编号回头划区域
- 模板见 `scripts/区域划分.json`（白字/KML/CEP 全部可配，注释在里面）。

用户只给了两条日志、没给区域 → 先按 `mode=image` 空区域跑一遍，把 `帧清单.txt` 和 2~3 张样张发给用户确认怎么分区，再重跑。

## 产物

| 阶段 | 产物 |
|---|---|
| ① 三件套（QGIS，`路测截图生成.py`） | `对比轨迹_<时间戳>.kml` + 两个图钉 png；`整体\整体.jpg`、`<场景>\区域整体.jpg`、`<场景>\NN_HHMMSS.jpg`（每段约 `seg_m`=250 m，编号全局连续）；`CEP_列表.xlsx`（sheet `CEP` 行=CEP60…95 / 列=整体+各场景；sheet `说明` 每列样本数）；`帧清单.txt` |
| ② Word（`roadtest_docx_report.py`） | `路测报告_<version>.docx`：1 概述+数据来源表 / 2 CEP 表 + 场景样本与时间范围表 / 3 各场景截图（区域整体 + 每帧一张，图注 `帧 NN（起始 hh:mm:ss）`）/ 4 初步结论（从表里挑偏差最小/最大场景，不写死） |
| ③ Excel（`excel_report.py` → 妙搭接口，单条 shell） | `路测报告_<version>_<日期>.xlsx`：单 sheet `路测`，列=编号/测试日期/测试版本/测试内容/场景/测试数据(F:G 合并嵌图)/**测试结果(H)/备注(I)**，一行=一个场景。**H/I 现在可由接口写入**：`--result`→H 列、`--remark`→I 列；不传则留空并打提示（提示必须转告用户） |

## 接口的硬限制（2026-10-16 按校验器实测出的 schema，改代码前先记住）

```
POST https://scnrhostplnc.feishuapp.com/app/app_4jxgwzvqczpd2/openapi/road-test-report/generate
Authorization: Bearer <key>          # 裸 key 会被判 "missing or invalid Authorization header"
Content-Type: application/json
{"version": "≤100字符",                          # 测试版本 -> C列
 "scenes": [ {
   "name": "≤255字符",                            # 场景 -> E列
   "result": "≤1000字符",                         # 测试结果 -> H列（可省）
   "remark": "≤1000字符",                         # 备注 -> I列（可省）
   "images": [ {
       "base64": "≤15,000,000字符",
       "fileName": "≤255字符 测试数据描述，一图一个" } ] } ] }
→ 201 {"reportId","downloadUrl","fileName","scenes":[{"name","files","result","remark"}]}
```

- **一图一描述**（用户口径）：描述放 `images[].fileName`。脚本自动生成（"<场景> 区域整体/分段NN（起始 hh:mm:ss）轨迹对比"），
  可用 `--desc-file` JSON 覆盖（键 `<场景>/<图片名>` 或 `<场景>`）。
  ⚠️ 实测（2026-10-16）：`fileName` 服务端**校验但不渲染**进 xlsx（响应也只回显 name/files/result/remark）。照常传，平台补上渲染后无需改脚本；用户若说"报告里没描述"，先确认服务端部署，不要改字段名瞎试——description/desc/text/caption/remark(图级)/title 等 50+ 候选都已实测不认。
- **`result` 只允许 `PASS` / `FAIL` / `PASS WITH COMMAND`(S)**（用户定的口径；脚本已做上传前校验，非法值直接拒绝）。
  缺 `--version` 或 `--result` 时脚本**拒绝上传并退出**（提示去问用户），除非显式 `--allow-blank`。
- **校验器是 class-validator 风格**：字段类型不对时 400 details 会报 `scenes.0.images.0.<字段> must be ...`——用"合法图+错误类型"可以探出 DTO 里真实存在哪些字段（本次就是这么发现 fileName/result/remark 的）。
- 路径**必须带 `/app/app_4jxgwzvqczpd2` 前缀**，只写 `/openapi/road-test-report/generate` 是 `404 page not found`。
- `scenes` 1~50 个；每个 scene 的 `images` **≤20 张**；`images` 的元素必须是对象，传字符串报 "must be either object or array"。
- `base64` 可以是裸 base64，也可以是 `data:image/jpeg;base64,...`，服务端都收。
- 网关硬上限 **12MB**（超了回 200 + `{"code":"k_func_ec_400002757",...}`，不是 4xx）；但**实测服务端 >6MB 传桶就易超时/500**，所以脚本按 6MB 预算选档 `(1600,85)→…→(640,72)`，且默认 **`--max-images 6`**（用户定的：每场景 6 张够看趋势，图小能看清即可，别改回全量）。
- 失败自动降档重试：3 次，每次减档+减图（6→4→3），单次墙钟 300s（子线程硬超时，requests 超时管不到发 body 阶段）；**非 201 一律把响应原文打出来——任何接口报错必须原样告知用户**（用户明确要求）。
- `downloadUrl` 是带签名的 CDN 链接，拿到就立刻下载，别隔天用。

## QGIS 出图的要点（踩过的坑，别改回去）

- 跑法：`cd /d D:\OSGeo4W\bin && python-qgis-ltr.bat "<skill>/scripts/路测截图生成.py" "<cfg>"`；一轮 46 张约 4~5 分钟，batch 里 `timeout` 给到 1800。
- QGIS 的 python **没有 pip / openpyxl**，所以 CEP 的 xlsx 是纯标准库手写的；改 `write_xlsx()` 后必须用带 openpyxl 的 python 回读验证。
- `setLayers()` 自上而下，影像底图放**最后**，否则盖住轨迹；矢量图层要从 NMEA 直接建内存图层（走 KML ogr 驱动会得到 0 要素）。
- 每张截图都要画**全程所有点**（黄=高精度、红=设备），白线=同刻连线每 5 秒一条、线上带距离白字+黑描边（默认开）；挑字规则：截图按屏幕像素去重（`gap=max(1,mpp/0.32)`），KML 按地面距离去重（`kml_label_min_sep=5`）—— 两套机制不一样，别混。
- KML 颜色是 `aabbggrr` 不是 `#rrggbb`；`kml_points` 保持默认 true（用户点名要过"点得开气泡"）。
- 一个区域必须是一段**连续帧**；帧号跳号会把区域整体图框错，遇到就拆成 `大马路(北)/大马路(南)`。
- 验收：`python "<skill>/scripts/check_artifacts.py" "<out_root>"`（查 KML XML/颜色/href/有没有定位点 + xlsx 回读 + 截图目录）。

## 交付方式（重要）

打开输出目录交付，**不要一次把几十张图塞进对话**（`run_tool_batch(last_only=True)` 也拦不住图片回灌，会把上下文冲爆）。
只发：`路测报告_*.docx`、`路测报告_*.xlsx`、`CEP_列表.xlsx`、`对比轨迹_*.kml`，外加用户点名的 2~3 张截图。
docx 常有 15MB 量级（46 张图全内嵌），发之前先 `send_file_to_user`，失败就说明体积、给目录路径。
Excel 报告走 `excel_report.py`，**固定为单条 shell 调用，不要再放回 `run_tool_batch`**（46 图大 body 在 batch 里会挂死 kernel，单独跑实测正常）。默认 6 张/场景，别改回去。

## 文件

| 文件 | 用途 |
|---|---|
| `scripts/路测全流程.json` | 全链路 batch：cfg/目录校验 → QGIS 出数 → 验收 → docx → 交付清单（**不含 Excel**） |
| `scripts/报告生成.json` | 已有三件套时的短 batch：验收 → docx → 交付清单（**不含 Excel**） |
| `scripts/路测截图生成.py` | QGIS 主脚本，出 KML + 截图 + CEP xlsx |
| `scripts/nmea.py` / `labels.py` | NMEA 解析 / 白字挑字（`labels.py` 纯 python，可离线测：`test_pick_labels.py`） |
| `scripts/check_artifacts.py` | 三件套体检，退出码 0 = 全过 |
| `scripts/roadtest_docx_report.py` | 三件套目录 → docx（`--dir --version [--out --title]`） |
| `scripts/excel_report.py` | 三件套目录 → 调接口 → xlsx（`--dir [--version --result --remark --desc-file --max-images(默认6) --max-edge --no-overall --api-key --out]`；一图一描述走 `images[].fileName`） |
| `scripts/区域划分.json` | 配置模板 |

## Batch 失败处理

1. 先确认四个参数都传了真实值（尤其别传空 `args={}`，`cfg`/`out_root` 不一致会让报告说"没找到场景子目录"）。
2. QGIS 步骤失败 → 单独跑那条 `python-qgis-ltr.bat` 看报错（多半是 cfg 路径或日志编码）。
3. Excel（单条 shell）报 `k_ec_000015` = key 不对/没读到；报 400 带 `scenes.0.images.0.xxx` 字段路径 = 类型/超限，按路径改；
   业务码在 200 里也可能出现（超 12MB），脚本已拦截——**任何报错原文都要转告用户**。
4. 仍失败可 inline actions 或逐条手跑；完成后告诉用户 batch 哪里出错、是否要改脚本。
