---
description: 'Use this skill when the user wants functional test cases turned into a pytest project with a thin "shell" layer decoupled from the execution base classes, with allure reporting. Triggers: 自动化测试脚本, 用例转pytest, 测试用例生成pytest, pytest壳, 伪脚本, 文字版本脚本, 先出骨架再填函数, 基类解耦, 用例和实际执行分开, allure报告, CAN/串口/平台基类组合, Excel用例转脚本, 版本自动化测试, 按场景切分, 分场景, 一个场景包含所有测试项, 不想频繁切环境, 安卓/iOS/鸿蒙/蓝牙/4G/蓝牙+4G 用例分组. The pytest layer only calls functions that print the case text (no real execution yet); the base classes (Serial/CAN/Platform API) are developed separately and later plugged into the pytest super class via uid registry.'
name: pressure-test-pytest
---

# 功能自动化：pytest 用例壳 + 基础类解耦 + allure 报告

把测试用例（Excel/表格）转成 pytest 工程的**三段式解耦**方案：

1. **pytest = 壳**：一条用例 = 一个参数化用例，函数体只调用基础类函数、用文字描述测试流程（打印编号/模块/前置/步骤/期望），**不做实际执行**；
2. **基础类 = 实际执行**：底层 Serial（串口）、CAN、Platform API 等类按 pressure-test-bases 模板开发，组合成超类（Layer 2）；
3. **最后合并**：基础类套进 pytest 的执行器（conftest 的 `base` fixture 换成持有超类的实例），用例壳零改动；
4. **测试报告 = allure**：步骤、附件、结果块、Environment、一键生成并打开。

> 验证案例：QDM522（21 个 Sheet / 461 条用例）从 Excel 一次生成、收集与运行全绿。

## 何时用本子 skill / 何时不用

| 场景 | 用什么 |
|:---|:---|
| 功能用例要先出 pytest 骨架，实际执行（CAN/串口/平台）另行开发、最后合并 | **本 skill** |
| 循环压测（while True、轮次统计、device.yaml） | pressure-test-generator |
| FCT 产测一体化项目（实机跑批 / 写后还原 / 结果归档） | **pressure-test-fct**（跑批与归档）+ 本项目骨架生成 |
| 只要基础类代码模板 | pressure-test-bases |

## 生成的工程结构

```
<product>_pytest/
├── cases.json                   数据层：Excel 提取的结构化用例（uid/cid/模块/优先级/前置/步骤/期望）
├── tests/test_XX_<模块>.py      用例层（生成，勿手改）：body 只有 base.run_case(case)
├── base/
│   ├── executor.py              基础类 BaseExecutor：run_case(打用例块→跑实现→判定块→断言)
│   ├── impls.py                 每条用例一个 @register(uid) 实现桩（桩阶段 return True）
│   ├── registry.py              uid → 实现函数注册表（两层之间唯一耦合点）
│   ├── logger.py                printf 三通道 + printf_msg_add 附件收集
│   └── case_loader.py           cases.json → pytest.param（p0-p3 marks，ids=uid）
├── conftest.py                  session 级 base fixture；导入 impls 触发注册
├── pytest.ini                   markers(try_run/p0..p3) + python_files + pythonpath = .
├── run_all.py                   pytest → environment.properties → allure generate → allure open
└── gen_from_excel.py            生成器自拷贝：Excel 更新后在工程内重跑
```

合并实际执行时的改动点**只有两个**（用例层零改动）：

