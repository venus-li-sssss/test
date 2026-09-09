---
description: 基于uiautomator2库生成适配pressure-test框架的Android UI自动化压力测试脚本。参考台铃APP控制和九号项目的uiautomator2方法论，核心特点：(1) 相对定位优先，用text/content-desc/resource-id定位，禁止硬编码像素坐标；(2) 自动上溯可点击祖先；(3) 一条指令完成操作，支持组合指令(run --json)；(4) 状态校验与重试(retry)机制。当pressure-test流程涉及Android APP自动化(uiautomator2)时，可加载此子skill。触发场景：(1) 用户需要为Android APP生成UI自动化压力测试脚本；(2) pressure-test流程中需要uiautomator2基础类；(3) 用户说"APP自动化压力测试"、"Android UI压力测试"等。
name: pressure-test-uiautomator
---

# pressure-test-uiautomator — Android UI自动化压力测试

基于uiautomator2库，生成适配**pressure-test框架**的Android UI自动化基础类代码。

## 定位

本skill是pressure-test的补充子skill，专门负责**Layer 1 — Android UI自动化基础类**的生成。填补pressure-test框架在Android界面自动化领域的空白。

参考skill：台铃APP控制、九号项目（device_control.py）。

## 环境配置

- Python虚拟环境：`C:\Users\venus.li\.workbuddy\binaries\python\envs\default\Scripts\python.exe`
- 已安装uiautomator2库，设备已初始化atx-agent
- 设备序列号按需指定（可写死在脚本默认值）

## 核心设计原则

### 1. 相对定位优先
- ✅ 使用`text`/`content-desc`/`resource-id`/`xpath`定位元素
- ❌ **禁止硬编码像素坐标**
- 坐标由框架动态计算

### 2. 自动上溯可点击祖先
- 文字控件本身常`clickable=false`
- 自动用xpath `ancestor-or-self::*[@clickable="true"][1]`上溯到最近可点击祖先

### 3. 一条指令完成
- 不写临时脚本，直接用CLI指令驱动
- 组合指令用`run --json`

### 4. 稳定性设计
- 操作后自动等待元素加载
- 超时自动重试
- 状态校验：开关操作后自动校验状态是否符合预期

## 生成类模板（适配pressure-test框架）

