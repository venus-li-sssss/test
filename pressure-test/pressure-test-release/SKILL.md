---
description: 'Use this skill when the user wants to run a 版本(固件版本) 自动化测试流程：收到新版本固件 → 烧录 → 按用例集执行 → 数据归档 → 出系统测试报告 / 修改点报告。Triggers: 版本自动化测试, 版本测试流程, 版本测试, 新版本怎么测, 版本回归, 固件版本测试, 系统测试报告, TestCase 执行, 修改点测试报告, 版本测试目录, 版本归档. NOT for FCT 产测(用 pressure-test-fct) / 循环压测(用 pressure-test-generator).'
name: pressure-test-release
---

# 版本自动化测试流程（固件版本 → 用例执行 → 报告与归档）

> 本 skill 管**"一个固件版本进来之后，从烧录到报告的那条链路"**；
> 产测（FCT）专项跑批用 `pressure-test-fct`；循环压测用 `pressure-test-generator`；
> 报告本体生成用仓库根目录的 `版本系统测试报告生成`。

## 版本目录规范（先建目录，再干活）

```
D:\work\<产品>\版本测试\<版本号>\
├── APP测试\              专项跑批结果（功能/业务/APP 相关）
│   ├── report\           allure HTML
│   └── log\              日志
├── FCT测试\              产测跑批（见 pressure-test-fct）
│   ├── report\  result\xml\  log\  说明.md
│   └── <指令说明>.xlsx
├── <TestCase 用例集>.xlsx     GNSS / Network / POWER_ON_OFF / 整车 …（按平台拆 Sheet）
├── 【机密】【MOB】…_<版本>_SystemTestReport_V1.0.xlsx     系统测试报告
└── …_<版本>_修改点测试报告_Report.xlsx                    修改点维度报告
```

- **版本号就是目录名**（如 `766`），不要带 `V`、不要带固件全串；
- 专项产物（FCT/APP）各自一个子目录，**别把 report/log 平铺在版本根目录**；
- 历史版本不改名、不合并 —— 跨版本对比靠目录结构一致。

## 流程（六步）

### ① 收版本 + 核对版本串

| 检查 | 做法 |
|:---|:---|
| 版本包来源 | qdisk「766底包」这类目录；双层 zip（外层 DBG 符号 + 内层真实固件） |
| 内层内容 | 根目录应有 `download.json` + `partition.bin` + 各镜像；先列一遍再烧 |
| 版本串拆分 | 固件全串 `…_QDM562CNAK_01.001.01.001_766` → 报告里"软件版本"填到 `…01.001.01.001`，"客户版本"填 `766` |
| 修改点 | 送测邮件/SMOD 里的 changelist，决定本轮要重点回归什么 |

### ② 烧录（aboot）

- 分区清单以**该包** `download.json` 为准，**每个固件都可能不同**；
- 已有版本的设备：客户信息区 `customer_fs` / `ext_flash` **默认不烧**（裸板/擦过片才全量）——
  仅 QDM562 有这条默认口径，别的项目照常全烧；
- 烧完**物理断电重上电**，`ATI` 核对版本；详见 `flash-tools` 的 aboot 一节。

### ③ 按用例集执行

| 维度 | 怎么跑 | 产物 |
|:---|:---|:---|
| 产测 FCT | `pressure-test-fct`（单 FCT 口 / 写操作三档 / 链路体检） | `FCT测试\report` + `说明.md` |
| 功能/业务（APP、网络、整车） | TestCase xlsx → pytest 壳（`pressure-test-pytest`）或既有脚本 | `APP测试\report` |
| GNSS / 路测 | `路测全流程`（NMEA → 对比 KML + 截图 + CEP 表） | 报告「路测」Sheet 的图与 CEP 数据 |
| 压力 / 稳定性 | `pressure-test-generator`（device.yaml + 轮次统计） | 轮次通过率、异常时间线 |

