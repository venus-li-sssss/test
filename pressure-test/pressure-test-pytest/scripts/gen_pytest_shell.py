# -*- coding: utf-8 -*-
"""
测试用例 Excel → pytest + allure 自动化测试工程生成器（pressure-test-pytest 子 skill）。

用法:
    python gen_pytest_shell.py --xlsx TestCase.xlsx [--out ./proj] [--product QDM522]

设计（解耦两层）:
  用例层  tests/test_*.py          —— 由本脚本从 Excel 自动生成，一条用例 = 一个参数化用例，
                                      函数体只调用 base.run_case(case)（壳：只打印文字，不实际执行）
  执行层  base/executor.py         —— 基础类 BaseExecutor（实际执行的落点，后续套入 CAN/串口/平台超类）
          base/impls.py            —— 每个用例一个实现桩函数（当前只打印用例文字），
                                      之后把真实执行逐条填进对应 uid 的函数即可
  数据    cases.json               —— Excel 提取出的结构化用例数据（唯一键 uid）

Excel 更新后重新运行本脚本即可再生成，执行层手写代码不受影响（impls.py 会被覆盖，
已实现函数请迁移到 base/impls_manual.py）。
"""
import io
import json
import re
import shutil
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import openpyxl

HERE = Path(__file__).resolve().parent
PRODUCT = "QDM522"                       # 产品名（main 里按参数重置）
XLSX_NAME = "QDM522_TestCase_V21.xlsx"   # Excel 文件名（main 里重置）

CID_RE = re.compile(r"^([^-]+)-([^-]+)-(\d+)$")
HDR_TEXT = "用例编号"

# 列: B..I
COL_ID, COL_MODULE, COL_TITLE, COL_PRIORITY, COL_CONTENT, COL_PRECOND, COL_STEPS, COL_EXPECT = range(2, 10)


def sanitize(text: str) -> str:
    """保留中文/字母/数字/下划线，其它字符变 _ （用于 uid / 标识符）"""
    text = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff]", "_", text or "")
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "NA"


def precond_key(precond: str, chan: str) -> str:
    p = (precond or "").strip()
    has_ble = ("蓝牙" in p) or ("蓝" in chan)
    has_4g = ("4G" in p.upper()) or (chan == "4")
    if has_ble and has_4g:
        return "4G_BT"
    if has_ble:
        return "BT"
    if has_4g:
        return "4G"
    return sanitize(p or chan)


def parse_workbook(path: Path):
    wb = openpyxl.load_workbook(path)
    all_cases, anomalies = [], []
    for sheet in wb.sheetnames:
        ws = wb[sheet]
        hdr = None
        for r in range(1, 25):
            v = ws.cell(r, COL_ID).value
            if v and str(v).strip() == HDR_TEXT:
                hdr = r
                break
        if hdr is None:
            anomalies.append((sheet, "header row not found"))
            continue

        used = {}
        n_sec = 0
        for r in range(hdr + 1, ws.max_row + 1):
            cid = ws.cell(r, COL_ID).value
            module = ws.cell(r, COL_MODULE).value
            title = ws.cell(r, COL_TITLE).value
            priority = ws.cell(r, COL_PRIORITY).value
            content = ws.cell(r, COL_CONTENT).value
            precond = ws.cell(r, COL_PRECOND).value
            steps = ws.cell(r, COL_STEPS).value
            expect = ws.cell(r, COL_EXPECT).value

            if cid is None:
                continue
            cid = str(cid).strip()
            m = CID_RE.match(cid)
            if not m:
                # 分区标题行（B 列有值、其余列基本为空）→ 跳过
                rest = [module, title, priority, content, precond, steps, expect]
                if any(v not in (None, "") for v in rest):
                    anomalies.append((sheet, r, cid, "not-a-case-id"))
                else:
                    n_sec += 1
                continue

            _, chan, num = m.group(1), m.group(2), m.group(3)
            module = str(module).strip() if module else "通用"
            pkey = precond_key(str(precond) if precond else "", chan)
            uid = f"{sanitize(sheet)}_{sanitize(module)}_{pkey}_{num}"
            if uid in used:
                k = 2
                while f"{uid}_{k}" in used:
                    k += 1
                uid = f"{uid}_{k}"
                anomalies.append((sheet, r, cid, f"dup uid -> {uid}"))
            used[uid] = r

            all_cases.append({
                "uid": uid,
                "cid": cid,
                "sheet": sheet,
                "row": r,
                "module": module,
                "title": str(title or content or cid).strip(),
                "priority": (str(priority).strip().upper() if priority else ""),
                "precond": str(precond).strip() if precond else "",
                "steps": str(steps).strip() if steps else "",
                "expected": str(expect).strip() if expect else "",
            })
        print(f"[parse] {sheet:12s} cases={len(used):3d} sections={n_sec}")
    return all_cases, anomalies