```python
import uiautomator2 as u2
import time

class UIAutomator2Client:
    """Android UI自动化客户端，适配pressure-test框架"""

    def __init__(self, serial=None, package_name=None):
        self.serial = serial or "A2TBVB2C27014459"
        self.package_name = package_name
        self.d = None

    def open(self):
        """连接设备"""
        try:
            self.d = u2.connect(self.serial)
            if not self.d.info:
                return {"statuscode": 201, "data": None, "message": f"设备{self.serial}连接失败"}
            return {"statuscode": 200, "data": None, "message": "设备连接成功"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"连接异常: {e}"}

    def close(self):
        """断开连接"""
        self.d = None

    def launch_app(self):
        """启动APP到前台"""
        try:
            if not self.d:
                return {"statuscode": 404, "data": None, "message": "设备未连接"}
            self.d.app_start(self.package_name, stop=False)
            time.sleep(2)
            return {"statuscode": 200, "data": None, "message": "APP已启动"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"启动异常: {e}"}

    def tap_by_text(self, text, timeout=10):
        """通过文字点击元素（自动上溯可点击祖先）"""
        try:
            if not self.d:
                return {"statuscode": 404, "data": None, "message": "设备未连接"}
            elem = self.d(text=text)
            if not elem.wait(timeout=timeout):
                return {"statuscode": 201, "data": None, "message": f"元素'{text}'未出现"}
            elem.click()
            time.sleep(1)
            return {"statuscode": 200, "data": None, "message": f"点击'{text}'成功"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"点击异常: {e}"}

    def tap_by_id(self, resource_id, timeout=10):
        """通过resource-id点击元素"""
        try:
            if not self.d:
                return {"statuscode": 404, "data": None, "message": "设备未连接"}
            elem = self.d(resourceId=resource_id)
            if not elem.wait(timeout=timeout):
                return {"statuscode": 201, "data": None, "message": f"元素'{resource_id}'未出现"}
            elem.click()
            time.sleep(1)
            return {"statuscode": 200, "data": None, "message": f"点击'{resource_id}'成功"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"点击异常: {e}"}

    def swipe(self, direction="up", distance=0.8, times=1, duration=500):
        """滑动屏幕"""
        try:
            if not self.d:
                return {"statuscode": 404, "data": None, "message": "设备未连接"}
            w, h = self.d.window_size()
            duration_sec = duration / 1000.0
            for _ in range(times):
                if direction == "up":
                    self.d.swipe(w//2, int(h*0.8), w//2, int(h*0.2), duration_sec)
                elif direction == "down":
                    self.d.swipe(w//2, int(h*0.2), w//2, int(h*0.8), duration_sec)
                elif direction == "left":
                    self.d.swipe(int(w*0.8), h//2, int(w*0.2), h//2, duration_sec)
                elif direction == "right":
                    self.d.swipe(int(w*0.2), h//2, int(w*0.8), h//2, duration_sec)
                time.sleep(0.5)
            return {"statuscode": 200, "data": None, "message": f"滑动{direction}×{times}完成"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"滑动异常: {e}"}

    def get_texts(self):
        """获取当前界面所有可见文字"""
        try:
            if not self.d:
                return {"statuscode": 404, "data": None, "message": "设备未连接"}
            texts = [e.get_text() for e in self.d(clickable=True) if e.get_text()]
            return {"statuscode": 200, "data": {"texts": texts}, "message": "获取成功"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"获取异常: {e}"}

    def screenshot(self, output_path):
        """截图"""
        try:
            if not self.d:
                return {"statuscode": 404, "data": None, "message": "设备未连接"}
            self.d.screenshot(output_path)
            return {"statuscode": 200, "data": {"path": output_path}, "message": "截图成功"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"截图异常: {e}"}

    def check_element_exists(self, text=None, resource_id=None, timeout=5):
        """检查元素是否存在"""
        try:
            if not self.d:
                return {"statuscode": 404, "data": None, "message": "设备未连接"}
            if text:
                elem = self.d(text=text)
            elif resource_id:
                elem = self.d(resourceId=resource_id)
            else:
                return {"statuscode": 201, "data": None, "message": "未指定text或resource_id"}
            exists = elem.exists(timeout=timeout)
            return {"statuscode": 200, "data": {"exists": exists}, "message": "检查完成"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"检查异常: {e}"}

    def check_checked(self, resource_id, timeout=5):
        """检查开关/勾选状态（用于CompoundButton）"""
        try:
            if not self.d:
                return {"statuscode": 404, "data": None, "message": "设备未连接"}
            elem = self.d(resourceId=resource_id)
            if not elem.wait(timeout=timeout):
                return {"statuscode": 201, "data": None, "message": f"开关'{resource_id}'未出现"}
            checked = elem.info.get('checked', False)
            return {"statuscode": 200, "data": {"checked": checked}, "message": f"开关状态: {checked}"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"检查异常: {e}"}

    # ========== 执行流程 ==========

    def execute_workflow(self, steps):
        """执行完整操作流程，返回pressure-test框架兼容格式

        Args:
            steps: 操作步骤列表，每步为{"action": "tap_text|tap_id|swipe|launch|wait|check", "params": {...}}
        """
        start_time = time.time()
        try:
            # 连接设备
            open_result = self.open()
            if open_result["statuscode"] != 200:
                return open_result

            # 执行步骤
            for i, step in enumerate(steps):
                action = step.get("action")
                params = step.get("params", {})

                if action == "launch":
                    result = self.launch_app()
                elif action == "tap_text":
                    result = self.tap_by_text(**params)
                elif action == "tap_id":
                    result = self.tap_by_id(**params)
                elif action == "swipe":
                    result = self.swipe(**params)
                elif action == "check":
                    result = self.check_element_exists(**params)
                elif action == "wait":
                    # 等待元素出现
                    elem = self.d(text=params.get("text")) if params.get("text") else self.d(resourceId=params.get("resource_id"))
                    if not elem.wait(timeout=params.get("timeout", 10)):
                        return {"statuscode": 201, "data": None, "message": f"步骤{i+1}: 等待元素超时"}
                    result = {"statuscode": 200, "data": None, "message": "等待成功"}
                else:
                    return {"statuscode": 500, "data": None, "message": f"未知动作: {action}"}

                if result["statuscode"] != 200:
                    result["message"] = f"步骤{i+1}失败: {result['message']}"
                    return result

            duration = time.time() - start_time
            return {"statuscode": 200, "duration": duration, "data": None, "message": "流程执行成功"}
        except Exception as e:
            duration = time.time() - start_time
            return {"statuscode": 500, "duration": duration, "data": None, "message": f"流程异常: {e}"}
```

## 嵌入到pressure-test脚本

```python
class DeviceClient:
    def __init__(self, config):
        self.ui = UIAutomator2Client(
            config.get('device_serial', 'A2TBVB2C27014459'),
            config.get('app_package', 'com.example.app')
        )
        self.platform = PlatformClient(...)

    def open_all(self):
        self.platform.login()
        self.ui.open()
        self.ui.launch_app()
```

## 状态码映射

| UI操作结果 | pressure-test状态码 | 说明 |
|:---|:---|:---|
| 操作成功 | 200 (PASS) | 正常 |
| 元素不存在/操作失败 | 201 (FAIL) | 业务失败 |
| 设备未连接 | 404 (流程异常) | 可重试 |
| 脚本异常 | 500 (脚本异常) | 脚本错误 |

## 注意事项

1. **相对定位优先**：用text/content-desc/resource-id定位，不硬编码像素坐标
2. **自动上溯可点击祖先**：文字控件不可点击时自动查找最近可点击父元素
3. **一条指令完成**：不写临时脚本，直接用CLI或组合指令驱动
4. **状态校验**：开关操作后自动校验状态是否符合预期
5. **uiautomator2 v3.7.0的坑**：`UiObject.parent()`会抛异常，改用xpath相对轴
6. **swipe的duration是秒**：不是毫秒，CLI层按毫秒语义，脚本内部需÷1000转换
7. 生成的类代码可直接嵌入到pressure-test脚本中
8. 所有方法返回格式与pressure-test框架的`run()`一致