**执行表回填**：Test Case xlsx 的结论列按 PASS / FAIL / Test-in-Process 回填，
失败项同时提 JIRA（`jira-data-access`），报告里的问题统计直接取自 JIRA 查询结果，别手抄。

### ④ 数据归档（跑完立刻做）

每跑完一个专项就归档，不要攒到最后：

```bash
python <pressure-test-fct>/scripts/archive_results.py ^
    --src "D:\work\<产品>\脚本\自动化测试\<项目>" ^
    --dst "D:\work\<产品>\版本测试\<版本>\FCT测试" ^
    --version 766 --device "IMEI ..." --firmware "ECU APP V0766 / 底包 0705" ^
    --console-log "_fct_run3.txt" --doc "<指令说明>.xlsx"
```

归档脚本会**自动挑本轮日志**、生成 `说明.md`、并自检 `index.html`/json 数/体积。

### ⑤ 出报告

| 报告 | 用什么 | 要点 |
|:---|:---|:---|
| 系统测试报告（版本级） | `版本系统测试报告生成` | 基于上一版报告改造；摘要/测试计划/常规压力/问题统计按本轮数据更新；路测 Sheet 由路测链路喂入 |
| 修改点测试报告 | `changelist2xlsx`（SMOD） | 按 changelist 建用例、置结论、导出报告；命名 `<固件全串>_修改点测试报告_Report.xlsx` |
| 专项 allure 报告 | 各跑批脚本自带 | 必须 HTTP 打开（`allure open <dir>`），双击 index.html 白屏 |

**命名口径**（贴到报告文件名里，别自创）：

```
【机密】【MOB】<固件全串>_SystemTestReport_V1.0.xlsx
<固件全串>_<版本号>_修改点测试报告_Report.xlsx
```

### ⑥ 收尾

- allure 起的 java 服务收掉（`Get-CimInstance Win32_Process` 匹配 `allure.*open` 再 Stop-Process）；
- 归档后核对：`report/index.html` 在、`说明.md` 在、json 数与用例数一致；
- 版本目录结构保持与历史版本一致（便于下个版本直接对照）。

## 与其它 skill 的边界

| 要做的事 | 用哪个 |
|:---|:---|
| 固件烧录 / 进下载模式 | `flash-tools`（aboot 一节） |
| FCT 产测实机跑批 + 归档 | `pressure-test-fct` |
| Excel 用例 → pytest 壳工程 | `pressure-test-pytest` |
| 循环压测 / 稳定性 | `pressure-test-generator` / `pressure-test-framework` |
| 串口/CAN/继电器等基类 | `pressure-test-bases` |
| 路测三件套（KML/截图/CEP） | `路测全流程` / `路测场景截图` |
| 系统测试报告 | `版本系统测试报告生成` |
| 修改点导入 / 建用例 / 导报告 | `changelist2xlsx` |
| 提/查 BUG | `jira-data-access` |
| 做 FOTA 升级包 | `做包` |

## 常见坑（版本维度）

1. **版本号三种写法别混**：固件全串 / 报告里的"软件版本"（截到 `01.001.01.001`）/ 客户版本（`766`）。
   提 JIRA、命名报告、写报告 Sheet 用的是不同口径，混了就搜不到历史。
2. **一份报告只对应一个版本**：`SystemTestReport` 文件名必须带版本，别拿上一版直接另存后忘改。
3. **专项产物散落**：FCT/APP 的 report、log 必须在版本目录的子目录里；留在脚本目录等于没归档。
4. **跑批中途中断**：前台命令有 60s 上限，长跑批用 `.bat` + 计划任务脱离会话（见 `pressure-test-fct`）。
5. **重启类用例会污染链路**：跑完设备要做断电重上电，再开下一个专项。
6. **报告数据要能溯源**：每个数字（用例数、通过率、问题数）都要能指到 allure/执行表/JIRA 查询，
   不许手改"看起来好看"。
