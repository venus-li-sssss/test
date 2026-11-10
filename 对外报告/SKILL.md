---
description: 'Use this skill when generating a customer-facing Word (docx) test report for ANY product/project — 对外报告, 对外测试报告, 客户交付报告, 生成对外报告, 测试报告(docx/Word), 修改点测试, 基本功能测试, 稳定性测试, 测试目的/测试内容/测试结论, 问题统计表, Ikotek 报告模板. 输入=一份 Word 模板 + 项目配置(JSON)。脚本与模板不含任何项目信息，换项目只换配置。'
name: 对外报告
---

# 对外报告（Word 版客户交付测试报告）

把「测试数据」灌进一份格式固定的 Word 模板，产出一份可以直接发给客户的测试报告。

**这个 skill 不绑定任何项目。** 脚本里没有项目名、型号、部件名、判定标准；
项目差异全部写在 `configs/<项目>_<版本>.json` 里。QDM559 只是一份**参考样例**，
不是规则来源。

## 和别的报告 skill 的区别

| 场景 | 用哪个 |
|---|---|
| 客户/外部交付，Word 文档（封面、修订记录、测试环境、章节表格、问题统计） | **本 skill** |
| 内部版本系统测试报告，xlsx 表格（常规功能新增列、摘要矩阵、路测 Sheet） | `版本系统测试报告生成` |
| 只把 changelist 修改点导入平台/生成用例 | `changelist2xlsx` |

## 目录结构

```
对外报告/
├── SKILL.md
├── generate_report.py      # 通用引擎：读配置 → 复制模板 → 填内容 → 出 docx
├── make_config.py          # 生成新项目配置 / 体检已有配置
├── config_template.json    # 通用配置骨架（只有占位符，没有项目数据）
├── configs/
│   └── qdm559_v22.json     # 参考样例：一份填满的真实配置（含项目专属经验）
├── media/
│   ├── base_template.docx  # 通用 Word 模板（只读，勿改）
│   └── env_image.png       # 默认测试环境图（可换成项目自己的）
└── output/                 # 产物目录
```

## 快速开始

```bat
:: 0. 依赖（缺什么装什么）
pip install python-docx Pillow pywin32

:: 1. 照骨架生成一份本项目的配置
cd <本 skill 目录>
python make_config.py --project <项目名> --version <版本号> --tester <测试人> ^
                      --location <地点> --sample-id <IMEI/SN> --out configs\<项目>_<版本>.json

:: 2. 手填配置里的 <占位符>（测试项、步骤、结果、备注、bug…）

:: 3. 体检 + 出报告
python make_config.py --check configs\<项目>_<版本>.json
python generate_report.py --config configs\<项目>_<版本>.json
```

产物默认落在 `output/`，文件名由 `report.output_pattern` 决定
（默认 `Ikotek_{project}_{version}_测试报告_{date}.docx`），可用 `--output` 覆盖。

`--no-toc` 跳过「调用 Word 更新目录」这一步（没装 Office 或批量跑时用）。
重跑永远从模板重新生成，幂等，不会叠加。

## 报告的固定骨架

模板决定版式（封面、前言、修订记录、页眉页脚），脚本往里填这些内容：

```
封面（项目名 / 版本 / 日期 / 状态）
修订记录（版本 / 日期 / 作者 / 说明）
1. 测试目的
2. 测试内容
   2.1 测试环境          ← 测试信息表（项目/人员/地点/周期/样品/部件版本）+ 环境照片
   2.2 修改点测试        ← 每项一张表：步骤 / 结果 / 备注
   2.3 基本功能测试      ← 同上
   2.4 稳定性测试        ← 同上（压力数据写在备注里）
   （章节可增删改，见 sections）
3. 测试结论
   3.1 测试小结
   问题统计表            ← Bug 号 / 等级 / 描述 / 备注
```

每个测试项的表格内容：

| 行 | 内容 |
|---|---|
| 测试项目 / 测试人员 | 取自 `test_info` |
| 测试地点 / 测试周期 | 取自 `test_info` |
| 样品数量 / 样品编号 | 取自 `test_info` |
| 版本信息（软件 + 硬件） | 取自 `test_info.components`（`HW` 单独成一行，其余逐行列出） |
| 测试步骤 | 自动编号 `1. 2. 3.` |
| 测试结果 | PASS / FAIL（FAIL 自动标红加粗） |
| 备注 | FAIL 时标红；多行用 `\n` 分隔 |

## 配置字段

所有字符串都支持占位符：`{project}` `{version}` `{date}` `{tester}` `{company}`
（取值来自 `report` + `test_info` 两段的扁平合并）。未知占位符原样保留，不会报错。

| 字段 | 作用 | 不写会怎样 |
|---|---|---|
| `report.title/version/date/author` | 写入文档属性；`version` 用于封面替换 | 用占位符原值 |
| `report.output_pattern` | 输出文件名模板 | 默认 `Ikotek_{project}_{version}_测试报告_{date}.docx` |
| `template` | 模板 docx 路径（相对配置文件） | 回落到 `media/base_template.docx` |
| `template_replacements` | 正文/表格里的「旧串 → 新值」替换表（封面旧型号、旧版本号、旧日期） | 不替换，模板旧信息会残留 |
| `header_replacements` | 页眉页脚同样做替换（先执行，优先级高于上一条） | 页眉仍是模板里的旧型号 |
| `revision` | 修订记录行 | 跳过，模板原有那一行保留 |
| `test_info` | 项目/人员/地点/周期/样品/编号/部件版本 | **必填** |
| `labels` | 表头文字（比如把「样品编号」改成「SN」） | 用内置中文表头 |
| `purpose` | 「1. 测试目的」标题与正文 | 用通用措辞 |
| `content_heading` | 「2. 测试内容」标题 | 同上 |
| `env` | 2.1 测试环境：是否启用、标题、图片、图宽、图注 | 启用，用内置图 |
| `sections` | 测试章节数组（见下） | 回落到旧写法 `modification_tests/basic_tests/stability_tests` |
| `conclusion` | 结论段标题、是否启用 | 启用，用默认标题 |
| `test_summary` | 3.1 测试小结的每一条 | 空 |
| `bugs` / `bug_labels` | 问题统计表的行与表头 | 不生成表 |