# ---------------------------------------------------------------- templates

def _subst(text: str) -> str:
    """模板 token 替换：先保护 xlsx 文件名整体，再换产品名，最后还原文件名。"""
    text = text.replace("QDM522_TestCase_V21.xlsx", "\x00")
    text = text.replace("QDM522", PRODUCT)
    return text.replace("\x00", XLSX_NAME)


def write_static_files(root: Path, n_cases: int, xlsx_name: str):
    (root / "base").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "log").mkdir(exist_ok=True)
    (root / "result").mkdir(exist_ok=True)

    files = {}

    files["pytest.ini"] = """[pytest]
python_files = test_*.py
pythonpath = .
addopts = -rs
markers =
    try_run: 正式用例（默认执行集）
    p0: P0 优先级
    p1: P1 优先级
    p2: P2 优先级
    p3: P3 优先级
"""

    files["requirements.txt"] = """pytest
allure-pytest
pytest-html
openpyxl
"""

    files["conftest.py"] = '''# -*- coding: utf-8 -*-
"""pytest 入口配置：session 级基础类实例 + 用例结束 allure 附件。"""
import allure
import pytest

from base.executor import BaseExecutor
from base.logger import flush_printf_msg
import base.impls  # noqa: F401  (触发用例实现桩注册)


@pytest.fixture(scope="session")
def base():
    """基础类实例（实际执行的落点）。执行层换成真机实现时只改 base/ 目录。"""
    ex = BaseExecutor()
    print(f"\\n===== QDM522 自动化测试启动 | 基础类: {type(ex).__name__} =====")
    return ex


@pytest.fixture(scope="function", autouse=True)
def attach_printf_msg():
    """用例结束后，把 printf_msg_add() 收集的关键数据挂成 allure 报告附件
    （参照 4G-ECU FCT 框架 Base_Test 的 autouse fixture）。"""
    yield
    for key, value in flush_printf_msg().items():
        allure.attach(str(value), name=key, attachment_type=allure.attachment_type.TEXT)
'''

    files["base/__init__.py"] = ''

    files["base/registry.py"] = '''# -*- coding: utf-8 -*-
"""用例实现注册表：uid -> 实现函数。执行层与用例层通过它解耦。"""

IMPLS = {}


def register(uid):
    """装饰器：把一个用例实现函数绑定到 uid。"""
    def deco(fn):
        IMPLS[uid] = fn
        return fn
    return deco


def lookup(uid):
    return IMPLS.get(uid)
'''

    files["base/logger.py"] = r'''# -*- coding: utf-8 -*-
"""打印/日志（照搬 auto-test 生成框架的 allure 打印机制）：

    printf(msg)          = 控制台 + log/script_log_*.txt + allure 步骤（报告里每步一行）
    printf_msg_add(k, v) = 收集关键数据；用例结束后由 conftest autouse fixture 挂成 allure 附件
"""
import os
from datetime import datetime
from pathlib import Path

import allure

LOG_DIR = str(Path(__file__).resolve().parents[1] / "log")


class Make_File:
    """自动加时间戳的日志文件。"""

    def __init__(self, file_name="script", mode="a+", encoding="utf-8"):
        if not os.path.isdir(LOG_DIR):
            os.makedirs(LOG_DIR, exist_ok=True)
        self.file_name = "{}/{}_log_{}.txt".format(
            LOG_DIR, file_name, datetime.now().strftime("%Y_%m_%d_%H_%M_%S"))
        self.file = open(self.file_name, mode=mode, encoding=encoding)

    def printf(self, msg):
        self.file.write("[{}] {}\r\n".format(datetime.now(), msg))
        self.file.flush()

    def close(self):
        try:
            self.file.close()
        except Exception:
            pass


_script_file = None


def get_script():
    global _script_file
    if _script_file is None:
        _script_file = Make_File("script")
    return _script_file


printf_msg = {}


def printf(msg):
    m = str(msg)
    print(m)
    with allure.step(m):
        pass
    try:
        get_script().printf(m)
    except OSError:
        pass


def allure_add_printf(msg, name="log"):
    allure.attach(str(msg), name=name, attachment_type=allure.attachment_type.TEXT)


def printf_msg_add(name, msg):
    """收集到 printf_msg，用例结束后由 fixture 挂到 allure 报告。"""
    printf_msg[name] = str(printf_msg.get(name, "")) + str(msg) + "\r\n"


def flush_printf_msg():
    """用例结束：取走收集到的数据并清空。"""
    out = {k: v for k, v in printf_msg.items() if v}
    for k in out:
        printf_msg[k] = ""
    return out
'''

    files["base/executor.py"] = '''# -*- coding: utf-8 -*-
"""
基础类（实际执行落点）。打印与判定口径对齐 4G-ECU FCT 框架：

    BaseExecutor.run_case(case) —— 用例层唯一入口：
      ① printf 用例块（编号/模块/测试项/步骤/期望，控制台+log/script_log+allure 步骤/附件）
      ② 执行 base/impls.py 中注册的该 uid 实现函数（桩实现=只打印文字）
      ③ printf 统一结果块并断言

状态码约定（与 FCT 框架一致，合并执行层时不用改口径）：
    200 PASS / 201 判定失败 / 404 无响应(超时) / 500 脚本异常
实现函数返回值：True / None 视为 PASS；或 dict {"statuscode":200,"reason":"...","data":...}
"""
from base.logger import printf, printf_msg_add, flush_printf_msg, allure_add_printf
from base.registry import lookup

PASS = 200


def norm_res(res):
    if res is None or res is True:
        return {"statuscode": PASS, "reason": ""}
    if res is False:
        return {"statuscode": 201, "reason": "实现函数返回 False"}
    if isinstance(res, dict):
        res.setdefault("statuscode", PASS)
        res.setdefault("reason", "")
        return res
    return {"statuscode": 201, "reason": "非法返回值 %r" % (res,)}


class BaseExecutor:

    def __init__(self):
        self.stats = {"stub": 0, "impl": 0}

    # ---------------- 用例层唯一入口 ----------------
    def run_case(self, case):
        printf_msg_add("用例信息", "[{}] {}\\n模块: {}  优先级: {}  前置: {}\\n步骤:\\n{}\\n期望:\\n{}\\n".format(
            case["uid"], case["title"], case["module"], case["priority"] or "-",
            case["precond"] or "-", case["steps"] or "-", case["expected"] or "-"))
        self.print_case(case)   # 用例块统一在这里打印一次（实现函数不要重复打）
        impl = lookup(case["uid"])
        if impl is None:
            self.stats["stub"] += 1
            res = {"statuscode": PASS, "reason": "桩：未注册实现，仅打印用例文字"}
        else:
            self.stats["impl"] += 1
            try:
                res = norm_res(impl(self, case))
            except Exception as e:
                res = {"statuscode": 500, "reason": repr(e)}
        self.step_report(case, res)
        # 附件必须在 call 阶段挂好（allure-pytest 2.13.x 写入 result.json 早于 fixture
        # teardown，teardown 里再 allure.attach 会变成孤儿文件挂不到报告上）
        for key, value in flush_printf_msg().items():
            allure_add_printf(value, name=key)
        assert res["statuscode"] == PASS, "{}: {}".format(case["uid"], res["reason"])
        return res

    # ---------------- 用例块（桩阶段：打印用例对应文字） ----------------
    def print_case(self, case):
        printf("[用例] {}  （Excel 编号 {} / {} 第{}行）".format(
            case["uid"], case["cid"], case["sheet"], case["row"]))
        printf("[模块] {}  [优先级] {}  [前置] {}".format(
            case["module"], case["priority"] or "-", case["precond"] or "-"))
        printf("[测试项] {}".format(case["title"]))
        printf("[步骤] {}".format(case["steps"] or "-"))
        printf("[期望] {}".format(case["expected"] or "-"))

    # ---------------- 统一结果块（参照 FCT 框架 step_report/check） ----------------
    def step_report(self, case, res, extra=None):
        if res.get("statuscode") == PASS:
            tag = "PASS" if "桩" not in str(res.get("reason", "")) else "PASS(桩)"
        else:
            tag = "FAIL({}) -> {}".format(res.get("statuscode"), res.get("reason"))
        printf("+------------------- [{}] {} -------------------".format(
            case["uid"], case["title"]))
        if extra:
            printf("| 说明: {}".format(extra))
        printf("| 判定: {}".format(tag))
        printf("+-----------------------------------------------------------")
        printf_msg_add("测试结果", "[{}] {}".format(case["uid"], tag))

    # ---------------- 真机动作位（后续填充示例） ----------------
    # def app_connect_vehicle(self, vehicle): ...   # TODO APP 连接车辆
    # def app_click(self, element): ...             # TODO 点击 APP 控件
    # def vehicle_power_on(self): ...               # TODO 车辆开机
    # def wait(self, seconds): ...                  # TODO 等待
    # 判定失败时返回 {"statuscode": 201, "reason": "实际与期望不一致: ..."}
'''

    files["base/case_loader.py"] = '''# -*- coding: utf-8 -*-
"""cases.json 读取 + pytest 参数化构造。"""
import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_cache = None


def _cases():
    global _cache
    if _cache is None:
        _cache = json.loads((_ROOT / "cases.json").read_text(encoding="utf-8"))["cases"]
    return _cache


def get_cases(sheet=None):
    if sheet is None:
        return list(_cases())
    return [c for c in _cases() if c["sheet"] == sheet]


def make_params(cases):
    marks_map = {"P0": pytest.mark.p0, "P1": pytest.mark.p1,
                 "P2": pytest.mark.p2, "P3": pytest.mark.p3}
    params = []
    for c in cases:
        marks = [marks_map[c["priority"]]] if c["priority"] in marks_map else []
        params.append(pytest.param(c, marks=marks, id=c["uid"]))
    return params


def get_sheet_params(sheet):
    return make_params(get_cases(sheet))
'''

    files["run_all.py"] = r'''# -*- coding: utf-8 -*-
"""一键执行：pytest 跑用例 -> allure 原始数据+环境信息 -> 生成/打开报告。

用法:
    python run_all.py                 # 全部用例
    python run_all.py -m p0           # 只跑 P0（其余参数透传给 pytest）

报告口径（对齐 auto-test 生成框架）:
    result\\xml             allure 原始数据（allure-pytest 直接写，不需要 allure 命令行）
    report\\allure          allure HTML（需安装 allure-commandline；未装自动跳过）
    report\\pytest_report.html   pytest-html 单文件报告（任何机器都能直接双击打开）
    log\\script_log_*.txt   脚本日志（与 allure 步骤同内容）
"""
import datetime
import os
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
RESULT_DIR = ROOT / "result" / "xml"
REPORT_DIR = ROOT / "report" / "allure"
HTML_REPORT = ROOT / "report" / "pytest_report.html"
OPEN_REPORT = os.environ.get("QDM_OPEN_REPORT", "1") == "1"


def main():
    extra = sys.argv[1:]
    now = datetime.datetime.now()
    REPORT_DIR.parent.mkdir(parents=True, exist_ok=True)
    pytest_args = ["-vs",
                   "--alluredir={}".format(RESULT_DIR), "--clean-alluredir",
                   "--html={}".format(HTML_REPORT), "--self-contained-html"]
    if "-m" not in extra:
        pytest_args += ["-m", "try_run"]     # 默认只跑正式用例；显式传 -m 时听用户的
    pytest_args += extra
    print("执行: pytest {}".format(" ".join(pytest_args)))
    code = pytest.main(pytest_args)

    # environment.properties 必须写在 pytest 之后（--clean-alluredir 会清空结果目录）
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    (RESULT_DIR / "environment.properties").write_text("\n".join([
        "Product=QDM522",
        "TestCases=QDM522_TestCase_V21.xlsx",
        "FirmwareType=正常软件版（APP控车功能测试）",
        "Stage=桩实现(仅打印用例文字)",
        "RunTime=" + now.strftime("%Y-%m-%d %H:%M:%S"),
        "",
    ]), encoding="utf-8")

    # -------- 生成 allure HTML --------
    if shutil.which("allure"):
        print("生成 allure 报告: {} -> {}".format(RESULT_DIR, REPORT_DIR))
        os.system("allure generate {} -o {} --clean".format(RESULT_DIR, REPORT_DIR))
        if (REPORT_DIR / "index.html").exists() and OPEN_REPORT:
            # allure 报告内部用 XHR 取数据，file:// 直开是空白页，必须走 HTTP
            subprocess.Popen("allure open {}".format(REPORT_DIR), shell=True)
            print("已在后台启动 allure 服务并打开浏览器（关闭该窗口即可停止服务）")
    else:
        print("未安装 allure-commandline，跳过 allure HTML 生成（原始数据仍在 result\\xml，")
        print("  以后装好可在本机执行: allure serve {})".format(RESULT_DIR))

    # -------- pytest-html 兜底报告（双击即看） --------
    if HTML_REPORT.exists():
        print("HTML 报告: {}".format(HTML_REPORT))
        if OPEN_REPORT and not shutil.which("allure"):
            webbrowser.open(HTML_REPORT.as_uri())
    return code


if __name__ == "__main__":
    sys.exit(main())
'''

    for rel, text in files.items():
        (root / rel).write_text(_subst(text), encoding="utf-8")

    (root / "tests" / "__init__.py").write_text("", encoding="utf-8")