```python
# ① conftest.py：base fixture 返回持有超类的执行器
class DeviceBase:                      # 超类 = 基础类组合（对齐框架 Layer 2）
    def __init__(self, cfg):           # cfg 可复用 device.yaml
        self.serial   = Serial(cfg["com"], 115200)     # pressure-test-bases/Serial
        self.can      = CAN(cfg["can_channel"])        # pressure-test-bases/CAN (zlgcan)
        self.platform = PlatformAPI(cfg["host"])       # pressure-test-bases/Platform API

class XxxExecutor(BaseExecutor):
    def __init__(self):
        super().__init__()
        self.dev = DeviceBase(load_yaml("device.yaml"))

# ② base/impls.py：对应 uid 的桩函数体换成真实操作（或迁到 impls_manual.py 覆盖注册）
@register("TCS_TCS_4G_001")
def impl_tcs_on_4g(base, case):
    base.dev.platform.app_switch("TCS", True)
    frame = base.dev.can.recv(0x123, timeout=3)
    if frame is None:
        return {"statuscode": 404, "reason": "CAN 无上报"}
    if "tcs=1" not in frame.text:
        return {"statuscode": 201, "reason": f"实际={frame.text} 期望含 tcs=1"}
    return {"statuscode": 200, "data": frame.text}
```

## 按环境场景切分（表是「手机系统 × 连接方式」二维矩阵时）

有的 TestCase 表编号是**四段** `模块-系统-连接方式-序号`（例 `激活绑定-安卓-4G+蓝牙-001`），
本质是 安卓/iOS/鸿蒙 × 蓝牙/4G/蓝牙+4G 的九宫格。按模块（Sheet）出文件会让**一次运行反复换环境**
（同一个 Sheet 里三种系统 × 三种连接交错），于是加 `--group-by scene`：

- **一个场景 = 一次环境准备 = 一个文件**，文件内含该场景下的全部测试项：
  `tests/test_scene_01_os_android.py` … `03_os_harmony.py`（系统场景，各含三种连接方式的用例）、
  `test_scene_04_conn_bt.py` / `05_conn_4g` / `06_conn_4g_bt`（连接场景，各含三种系统的用例）
- **组内按另一维度成块排序**：系统场景按 蓝牙→4G→蓝牙+4G，连接场景按 安卓→iOS→鸿蒙，
  块内仍按 模块顺序 + Excel 行号 → **一个文件只切 3 次环境**，不是 N 次
- 同一条用例会在两个场景里各出现一次（这是有意的：场景 = 可独立跑的环境），
  但**实现函数只有一份**（uid 注册表共用），用例层零改动
- `--group-by auto`（默认）会自己判断：编号是四段就按场景切，三段就按模块切（老行为），不会悄悄改老工程结构
- 跑单个场景：`python -m pytest -vs tests/test_scene_01_os_android.py`（文件名全 ASCII，cmd 里好打）

**uid 扩展**：二维表的模块列常写成 `模块-系统-连接方式` → 生成时剥掉后缀只留模块名，
系统并进 uid：`车辆详情_开关机_android_4G_001` / `…_ios_4G_BT_001`，
同一序号在不同系统下不会撞车。`cases.json` 多两个字段 `os` / `conn`，用例筛选走
`get_scene_params("os:android")` / `"conn:bt"`。

**实测（QDM562 整车 TestCase V1.0）**：20 个有内容 Sheet / 1158 条 / 3 系统 × 3 连接 →
6 个场景文件：安卓 386、iOS 386、鸿蒙 386、蓝牙 363、4G 372、蓝牙+4G 423；
`pytest -q --co -m try_run` 收集 **2316** 项（1158×2，两个场景各一次），桩跑全绿（`PASS(桩)`），单文件 386 项 0.06s 收集完成。

## 真机执行层怎么接进来（超类 + 页面模式基础类 + 规则表）

壳工程评审通过后再接真机，**用例层零改动**。生成器只重写 `tests/ / cases.json / base/impls.py /
conftest.py / README.md`，下面这些是人写的、重跑生成器不会丢：

| 文件 | 作用 |
| --- | --- |
| `base/executor_custom.py` | `CustomExecutor`，装配设备超类；**conftest 自动优先用它**，没有就退回 `BaseExecutor` |
| `base/impls_manual.py` | 手写实现：`RULES` 规则表批量 `@register(uid)` 覆盖 `impls.py` 的桩 |
| `base/<通道>.py` | 基础类（APP / 平台 / 上位机 / CAN / 串口…） |
| `device.yaml` | 各通道配置，与压测脚本同一口径 |