### sections（章节）

```json
"sections": [
  {"heading": "2.2 修改点测试",
   "items": [
     {"title": "某修改点", "steps": ["步骤1", "步骤2"], "result": "PASS", "remark": ""}
   ]},
  {"heading": "2.5 路测",
   "intro": "本节为可选章节，说明文字写这里",
   "items": [ ... ]}
]
```

- 章节可任意增减、改名、调序；`heading` 前两位编号（`2.2`）会被自动用作子项编号前缀
  → 输出 `2.2.1`、`2.2.2`…（`title` 自带数字则不重复加）。
- `env_table: true` 让该章节先插一张测试信息表（适合没有 2.1 节的项目）。
- 某个项目没有的章节，直接从 `sections` 里删掉，报告里就不会出现。

## 对外口径（通用写作规则，跟项目无关）

1. **测试步骤必须对得上测试用例或压力脚本**，不要写「随便点一下」。步骤颗粒度到「操作 + 观察点」。
2. **PASS 的备注**：功能/修改点测试留空；稳定性（压力）测试**必须写数据**——次数、成功率、平均耗时、异常次数。
3. **FAIL 的备注**：问题编号 + 标题 + 复现概率/当前状态，脚本自动标红。没提单的失败不要默默写 FAIL。
4. **样品数量用中文**：`2片` / `1台`，不要写 `2PCS`（`make_config.py --check` 会拦）。
5. **结果只有三种**：PASS / FAIL / BLOCK（BLOCK 必须写原因，否则对外看起来像是漏测）。
6. **交付前清模板残留**：封面型号、页眉型号、页脚「[在此处键入]」、图注编号，逐项核对。
7. **别泄露内部信息**：内部服务器地址、内部账号、未结案的内部讨论不要出现在对外报告里。

## 新项目接入清单

1. 准备模板：能直接用 `media/base_template.docx`（Ikotek 通用版式）；客户有专属模板就放进来，用 `template` 指过去。
2. `python make_config.py --project ... --out configs/<项目>_<版本>.json` 生成配置。
3. 打开模板，记下**封面旧型号串 / 旧版本号 / 旧日期 / 页眉型号串**，填进
   `template_replacements` 和 `header_replacements` —— 这一步最容易被忘，忘了报告就带着上一个项目的名字交付。
4. 填 `test_info`、`sections`（修改点 / 基本功能 / 稳定性…）、`test_summary`、`bugs`。
5. `--check` 通过 → 出报告 → 用 Word 打开核对（页数、目录、红字、表格有没有被挤变形）。

## 参考样例：QDM559 V22（仅作参照）

`configs/qdm559_v22.json` 是一份填满的完整配置，可以直接看它学**格式**，但里面的
数值、部件名、判定标准、步骤措辞都是 QDM559 这个项目的，**不要照抄**。

那份配置里还留了几条本项目专属经验（配置里的 `_项目专属经验`），举例说明什么叫「具体项目具体写」：

- 部件类型按本项目平台实际字段写（ECU / DIS / MCU / BMS / TFT / CHG），换项目就换成本项目的部件名；
- 升级类步骤写平台上看得到的说法（「平台查看 ECU 版本号」），别写本项目平台没有的叫法；
- 组合升级要把参与升级的部件逐个列出来；
- 模板封面是上一代型号串、页眉要换成本项目型号（这就是 `*_replacements` 存在的意义）。

## 踩坑

- **模板的 Heading 样式自带自动编号**：直接用 `doc.add_heading` 会得到「1.1 1. 测试目的」这种鬼东西。
  脚本用自定义段落 + `outlineLvl` 绕开，改标题逻辑时别退回去用模板样式。
- **文字替换要按整段匹配**：Word 会把一个词拆进多个 run（`QDM`+`551`+`-EA`），按 run 替换会漏、会留半截。
- **页眉有 奇/偶/首页 三套**：只改 `section.header` 会漏掉 `even_page_header` / `first_page_header`。
- **`[INSERT_TABLES_HERE]` 标记段必须删掉再插内容**，否则目录里会多出一条。
- **图片路径别写历史遗留的临时文件名**：原脚本曾指向一个不存在的 hash 命名 png，图静默丢失。
  现在 `env.image` 不存在会打印提示，不会静默跳过。
- **`update_toc` 靠 Word COM**：没装 Office 会失败，这是正常的——手动在 Word 里 Ctrl+A → F9，或者用 `--no-toc`。
- **模板的页面设置/页码域不要动**，改动后 Word 会提示「修复」。
- **每次重跑都从模板复制**，所以改了配置重跑即可，不会把上一版内容叠进去。

## 脚本命令速查

| 命令 | 作用 |
|---|---|
| `python generate_report.py --config <cfg>` | 出报告（默认更新目录） |
| `python generate_report.py --config <cfg> --output <path>` | 指定输出文件 |
| `python generate_report.py --config <cfg> --no-toc` | 不调 Word 更新目录 |
| `python make_config.py --project ... --out <cfg>` | 从骨架生成新配置 |
| `python make_config.py --check <cfg>` | 体检：JSON 语法、必填项、结果值、未填占位符、模板是否存在 |
