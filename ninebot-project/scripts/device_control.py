#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
device_control.py —— 基于 uiautomator2 的 Android 设备控制脚本

设计原则：相对定位优先，禁止硬编码绝对像素坐标
  - 用元素的属性(text/description/resourceId)或层级关系(parent/child/sibling/xpath)定位
  - 点击时直接对「元素对象」调用 .click()，坐标由框架按元素当前位置动态计算
  - 适配「文字控件本身不可点击，需上溯到可点击祖先」这类常见坑

调用方式（发指令）：
  1) 单条指令（子命令）
     python device_control.py status
     python device_control.py launch --package com.ninebot.segway
     python device_control.py tap --text "闪灯鸣笛"
     python device_control.py tap --text "闪灯鸣笛" --up 1
     python device_control.py tap --xpath '//*[@text="闪灯鸣笛"]/..'
     python device_control.py screenshot --out shot.png
     python device_control.py dump --out ui.xml
     python device_control.py texts
     python device_control.py wait --text "自动锁车设置" --timeout 8
     python device_control.py retry --id "com.ninebot.segway:id/switch_view" --expect "checked:false" --max 5 --settle 30
     python device_control.py get_device_info          # 设备信息页：型号/车架号/各固件版本
     python device_control.py get_battery_info         # 电池信息页：主电池/电压/温度/应急电池
     python device_control.py ble_upgrade_app --wait-task 30   # APP侧蓝牙升级刷写(需平台先下发且车辆蓝牙连手机)
     python device_control.py go_to_page --page battery   # 页面导航：home/more_functions/device_info/battery/safety/throttle/lab/fota_page
     python device_control.py power_on   # 滑动开机：adb input swipe 把「滑动开机」滑块滑过去(→「开机中」)，真正通电需按整车电源按钮
     python device_control.py power_off  # 点击关机：点击「点击关机」红色按钮，回到「滑动开机」关机态

  2) 批量指令（JSON 列表，每条为 [命令, {选项}]）
     python device_control.py run --json '[["status",{}],["tap",{"text":"闪灯鸣笛"}],["screenshot",{"out":"x.png"}]]'

可选：--serial 指定设备序列号；不传则连第一个设备。

  设计理念：脚本保持「通用指令集」，AI 只发指令、组合指令来驱动，不每次写新脚本。
  - 单步：tap / status / screenshot / dump / texts / launch
  - 组合：run --json '[["status",{}],["tap",{"text":"x"}],...]'
  - 导航：go_to_page / get_device_info / get_battery_info —— 统一页面树(PAGE_TREE)管理"去哪个页面"
  - 蓝牙升级：ble_upgrade_app —— APP侧固件刷写(配合 ninebot_ota.py 的 ble-upgrade 平台下发)
  - 重试：retry —— 针对 APP 超时太短导致的「假失败」：反复下发同一操作，
          直到 APP 在超时(settle, 默认12s)内达到期望状态(如开关 checked:false)，最多 max 次，最后统计结果。
"""

import argparse
import json
import sys
import time
import subprocess
import shutil
import re
import xml.etree.ElementTree as ET

try:
    import uiautomator2 as u2
except ImportError:
    print("ERROR: uiautomator2 未安装，请先执行:\n"
          "  pip install uiautomator2\n"
          "  python -m uiautomator2 init")
    sys.exit(2)


# 默认设备序列号（留空则连接第一个设备）。可改成你的设备号。
DEFAULT_SERIAL = "A2TBVB2C27014459"


# --------------------------------------------------------------------------- #
# 设备连接
# --------------------------------------------------------------------------- #
def get_device(serial=None):
    serial = serial or DEFAULT_SERIAL
    d = u2.connect(serial) if serial else u2.connect()
    d.info  # 触发一次真正连接
    return d


# --------------------------------------------------------------------------- #
# 相对定位核心
# --------------------------------------------------------------------------- #
def _xpath_attr(attr, value):
    """生成 xpath 属性选择，自动处理引号嵌套。"""
    if not isinstance(value, str):
        value = str(value)
    if '"' in value and "'" in value:
        # 同时包含单双引号：用 concat 拼接
        parts = value.split('"')
        expr = '"""'.join(f'"{p}"' for p in parts)
        return f'//*[@{attr}=concat({expr})]'
    if '"' in value:
        return f"//*[@{attr}='{value}']"
    return f'//*[@{attr}="{value}"]'


def _build_anchor_xpath(opts):
    """把用户选项转成 xpath 锚点表达式。"""
    if opts.get("xpath"):
        return opts["xpath"]
    if opts.get("text"):
        return _xpath_attr("text", opts["text"])
    if opts.get("desc"):
        return _xpath_attr("content-desc", opts["desc"])
    if opts.get("id"):
        return _xpath_attr("resource-id", opts["id"])
    return None


def click_target(d, xpath):
    """定位并点击一个 xpath 目标；返回 (ok, message)。"""
    ele = d.xpath(xpath)
    if not ele.exists:
        return False, "target element not found"
    ele.click()
    return True, "clicked"


# --------------------------------------------------------------------------- #
# 指令处理器：每个接收 (d, opts) 返回可 JSON 序列化的结果
# --------------------------------------------------------------------------- #
def do_status(d, opts):
    info = d.info
    cur = d.app_current()
    return {
        "connected": True,
        "serial": d.serial,
        "screen_on": info.get("screenOn"),
        "current_app": cur,
    }


def do_launch(d, opts):
    pkg = opts["package"]
    before = d.app_current().get("package")
    was_foreground = (before == pkg)
    d.app_start(pkg, wait=True, stop=False)  # stop=False：不杀进程，已运行则直接调前台
    time.sleep(1.5)
    d.screen_on()
    after = d.app_current().get("package")
    return {
        "action": "already_foreground" if was_foreground else "app_start",
        "package": pkg,
        "current": after,
        "success": after == pkg,
    }


def do_tap(d, opts):
    anchor = _build_anchor_xpath(opts)
    if not anchor:
        return {"ok": False, "message": "no selector given", "target": None}

    up = opts.get("up")
    if up is not None:
        # 显式相对定位：点第 N 层祖先（0=自身）
        target = anchor if up == 0 else f"{anchor}/ancestor::*[{up}]"
        strategy = f"up={up}"
    else:
        # 自动模式：自身可点或上溯最近可点击祖先
        target = f'{anchor}/ancestor-or-self::*[@clickable="true"][1]'
        strategy = "nearest clickable ancestor-or-self"

    ok, msg = click_target(d, target)
    return {"ok": ok, "message": f"{msg} ({strategy})", "target": anchor}


def do_tap_xy(d, opts):
    """按设备像素坐标点击（图像兜底用）。x/y 为设备像素，与 `adb input tap` 同坐标系。
    典型场景：uiautomator dump 抓不到的 canvas/SVGA/游戏化/自定义绘制控件，
    由图像理解（截图→识别元素像素位置）给出坐标后调用本命令落点。"""
    try:
        x = float(opts["x"])
        y = float(opts["y"])
    except (KeyError, TypeError, ValueError):
        return {"ok": False, "message": "x/y 必填且为数字(设备像素)", "target": None}
    d.click(int(x), int(y))
    return {"ok": True, "message": f"clicked at ({int(x)},{int(y)})", "target": (int(x), int(y))}


def do_screenshot(d, opts):
    path = opts.get("out") or "screenshot.png"
    d.screenshot(path)
    return {"saved": path}


def do_dump(d, opts):
    path = opts.get("out") or "ui_dump.xml"
    xml = d.dump_hierarchy()
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml)
    return {"dumped": path}


def do_texts(d, opts):
    out = []
    for e in d(className="android.widget.TextView"):
        t = e.info.get("text", "")
        if t:
            out.append(t)
    return {"texts": out}


# --------------------------------------------------------------------------- #
# 通用重试指令（retry）：针对 APP 短超时导致的「假失败」
#   反复下发同一操作，直到 APP 在超时(settle)内达到期望状态，最多 max 次，统计结果
# --------------------------------------------------------------------------- #
def _resolve_check_xpath(opts, tap_xpath):
    """解析「校验元素」的 xpath。
    未显式指定时，默认=被点元素本身（点开关就校验开关；点普通控件可用 --check-* 另指）。
    """
    if opts.get("check_xpath"):
        return opts["check_xpath"]
    if opts.get("check_id"):
        return _xpath_attr("resource-id", opts["check_id"])
    if opts.get("check_text"):
        return _xpath_attr("text", opts["check_text"])
    if opts.get("check_desc"):
        return _xpath_attr("content-desc", opts["check_desc"])
    return tap_xpath


def _wait_until_exists(d, xpath, timeout):
    """轮询等待元素出现（APP 点完会进『正在设置...』隐藏开关，需等其重现）。"""
    steps = max(1, int(timeout / 0.5))
    for _ in range(steps):
        if d.xpath(xpath).exists:
            return True
        time.sleep(0.5)
    return d.xpath(xpath).exists