**基础类怎么切**：一个通道一个类，互不依赖（对齐 pressure-test-bases 的 Layer 1）；
APP 类用**页面模式**（先定页面 → 再看该页需要的元素 → 再写操作），把页面和元素写成**数据表**
（`PAGES` / `ELEMENTS`，元素带 `page / text / type / layer`），类里只负责把表翻译成现成 helper 的
CLI（`go_to_page` / `tap --text` / `cmd --target ... --action on|off` / `get_device_info` …），
**不要重写 uiautomator2 那一层**（那条链在 ninebot-project skill 里已经调稳）。
超类（Layer 2）= 组合这些基础类，`open_all()/close_all()` 统一处理。

**别逐条手写 1158 个函数**：用规则表

```python
RULES = [
    ("车辆详情", ["闪灯鸣笛"], act_flash_horn, "AUTO"),
    ("TCS",     ["TCS", "牵引力"], mk_toggle("mf.tcs", "牵引力控制系统"), "PARTIAL"),
    ("设备信息", ["设备型号", "车架号", "固件"], act_device_info, "AUTO"),
]
# 命中即 register(uid)，一条规则覆盖 N 条用例；没命中继续走 impls.py 的桩
```

**判定要防「假绿」**：这批用例大量是「APP 点一下 → 再去车上拧油门/捏刹车/刷卡验证」。
只写 APP 那半段就报 PASS 等于假绿；一律 FAIL 又淹没真问题。约定：

| 状态码 | 含义 | 报告 |
| --- | --- | --- |
| 200 | 自动化可完全判定（APP 读到的值 / 开关状态 / 平台指令记录即验收依据） | 绿 |
| 201 且 reason 以 `PARTIAL` 开头 | APP 侧已自动执行并核验，物理/仪表/BLE 项待人工 | `pytest.xfail`（黄，原因写明缺哪步） |
| 404 / 500 | 连不上 / 脚本异常 | 红 |

在 `CustomExecutor.run_case` 里拦 `AssertionError`，`PARTIAL` 就转 `pytest.xfail`——不上报假 PASS，
也不把整轮跑红。另加 **mock 开关**（如 `QDM562_MOCK=1`）：不连设备时所有动作只打印，用来验证
壳/超类/注册表/报告链路，全绿才说明接线没问题。

**实测（QDM562 整车 1158 条）**：接真机动作 **513 条**（AUTO 72 / PARTIAL 441），其余 645 条仍是桩；
mock 全量 6 个场景 2316 项 **6.67s 全绿**；文档由 `tools/gen_docs.py` 从 `PAGES/ELEMENTS/RULES`
生成（页面模型 / 覆盖统计），改一处不写两处。

## 判定口径（与压力框架一致，合并时不用改）

实现函数返回值 → `norm_res` 归一化：

| 返回 | 状态码 | 报告表现 |
|:---|:---|:---|
| `True` / `None` | 200 PASS | 判定块 `PASS` |
| `{"statuscode":200,"data":...}` | 200 PASS | 判定块 `PASS` |
| `False` / `{"statuscode":201,"reason":...}` | 201 判定失败 | `FAIL(201) -> reason`，断言失败 |
| 404 无响应/超时 | 404 | `FAIL(404) -> ...` |
| 抛异常（executor 捕获） | 500 | `FAIL(500) -> repr(e)`，不中断整轮 |

桩阶段判定块显示 `PASS(桩)`，全绿是**预期**，不是结果。

## allure 报告要点（实测踩坑，全部已内置）

1. `printf()` 一次写三份：控制台 + `log/script_log_*.txt` + `allure.step`（报告里每步一行）。用例块、判定结果块都走它；
2. 关键数据用 `printf_msg_add(name, msg)` 收集（用例信息/测试结果），**必须在 call 阶段（run_case 内）挂附件**：allure-pytest 2.13.x 在 fixture teardown 前就定稿 result.json，teardown 里 `allure.attach` 会变成孤儿文件挂不上报告（2.16 正常，别赌版本）；
3. `environment.properties` **必须写在 pytest.main 之后**（`--clean-alluredir` 会清空结果目录，先写就被删）；
4. allure HTML 内部用 XHR 取数据，**file:// 双击打开是空白页**：用 `allure open <dir>` 起 HTTP 服务打开；没装 allure 命令行时用 `pytest --html=report/pytest_report.html --self-contained-html` 兜底（单文件可直接双击）；
5. Windows 下 allure 是 `.bat`：`subprocess.run(["allure", ...])` 会抛 FileNotFoundError 误报"未安装"，要用 `os.system` / `shell=True`（或先 `shutil.which`）。

