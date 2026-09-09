---
description: 基于 Python uiautomation 库生成适配 pressure-test 框架的 Windows UI 自动化压力测试脚本。核心特点：(1) 通过【规划→编码→测试→修复】迭代循环实时验证；(2) 强制使用相对定位，禁止坐标定位；(3) 先读取元素判断软件当前状态，再基于当前状态执行。当 pressure-test 流程涉及 Windows 界面自动化（EPAT、uiautomation 等）时，可加载此子 skill。触发场景：(1) 用户需要为 Windows UI 自动化生成压力测试脚本；(2) pressure-test 流程中需要 uiautomation 基础类；(3) 用户说"生成 UI 自动化压力脚本"、"Windows 界面压力测试"等。
name: pressure-test-uiautomation
---

# pressure-test-uiautomation — Windows UI 自动化压力测试

基于 Python uiautomation 库，生成适配 **pressure-test 框架** 的 Windows UI 自动化基础类代码。

## 定位

本 skill 是 pressure-test 的补充子 skill，专门负责 **Layer 1 — Windows UI 自动化基础类** 的生成。填补 pressure-test 框架在 Windows 界面自动化领域的空白。

生成的类可直接嵌入到 pressure-test 脚本中，作为 `DeviceClient` 超类的一个组成部分。

## 核心工作流：规划 → 编码 → 测试 → 修复

**这是一个迭代式的关键流程，不是一次性生成脚本就结束！**

### 第0步：判断当前软件状态（必须首先执行！）

**在执行任何操作之前，必须先读取元素并判断当前状态！**

1. **第一次：获取桌面元素树（发现可用窗口）**
   - 执行 `export_ui_tree.py --root "桌面"` 获取桌面上所有窗口
   - 保存输出到临时文件
   - **目的**：发现当前桌面上有哪些窗口可用

2. **分析桌面元素树，确定目标软件窗口名称**
   - 找到目标软件的窗口名称（如："EPAT", "记事本"）

3. **第二次及以后：仅获取目标软件的元素**
   - 执行 `export_ui_tree.py --root "窗口名称"`

4. **获取窗口的空间信息（位置和大小）**
   - 使用 Python 获取窗口的 Bounds 信息

5. **分析当前软件状态，制定执行策略**
   - 基于当前状态进行操作，不要假设从固定起点开始

### 迭代循环

#### 📋 阶段1：规划（Plan）
- 读取当前元素信息
- 识别相关元素的特征（Name, ControlType, AutomationId等）
- **必须使用相对定位**，禁止使用坐标定位

#### 💻 阶段2：编码（Code）
- 编写 uiautomation 脚本
- **必须使用相对定位**（基于元素属性或层级关系）
- 添加等待时间、错误处理（try-except）
- 添加状态验证代码

#### 🧪 阶段3：测试（Test）
- 实际运行脚本
- 验证执行结果（再次读取元素树对比）

#### 🔧 阶段4：修复（Fix）
- 如果测试失败，分析元素树找出问题
- 常见问题：元素定位错误、等待时间不够、状态判断错误
- **返回阶段1，重新迭代**

## 定位策略：必须使用相对定位！

**❌ 禁止使用的定位方式：**
- 坐标定位（x, y 坐标）

**✅ 必须使用的定位方式：相对定位**
- 基于元素的**属性**进行定位（Name, AutomationId, ClassName, ControlType）
- 基于元素在**控件树中的层级关系**进行定位

## 生成类模板（适配 pressure-test 框架）

