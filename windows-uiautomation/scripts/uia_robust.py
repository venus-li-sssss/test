# -*- coding: utf-8 -*-
"""Windows UIA 自动化稳定化小工具（配合 SKILL.md 使用）

只依赖 uiautomation（+ 可选 pyserial 用于端口占用判定）。

用法示例
--------
    import uiautomation as auto
    from uia_robust import dump_control, ctl_state, wait_state, click_until, port_free

    BTN = {"ClassName": "QPushButton", "AutomationId": "...pushButton_openOrClose"}
    win = auto.WindowControl(searchDepth=1, ClassName="WindowBase", Name="Frame")

    dump_control(BTN)                 # 第一次接新界面：先 dump 看 ControlType/Name/ToggleState
    print(ctl_state(BTN))             # 'on' / 'off' / None
    click_until(win, BTN, "on")       # 点两次 + 轮询，返回是否成功
    print(port_free("COM246"))        # True=端口没人占
"""
from __future__ import annotations

import time

try:
    import uiautomation as auto
except Exception:  # pragma: no cover - 允许在没装 uiautomation 的机器上 import 本模块做纯逻辑测试
    auto = None

DEFAULT_TIMEOUT = 2          # 控件定位超时（秒）。库默认 10s，太长，一律缩短
POLL_INTERVAL = 0.2


def _make(cls_name, props, timeout=DEFAULT_TIMEOUT):
    """按类名构造控件（带 searchTimeout），失败返回 None。"""
    if auto is None:
        raise RuntimeError("未安装 uiautomation：pip install uiautomation")
    try:
        return getattr(auto, cls_name)(searchTimeout=timeout, **props)
    except Exception:
        return None


def dump_control(props, timeout=DEFAULT_TIMEOUT, extra_classes=("CheckBoxControl", "ButtonControl", "Control")):
    """把控件真实属性打出来：ControlType / ClassName / Name / ToggleState。

    接新界面第一步就用它 —— 别照抄别人的类名（Qt 的 QPushButton 在 UIA 里常是 CheckBoxControl）。
    """
    for cls_name in extra_classes:
        ctl = _make(cls_name, props, timeout)
        if ctl is None:
            continue
        try:
            exists = ctl.Exists(0.3, 0.05)
        except Exception:
            exists = False
        info = {"by": cls_name, "exists": exists}
        if exists:
            for attr in ("ControlTypeName", "ClassName", "Name", "AutomationId"):
                try:
                    info[attr] = getattr(ctl, attr)
                except Exception as exc:  # noqa: BLE001
                    info[attr] = "<读取失败: %s>" % exc
            try:
                pattern = ctl.GetTogglePattern()
                info["ToggleState"] = None if pattern is None else int(pattern.ToggleState)
            except Exception as exc:  # noqa: BLE001
                info["ToggleState"] = "<无TogglePattern: %s>" % exc
        print(info)
    return None


def ctl_state(props, timeout=DEFAULT_TIMEOUT, refresh=True):
    """读开关型控件状态：'on'（勾选=已启用）/ 'off' / None。

    优先级：ToggleState（真状态）> 文字包含匹配（按钮文字通常是"下一步动作"）。
    """
    for cls_name in ("CheckBoxControl", "ButtonControl"):
        ctl = _make(cls_name, props, timeout)
        if ctl is None:
            continue
        try:
            if not ctl.Exists(0.3, 0.05):
                continue
        except Exception:
            continue
        if refresh:
            try:
                ctl.Refind()          # 破缓存：点完按钮立刻读还是旧值就是这个坑
            except Exception:
                pass
        try:
            pattern = ctl.GetTogglePattern()
            if pattern is not None:
                ts = int(pattern.ToggleState)
                if ts == 1:
                    return "on"
                if ts == 0:
                    return "off"
        except Exception:
            pass
        try:
            name = str(ctl.Name or "").strip()
        except Exception:
            name = ""
        if "关闭" in name:
            return "on"
        if "打开" in name:
            return "off"
    return None


def wait_state(props, target, timeout=8.0, interval=POLL_INTERVAL):
    """轮询直到状态等于 target（'on'/'off'），返回是否成功。"""
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if ctl_state(props) == target:
            return True
        time.sleep(interval)
    return False


def click_until(win, props, target, wait_seconds=8.0, max_clicks=2):
    """点击直到状态变成 target：先 SetTopmost，最多点 max_clicks 次，每次点完轮询。

    返回 True/False。首次点击打空（窗口刚激活）是常见现象，所以允许点两次。
    """
    if win is not None:
        try:
            win.SetTopmost()
        except Exception:
            pass
    if ctl_state(props) == target:
        return True
    for attempt in range(1, max_clicks + 1):
        if ctl_state(props) == target:
            return True
        try:
            ctl = _make("CheckBoxControl", props, DEFAULT_TIMEOUT) or _make("ButtonControl", props, DEFAULT_TIMEOUT)
            if ctl is None:
                return False
            ctl.Click()
        except Exception:
            return False
        if wait_state(props, target, wait_seconds):
            return True
        print("[click_until] 第%d次点击后 %.1fs 仍未变成 %s" % (attempt, wait_seconds, target))
    return False


def port_free(com, baudrate=115200):
    """端口是否已被释放（能 open 就是释放了）。

    True=可打开（没人占用）/ False=被占用或不可用。
    注意：会短暂 open/close 一次，个别板子的 USB CDC 会被 DTR 抖动影响，别高频调用。
    """
    try:
        import serial
    except Exception:
        raise RuntimeError("需要 pyserial：pip install pyserial")
    try:
        probe = serial.Serial(com, baudrate, timeout=0.1)
        probe.close()
        return True
    except Exception:
        return False
