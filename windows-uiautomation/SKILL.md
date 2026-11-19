---
name: windows-uiautomation
description: Windows 桌面自动化（uiautomation 库）稳定性经验。用于「脚本点 GUI 按钮/读控件状态不可靠、偶发点不动、读到的状态是旧的、每次要等 10 秒、串口被 GUI 占着脚本打不开」这类场景。Triggers: windows自动化, 桌面自动化, UIAutomation, uiautomation, UI自动化, 上位机自动化, 点按钮没反应, 控件状态读不准, ToggleState, Refind, searchTimeout, 打开串口, 关闭串口, 串口被占用, QPushButton, CheckBoxControl, SetTopmost, 点击打空, 独占串口, 上位机脚本控制.
---

# Windows 桌面自动化（uiautomation）稳定性

**一句话**：Windows GUI 自动化的失败几乎都不是"点不到"，而是**控件类型选错、读了缓存值、超时没限制、独占资源没交接**。这个 skill 是 QDM562 上位机（`NinebotPluginPlatform.exe`）串口开关反复不稳后，用实测一点点钉出来的做法。

## 何时用我

- 脚本要操作**别人写的桌面程序**（上位机 / 烧录工具 / 测试软件），出现：偶发点不动、状态读错、每步卡 10 秒、串口打不开。
- 要在 GUI 和脚本之间**交接独占资源**（串口、USB 设备、文件锁）。
- 要写"点了按钮 → 等结果 → 失败重试"的稳定流程。

## 五条铁律（每一条都是踩出来的）

1. **先 dump 控件再写代码**。别照抄"看着像"的类。
2. **`searchTimeout` 一律缩短**（1~3 s）。库默认 10 s，一次定位失败就白白卡 10 秒，看起来像"脚本卡死"。
3. **状态优先用 `ToggleState`，其次 `Refind()` + 文字包含匹配**；永远不要信"同一个控件对象第二次读到的 Name"。
4. **点击后必须"轮询状态直到变化"**，超时再点一次（最多 2 次），不要点完就往下走。
5. **独占资源要先让 GUI 松手，脚本用完还回去**；两边都要有"端口级"校验，不能只看界面文字。

## 一、先 dump，再写

```python
import uiautomation as auto

ctl = auto.Control(AutomationId="...pushButton_openOrClose")   # 用 Control 泛型先探
print(ctl.Exists(1, 0.1), ctl.ControlTypeName, ctl.ClassName, repr(ctl.Name))
try:
    print(ctl.GetTogglePattern().ToggleState)   # 0=Off 1=On
except Exception as e:
    print("无 TogglePattern:", e)
```

实测（NinebotPluginPlatform 的"打开串口"按钮）：

| 用哪个类找 | 结果 |
|---|---|
| `CheckBoxControl(**{ClassName:"QPushButton", AutomationId:...})` | ✅ exists=True，`Name='打开'`，`ControlType=CheckBoxControl`，`ClassName=QPushButton`，`ToggleState=0` |
| `ButtonControl(...)` | ❌ **Exists=False，等满 10 s 才返回** |

> **结论**：QWidget 系（Qt）大量用 `QPushButton` 实现"开关型"按钮，UIA 的 **ControlType 是 CheckBoxControl**。按类名 `QPushButton` 推断用 `ButtonControl` 是错的。

## 二、状态判定三招（按优先级）

```python
def state(win, props, timeout=2):
    for cls in ("CheckBoxControl", "ButtonControl"):
        try:
            ctl = getattr(auto, cls)(searchTimeout=timeout, **props)
            if not ctl.Exists(0.3, 0.05):
                continue
            try:
                ctl.Refind()                      # ① 破缓存
            except Exception:
                pass
            try:
                p = ctl.GetTogglePattern()
                if p is not None:
                    ts = int(p.ToggleState)       # ② 真状态
                    if ts == 1: return "on"
                    if ts == 0: return "off"
            except Exception:
                pass
            name = str(ctl.Name or "").strip()
            if "关闭" in name: return "on"        # ③ 文字兜底（按钮文字=下一步动作）
            if "打开" in name: return "off"
        except Exception:
            continue
    return None
```

要点：
- `Refind()` 是**关键**：UIA 控件包装对象会缓存属性，点完按钮立刻再读 `Name` 还是旧值 → 判断"没点上" → 再点一次 → 反而点回去了。
- 文字匹配用 `in`，不要 `==`：按钮文字可能带空格、全角、"打开串口"之类的后缀。
- 拿不到就返回 `None`，让上层重试，别硬猜。

## 三、点击要"点得动"