def _eval_expect(d, check_xpath, expect):
    """校验元素是否达到期望状态。返回 (ok, 描述)。"""
    ele = d.xpath(check_xpath)
    if expect.startswith("checked:"):
        want = expect.split(":", 1)[1].lower() in ("true", "1", "yes")
        if not ele.exists:
            return False, "check-element-gone"
        got = bool(ele.info.get("checked"))
        return (got == want), f"checked={got}"
    if expect == "exists":
        return ele.exists, ("exists" if ele.exists else "gone")
    if expect == "gone":
        return (not ele.exists), ("gone" if not ele.exists else "exists")
    if expect.startswith("text:"):
        want = expect.split(":", 1)[1]
        if not ele.exists:
            return False, "gone"
        return (ele.info.get("text") == want), f"text={ele.info.get('text')}"
    return False, f"unknown-expect:{expect}"


def do_retry(d, opts):
    anchor = _build_anchor_xpath(opts)
    if not anchor:
        return {"ok": False, "message": "no tap selector (text/desc/id/xpath)"}

    up = opts.get("up")
    if up == 0:
        tap_xpath = anchor
    elif up:
        tap_xpath = f"{anchor}/ancestor::*[{up}]"
    else:
        tap_xpath = f'{anchor}/ancestor-or-self::*[@clickable="true"][1]'

    check_xpath = _resolve_check_xpath(opts, tap_xpath)
    expect = opts.get("expect") or "exists"
    maxn = int(opts.get("max") or 5)
    settle = float(opts.get("settle") or 12)

    history = []
    final_ok = False
    final_state = None

    for i in range(1, maxn + 1):
        # 先等目标元素重现（APP 点完会进『正在设置...』把开关临时移除，需等其回来再操作）
        if not _wait_until_exists(d, tap_xpath, settle):
            history.append({"attempt": i, "action": "wait", "state": "tap-target-gone",
                            "ok": False, "error": "tap target 在超时内未重现"})
            continue
        # 已满足期望则直接成功（避免重复操作）
        ok, st = _eval_expect(d, check_xpath, expect)
        if ok:
            final_ok, final_state = True, st
            history.append({"attempt": i, "action": "pre-check", "state": st, "ok": True})
            break
        # 下发操作
        d.xpath(tap_xpath).click()
        # 在 settle 时长内持续轮询期望状态（覆盖长过渡，避免在『正在设置...』途中误重Tap）
        deadline = time.time() + settle
        ok, st = False, None
        while time.time() < deadline:
            ok, st = _eval_expect(d, check_xpath, expect)
            if ok:
                break
            time.sleep(0.5)
        history.append({"attempt": i, "action": "tap", "state": st, "ok": ok})
        if ok:
            final_ok, final_state = True, st
            break

    return {
        "ok": final_ok,
        "expect": expect,
        "attempts": len(history),
        "max_retries": maxn,
        "final_state": final_state,
        "summary": "success" if final_ok else f"failed after {maxn} retries",
        "history": history,
    }


def do_wait(d, opts):
    """等待某元素出现(--gone 时等待消失)，用于组合指令里的页面跳转同步。"""
    anchor = _build_anchor_xpath(opts)
    if not anchor:
        return {"ok": False, "message": "no selector"}
    timeout = float(opts.get("timeout") or 10)
    steps = max(1, int(timeout / 0.5))
    if opts.get("gone"):
        for _ in range(steps):
            if not d.xpath(anchor).exists:
                return {"ok": True, "waited": "gone"}
            time.sleep(0.5)
        return {"ok": not d.xpath(anchor).exists, "waited": "timeout"}
    ok = _wait_until_exists(d, anchor, timeout)
    return {"ok": ok, "waited": "found" if ok else "timeout"}


def do_swipe(d, opts):
    """滑动屏幕，支持方向、距离、次数控制"""
    direction = opts.get("direction", "up")
    distance = float(opts.get("distance", 0.8))  # 滑动距离占屏幕高度比例，0~1
    times = int(opts.get("times", 1))  # 滑动次数
    duration_ms = int(opts.get("duration", 500))  # 滑动时长，毫秒（CLI 语义）
    duration = duration_ms / 1000.0  # uiautomator2 的 swipe duration 单位为秒
    
    w, h = d.window_size()
    results = []
    
    for i in range(times):
        if direction == "up":
            # 从下往上滑，页面向下滚动
            start_x, start_y = w // 2, int(h * (1 - (1 - distance) / 2))
            end_x, end_y = w // 2, int(h * (1 - distance) / 2)
        elif direction == "down":
            # 从上往下滑，页面向上滚动
            start_x, start_y = w // 2, int(h * (1 - distance) / 2)
            end_x, end_y = w // 2, int(h * (1 - (1 - distance) / 2))
        elif direction == "left":
            # 从右往左滑，页面向右滚动
            start_x, start_y = int(w * (1 - (1 - distance) / 2)), h // 2
            end_x, end_y = int(w * (1 - distance) / 2), h // 2
        elif direction == "right":
            # 从左往右滑，页面向左滚动
            start_x, start_y = int(w * (1 - distance) / 2), h // 2
            end_x, end_y = int(w * (1 - (1 - distance) / 2)), h // 2
        else:
            results.append({"attempt": i+1, "ok": False, "error": f"unsupported direction: {direction}"})
            continue
        
        try:
            d.swipe(start_x, start_y, end_x, end_y, duration=duration)  # duration 已转秒
            results.append({"attempt": i+1, "ok": True, "direction": direction, "distance": distance})
            time.sleep(0.3)  # 滑动后等待页面稳定
        except Exception as e:
            results.append({"attempt": i+1, "ok": False, "error": str(e)})
    
    return {
        "success_count": sum(1 for r in results if r["ok"]),
        "total_count": times,
        "direction": direction,
        "results": results
    }


# --------------------------------------------------------------------------- #
# 滑动开机 / 点击关机（车辆电源控制）
#
# 关键坑（已实探 2026-08-05）：
#  - 首页「滑动开机」滑块是自定义 svgaView 控件，uiautomator2 的 d.touch/d.swipe
#    被它**完全忽略**（pill 红色中心死死不动）；只有系统 `adb shell input swipe`
#    通道（带真实手指类型）能驱动它。故滑动开机必须用 adb input，不能用 d.swipe。
#  - 滑动开机「滑过去」只到「开机中」过渡态；真正通电还需物理按整车电源按钮
#    （之后才显示「点击关机」）。自动化只能完成"滑过去"这一步。
#  - 关机（点击关机）则是常规可点 tile，uiautomator2 click 即可。
#  - 坐标系用屏幕比例换算（基准 1080x2400 实测）：滑块仅在该设备固定位置出现。
# --------------------------------------------------------------------------- #
def _collect_texts(d):
    """收集当前界面所有非空文字（列表）。"""
    out = []
    for e in d(className="android.widget.TextView"):
        try:
            t = e.info.get("text", "")
            if t:
                out.append(t.strip())
        except Exception:
            pass
    return out


def _power_on_coords(d):
    """滑動开机滑块坐标（屏幕比例换算）。
    返回 (start_x, start_y, end_x, end_y)：start=红色按钮(thumb)中心(最左)，
    end=拖到滑块右界之外使 thumb 被 clamp 到底。"""
    w, h = d.window_size()
    sx = int(w * 0.4343)   # 红色按钮中心(最左)，基准 469/1080
    sy = int(h * 0.4783)   # 基准 1148/2400
    ex = int(w * 0.7037)   # 超出右界，基准 760/1080
    ey = sy
    return sx, sy, ex, ey


def _power_off_point(d):
    """点击关机的红色电源按钮坐标（屏幕比例换算）。基准 dump XML 中 svgaView 视觉中心 (540,1148)。"""
    w, h = d.window_size()
    cx = int(w * 0.5)        # 540/1080
    cy = int(h * 0.4783)     # 1148/2400
    return cx, cy