def gen_impls(root: Path, cases, xlsx_name):
    head = f'''# -*- coding: utf-8 -*-
"""每个用例的基础类实现桩（自动生成，共 {len(cases)} 条）。

用例块（编号/步骤/期望）由 BaseExecutor.run_case 统一打印，实现函数里只写真实动作。
真实执行开发：按 uid 搜索本文件，把函数体的 return True 替换为真机操作；
判定失败返回 {{"statuscode": 201, "reason": "..."}}（200=PASS / 404=超时无响应 / 500=脚本异常）。
重新生成时已实现内容请迁移到 base/impls_manual.py 并用 @register(uid) 覆盖
（registry 后注册者生效）。
数据源: {xlsx_name}
"""
from base.registry import register

'''
    parts = [head]
    used_names = set()
    last_sheet = None
    for c in cases:
        if c["sheet"] != last_sheet:
            parts.append(f"\n# ============ {c['sheet']}（Excel 编号 {c['cid']} 系列） ============\n")
            last_sheet = c["sheet"]
        fname = f"impl_{sanitize(c['uid'])}_R{c['row']}"
        while fname in used_names:
            fname += "x"
        used_names.add(fname)
        doc = (c["title"].replace('"""', "'").replace("\n", " "))[:80]
        parts.append(
            f'\n@register("{c["uid"]}")  # {c["cid"]} {c["priority"]}\n'
            f'def {fname}(base, case):\n'
            f'    """{doc}"""\n'
            f'    # TODO: 真实执行（APP UI / 车辆指令 / 平台接口）。桩阶段由 run_case 打印用例文字\n'
            f'    return True\n'
        )
    (root / "base" / "impls.py").write_text("".join(parts), encoding="utf-8")