```python
win.SetTopmost()                  # 窗口被遮挡时点击会打空
for attempt in (1, 2):            # 最多点两次
    if state(...) != "target": break
    btn.Click()                   # 首次点击偶发丢失（窗口刚激活/焦点切换）
    if wait_state("target", 8): break
```

- 打开串口实测 **~3.0 s** 才变状态（库内部要枚举+打开），所以轮询窗口给 **8 s**；关闭只要 **~1.05 s**。
- `Click()` 走鼠标移动+点击，**要求窗口可见/未被遮挡**；远程桌面最小化、锁屏环境会失败。

## 四、独占资源交接（串口/设备）

场景：GUI 自己会开串口，但你要用 pyserial 独占它读原始流（GUI 解析不了二进制+文本混流）。

```python
# 1) 让 GUI 松手（点"关闭"），并且用"端口级"校验
def ensure_closed(...):
    for _ in range(3):
        if state(...) == "off": return True
        click(); 
        if wait_state("off", 8): return True
        if port_free(): return True          # 兜底：能 open 就是真松手了
        sleep(1.5)
    return False

def port_free(com):
    try:
        import serial; serial.Serial(com, 115200, timeout=0.1).close(); return True
    except Exception as e:
        return False        # PermissionError/"拒绝访问" = 还占着

# 2) 脚本独占
ser = serial.Serial(com, 115200, timeout=0.2)   # 失败要重来一次"让 GUI 松手"

# 3) 用完还回去（必须，否则下一轮 GUI 打不开）
ensure_opened(...)      # 同样 点两次 + 轮询 + port_free() 的**反向**校验
```

实测数据（上位机串口开关 3 轮循环）：

```
初始: off / 端口空闲
第1轮: 打开=True(3.02s) 关闭=True(1.05s) 关闭后端口可打开=True
第2轮: 打开=True(2.97s) 关闭=True(1.06s) 关闭后端口可打开=True
第3轮: 打开=True(2.98s) 关闭=True(1.06s) 关闭后端口可打开=True
成功 3/3
```

## 五、重试与日志

- **分层重试**：单步（点击/等待）2 次 → 单功能（开关串口）3 轮 → 业务层（整个查询）3 次。
- 每次失败**把判据打出来**：`按钮=打开, 端口占用=True, 已点击2次`。否则事后只有"失败了"三个字，无从下手。
- 不要 `except: pass`。GUI 自动化里 90% 的"偶发"都是被静默吞掉的异常。

## 六、排错表

| 现象 | 大概率原因 | 处理 |
|---|---|---|
| 每步固定卡 10 秒 | 控件定位失败 + 默认 `searchTimeout` | 所有控件构造都传 `searchTimeout=1~3` |
| 点了按钮，状态还是旧值 | UIA 属性缓存 | `Refind()` 后再读；或重新构造控件 |
| 第一次点击无效，第二次才成 | 窗口刚激活/焦点切换，点击打空 | `SetTopmost()` + 最多点两次 + 轮询状态 |
| `ButtonControl` 找不到但界面明明有 | ControlType 是 CheckBoxControl（Qt QPushButton） | 换 `CheckBoxControl`，或用泛型 `Control` 先 dump |
| 状态永远不匹配 | 按钮文字带空格/全角 | 用 `in` 包含匹配 |
| 脚本打不开串口（拒绝访问） | GUI 还占着 | 先点关闭 + `port_free()` 校验；或先杀/重启 GUI |
| GUI 打不开串口（脚本用过之后） | 脚本没 close 句柄 | 在 `finally` 里 `ser.close()`，再"还回"串口 |
| RDP/锁屏后全挂 | 无交互桌面 | 自动化必须在**有交互的已登录会话**里跑 |

## 七、可直接用的脚本

`scripts/uia_robust.py` —— 把上面的做法封成 5 个函数：

```python
from uia_robust import ctl_state, wait_state, click_until, port_free, dump_control

dump_control({"ClassName": "QPushButton", "AutomationId": "..."})   # 先探
s = ctl_state({"ClassName": "QPushButton", "AutomationId": "..."})  # 'on'/'off'/None
click_until(win, props, "on")                                       # 点两次+轮询
port_free("COM246")                                                 # 端口是否已释放
```

## 八、边界

- 只适用于 **Windows + 有交互桌面**；服务/无桌面会话（Session 0）里 UIA 不可用。
- 目标程序若用自绘控件（无 UIA 树），这条路走不通，只能图像识别或改用其命令行/协议接口。
- 版本升级后控件树会变（AutomationId/Name 都可能改）→ 升级 GUI 后**先重新 dump** 再改选择器。
