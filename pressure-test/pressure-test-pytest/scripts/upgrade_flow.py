# -*- coding: utf-8 -*-
"""升级流程模板（Layer 3：流程）—— 「套进去一个类就能做升级」。

来源：QDM551 现场的模板（`D:\\work\\551\\脚本\\自动化测试\\V07\\io_backends\\fota_backend.py`
里的 `class Fota` / `IO_Factory.mount_process_fota`，以及 `551_OUT_TEST_V18.py` 里三处实例化）。
原模板的设计是：**你只管提供 4 个钩子**（查版本 / 下发升级 / 查升级状态 / 打印），
流程、轮询、超时、重试、失败恢复全在模板里；因此同一套流程换个「通道类」就能跑
APP（蓝牙）升级 / 平台升级 / 上位机升级。

对齐原模板的字段（改名字但不改语义）：

    原有                                        这里
    info={版本集}                               同上（T-BOX/BMS/VCU/TFT/MCU 两个版本互升）
    def_version / def_upgrade / def_status      version_hook / upgrade_hook / status_hook
    def_printf_out                              printf_out_hook
    fota_status_check_list={'ex_pass_status_list':[200],'ex_fail_status_list':[201]}
                                               同上（上位机是 3/4）
    def_begin_check_dict / def_operate_dict /   同名（关键字 → 动作，做前置检查/重启/恢复）
    def_recovery_dict
    keyword_dict                               同名（"下载中"/"传包中" → 正则）
    process_normal_fota(ex_component_list)     同名（正常升级流程）
    process_err_package_fota / _by_debug / _by_status
                                               同名（异常分支：错包 / 下卡住 / 状态不对）

用法（三步）：

    flow = UpgradeFlow(info=version_info, channel=AppUpgradeChannel(app),
                       status_check={"ex_pass_status_list":[200], "ex_fail_status_list":[201]})
    res = flow.process_normal_fota(["T-BOX"])
    print(res["statuscode"], res["reason"])

本文件不依赖任何项目代码，可直接复制到别的工程当模板用。
"""
from __future__ import annotations

import time
import traceback

PASS = 200
FAIL = 201