def gen_readme(root: Path, n_cases, n_sheets, xlsx_name):
    md = f"""# QDM522 pytest 自动化测试（桩实现版）

从 `{xlsx_name}` 自动生成，共 **{n_cases} 条用例 / {n_sheets} 个功能模块（Sheet）**。

## 分层（解耦设计）

```
tests/test_XX_<模块>.py    用例层：一条 Excel 用例 = 一个参数化用例，
                              函数体只调 base.run_case(case)（自动生成，勿手改）
cases.json                 数据层：Excel 提取的结构化用例（uid/cid/模块/优先级/前置/步骤/期望）
base/executor.py           基础类 BaseExecutor：实际执行的落点（run_case/step_report/判定断言）
base/impls.py              每条用例一个实现桩函数（按 uid 注册），未来在这里填真实执行
base/logger.py             printf 三通道打印：控制台 + log/script_log_*.txt + allure 步骤/附件
base/registry.py           uid -> 实现函数 的注册表（两层之间的唯一耦合点）
```

合并计划：真机执行开发时，只需要在 `base/` 里新增驱动（APP UI / 车辆指令 / 平台接口），
并把 `impls.py` 里对应 uid 的 `base.print_case(case)` 替换成真实步骤；**tests/ 零改动**。

## uid 规则

Excel 用例编号（如 `车辆详情-4-001`）在模块×连接方式分段中会重复，所以唯一键 uid =
`模块_子模块_连接_序号`（连接：`4G` / `BT` 蓝牙 / `4G_BT` 双通道；重复时追加 `_2`）。
每条用例都保留 `cid` + Excel 行号可回查原始表格。

## 运行

```bash
pip install -r requirements.txt
python -m pytest -q --co -m try_run      # 只看收集到的用例
python -m pytest -vs -m p0               # 只跑 P0
python run_all.py                        # 全量 + allure/HTML 报告
```

## allure 报告（对齐 auto-test 生成框架）

- 每条用例的执行过程 = allure **步骤**（用例块 + 判定结果块 `+--- [uid] 测试项 --- 判定: PASS ---+`），
  同时写 `log/script_log_*.txt`（同一内容三份：控制台/日志/报告）。
- 关键数据走 `printf_msg_add(name, msg)` 收集，用例结束由 conftest 的 autouse fixture
  挂成 allure **附件**（当前有「用例信息」「测试结果」两个）。
- `python run_all.py` 产出：
  | 位置 | 内容 | 怎么看 |
  | --- | --- | --- |
  | `result\\xml` | allure 原始数据 + environment.properties | 装了 allure 命令行后 `allure serve result\\xml` |
  | `report\\allure` | allure HTML（需 allure-commandline，未装自动跳过） | `allure open report\\allure`（必须 HTTP，file:// 是空白页） |
  | `report\\pytest_report.html` | pytest-html 单文件报告 | 任何机器双击即看 |
- 桩阶段全部 PASS（含判定块显示 `PASS(桩)`），这是预期；接真实执行后 FAIL 才有意义。

## 更新用例

Excel 换了版本后：`python gen_from_excel.py --xlsx <新xlsx> --out <本工程目录>`
（已实现用例先迁移到 `base/impls_manual.py`）。
"""
    (root / "README.md").write_text(_subst(md), encoding="utf-8")