## uid 规则（Excel 用例编号 ≠ 唯一键！）

公司 TestCase 表的编号按 模块×连接方式 **分段重置**，同一编号会重复出现（实测 车辆详情-4-001 出现 20+ 次），直接用编号做 key 会互相覆盖。

- uid = `模块_子模块_通道_序号`（如 `车辆详情_开关机_4G_BT_001`），撞车自动加 `_2`；
- 通道**以"前置条件"列为准**，不要信编号段：`-4-` 既可能是 4G 也可能是 4G+蓝牙（`-蓝-` 才是纯蓝牙）→ `4G` / `BT` / `4G_BT`；
- 每条用例保留 `cid` + Excel 行号，报告标题/附件可回查原表。

## 解析假设（换表格格式要改 parse_workbook）

- 每 Sheet 表头行 = B 列为 `用例编号` 的那行；B..I 列 = 编号/模块/测试项/优先级/测试内容/前置条件/执行步骤/期望结果；
- 用例行：编号匹配 `xxx-yyy-001`（三段的 `^[^-]+-[^-]+-(\d+)$`）或 `xxx-yyy-zzz-001`（四段的
  `^[^-]+-[^-]+-[^-]+-(\d+)$`，系统×连接方式二维表）；四段表多解析出 `os` / `conn` 两个字段；
- 模块列只在分段首行有值 → 向下沿用该值（仍空则取编号前缀），不再一律落到 `通用`；
- 分区标题行（仅 B 列有值、B:M 合并）跳过。

## 生成与执行

```bash
python scripts/gen_pytest_shell.py --xlsx TestCase.xlsx --out ./proj --product QDM522   # 一维表：按模块切
python scripts/gen_pytest_shell.py --xlsx TestCase.xlsx --out ./proj --product QDM562 --group-by scene  # 二维表：按环境场景切
cd proj
python -m pytest -q --co -m try_run        # 收集数 = Excel 用例数（场景模式 = 用例数 × 2；先自检再宣称完成）
python -m pytest -vs tests/test_scene_01_os_android.py   # 只跑一个环境场景
python -m pytest -vs -m p0                 # 只跑 P0（优先级已做成 marks）
python -m pytest -vs -k "TCS_TCS_4G_001"   # 单条（-k 用 uid，别用中文）
python run_all.py                          # 全量 + allure/HTML 报告，自动开浏览器
```

## 合并与更新流程

1. 壳阶段交付评审：Excel ↔ 报告逐条对得上（报告标题含 cid+行号）；
2. 基础类按 pressure-test-bases 逐领域开发调试（串口/CAN/平台互不阻塞，可并行）；
3. Excel 换版：**先把 impls.py 里已实现的函数迁到 base/impls_manual.py**（`@register` 后注册者生效，可覆盖桩），再重跑生成器；
4. 合并：conftest 的 base fixture 换成持有超类的 executor → 逐条把 return True 换成真实动作 → 按状态码判定。

## 注意事项（Windows）

- 中文不走路过命令行参数（cmd 是 GBK）：用例名/模块名一律进 UTF-8 文件；`-k` 过滤用 uid；
- pytest.ini 的 `python_files` 要能匹配生成的文件名、`pythonpath = .` 让 `from base...` 可导入、marker 必须注册否则 `-m try_run` 直接报错；
- 生成器模板里写 `\n` 的文件用 **raw 字符串**存模板，否则 `\n` 被外层解释成真换行，生成物直接语法错（实测踩过）；
- 一条用例内的多步骤在桩阶段就是文字（步骤/期望原样打印）；写真实执行时步骤文案不要重复打印，用例块由 run_case 统一输出。