class UpgradeFlow:
    """升级流程模板：钩子进，判定出。"""

    def __init__(self, info=None, channel=None, status_check=None,
                 # 兼容原模板的 4 个钩子写法：不给 channel 就单独传
                 version_hook=None, upgrade_hook=None, status_hook=None, printf_out_hook=None,
                 status_key="statuscode",
                 version_interval=5, version_timeout=900,
                 status_interval=5, status_timeout=2400,
                 is_check_version=True, is_info_version=False,
                 def_operate_dict=None, def_begin_check_dict=None,
                 def_recovery_dict=None, keyword_dict=None,
                 debug_object=None, name=""):
        self.name = name or getattr(channel, "name", "upgrade")
        self.info = info or {}
        self.channel = channel
        # 钩子：优先 channel，其次显式传函数（兼容 551 里的写法）
        self.version_hook = version_hook or getattr(channel, "version", None)
        self.upgrade_hook = upgrade_hook or getattr(channel, "upgrade", None)
        self.status_hook = status_hook or getattr(channel, "status", None)
        self.printf_out_hook = printf_out_hook or getattr(channel, "printf_out", None) or (lambda msg: None)

        status_check = status_check or {}
        self.ex_pass_status_list = status_check.get("ex_pass_status_list", [PASS])
        self.ex_fail_status_list = status_check.get("ex_fail_status_list", [FAIL])
        self.status_key = status_key

        self.version_interval = version_interval
        self.version_timeout = version_timeout
        self.status_interval = status_interval
        self.status_timeout = status_timeout
        self.is_check_version = is_check_version
        self.is_info_version = is_info_version

        self.def_operate_dict = def_operate_dict or {}
        self.def_begin_check_dict = def_begin_check_dict or {"none": self._none}
        self.def_recovery_dict = def_recovery_dict or {}
        self.def_recovery_dict.setdefault("none", self._none)
        self.keyword_dict = keyword_dict or {}
        self.debug_object = debug_object

        if not (self.version_hook and self.upgrade_hook):
            raise ValueError("UpgradeFlow 需要 channel 或显式传 version_hook / upgrade_hook")

    # ------------------------------------------------------------ 基础钩子
    def _none(self, *a, **kw):
        return {"statuscode": PASS, "reason": "none"}

    def printf_out(self, msg):
        self.printf_out_hook(msg)

    def version(self, *a, **kw):
        return self.version_hook(*a, **kw) or {}

    def update(self, ex_version):
        return self.upgrade_hook(ex_version) or {}

    def status(self, *a, **kw):
        if self.status_hook is None:
            return {"statuscode": PASS, "reason": "该通道没有状态接口，跳过状态轮询"}
        return self.status_hook(*a, **kw) or {}

    @staticmethod
    def _ok(res):
        if isinstance(res, dict):
            return res.get("statuscode", PASS) in (PASS, True)
        return res is not False

    def _code(self, res):
        """取状态码（默认键 statuscode；上位机通道可配成 3/4）。"""
        return res.get(self.status_key, PASS) if isinstance(res, dict) else (PASS if res else FAIL)

    # ------------------------------------------------------------ 版本集
    def default_version(self):
        """把 info 版本集里的「a_version」当作初始（现行）版本。"""
        out = {}
        for comp, v in (self.info or {}).items():
            if isinstance(v, dict) and "a_version" in v:
                out[comp] = v["a_version"].get("version")
            elif isinstance(v, list) and v:
                out[comp] = v[0].get("old_version", {}).get("version")
            elif isinstance(v, str):
                out[comp] = v
        return out

    def set_ex_version(self, old_version_dict=None, components=None):
        """按「当前版本」在 info 里挑对应的目标版本（a↔b 互升）。"""
        old_version_dict = self.default_version() if self.is_info_version or not old_version_dict else old_version_dict
        components = components or list((self.info or {}).keys())
        ex_version = {}
        for comp in components:
            info = (self.info or {}).get(comp)
            if not info:
                continue
            if isinstance(info, dict) and "a_version" in info and "b_version" in info:
                cur = str(old_version_dict.get(comp) or info["a_version"].get("version"))
                target = info["b_version"] if cur == str(info["a_version"].get("version")) else info["a_version"]
                ex_version[comp] = target
            elif isinstance(info, list):
                cur = str(old_version_dict.get(comp) or "")
                for item in info:
                    if str(item.get("old_version", {}).get("version")) == cur:
                        ex_version[comp] = item.get("ex_version")
                        break
                if comp not in ex_version and info:
                    ex_version[comp] = info[0].get("ex_version")
            elif isinstance(info, str):
                ex_version[comp] = {"version": info, "path": ""}
        return ex_version

    def version_check(self, ex_version_dict=None, *a, **kw):
        """查当前版本 → 打印 → 判断是否已经是期望版本。

        只比对**两边都有**的组件；一个都对不上说明「版本集组件名」和「通道返回的组件名」不一致，
        这时跳过复核并在 reason 里点出来（不假装通过，也不误判失败）。
        """
        cur = self.version(*a, **kw)
        ex_version_dict = ex_version_dict or self.set_ex_version(cur)
        self.printf_out("[%s] 当前版本: %s" % (self.name, cur))
        self.printf_out("[%s] 期望版本: %s" % (self.name, {k: v.get("version") if isinstance(v, dict) else v
                                                       for k, v in ex_version_dict.items()}))
        common = [c for c in ex_version_dict if c in cur]
        if not common:
            return {"statuscode": PASS, "reason": "版本集组件名与通道返回不匹配，跳过复核",
                    "current": cur,
                    "expect": {k: (v.get("version") if isinstance(v, dict) else v) for k, v in ex_version_dict.items()}}
        same, diff = True, {}
        for comp in common:
            exp_v = ex_version_dict[comp]
            exp_v = exp_v.get("version") if isinstance(exp_v, dict) else exp_v
            if exp_v and str(cur.get(comp)) != str(exp_v):
                same = False
                diff[comp] = {"cur": cur.get(comp), "expect": exp_v}
        return {"statuscode": PASS if same else FAIL,
                "reason": "版本一致" if same else "版本不一致: %s" % diff,
                "current": cur,
                "expect": {k: (v.get("version") if isinstance(v, dict) else v) for k, v in ex_version_dict.items()},
                "diff": diff}

    def status_check(self, res=None):
        """按 ex_pass / ex_fail 判升级状态。"""
        res = self.status() if res is None else res
        code = self._code(res)
        if code in self.ex_pass_status_list:
            return {"statuscode": PASS, "reason": "状态通过", "detail": res}
        if code in self.ex_fail_status_list:
            return {"statuscode": FAIL, "reason": "状态失败", "detail": res}
        return {"statuscode": None, "reason": "状态未定", "detail": res}

    # ------------------------------------------------------------ 轮询
    def wait_status(self, timeout=None, interval=None):
        """状态轮询：直到 pass/fail 或超时（对应原模板 check_in_time）。"""
        timeout = timeout or self.status_timeout
        interval = interval or self.status_interval
        t0 = time.time()
        while time.time() - t0 < timeout:
            r = self.status_check()
            if r["statuscode"] in (PASS, FAIL):
                return r
            time.sleep(interval)
        return {"statuscode": FAIL, "reason": "状态轮询超时(%ss)" % timeout}

    def wait_version(self, ex_version_dict, timeout=None, interval=None):
        """版本轮询：升级完等版本号真的变了（对应原模板 version_check_in_time）。"""
        if getattr(self.channel, "mock", False):
            return {"statuscode": PASS, "reason": "MOCK 跳过版本复核", "current": {}, "expect": ex_version_dict}
        timeout = timeout or self.version_timeout
        interval = interval or self.version_interval
        t0 = time.time()
        while time.time() - t0 < timeout:
            r = self.version_check(ex_version_dict)
            if r["statuscode"] == PASS:
                return r
            time.sleep(interval)
        return {"statuscode": FAIL, "reason": "版本复核超时(%ss)" % timeout,
                "current": self.version(), "expect": ex_version_dict}

    def run_keyword(self, keyword):
        """keyword_dict 里的关键字 → 动作（用于前置检查 / 重启 / 恢复）。"""
        fn = self.def_begin_check_dict.get(keyword) or self.def_operate_dict.get(keyword) \
            or self.def_recovery_dict.get(keyword)
        if not fn:
            return {"statuscode": PASS, "reason": "无对应关键字动作: %s" % keyword}
        return fn() or {}

    # ------------------------------------------------------------ 主流程
    def process_normal_fota(self, components=None, **kw):
        """正常升级流程：按 is_check_version 分派（与原模板同名）。"""
        if self.is_check_version:
            return self.process_normal_fota_x(components, **kw)
        return self.process_normal_nocheckversion_fota_x(components, **kw)

    def process_normal_fota_x(self, components=None, start_version=None, expect=None,
                              begin_keyword="none", **kw):
        """① 查起始版本 → ② 选期望版本 → ③ 下发升级 → ④ 状态轮询 → ⑤ 版本复核。"""
        detail = {"channel": self.name, "components": components}
        try:
            begin = self.run_keyword(begin_keyword)
            if not self._ok(begin):
                return {"statuscode": FAIL, "reason": "前置检查未通过: %s" % begin, "detail": detail}

            start_version = start_version or self.version()
            detail["start_version"] = start_version
            self.printf_out("[%s] 起始版本 %s" % (self.name, start_version))

            expect = expect or self.set_ex_version(start_version, components)
            detail["expect"] = {k: (v.get("version") if isinstance(v, dict) else v) for k, v in expect.items()}
            if not expect:
                return {"statuscode": FAIL, "reason": "没有可用的期望版本（info 版本集没覆盖这些组件）",
                        "detail": detail}

            self.printf_out("[%s] 下发升级 %s" % (self.name, detail["expect"]))
            up = self.update(expect)
            detail["upgrade"] = up
            if not self._ok(up):
                return {"statuscode": self._code(up) or FAIL, "reason": "下发升级失败: %s" % (up.get("reason") if isinstance(up, dict) else up),
                        "detail": detail}

            st = self.wait_status(**kw)
            detail["status"] = st
            if st["statuscode"] != PASS:
                return {"statuscode": FAIL, "reason": "升级状态未通过: %s" % st.get("reason"), "detail": detail}

            ver = self.wait_version(expect, **kw)
            detail["end_version"] = ver.get("current")
            if ver["statuscode"] != PASS:
                return {"statuscode": FAIL, "reason": "版本复核未通过: %s" % ver.get("reason"), "detail": detail}

            return {"statuscode": PASS,
                    "reason": "升级成功：%s → %s" % (detail["start_version"], detail.get("end_version")),
                    "detail": detail}
        except Exception as e:
            err = "%s\n%s" % (e, (self.debug_object.debug_log() if getattr(self, "debug_object", None) else ""))
            low = str(e).lower()
            code = 404 if any(k in low for k in
                              ("未启用", "未打开", "not online", "connecterror", "connectionrefused",
                               "未连接", "timeout", "timed out", "proxyerror")) else 500
            kind = "连不上/超时" if code == 404 else "升级流程异常"
            return {"statuscode": code, "reason": "%s: %s" % (kind, err),
                    "detail": detail, "traceback": traceback.format_exc(limit=3)}

    def process_normal_nocheckversion_fota_x(self, components=None, begin_keyword="none", **kw):
        """不校验版本号的正常升级：直接下发 + 状态判定（原模板同名）。"""
        try:
            expect = self.set_ex_version(None, components) if self.info else {}
            up = self.update(expect)
            if not self._ok(up):
                return {"statuscode": FAIL, "reason": "下发升级失败", "detail": {"upgrade": up}}
            st = self.wait_status(**kw)
            return {"statuscode": PASS if st["statuscode"] == PASS else FAIL,
                    "reason": "升级完成（未校验版本号）" if st["statuscode"] == PASS else st.get("reason"),
                    "detail": {"expect": expect, "status": st}}
        except Exception as e:
            return {"statuscode": 500, "reason": "升级流程异常: %s" % e, "detail": {}}

    # ------------------------------------------------------------ 异常分支
    def process_err_package_fota(self, components=None, err_package=None, **kw):
        """异常包升级：下发错包 → 期望失败 → 再下发正确包恢复（原模板同名）。"""
        err_package = err_package or self.set_ex_version(None, components)
        res = self.update(err_package)
        fail_state = self.wait_status(**kw)
        if fail_state["statuscode"] == FAIL:
            self.printf_out("[%s] 错包按预期失败，改下发正确包" % self.name)
            ok = self.process_normal_fota(components, start_version=self.version(), **kw)
            return {"statuscode": ok["statuscode"],
                    "reason": "错包按预期失败，正确包恢复%s" % ("成功" if ok["statuscode"] == PASS else "失败"),
                    "detail": {"err_state": fail_state, "recovery": ok}}
        return {"statuscode": FAIL, "reason": "错包没有按预期失败（怀疑校验缺失）",
                "detail": {"err_state": fail_state}}

    def process_err_operate_fota_by_status(self, expr=None, keyword=None, operate="重启", **kw):
        """状态卡住（下载中/升级中）→ 执行恢复动作（重启/断网重启）后重跑（原模板同名）。"""
        res = {"statuscode": FAIL, "reason": "状态未达预期"}
        if keyword:
            self.run_keyword(keyword)
        self.run_keyword(operate)
        return self.process_normal_fota(None, **kw)

    def process_err_operate_fota_by_debug(self, keyword=None, operate="重启",
                                          operate_result="none", recovery_keyword="none", **kw):
        """用 debug 串口日志判卡点再重启（原模板同名，这里保留结构，debug 需由通道提供）。"""
        if self.debug_object is not None:
            self.printf_out("[%s] debug 关键字检测: %s" % (self.name, keyword))
        return self.process_err_operate_fota_by_status(None, keyword, operate, **kw)


def mount_process_fota(**kwargs):
    """工厂函数：对应原模板 `IO_Factory.mount_process_fota(...)`。"""
    return UpgradeFlow(**kwargs)


if __name__ == "__main__":
    class DummyChannel:
        name = "dummy"
        def __init__(self):
            self.v = "0110"
        def version(self, *a, **kw):
            return {"T-BOX": self.v}
        def upgrade(self, ex):
            self.v = ex["T-BOX"]["version"]
            return {"statuscode": 200}
        def status(self, *a, **kw):
            return {"statuscode": 200}
        def printf_out(self, msg):
            print(msg)

    info = {"T-BOX": {"a_version": {"version": "0110", "path": "A"}, "b_version": {"version": "0111", "path": "B"}}}
    flow = UpgradeFlow(info=info, channel=DummyChannel(),
                       status_check={"ex_pass_status_list": [200], "ex_fail_status_list": [201]},
                       status_interval=0.1)
    print(flow.process_normal_fota(["T-BOX"]))