def main():
    global PRODUCT, XLSX_NAME
    import argparse
    ap = argparse.ArgumentParser(
        description="测试用例 Excel → pytest 壳工程（用例层/执行层解耦 + allure 报告）")
    ap.add_argument("--xlsx", required=True, help="测试用例 Excel（公司 TestCase 标准表格式）")
    ap.add_argument("--out", default=None, help="输出工程目录，默认 ./<product>_pytest")
    ap.add_argument("--product", default=None,
                    help="产品名（README/banner/environment），默认从文件名 Xxxx_TestCase 提取")
    a = ap.parse_args()

    xlsx = Path(a.xlsx).resolve()
    XLSX_NAME = xlsx.name
    if a.product:
        PRODUCT = a.product
    else:
        m = re.search(r"([A-Za-z][A-Za-z0-9\-]*?)_TestCase", xlsx.stem, re.I)
        PRODUCT = m.group(1) if m else xlsx.stem
    root = Path(a.out).resolve() if a.out else Path.cwd() / "{}_pytest".format(PRODUCT)
    root.mkdir(parents=True, exist_ok=True)

    cases, anomalies = parse_workbook(xlsx)
    by_sheet = {}
    for c in cases:
        by_sheet.setdefault(c["sheet"], 0)
        by_sheet[c["sheet"]] += 1

    write_static_files(root, len(cases), xlsx.name)
    (root / "cases.json").write_text(
        json.dumps({"source": str(xlsx), "count": len(cases), "cases": cases},
                   ensure_ascii=False, indent=1), encoding="utf-8")

    # 生成 tests/ 文件
    cls_tpl = '''# -*- coding: utf-8 -*-
"""由 gen_from_excel.py 自动生成，勿手工编辑。用例增删请改 Excel 后重跑生成器。
数据源: cases.json（{sheet}，{ncase} 条）"""
import allure
import pytest

from base.case_loader import get_sheet_params


@pytest.mark.try_run
@allure.feature("{sheet}")
class Test{cls}:
    """{sheet}（{ncase} 条用例）"""

    @pytest.mark.parametrize("case", get_sheet_params("{sheet}"))
    def test_case(self, base, case):
        allure.dynamic.story(case["module"])
        allure.dynamic.title(f\'{{case["uid"]}}｜{{case["title"]}}\')
        allure.dynamic.description(
            f\'编号: {{case["cid"]}}  (Excel {{case["sheet"]}} 第{{case["row"]}}行)\\n\'
            f\'优先级: {{case["priority"] or "-"}}  前置条件: {{case["precond"] or "-"}}\\n\'
            f\'步骤:\\n{{case["steps"]}}  \\n期望结果:\\n{{case["expected"]}}\')
        base.run_case(case)
'''
    tdir = root / "tests"
    for f in tdir.glob("test_*.py"):
        f.unlink()
    for i, sheet in enumerate(by_sheet, 1):
        cls = sanitize(sheet)
        text = cls_tpl.format(sheet=sheet, cls=cls, ncase=by_sheet[sheet])
        (tdir / f"test_{i:02d}_{cls}.py").write_text(text, encoding="utf-8")

    gen_impls(root, cases, xlsx.name)
    gen_readme(root, len(cases), len(by_sheet), xlsx.name)

    # 生成器自拷贝：项目内可独立再生（Excel 更新后直接在工程里重跑）
    try:
        shutil.copy(Path(__file__), root / "gen_from_excel.py")
    except Exception:
        pass

    print("-" * 60)
    print(f"生成完成: {len(cases)} 条用例, {len(by_sheet)} 个测试文件 -> {root}")
    if anomalies:
        print(f"注意 {len(anomalies)} 处异常（重复编号已自动加后缀）：")
        for a in anomalies[:10]:
            print("   ", a)


if __name__ == "__main__":
    main()