```python
import uiautomation as auto
import time

class UIAutomationClient:
    """Windows UI 自动化客户端，适配 pressure-test 框架"""

    def __init__(self, window_name, export_ui_tree_path=None):
        self.window_name = window_name
        self.window = None
        self.export_ui_tree_path = export_ui_tree_path or "D:/python学习/ui自动化/export_ui_tree.py"

    def open(self):
        """连接目标窗口"""
        try:
            self.window = auto.WindowControl(searchDepth=1, Name=self.window_name)
            if not self.window.Exists(0, 0):
                return {"statuscode": 201, "data": None, "message": f"窗口 '{self.window_name}' 不存在"}
            self.window.SwitchToThisWindow()
            time.sleep(0.5)
            return {"statuscode": 200, "data": None, "message": "窗口连接成功"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"连接窗口异常: {e}"}

    def close(self):
        """断开连接"""
        self.window = None

    def click_button(self, button_name, search_depth=8):
        """点击指定名称的按钮"""
        try:
            if not self.window:
                return {"statuscode": 404, "data": None, "message": "窗口未连接"}
            button = self.window.ButtonControl(searchDepth=search_depth, Name=button_name)
            if not button.Exists(0, 0):
                return {"statuscode": 201, "data": None, "message": f"按钮 '{button_name}' 不存在"}
            button.Click()
            time.sleep(1)
            return {"statuscode": 200, "data": None, "message": f"点击 '{button_name}' 成功"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"点击异常: {e}"}

    def set_text(self, edit_name, text, search_depth=8):
        """在指定输入框中输入文本"""
        try:
            if not self.window:
                return {"statuscode": 404, "data": None, "message": "窗口未连接"}
            edit = self.window.EditControl(searchDepth=search_depth, Name=edit_name)
            if not edit.Exists(0, 0):
                return {"statuscode": 201, "data": None, "message": f"输入框 '{edit_name}' 不存在"}
            edit.SetValue(text)
            time.sleep(0.5)
            return {"statuscode": 200, "data": None, "message": f"输入 '{edit_name}' 成功"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"输入异常: {e}"}

    def select_list_item(self, list_name, item_name, search_depth=8):
        """在列表中选择指定项"""
        try:
            if not self.window:
                return {"statuscode": 404, "data": None, "message": "窗口未连接"}
            lst = self.window.ListControl(searchDepth=search_depth, Name=list_name)
            if not lst.Exists(0, 0):
                return {"statuscode": 201, "data": None, "message": f"列表 '{list_name}' 不存在"}
            item = lst.ListItemControl(searchDepth=1, Name=item_name)
            if not item.Exists(0, 0):
                return {"statuscode": 201, "data": None, "message": f"列表项 '{item_name}' 不存在"}
            item.Click()
            time.sleep(1)
            return {"statuscode": 200, "data": None, "message": f"选择 '{item_name}' 成功"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"选择异常: {e}"}

    def check_element_exists(self, control_type, name, search_depth=8):
        """检查元素是否存在"""
        try:
            if not self.window:
                return {"statuscode": 404, "data": None, "message": "窗口未连接"}
            control = self.window.Control(searchDepth=search_depth, Name=name)
            exists = control.Exists(0, 0)
            return {"statuscode": 200, "data": {"exists": exists}, "message": "检查完成"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"检查异常: {e}"}

    # ========== 执行流程（可选） ==========

    def execute_workflow(self, steps):
        """执行完整操作流程，返回 pressure-test 框架兼容格式
        
        Args:
            steps: 操作步骤列表，每步为 {"action": "click|set_text|select", "params": {...}}
        """
        start_time = time.time()
        try:
            # 连接窗口
            open_result = self.open()
            if open_result["statuscode"] != 200:
                return open_result

            # 执行步骤
            for i, step in enumerate(steps):
                action = step.get("action")
                params = step.get("params", {})
                
                if action == "click":
                    result = self.click_button(**params)
                elif action == "set_text":
                    result = self.set_text(**params)
                elif action == "select":
                    result = self.select_list_item(**params)
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

## 嵌入到 pressure-test 脚本

```python
class DeviceClient:
    def __init__(self, config):
        self.ui = UIAutomationClient(config['window_name'])
        self.platform = PlatformClient(...)

    def open_all(self):
        self.platform.login()
        self.ui.open()
```

## 状态码映射

| UI 操作结果 | pressure-test 状态码 | 说明 |
|:---|:---|:---|
| 操作成功 | 200 (PASS) | 正常 |
| 元素不存在/操作失败 | 201 (FAIL) | 业务失败 |
| 窗口未连接 | 404 (流程异常) | 可重试 |
| 脚本异常 | 500 (脚本异常) | 脚本错误 |

## 注意事项

1. **窗口必须在最前面**：执行前必须调用 `window.SwitchToThisWindow()`
2. **必须使用相对定位**：禁止坐标定位（x, y），只用元素属性定位
3. **先判断状态**：不假设软件在固定状态，每次先读取元素判断当前状态
4. **迭代验证**：规划→编码→测试→修复，直到脚本正确执行
5. 生成的类代码可直接嵌入到 pressure-test 脚本中
6. 所有方法返回格式与 pressure-test 框架的 `run()` 一致