def do_power_on(d, opts):
    """APP 滑动开机（车辆关机态「滑动开机」→ 过渡态「开机中」）。
    必须用 adb input swipe（uiautomator2 通道无效）。滑过去后还需物理按整车电源按钮才真正开机。"""
    # 1) 确保在首页（滑块仅在 home 关机态出现）
    nav = navigate_to(d, "home")
    time.sleep(1.5)

    texts = _collect_texts(d)
    if "点击关机" in texts:
        return {"ok": True, "state": "already_on",
                "note": "车辆已开机（显示「点击关机」），无需滑动开机"}
    if "滑动开机" not in texts:
        return {"ok": False, "state": "not_in_off_state",
                "current_texts_snippet": texts[:12],
                "note": "当前不在『滑动开机』关机态，无法滑动开机；请先确认车辆已关机且停在首页"}

    # 2) 用 adb input swipe 滑动（唯一有效通道）
    sx, sy, ex, ey = _power_on_coords(d)
    adb = shutil.which("adb") or "adb"
    cmd = [adb, "-s", d.serial, "shell", "input", "swipe",
           str(sx), str(sy), str(ex), str(ey), "1800"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
    except Exception as e:
        return {"ok": False, "error": f"adb swipe 执行失败: {e}"}
    if proc.returncode != 0:
        return {"ok": False, "error": "adb swipe 返回非零", "stderr": proc.stderr.strip()}

    # 3) 等待并核验
    time.sleep(5)
    texts2 = _collect_texts(d)
    slid = ("滑动开机" not in texts2) and (("开机中" in texts2) or ("点击关机" in texts2))
    state_after = ("开机中" if "开机中" in texts2
                   else "已经开机" if "点击关机" in texts2
                   else "滑动开机(未动)")
    return {
        "ok": slid,
        "swipe": {"from": [sx, sy], "to": [ex, ey], "duration_ms": 1800},
        "state_before": "滑动开机",
        "state_after": state_after,
        "note": "滑块已滑过去（thumb 转右）；真正通电还需物理按整车电源按钮（之后显示「点击关机」）",
    }


def do_power_off(d, opts):
    """APP 点击关机（车辆开机态「点击关机」→ 关机态「滑动开机」）。
    开机态下 svgaView 是常规可点 tile，uiautomator2 click 即可触发。"""
    nav = navigate_to(d, "home")
    time.sleep(1.5)

    texts = _collect_texts(d)
    if "滑动开机" in texts:
        return {"ok": True, "state": "already_off",
                "note": "车辆已关机（显示「滑动开机」），无需点击关机"}
    if "点击关机" not in texts:
        return {"ok": False, "state": "not_in_on_state",
                "current_texts_snippet": texts[:12],
                "note": "当前不在『点击关机』开机态，无法点击关机"}

    cx, cy = _power_off_point(d)
    d.click(cx, cy)
    time.sleep(6)
    texts2 = _collect_texts(d)
    off = "滑动开机" in texts2
    return {
        "ok": off,
        "click": [cx, cy],
        "state_before": "点击关机",
        "state_after": "滑动开机" if off else "点击关机(未生效)",
    }


# --------------------------------------------------------------------------- #
# 页面导航引擎（统一"去目标页面"）
#   核心思路：用页面树 PAGE_TREE 描述「各页面怎么标识」+「从本页能跳到哪些页」
#            → 先 detect_current_page 查当前页（若已知可跳过）
#            → 再 BFS 求「当前页 → 目标页」最短路径，逐边执行导航动作。
#   关键约定：去页面（navigate_to / go_to_page）与 在页面操作（extract_*）严格分离。
#            以后新增目标页，只需在 PAGE_TREE 加边，不用改任何业务逻辑。
# --------------------------------------------------------------------------- #
NINEBOT_PKG = "com.ninebot.segway"

PAGE_TREE = {
    # 不在九号APP内（桌面/其他APP/锁屏）。统一入口：启动APP → home
    "outside": {
        "edges": {
            "home": {"action": "launch", "package": NINEBOT_PKG},
        },
    },
    # 首页：含「更多功能」入口
    "home": {
        "edges": {
            "more_functions": {"action": "tap_text", "text": "更多功能"},
        },
    },
    # 更多功能页：含「设备信息」入口（在底部，需滚动）
    "more_functions": {
        "edges": {
            "home": {"action": "back"},
            "device_info": {"action": "scroll_tap_text", "text": "设备信息", "max_scroll": 6},
            "battery": {"action": "tap_text", "text": "电池信息与设置"},
            "throttle": {"action": "tap_text", "text": "转把设置"},
            "safety": {"action": "tap_text", "text": "安心守护"},
            "lab": {"action": "tap_text", "text": "实验室"},
        },
    },
    # 设备信息页：DynamicDeviceInfoActivity
    "device_info": {
        "edges": {
            "more_functions": {"action": "back"},
            # 底部「检查固件更新」(tv_title，无 clickable 祖先) → 固件升级页
            "fota_page": {"action": "scroll_tap_text_soft", "text": "检查固件更新", "max_scroll": 18},
        },
    },
    # 固件升级页：cn.ninebot.react.NBReactActivity
    # 平台下发的蓝牙升级(c:ota)任务在此页以「下一步/确认升级/开始升级」呈现；
    # 若车辆未蓝牙连上手机，则只显示「已经是最新固件」+「检测更新」（无任务）。
    "fota_page": {
        "edges": {
            "device_info": {"action": "back"},
        },
    },
    # 电池信息与设置页：cn.ninebot.react.NBReactActivity（与 fota 同容器，靠文字区分）
    # 数据：主电池/应急通信电池电量、电压、温度、充电上限调节、电池详情/管理
    "battery": {
        "edges": {
            "more_functions": {"action": "back"},
        },
    },
    # 安心守护页：cn.ninebot.react.NBReactActivity（电子围栏）
    "safety": {
        "edges": {
            "more_functions": {"action": "back"},
        },
    },
    # 转把设置页：cn.ninebot.device.dynamic.sub.DynamicList2Activity
    "throttle": {
        "edges": {
            "more_functions": {"action": "back"},
        },
    },
    # 实验室页：cn.ninebot.device.dynamic.sub.DynamicList2Activity（智能后仰抑制等实验功能）
    "lab": {
        "edges": {
            "more_functions": {"action": "back"},
        },
    },
}


# --------------------------------------------------------------------------- #
# 设备信息页固件模块名 <-> 平台(iot-test.ninebot.com)零部件代码 对照
# --------------------------------------------------------------------------- #
# APP 设备信息页 (DynamicDeviceInfoActivity) 显示的六大固件模块 ↔
# 平台"车辆信息"表 (iot-test.ninebot.com) 零部件代码。
# 行业命名约定 + 截图实测（Xaber 300 美洲版，2026-08-05）。
# 平台固件版本号格式：4 位 hex 编码（如 0317 / 023e / 2008），见转换函数。
# 注意：九号电摩的 T-BOX（车载通信/中控一体模块）= 中控 = ECU
APP_TO_PLATFORM = {
    "仪表控制器": "DIS",  # Display Instrumentation System
    "彩屏仪表":   "TFT",  # TFT 彩屏
    "中控":       "ECU",  # Electronic Control Unit
    "电池":       "BMS",  # Battery Management System
    "电机控制器": "MCU",  # Motor Control Unit
    "充电器":     "CHG",  # Charger
}
PLATFORM_TO_APP = {v: k for k, v in APP_TO_PLATFORM.items()}
# 英文 key (firmware_versions) → APP 模块名（用于 build platform_versions）
FIRMWARE_KEY_TO_APP = {
    "instrument_controller": "仪表控制器",
    "central_control":       "中控",
    "display":               "彩屏仪表",
    "battery":               "电池",
    "motor_controller":      "电机控制器",
    "charger":               "充电器",
}


def _format_platform_version(app_version):
    """APP 显示的版本号 vX.Y[.Z][.W] → 平台 4 位 hex 编码。

    转换规则（截图平台验证）：
    - APP 3 段 vX.Y.Z     → 平台 "0" + X + Y + Z（hex：10-15 → a-f）
    - APP 4 段 vX.Y.Z.W   → 平台 X + Y + Z + W（hex）
    - 单段必须 ≤ 15（hex 一位），否则原样返回（防御性）。

    实测用例：
        v3.1.7   → 0317    (TFT)
        v2.3.14  → 023e    (ECU)
        v2.0.0.8 → 2008    (BMS)
        v5.0.13  → 050d    (CHG)
    """
    if not app_version:
        return None
    s = app_version.lstrip("v").strip()
    if not s:
        return None
    parts = s.split(".")
    if len(parts) not in (3, 4):
        return s
    hex_digits = ""
    for p in parts:
        try:
            n = int(p)
        except ValueError:
            return s
        if n < 0 or n > 15:
            return s
        hex_digits += format(n, "x")
    return ("0" + hex_digits) if len(parts) == 3 else hex_digits


def _all_texts_list(d):
    """从完整 UI 层级 XML 提取全部可见文字（text + content-desc）。
    等价于 `adb shell uiautomator dump` 后解析，但由 uiautomator2 的 d.dump_hierarchy() 直接获取，
    比只取 TextView 类名更可靠：能拿到标题栏、自定义控件等所有文字，是页面识别/控件定位的基础。
    返回去重、保序的列表。"""
    try:
        xml = d.dump_hierarchy()
    except Exception:
        return []
    out = []
    try:
        root = ET.fromstring(xml)
        for node in root.iter():
            for attr in ("text", "content-desc"):
                v = node.get(attr) or ""
                if v.strip():
                    out.append(v.strip())
    except Exception:
        # 退化：正则抓取 text= / content-desc=
        out = re.findall(r'(?:text|content-desc)="([^"]*)"', xml or "")
        return [t.strip() for t in out if t.strip()]
    seen, res = set(), []
    for t in out:
        if t not in seen:
            seen.add(t)
            res.append(t)
    return res


def _collect_texts_list(d):
    # 统一走完整 XML 提取（uiautomator2 dump_hierarchy + 解析），页面/控件识别更稳。
    return _all_texts_list(d)


def scroll_to_text(d, text, maxn=18, direction="up"):
    """确定性滚动：反复向 direction 方向滑屏，直到 text 出现（或达 maxn 次）。
    用于「检查固件更新」这类藏在底部、且自身无 clickable 祖先的元素——
    必须先滚到它出现，再用 u2 的 d(text=...).click() 点其元素中心（仍属相对定位）。"""
    w, h = d.window_size()
    if direction == "up":
        sy, ey = int(h * 0.82), int(h * 0.18)
    else:
        sy, ey = int(h * 0.18), int(h * 0.82)
    for _ in range(maxn):
        if d(text=text).exists:
            return True
        d.swipe(w // 2, sy, w // 2, ey, duration=0.3)
        time.sleep(0.4)
    return d(text=text).exists


def _detect_nbreact(d):
    """NBReactActivity 是通用 React 容器，同时承载多个设备子页，按页面文字区分。"""
    texts = _collect_texts_list(d)
    joined = "".join(texts)
    if any(k in joined for k in ("固件升级", "检测更新", "已经是最新固件", "下一步", "确认升级", "开始升级")):
        return "fota_page"
    if any(k in joined for k in ("电池详情", "主电池", "剩余电量", "应急通信电池", "充电上限")):
        return "battery"
    if any(k in joined for k in ("安心守护", "添加电子围栏", "电子围栏")):
        return "safety"
    return "fota_page"  # 兜底（三者中最常见入口）


def _detect_list2(d):
    """DynamicList2Activity 既承载 转把设置(throttle)/实验室(lab) 两个根页，
    也承载「更多功能」的二级子页（灯光设置/音效设置/NFC和密码设置/快捷功能定义/安防设置/骑行模式设置 等，
    同样复用 DynamicList2Activity）。按文字区分根页；都不命中则判为 more_functions 子页。"""
    texts = _collect_texts_list(d)
    joined = "".join(texts)
    if "转把校准" in joined:
        return "throttle"
    if any(k in joined for k in ("实验室", "智能后仰抑制", "了解小组件")):
        return "lab"
    return "more_functions_sub"


def detect_current_page(d):
    """查询当前页面：返回页面树中的页面 id。
    取值：'outside'(不在九号APP) / 'home' / 'more_functions' / 'device_info' / 'unknown'(在前台但无法识别)。
    优先用 activity 名精确判定（各页 activity 不同且稳定）；activity 命不中时再用页面文字兜底。"""
    try:
        cur = d.app_current()
    except Exception:
        return "outside"
    pkg = cur.get("package") or ""
    act = cur.get("activity") or ""
    if NINEBOT_PKG not in pkg:
        return "outside"
    # 1) activity 精确判定（最稳）
    if "DynamicDeviceInfoActivity" in act:
        return "device_info"
    if "DynamicListActivity" in act:
        # 该 activity 同时承载「更多功能」根页与其所有二级设置子页（灯光/音效/安防/骑行模式…）。
        # 根页标题为「更多功能」且列出全部设置项；子页只显示单个设置控件。用完整 XML 文字做判别：
        #   命中标题「更多功能」 或 命中的已知设置项 >=5 个 -> 根页；否则 -> 二级子页。
        # 否则子页会被误判为根页，导致 navigate_to 不回退、点到错误控件（历史踩坑）。
        texts = _collect_texts_list(d)
        known_items = [k for k in ("安防设置", "灯光设置", "音效设置", "NFC和密码设置",
                                   "快捷功能定义", "驻车感应", "自动锁车设置", "低电量延长续航",
                                   "电子刹车", "能量回收强度", "骑行模式设置", "公英制切换",
                                   "转把设置", "安心守护", "实验室", "电池信息与设置",
                                   "设备信息", "解绑车辆") if k in texts]
        if "更多功能" in texts or len(known_items) >= 5:
            return "more_functions"
        return "more_functions_sub"  # 任意二级设置子页（非页面树节点，需先返回根页）
    if "NBReactActivity" in act:
        # 通用 React 容器：同时承载 固件升级页/电池页/安心守护页，须按文字区分
        return _detect_nbreact(d)
    if "DynamicList2Activity" in act:
        # 同时承载 转把设置/实验室，须按文字区分
        return _detect_list2(d)
    if "MainOversea" in act:
        return "home"
    # 2) 兜底：部分机型/版本 activity 命名不同，用页面文字判定
    texts = _collect_texts_list(d)
    if "车架号" in texts:
        return "device_info"
    if "设备信息" in texts:
        return "more_functions"
    if "更多功能" in texts:
        return "home"
    return "unknown"


def _exec_nav_action(d, action):
    """执行一条导航边动作。返回 (ok, message)。"""
    atype = action.get("action")
    if atype == "launch":
        do_launch(d, {"package": action["package"]})
        time.sleep(2)
        return True, "launched"
    if atype == "back":
        d.press("back")
        time.sleep(1)
        return True, "back"
    if atype == "tap_text":
        xpath = f'//*[@text="{action["text"]}"]/ancestor-or-self::*[@clickable="true"][1]'
        if not d.xpath(xpath).exists:
            return False, f"未找到可点击的 {action['text']}"
        d.xpath(xpath).click()
        time.sleep(1)
        return True, f"tapped {action['text']}"
    if atype == "scroll_tap_text":
        # 滚动到目标文字出现并点击（用于底部入口，如「设备信息」）
        text = action["text"]
        max_scroll = int(action.get("max_scroll", 6))
        w, h = d.window_size()
        xpath = f'//*[@text="{text}"]/ancestor-or-self::*[@clickable="true"][1]'
        for _ in range(max_scroll):
            if d.xpath(xpath).exists:
                d.xpath(xpath).click()
                time.sleep(1.5)
                return True, f"scrolled & tapped {text}"
            d.swipe(w // 2, int(h * 0.8), w // 2, int(h * 0.2), duration=0.5)
            time.sleep(0.5)
        return False, f"滚动 {max_scroll} 次仍未找到 {text}"
    if atype == "scroll_tap_text_soft":
        # 用于无 clickable 祖先、但可按文字点其元素中心的入口（如「检查固件更新」tv_title）。
        # 先 scroll_to_text 滚到可见，再 d(text=...).click() 点元素中心（u2 自动按当前 bounds 计算坐标）。
        text = action["text"]
        maxn = int(action.get("max_scroll", 18))
        if not scroll_to_text(d, text, maxn=maxn):
            return False, f"滚动 {maxn} 次仍未找到 {text}"
        d(text=text).click()
        time.sleep(1.5)
        return True, f"scrolled & soft-tapped {text}"
    return False, f"unknown nav action: {atype}"


def _bfs_path(start, target):
    """在 PAGE_TREE 上做 BFS，返回从 start 到 target 的页面 id 路径（含两端）；无解返回 None。"""
    if start == target:
        return [start]
    from collections import deque
    q = deque([[start]])
    seen = {start}
    while q:
        path = q.popleft()
        node = path[-1]
        for nxt in PAGE_TREE.get(node, {}).get("edges", {}):
            if nxt in seen:
                continue
            seen.add(nxt)
            new_path = path + [nxt]
            if nxt == target:
                return new_path
            q.append(new_path)
    return None


def navigate_to(d, target, max_reset=3):
    """统一导航：从当前页（未知则先查 + 兜底）走到 target 页面。
    返回 {ok, target, from, path, steps[], final_page}。"""
    # 1) 起始页判定
    start = detect_current_page(d)
    if start == "unknown":
        # 兜底：连按返回尝试回到已知页，否则重新拉起APP
        for _ in range(max_reset):
            d.press("back")
            time.sleep(1)
            start = detect_current_page(d)
            if start not in ("unknown", "outside"):
                break
        if start in ("unknown", "outside"):
            do_launch(d, {"package": NINEBOT_PKG})
            time.sleep(2)
            start = detect_current_page(d)
    elif start == "outside":
        do_launch(d, {"package": NINEBOT_PKG})
        time.sleep(2)
        start = detect_current_page(d)

    # 1.5) 当前页不在页面树中（多为某页的二级子页，如「更多功能」的灯光设置页）：
    # 先按返回回到可识别的根页，再走页面树导航。
    if start not in PAGE_TREE and start not in ("outside", "unknown"):
        d.press("back")
        time.sleep(1.2)
        start = detect_current_page(d)

    # 2) 求最短路径
    path = _bfs_path(start, target)
    if not path:
        return {"ok": False, "target": target, "from": start,
                "error": f"页面树中无路径：{start} -> {target}",
                "available_pages": list(PAGE_TREE.keys())}

    # 3) 逐边执行 + 到达校验（tap 类动作失败可重试）
    steps = []
    cur = start
    for nxt in path[1:]:
        edge = PAGE_TREE[cur]["edges"].get(nxt)
        if not edge:
            return {"ok": False, "target": target, "from": start,
                    "error": f"缺少边 {cur}->{nxt}", "path": path, "steps": steps}
        ok, msg = _exec_nav_action(d, edge)
        verified = (detect_current_page(d) == nxt)
        # tap 类动作未达预期时重试（应对点击未及时生效）
        retries = 0
        while not verified and edge.get("action") in ("tap_text", "scroll_tap_text") and retries < 2:
            time.sleep(0.6)
            ok, msg = _exec_nav_action(d, edge)
            verified = (detect_current_page(d) == nxt)
            retries += 1
        steps.append({"from": cur, "to": nxt, "ok": ok, "verified": verified, "message": msg})
        if not verified:
            return {"ok": False, "target": target, "from": start, "path": path,
                    "steps": steps, "error": f"导航到 {nxt} 校验失败（当前实际页={detect_current_page(d)}）"}
        cur = nxt
        time.sleep(0.3)

    final = detect_current_page(d)
    return {
        "ok": final == target,
        "target": target,
        "from": start,
        "path": path,
        "steps": steps,
        "final_page": final,
    }


def do_go_to_page(d, opts):
    """统一导航命令：走到指定目标页面（只负责"去"，不操作）。"""
    target = opts.get("page")
    if not target or target not in PAGE_TREE:
        return {"ok": False, "error": f"未知目标页面：{target}",
                "available_pages": list(PAGE_TREE.keys())}
    return navigate_to(d, target)


def extract_device_info(d):
    """操作层：假设已在设备信息页，完整收集并解析设备信息（型号/车架号/各固件版本）。

    注意：「固件详情」只是区块标题、不可点击（无 clickable 祖先，tap 会失败）。
    各模块固件版本直接显示在设备信息页内、该标题下方，故此处只滚动页面收集文字，绝不 tap「固件详情」。
    """
    info = {}
    w, h = d.window_size()
    # 先滚回页面顶部
    for _ in range(4):
        d.swipe(w // 2, int(h * 0.2), w // 2, int(h * 0.8), duration=0.5)
        time.sleep(0.4)
    # 向下滚动收集全部文字（合并去重）
    all_texts = []
    for _ in range(10):
        page_texts = []
        for e in d(className="android.widget.TextView"):
            t = e.info.get("text", "")
            if t:
                page_texts.append(t.strip())
        for t in page_texts:
            if t not in all_texts:
                all_texts.append(t)
        if "检查固件更新" in page_texts:  # 已滚动到页面底部
            break
        d.swipe(w // 2, int(h * 0.8), w // 2, int(h * 0.2), duration=0.5)
        time.sleep(0.5)
    texts = all_texts

    # 解析基础信息
    info["model"] = texts[0] if texts else ""
    for i in range(len(texts)):
        if ("激活" in texts[i]) and (" " in texts[i]):  # 形如 "2026.01.21 激活"
            info["activate_time"] = texts[i].split(" ")[0]
        elif texts[i] == "激活时间" and i + 1 < len(texts):
            info["activate_time"] = texts[i + 1]
        elif texts[i] == "车架号" and i + 1 < len(texts):
            info["vin"] = texts[i + 1]
        elif texts[i] == "设备序列号" and i + 1 < len(texts):
            info["sn"] = texts[i + 1]
        elif texts[i] == "车辆总里程" and i + 1 < len(texts):
            info["total_mileage"] = texts[i + 1]

    # 解析固件版本（仅当下一字段形如版本号 vX.Y.Z 才赋值）
    def _is_version(s):
        return bool(s) and s[0].lower() == "v" and any(c.isdigit() for c in s)
    firmware = {}
    for i in range(len(texts) - 1):
        if texts[i] == "仪表控制器" and _is_version(texts[i + 1]):
            firmware["instrument_controller"] = texts[i + 1]
        elif texts[i] == "中控" and _is_version(texts[i + 1]):
            firmware["central_control"] = texts[i + 1]
        elif texts[i] == "彩屏仪表" and _is_version(texts[i + 1]):
            firmware["display"] = texts[i + 1]
        elif texts[i] == "电池" and _is_version(texts[i + 1]):
            firmware["battery"] = texts[i + 1]
        elif texts[i] == "充电器" and _is_version(texts[i + 1]):
            firmware["charger"] = texts[i + 1]
        elif texts[i] == "电机控制器":
            # 电机控制器本行后无独立版本号（实际未单独显示），不强行赋值
            firmware["motor_controller"] = "未单独显示"
    info["firmware_versions"] = firmware

    # 平台 (iot-test.ninebot.com) 视角的版本：APP 模块名 → 平台代码 + 双向版本号
    # 目的：让 get_device_info 既给 APP 视角（firmware_versions），又给平台视角（platform_versions），
    #       排查固件问题时可以直接把 APP 版本号对到平台零部件代码。
    platform_versions = {}
    for fw_key, app_ver in firmware.items():
        app_name = FIRMWARE_KEY_TO_APP.get(fw_key)
        plat_code = APP_TO_PLATFORM.get(app_name) if app_name else None
        if not plat_code:
            continue
        # 电机控制器等 APP 不显示独立版本号 → 用 null 表示
        if app_ver == "未单独显示":
            platform_versions[plat_code] = {
                "app_label":   app_name,
                "app_version": None,
                "platform_tag": None,
            }
        else:
            platform_versions[plat_code] = {
                "app_label":   app_name,
                "app_version": app_ver,
                "platform_tag": _format_platform_version(app_ver),
            }
    # 电机控制器 APP 无独立版本号 → 标记 null（兜底，正常循环已处理）
    if "MCU" not in platform_versions:
        platform_versions["MCU"] = {
            "app_label":   "电机控制器",
            "app_version": None,
            "platform_tag": None,
        }
    # 按平台"零部件名称"列固定顺序输出（DIS → ECU → TFT → CHG → MCU → BMS）
    ordered = {code: platform_versions[code]
               for code in ("DIS", "ECU", "TFT", "CHG", "MCU", "BMS")
               if code in platform_versions}
    info["platform_versions"] = ordered
    info["module_map_app_to_platform"] = APP_TO_PLATFORM
    info["tbox_equivalent"] = "中控 (ECU) — 九号电摩 T-BOX 即中控模块"
    return {"info": info, "raw_texts": texts}


def do_get_device_info(d, opts):
    """九号APP专用：先统一导航到「设备信息」页，再到该页提取完整设备版本信息。
    导航与提取分离——去页面交给 navigate_to，本函数只负责到达后的操作。"""
    nav = navigate_to(d, "device_info")
    if not nav["ok"]:
        return {"ok": False, "navigation": nav, "error": "导航到设备信息页失败"}
    extracted = extract_device_info(d)
    extracted["info"]["_navigation"] = {"from": nav["from"], "path": nav["path"]}
    return {
        "ok": True,
        "device_info": extracted["info"],
        "raw_texts": extracted["raw_texts"],
    }


def extract_battery(d):
    """操作层：假设已在电池信息与设置页(NBReactActivity)，提取电池数据。
    关键字段（实测 Xaber 300 美洲版）：主电池电量%、电压、温度、应急通信电池%、充电上限调节。"""
    texts = []
    for e in d(className="android.widget.TextView"):
        try:
            t = e.info.get("text", "")
            if t:
                texts.append(t.strip())
        except Exception:
            pass
    info = {"raw_texts": texts}
    # 数值/单位/标签排列不固定（多为 [值][单位][标签]，个别为 [标签][值][单位]），
    # 故对每个标签在其邻位(±2)内找「含数字且非单位」的 token 作为数值。
    units = {"%", "V", "℃", "A", "W"}
    def _is_num(tok):
        return any(c.isdigit() for c in tok) and tok not in units
    pairs = {
        "剩余电量": "main_battery_percent",
        "电压": "voltage",
        "温度": "temperature",
        "应急通信电池": "emergency_battery_percent",
    }
    for i, tok in enumerate(texts):
        if tok in pairs and info.get(pairs[tok]) is None:
            key = pairs[tok]
            cand = None
            # 两种排列：① [值][单位][标签] → 标签前一 token 是单位，值在其前(i-2)
            #           ② [标签][值][单位] → 标签后一 token 是数字(i+1)
            if i - 1 >= 0 and texts[i - 1] in units:
                cand = texts[i - 2] if i - 2 >= 0 else None
            elif i + 1 < len(texts) and _is_num(texts[i + 1]):
                cand = texts[i + 1]
            if cand and _is_num(cand):
                info[key] = cand
    info["has_charge_limit"] = any("充电上限" in t for t in texts)
    info["has_battery_detail"] = any("电池详情" in t for t in texts)
    return info


def do_get_battery_info(d, opts):
    """九号APP专用：导航到「电池信息与设置」页并提取电池数据。"""
    nav = navigate_to(d, "battery")
    if not nav["ok"]:
        return {"ok": False, "navigation": nav, "error": "导航到电池信息页失败"}
    info = extract_battery(d)
    info["_navigation"] = {"from": nav["from"], "path": nav["path"]}
    return {"ok": True, "battery_info": info}


def do_ble_upgrade_app(d, opts):
    """九号APP侧蓝牙升级刷写（配合 ninebot_ota.py 的 ble-upgrade 平台下发）。
    参考 QDM551平台IOT升级压力_V21.py 的 fota_begin：
      设备信息页 → 点「检查固件更新」→ 固件升级页(NBReactActivity)
      → 若「下一步」出现则就绪；否则点「检测更新」再查
      → 点「下一步」→「确认升级」→「开始升级」经 BLE 把固件刷入 ECU。
    注意：平台(c:ota)下发后，APP 须收到该指令且车辆经蓝牙连上手机，升级页才会出现任务；
          否则只显示「已经是最新固件」，此时无法点击「开始升级」（环境前提未满足）。"""
    nav = navigate_to(d, "fota_page")
    if not nav["ok"]:
        return {"ok": False, "navigation": nav, "error": "导航到固件升级页失败"}

    def _page_texts():
        out = []
        for e in d(className="android.widget.TextView"):
            try:
                t = e.info.get("text", "")
                if t:
                    out.append(t)
            except Exception:
                pass
        return out

    def _task_ready():
        return (d(text="下一步").exists or d(text="确认升级").exists
                or d(text="开始升级").exists)

    # 等待平台 c:ota 任务在 APP 端浮现（参考 fota_task：先查 下一步，无则点 检测更新 再查）
    wait_task = int(opts.get("wait_task") or 25)
    deadline = time.time() + wait_task
    ready = False
    while time.time() < deadline:
        if _task_ready():
            ready = True
            break
        if d(text="检测更新").exists:
            d(text="检测更新").click()
            time.sleep(2)
        time.sleep(2)
    if not ready:
        return {
            "ok": False,
            "error": "固件升级页未出现蓝牙升级任务（APP 未收到平台 c:ota，或车辆未通过蓝牙连上手机）",
            "page_texts": _page_texts(),
        }

    # 参考脚本 fota_begin：依次点击 下一步 → 确认升级 → 开始升级（存在才点，避免误触）
    steps = []
    for btn in ("下一步", "确认升级", "开始升级"):
        if d(text=btn).exists:
            d(text=btn).click()
            time.sleep(2)
            steps.append({"btn": btn, "clicked": True})
        else:
            steps.append({"btn": btn, "clicked": False, "note": "未出现(可能已合并到上一步)"})

    return {
        "ok": True,
        "message": "已点击「开始升级」，APP 正在经 BLE 把固件刷入 ECU；可查平台 get-upgrade-history 看 status -1→0→1",
        "steps": steps,
    }


def do_setting(d, opts):
    """打开「更多功能」里任意设置项（一行直达）。navigate_to(more_functions) 后点对应文字。
    适用：安防设置/灯光设置/音效设置/NFC和密码设置/快捷功能定义/驻车感应/自动锁车设置/
    低电量延长续航/电子刹车/能量回收强度/骑行模式设置/公英制切换/转把设置/安心守护/实验室/
    电池信息与设置/设备信息 等。打开后若是二级列表页/对话框，再用 tap/retry 操作。
    """
    name = opts.get("name")
    if not name:
        return {"ok": False, "message": "缺少 --name"}
    nav = navigate_to(d, "more_functions")
    if not nav["ok"]:
        return {"ok": False, "navigation": nav}

    anchor = _xpath_attr("text", name)
    if not d.xpath(anchor).exists:
        # 列表较长，向下滚动至多 6 次尝试定位
        for _ in range(6):
            do_swipe(d, {"direction": "up", "distance": 0.8, "times": 1})
            time.sleep(0.4)
            if d.xpath(anchor).exists:
                break
    if not d.xpath(anchor).exists:
        return {"ok": False, "message": f"在「更多功能」未找到「{name}」", "page": "more_functions"}
    ok, msg = click_target(d, f'{anchor}/ancestor-or-self::*[@clickable="true"][1]')
    return {"ok": ok, "opened": name, "message": msg, "current_page": detect_current_page(d)}


# ── 确认弹窗 / 失败归因 ─────────────────────────────────────────────
# 九号 APP 的开关确认框按钮文案并不统一（确定/确认/开启/关闭/继续/我知道了…），
# 只认「确定」会导致弹窗卡住 → 脚本以为点了没反应 → 无脑重试。
CONFIRM_WORDS = ["确定", "确认", "继续", "同意", "我知道了", "知道了", "好的",
                 "是", "开启", "关闭", "OK", "Confirm", "Yes"]
CANCEL_WORDS = ["取消", "再想想", "暂不", "不了", "否", "Cancel", "No"]
# 页面出现这些字样 = APP 已明确报错/给出前置条件，重试没有意义
ERROR_HINTS = ["失败", "超时", "请稍后", "网络异常", "异常", "无法", "不支持",
               "请先", "未连接", "离线", "请重试", "错误", "关机", "未开机"]
# 过渡态：APP 已把指令发出去、正在等车辆回应。此时"重试点击"只会叠加指令，必须先定责。
PENDING_HINTS = ["正在设置", "设置中", "加载中", "请稍候", "正在处理", "同步中", "正在获取"]


def _clickable_nodes(d, limit=40):
    """解析当前层级里所有 clickable=true 节点（文字/desc/id/bounds），用于诊断。"""
    try:
        xml = d.dump_hierarchy()
    except Exception:
        return []
    out = []
    for tag in re.findall(r"<node [^>]*/?>", xml):
        if 'clickable="true"' not in tag:
            continue

        def _a(k):
            m = re.search(k + r'="([^"]*)"', tag)
            return m.group(1) if m else ""
        label = _a("text") or _a("content-desc") or _a("resource-id")
        out.append({"label": label, "bounds": _a("bounds"),
                    "enabled": _a("enabled") != "false"})
        if len(out) >= limit:
            break
    return out


def _visible_dialog(d):
    """检测当前是否存在确认弹窗。返回 {confirm_candidates, cancel_candidates} 或 None。
    判据：存在【可点击】的确认类或取消类按钮。只看页面文字会把普通文案误判成按钮。"""
    clickables = _clickable_nodes(d)
    labels = [c["label"] for c in clickables if c["label"]]
    confirms = [l for l in labels if l.strip() in CONFIRM_WORDS]
    cancels = [l for l in labels if l.strip() in CANCEL_WORDS]
    if not confirms and not cancels:
        return None
    return {"confirm_candidates": confirms, "cancel_candidates": cancels,
            "all_clickable_labels": labels[:20]}


def _try_confirm_dialog(d, confirm_text=None):
    """若存在确认弹窗则点确认按钮。返回实际点击的按钮文字，未点返回 None。"""
    words = [confirm_text] if confirm_text else CONFIRM_WORDS
    for w in words:
        if not w:
            continue
        ele = d(text=w)
        if ele.exists and ele.info.get("clickable", True):
            try:
                ele.click()
                return w
            except Exception:
                continue
    return None


def _diagnose_toggle(d, name, switch_xpath, expect, ctx):
    """开关未达期望状态时的**失败归因取证**：不重试，只采集证据并给出结论。
    返回 {reason, explain, next_action, evidence...}。"""
    diag = {"setting": name, "expect": expect, "context": ctx}
    try:
        diag["activity"] = (d.app_current() or {}).get("activity")
    except Exception as e:
        diag["activity"] = f"<err:{e}>"

    try:
        texts = _all_texts_list(d)
    except Exception:
        texts = []
    diag["page_texts"] = texts[:50]
    diag["error_hints"] = sorted({t for t in texts
                                  if any(h in t for h in ERROR_HINTS)})
    diag["pending_hints"] = sorted({t for t in texts
                                    if any(h in t for h in PENDING_HINTS)})
    dlg = _visible_dialog(d)
    diag["dialog"] = dlg

    # 开关现况（先按原 xpath，失效则重新定位）
    sw = {"exists": False}
    xp = switch_xpath
    ele = d.xpath(xp)
    if not ele.exists:
        xp = _locate_switch(d, name, scroll_tries=2) or xp
        ele = d.xpath(xp)
    if ele.exists:
        info = ele.info or {}
        sw = {"exists": True, "checked": bool(info.get("checked")),
              "enabled": info.get("enabled", True), "xpath": xp}
    diag["switch"] = sw

    # 诊断截图
    try:
        shot = f"diag_{re.sub(r'[^A-Za-z0-9一-龥]', '', name)}_{int(time.time())}.png"
        d.screenshot(shot)
        diag["screenshot"] = shot
    except Exception:
        pass

    # ── 归因（按优先级，命中即停）──
    if dlg and dlg.get("confirm_candidates"):
        diag["reason"] = "dialog_pending"
        diag["explain"] = ("弹出了确认框但未被确认（脚本没点中确认按钮）。"
                           f"页面可点确认按钮候选：{dlg['confirm_candidates']}")
        diag["next_action"] = ("用 --confirm-text \"<按钮文字>\" 指定确认按钮后重跑一次；"
                               "不要盲目重试点开关，否则会反复弹框。")
    elif dlg and dlg.get("cancel_candidates"):
        diag["reason"] = "dialog_unknown_buttons"
        diag["explain"] = ("存在弹窗（检测到取消类按钮）但确认按钮文案不在词库里。"
                           f"当前可点元素：{dlg.get('all_clickable_labels')}")
        diag["next_action"] = "从上面 all_clickable_labels 里挑出确认按钮，用 --confirm-text 指定。"
    elif diag["pending_hints"]:
        diag["reason"] = "still_pending"
        diag["explain"] = (f"APP 仍停在过渡态 {diag['pending_hints']}，说明指令已下发、"
                           "正在等待车辆回应，settle 窗口内未等到结果。"
                           "这是【设备响应慢或无响应】的典型征兆。")
        diag["next_action"] = ("禁止再点开关（会叠加重复指令）。按 §8.5.2 跑 "
                               "`ninebot_ota.py commands <IMEI> --minutes 5` 看该指令："
                               "有下发无回应=FAIL(设备侧无响应)；有下发有回应但APP仍转圈"
                               "=FAIL(APP侧未刷新)。确需重试请加大 --settle 至 40~60。")
    elif diag["error_hints"]:
        diag["reason"] = "app_error_hint"
        diag["explain"] = f"APP 已明确给出错误/前置条件提示：{diag['error_hints']}"
        diag["next_action"] = "先满足前置条件（车辆开机/在线/连接等），重试无意义。"
    elif not sw["exists"]:
        diag["reason"] = "switch_missing"
        diag["explain"] = (f"操作后「{name}」开关从页面消失，当前 activity="
                           f"{diag['activity']}，页面可能已跳转或重渲染未完成。")
        diag["next_action"] = "检查是否被推到子页；确认页面稳定后再单次重试（勿连点）。"
    elif not sw.get("enabled", True):
        diag["reason"] = "switch_disabled"
        diag["explain"] = f"「{name}」开关处于不可用(enabled=false)状态，属前置条件不满足。"
        diag["next_action"] = "检查车辆开机/在线状态，重试无意义。"
    elif ctx.get("confirmed_dialog"):
        diag["reason"] = "confirmed_but_unchanged"
        diag["explain"] = (f"确认框已点「{ctx.get('confirmed_dialog')}」，但开关仍为 "
                           f"checked={sw.get('checked')}，未变为期望值。")
        diag["next_action"] = ("按 §8.5.2 三段归因跑 "
                               "`ninebot_ota.py commands <IMEI> --watch 30` 定责："
                               "无下发=脚本 / 有下发无响应=设备无响应(FAIL-设备侧) / "
                               "有下发有响应但APP不变=APP侧缺陷(FAIL-APP侧)。")
    else:
        diag["reason"] = "state_unchanged_no_dialog"
        diag["explain"] = (f"已点击开关，无弹窗、无错误提示，但状态仍为 "
                           f"checked={sw.get('checked')}。")
        diag["next_action"] = ("按 §8.5.2 跑 `commands --watch 30` 看平台是否有下发："
                               "无下发说明点击未生效(脚本问题)，有下发说明设备/APP 侧问题。")
    return diag


def _locate_switch(d, name, scroll_tries=6):
    """导航到 more_functions 并定位 name 行内开关，返回可点击的 switch xpath；找不到返回 None。
    优先按 resource-id=com.ninebot.segway:id/switch_view 精确匹配（九号 APP 开关通用 id，class=android.widget.CompoundButton），
    并兼容 class 兜底。⚠️ uiautomator2 的 xpath 必须用谓语形式 [@resource-id=...]/[@class=...]，
    不能写 //android.widget.CompoundButton（class 当标签名在 u2 xpath 中无效，永远匹配不到）。"""
    nav = navigate_to(d, "more_functions")
    if not nav["ok"]:
        return None
    for _ in range(scroll_tries):
        for n in range(1, 6):
            xp = (f'//*[@text="{name}"]/ancestor::*[{n}]'
                  f'//*[@resource-id="com.ninebot.segway:id/switch_view"]')
            if d.xpath(xp).exists:
                return xp
        for n in range(1, 6):
            xp = (f'//*[@text="{name}"]/ancestor::*[{n}]'
                  f'//*[contains(@class,"CompoundButton") or @checkable="true"]')
            if d.xpath(xp).exists:
                return xp
        do_swipe(d, {"direction": "up", "distance": 0.8, "times": 1})
        time.sleep(0.4)
    return None


def do_toggle_setting(d, opts):
    """切换「更多功能」里某行内开关（如 驻车感应/自动驻车/低电量延长续航/电子刹车 等）。

    ⚠️ 行为准则（v1.8.0 起）：**失败不重试，先归因**。
    默认 --max 1，即只点一次；未达期望状态立即停止并输出 `diagnosis`
    （弹窗未确认 / 按钮文案不识别 / APP 报错 / 开关禁用 / 已确认但未变化 …）+ 诊断截图。
    只有在明确知道属于"过渡态未稳定"时，才用 --max >1 显式开启有限重试。

    参数：
      --name  必填，开关行文字
      --expect  默认 checked:true
      --settle  默认 20（关闭类带确认框建议 25~30）
      --max     默认 1（不重试）
      --confirm-text  指定确认框按钮文字（诊断报 dialog_pending 时按提示填）
    """
    name = opts.get("name")
    expect = opts.get("expect") or "checked:true"
    maxn = int(opts.get("max") or 1)
    settle = float(opts.get("settle") or 20)
    confirm_text = opts.get("confirm_text") or opts.get("confirm-text")
    if not name:
        return {"ok": False, "message": "缺少 --name"}

    nav = navigate_to(d, "more_functions")
    if not nav["ok"]:
        return {"ok": False, "message": "无法进入更多功能页", "navigation": nav}

    switch_xpath = _locate_switch(d, name)
    if not switch_xpath:
        return {"ok": False, "reason": "switch_not_found",
                "message": f"未找到「{name}」对应的行内开关",
                "next_action": "确认开关名称是否准确；或先用 `texts` 列出当前页所有条目。",
                "page_texts": _all_texts_list(d)[:40]}

    history = []
    final_ok, final_state, confirmed = False, None, None

    for i in range(1, maxn + 1):
        if not _wait_until_exists(d, switch_xpath, min(settle, 8)):
            switch_xpath = _locate_switch(d, name, scroll_tries=2) or switch_xpath

        ok, st = _eval_expect(d, switch_xpath, expect)
        if ok:
            final_ok, final_state = True, st
            history.append({"attempt": i, "action": "pre-check", "state": st, "ok": True})
            break

        # 点击开关（一轮只点一次）
        try:
            d.xpath(switch_xpath).click()
        except Exception as e:
            history.append({"attempt": i, "action": "tap", "state": f"click-error:{e}", "ok": False})
            break

        # settle 窗口内轮询：确认框出现即按词库/指定文案确认；容忍过渡态开关暂时消失
        deadline = time.time() + settle
        while time.time() < deadline:
            clicked = _try_confirm_dialog(d, confirm_text)
            if clicked:
                confirmed = clicked
                time.sleep(1.2)
                switch_xpath = _locate_switch(d, name, scroll_tries=2) or switch_xpath
                continue
            if d.xpath(switch_xpath).exists:
                ok2, st2 = _eval_expect(d, switch_xpath, expect)
                if ok2:
                    final_ok, final_state = True, st2
                    break
            time.sleep(0.4)

        history.append({"attempt": i, "action": "tap+settle",
                        "state": final_state if final_ok else "not-reached",
                        "ok": final_ok, "confirmed_dialog": confirmed})
        if final_ok:
            break

    result = {
        "ok": final_ok,
        "setting": name,
        "expect": expect,
        "attempts": len(history),
        "max_retries": maxn,
        "final_state": final_state,
        "confirmed_dialog": confirmed,
        "history": history,
    }
    if final_ok:
        result["summary"] = "success"
        return result

    # ── 失败：立即归因取证，不再重试 ──
    result["summary"] = "failed - see diagnosis (未重试，已转入归因)"
    result["diagnosis"] = _diagnose_toggle(
        d, name, switch_xpath, expect,
        {"attempts": len(history), "confirmed_dialog": confirmed,
         "confirm_text_arg": confirm_text})
    return result


HANDLERS = {
    "status": do_status,
    "launch": do_launch,
    "tap": do_tap,
    "tap_xy": do_tap_xy,
    "screenshot": do_screenshot,
    "dump": do_dump,
    "texts": do_texts,
    "retry": do_retry,
    "wait": do_wait,
    "swipe": do_swipe,
    "get_device_info": do_get_device_info,
    "get_battery_info": do_get_battery_info,
    "ble_upgrade_app": do_ble_upgrade_app,
    "go_to_page": do_go_to_page,
    "power_on": do_power_on,
    "power_off": do_power_off,
    "setting": do_setting,
    "toggle_setting": do_toggle_setting,
}


# --------------------------------------------------------------------------- #
# CLI 解析
# --------------------------------------------------------------------------- #
def build_parser():
    p = argparse.ArgumentParser(description="uiautomator2 设备控制（相对定位）")
    p.add_argument("--serial", help="设备序列号，默认连第一个/DEFAULT_SERIAL")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="查看连接状态与前台 APP")

    sp = sub.add_parser("launch", help="启动/调起 APP（已运行则不重启）")
    sp.add_argument("--package", required=True)

    sp = sub.add_parser("tap", help="相对定位并点击")
    sp.add_argument("--text", help="按文字定位")
    sp.add_argument("--desc", help="按 content-desc 定位")
    sp.add_argument("--id", help="按 resourceId 定位")
    sp.add_argument("--xpath", help="按 xpath 定位（最强相对关系）")
    sp.add_argument("--up", type=int, default=None,
                    help="点第 N 层祖先(0=自身)；不填则自动上溯可点击祖先")

    sp = sub.add_parser("tap_xy", help="按设备像素坐标点击（图像兜底：截图→图像理解得坐标→落点）")
    sp.add_argument("--x", required=True, help="设备像素 X（与 adb input tap 同坐标系）")
    sp.add_argument("--y", required=True, help="设备像素 Y")

    sp = sub.add_parser("screenshot", help="截图")
    sp.add_argument("--out", default="screenshot.png")

    sp = sub.add_parser("dump", help="导出 UI 层级 XML")
    sp.add_argument("--out", default="ui_dump.xml")

    sub.add_parser("texts", help="列出当前界面所有文字（发现元素用）")

    sp = sub.add_parser("run", help="批量执行 JSON 指令列表")
    sp.add_argument("--json", required=True,
                    help='指令列表，如 \'[["status",{}],["tap",{"text":"x"}]]\'')

    sp = sub.add_parser("wait", help="等待某元素出现(--gone 则等消失)，用于组合指令里的页面同步")
    sp.add_argument("--text", help="按文字等待")
    sp.add_argument("--desc", help="按 content-desc 等待")
    sp.add_argument("--id", help="按 resourceId 等待")
    sp.add_argument("--xpath", help="按 xpath 等待")
    sp.add_argument("--timeout", type=float, default=10, help="最长等待秒数（默认 10）")
    sp.add_argument("--gone", action="store_true", help="改为等待『消失』")

    sp = sub.add_parser("retry", help="重试操作直到 APP 在超时内达到期望状态（应对 APP 短超时假失败），最多 max 次并统计")
    sp.add_argument("--text", help="点按目标：按文字定位")
    sp.add_argument("--desc", help="点按目标：按 content-desc 定位")
    sp.add_argument("--id", help="点按目标：按 resourceId 定位")
    sp.add_argument("--xpath", help="点按目标：按 xpath 定位")
    sp.add_argument("--up", type=int, default=None,
                    help="点第 N 层祖先(0=自身)；不填则自动上溯可点击祖先")
    sp.add_argument("--check-text", help="校验元素：按文字（默认=被点元素内最近 CompoundButton）")
    sp.add_argument("--check-desc", help="校验元素：按 content-desc")
    sp.add_argument("--check-id", help="校验元素：按 resourceId")
    sp.add_argument("--check-xpath", help="校验元素：按 xpath")
    sp.add_argument("--expect", required=True,
                    help="期望状态: checked:true | checked:false | exists | gone | text:<值>")
    sp.add_argument("--max", type=int, default=5, help="最多重试次数（默认 5）")
    sp.add_argument("--settle", type=float, default=8,
                    help="每次操作后等待 APP 响应的秒数（默认 8，覆盖『正在设置...』时长）")

    sp = sub.add_parser("swipe", help="滑动屏幕，支持方向、距离、次数控制")
    sp.add_argument("--direction", default="up", choices=["up", "down", "left", "right"],
                    help="滑动方向：up(上滑，页面下滚)/down(下滑，页面上滚)/left(左滑，页面右滚)/right(右滑，页面左滚)，默认up")
    sp.add_argument("--distance", type=float, default=0.8,
                    help="滑动距离占屏幕高度/宽度比例，0~1，默认0.8")
    sp.add_argument("--times", type=int, default=1,
                    help="滑动次数，默认1")
    sp.add_argument("--duration", type=int, default=500,
                    help="滑动时长，毫秒，默认500")

    sub.add_parser("get_device_info", help="九号APP专用：导航到设备信息页并提取完整设备版本信息")

    sub.add_parser("get_battery_info", help="九号APP专用：导航到电池信息与设置页并提取电池数据(电量/电压/温度/应急电池)")

    sp = sub.add_parser("ble_upgrade_app", help="APP侧蓝牙升级刷写：设备信息→检查固件更新→固件升级页→下一步/确认升级/开始升级（需平台先下发且车辆蓝牙已连手机）")
    sp.add_argument("--wait-task", type=int, default=25, help="等待 APP 端蓝牙升级任务浮现的最长秒数（默认 25）")

    sp = sub.add_parser("go_to_page", help="统一导航：走到指定目标页面（只负责去，不操作），如 home/more_functions/device_info")
    sp.add_argument("--page", required=True, choices=list(PAGE_TREE.keys()),
                    help="目标页面 id（页面树中的节点）")

    sp = sub.add_parser("power_on", help="APP 滑动开机：用 adb input swipe 把首页「滑动开机」滑块滑过去(thumb转右→「开机中」)；真正通电还需物理按整车电源按钮")
    sp = sub.add_parser("power_off", help="APP 点击关机：点击首页「点击关机」红色按钮，回到「滑动开机」关机态")

    sp = sub.add_parser("setting", help="一键打开「更多功能」里任意设置项（安防设置/灯光设置/音效设置/NFC和密码设置/快捷功能定义/驻车感应/自动锁车设置/低电量延长续航/电子刹车/能量回收强度/骑行模式设置/公英制切换/转把设置/安心守护/实验室/电池信息与设置/设备信息 等）")
    sp.add_argument("--name", required=True, help="设置项名称（与 APP 中文字完全一致）")

    sp = sub.add_parser("toggle_setting", help="切换「更多功能」里某行内开关（驻车感应/自动驻车/低电量延长续航/电子刹车 等）。失败不重试，直接输出 diagnosis 归因+截图")
    sp.add_argument("--name", required=True, help="开关所在行的文字（如 驻车感应）")
    sp.add_argument("--expect", default="checked:true", help="期望状态: checked:true | checked:false（默认 checked:true）")
    sp.add_argument("--max", type=int, default=1,
                    help="尝试次数（默认 1 = 不重试）。失败会自动归因，只有确认是过渡态未稳定才调大")
    sp.add_argument("--settle", type=float, default=20, help="每次操作后等待开关重现并判定状态的秒数（默认 20，关闭类长操作请给到 30）")
    sp.add_argument("--confirm-text", dest="confirm_text", default=None,
                    help="确认框按钮文字（诊断报 dialog_pending 时按提示填，如 确定/开启/我知道了）")

    return p


def opts_from_args(args):
    """把 argparse 的子命令参数转成 opts 字典。"""
    keys = ["package", "text", "desc", "id", "xpath", "up", "out", "name",
            "check_text", "check_desc", "check_id", "check_xpath",
            "expect", "max", "settle", "timeout", "gone",
            "direction", "distance", "times", "duration", "page", "wait_task"]
    return {k: getattr(args, k, None) for k in keys if getattr(args, k, None) is not None}


def main():
    try:
        args = build_parser().parse_args()
        d = get_device(args.serial)

        if args.command == "run":
            instructions = json.loads(args.json)
            results = []
            for instr in instructions:
                if isinstance(instr, str):
                    instr = json.loads(instr)
                cmd = instr[0]
                opts = instr[1] if len(instr) > 1 else {}
                if cmd not in HANDLERS:
                    results.append({"command": cmd, "error": "unknown command"})
                    continue
                results.append({"command": cmd, "result": HANDLERS[cmd](d, opts)})
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            opts = opts_from_args(args)
            result = HANDLERS[args.command](d, opts)
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        import traceback
        print(json.dumps({
            "error": str(e),
            "traceback": traceback.format_exc()
        }, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
