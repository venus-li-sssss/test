---
description: 'Use this skill when the user wants functional test cases turned into a pytest project with a thin "shell" layer decoupled from the execution base classes, with allure reporting. Triggers: 自动化测试脚本, 用例转pytest, 测试用例生成pytest, pytest壳, 基类解耦, 用例和实际执行分开, allure报告, CAN/串口/平台基类组合, Excel用例转脚本. The pytest layer only calls functions that print the case text (no real execution yet); the base classes (Serial/CAN/Platform API) are developed separately and later plugged into the pytest super class via uid registry.'
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
| FCT 产测一体化项目（spec.json+sim 自检+协议层） | pressure-test-framework / auto-test |
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
- 用例行：编号匹配 `xxx-yyy-001`（正则 `^[^-]+-[^-]+-(\d+)$`）；
- 分区标题行（仅 B 列有值、B:M 合并）跳过。

## 生成与执行

```bash
python scripts/gen_pytest_shell.py --xlsx TestCase.xlsx --out ./proj --product QDM522
cd proj
python -m pytest -q --co -m try_run        # 收集数 = Excel 用例数（先自检再宣称完成）
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
