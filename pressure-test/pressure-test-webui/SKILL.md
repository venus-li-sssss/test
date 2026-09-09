---
description: 基于 Selenium WebDriver/Playwright 生成适配 pressure-test 框架的 Web UI 自动化压力测试脚本。核心特点：(1) 智能等待策略（显式等待优先，隐式等待兜底）；(2) 多定位策略（CSS/XPath/text/ID），禁止硬编码像素坐标；(3) 页面状态校验（URL/元素可见性/文本内容）；(4) 截图取证与多标签页管理。当 pressure-test 流程涉及 Web 界面自动化时，可加载此子 skill。触发场景：(1) 用户需要为 Web 应用生成 UI 自动化压力测试脚本；(2) pressure-test 流程中需要 Web UI 基础类；(3) 用户说"web 自动化压力测试"、"网页压力测试"等。
name: pressure-test-webui
---

# pressure-test-webui — Web UI 自动化压力测试

基于 Selenium WebDriver / Playwright，生成适配 **pressure-test 框架** 的 Web UI 自动化基础类代码。

## 定位

本 skill 是 pressure-test 的补充子 skill，专门负责 **Layer 1 — Web UI 自动化基础类** 的生成。填补 pressure-test 框架在 Web 界面自动化领域的空白。

参考经验：uiautomation-script-generator（Windows UI 规划→编码→测试→修复迭代）、pressure-test-uiautomator（Android UI 相对定位、retry 机制）。

## 技术选型

| 方案 | 适用场景 | 优势 | 劣势 |
|:---|:---|:---|:---|
| **Selenium WebDriver** | 通用 Web 自动化，兼容性好 | 生态成熟，多浏览器支持，中文文档丰富 | 需要 WebDriver 驱动，速度较慢 |
| **Playwright** | 现代 Web 应用，需要高速执行 | 自带浏览器，自动等待，速度快，支持录屏 | 相对较新，部分老旧浏览器不支持 |

**默认推荐 Playwright**（速度更快，自带等待机制，适合压力测试场景），但保留 Selenium 模板供兼容性需求。

## 核心工作流：探索 → 规划 → 编码 → 测试 → 修复

### 第0步：页面探索（必须先执行！）

**在执行任何操作之前，必须先了解目标页面结构！**

1. **打开目标页面**，等待加载完成
2. **获取页面基本信息**：URL、标题、关键元素可见性
3. **截图保存**（用于后续对比验证）
4. **提取关键元素选择器**：按钮、输入框、链接、表格等

### 迭代循环

#### 📋 阶段1：规划（Plan）
- 分析页面结构，确定目标元素
- 选择最佳定位策略（优先级：CSS > XPath > text > ID）
- **禁止使用绝对坐标定位**

#### 💻 阶段2：编码（Code）
- 编写 Web UI 自动化脚本
- 添加显式等待（WebDriverWait / page.wait_for_selector）
- 添加错误处理（try-except）
- 添加状态验证代码

#### 🧪 阶段3：测试（Test）
- 实际运行脚本
- 验证执行结果（截图对比、元素状态检查）

#### 🔧 阶段4：修复（Fix）
- 如果测试失败，分析失败截图和日志
- 常见问题：选择器失效、等待超时、页面跳转未处理
- **返回阶段1，重新迭代**

## 定位策略：禁止坐标定位！

**❌ 禁止使用的定位方式：**
- 硬编码像素坐标（x, y）
- 基于绝对位置的点击

**✅ 必须使用的定位方式（按优先级）：**

| 策略 | Selenium 示例 | Playwright 示例 | 适用场景 |
|:---|:---|:---|:---|
| CSS 选择器 | `driver.find_element(By.CSS_SELECTOR, ".btn")` | `page.locator(".btn")` | 首选，精确高效 |
| XPath | `driver.find_element(By.XPATH, "//button")` | `page.locator("xpath=//button")` | 复杂层级关系 |
| 文本内容 | `driver.find_element(By.LINK_TEXT, "登录")` | `page.get_by_text("登录")` | 按钮/链接文字 |
| ID | `driver.find_element(By.ID, "submit")` | `page.locator("#submit")` | 唯一标识 |
| Name | `driver.find_element(By.NAME, "username")` | `page.locator("[name='username']")` | 表单元素 |
| 角色 | `-` | `page.get_by_role("button", name="提交")` | 无障碍属性 |

## 等待策略（压力测试关键！）

压力测试中，页面加载速度是重要的测试指标，但过度的等待会减慢测试速度。采用**分层等待策略**：

### 1. 显式等待（优先）
等待特定条件满足，条件满足后立即继续：
```python
# Selenium
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
wait = WebDriverWait(driver, 10)
element = wait.until(EC.presence_of_element_located((By.ID, "result")))

# Playwright
page.wait_for_selector("#result", state="visible", timeout=10000)
```

### 2. 隐式等待（兜底）
全局设置元素查找超时：
```python
# Selenium
driver.implicitly_wait(5)

# Playwright
page.set_default_timeout(5000)
```

### 3. 固定等待（谨慎使用）
仅用于以下场景：
- 页面跳转后的渲染缓冲（0.5-1秒）
- 动画完成等待
- 异步数据加载完成后的小缓冲

## 生成类模板（Playwright 版，适配 pressure-test 框架）

```python
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import time
import os

class WebUIClient:
    """Web UI 自动化客户端，适配 pressure-test 框架"""

    def __init__(self, config=None):
        self.config = config or {}
        self.base_url = self.config.get("base_url", "")
        self.browser_type = self.config.get("browser", "chromium")  # chromium/firefox/webkit
        self.headless = self.config.get("headless", False)
        self.screenshot_dir = self.config.get("screenshot_dir", "./screenshots")
        self.timeout = self.config.get("timeout", 10000)  # 毫秒
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def open(self):
        """启动浏览器并打开目标页面"""
        try:
            self.playwright = sync_playwright().start()
            browser_launcher = getattr(self.playwright, self.browser_type)
            self.browser = browser_launcher.launch(headless=self.headless)
            self.context = self.browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN"
            )
            self.page = self.context.new_page()
            self.page.set_default_timeout(self.timeout)
            if self.base_url:
                self.page.goto(self.base_url, wait_until="domcontentloaded")
            if not os.path.exists(self.screenshot_dir):
                os.makedirs(self.screenshot_dir)
            return {"statuscode": 200, "data": {"url": self.page.url}, "message": "浏览器启动成功"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"启动异常: {e}"}

    def close(self):
        """关闭浏览器"""
        try:
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            self.page = None
            self.browser = None
            self.playwright = None
        except Exception:
            pass

    def navigate(self, url):
        """导航到指定 URL"""
        try:
            if not self.page:
                return {"statuscode": 404, "data": None, "message": "浏览器未启动"}
            self.page.goto(url, wait_until="domcontentloaded")
            return {"statuscode": 200, "data": {"url": self.page.url}, "message": "导航成功"}
        except PlaywrightTimeout:
            return {"statuscode": 201, "data": None, "message": f"导航超时: {url}"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"导航异常: {e}"}

    def click(self, selector, timeout=None):
        """点击元素"""
        try:
            if not self.page:
                return {"statuscode": 404, "data": None, "message": "浏览器未启动"}
            t = timeout or self.timeout
            self.page.wait_for_selector(selector, state="visible", timeout=t)
            self.page.click(selector)
            time.sleep(0.5)
            return {"statuscode": 200, "data": None, "message": f"点击 '{selector}' 成功"}
        except PlaywrightTimeout:
            return {"statuscode": 201, "data": None, "message": f"元素 '{selector}' 未出现"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"点击异常: {e}"}

    def click_text(self, text, timeout=None):
        """通过文本内容点击元素"""
        try:
            if not self.page:
                return {"statuscode": 404, "data": None, "message": "浏览器未启动"}
            t = timeout or self.timeout
            locator = self.page.get_by_text(text, exact=True)
            locator.wait_for(state="visible", timeout=t)
            locator.click()
            time.sleep(0.5)
            return {"statuscode": 200, "data": None, "message": f"点击文本 '{text}' 成功"}
        except PlaywrightTimeout:
            return {"statuscode": 201, "data": None, "message": f"文本 '{text}' 未出现"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"点击异常: {e}"}

    def fill(self, selector, text, timeout=None):
        """在输入框中输入文本"""
        try:
            if not self.page:
                return {"statuscode": 404, "data": None, "message": "浏览器未启动"}
            t = timeout or self.timeout
            self.page.wait_for_selector(selector, state="visible", timeout=t)
            self.page.fill(selector, text)
            time.sleep(0.3)
            return {"statuscode": 200, "data": None, "message": f"输入 '{selector}' 成功"}
        except PlaywrightTimeout:
            return {"statuscode": 201, "data": None, "message": f"输入框 '{selector}' 未出现"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"输入异常: {e}"}

    def select_option(self, selector, value=None, label=None, timeout=None):
        """在下拉框中选择选项"""
        try:
            if not self.page:
                return {"statuscode": 404, "data": None, "message": "浏览器未启动"}
            t = timeout or self.timeout
            self.page.wait_for_selector(selector, state="visible", timeout=t)
            if label:
                self.page.select_option(selector, label=label)
            elif value:
                self.page.select_option(selector, value=value)
            else:
                return {"statuscode": 201, "data": None, "message": "未指定 value 或 label"}
            time.sleep(0.3)
            return {"statuscode": 200, "data": None, "message": "选择成功"}
        except PlaywrightTimeout:
            return {"statuscode": 201, "data": None, "message": f"下拉框 '{selector}' 未出现"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"选择异常: {e}"}

    def check_element_exists(self, selector, timeout=None):
        """检查元素是否存在"""
        try:
            if not self.page:
                return {"statuscode": 404, "data": None, "message": "浏览器未启动"}
            t = timeout or 5000
            locator = self.page.locator(selector)
            count = locator.count()
            exists = count > 0
            return {"statuscode": 200, "data": {"exists": exists, "count": count}, "message": "检查完成"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"检查异常: {e}"}

    def get_text(self, selector, timeout=None):
        """获取元素文本内容"""
        try:
            if not self.page:
                return {"statuscode": 404, "data": None, "message": "浏览器未启动"}
            t = timeout or self.timeout
            self.page.wait_for_selector(selector, state="visible", timeout=t)
            text = self.page.locator(selector).inner_text()
            return {"statuscode": 200, "data": {"text": text}, "message": "获取成功"}
        except PlaywrightTimeout:
            return {"statuscode": 201, "data": None, "message": f"元素 '{selector}' 未出现"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"获取异常: {e}"}

    def get_texts(self, selector):
        """获取所有匹配元素的文本列表"""
        try:
            if not self.page:
                return {"statuscode": 404, "data": None, "message": "浏览器未启动"}
            locator = self.page.locator(selector)
            texts = locator.all_inner_texts()
            return {"statuscode": 200, "data": {"texts": texts, "count": len(texts)}, "message": "获取成功"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"获取异常: {e}"}

    def screenshot(self, name=None):
        """截图保存"""
        try:
            if not self.page:
                return {"statuscode": 404, "data": None, "message": "浏览器未启动"}
            filename = name or f"screenshot_{int(time.time())}.png"
            filepath = os.path.join(self.screenshot_dir, filename)
            self.page.screenshot(path=filepath, full_page=True)
            return {"statuscode": 200, "data": {"path": filepath}, "message": "截图成功"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"截图异常: {e}"}

    def wait_for_url(self, url_pattern, timeout=None):
        """等待 URL 变化到指定模式"""
        try:
            if not self.page:
                return {"statuscode": 404, "data": None, "message": "浏览器未启动"}
            t = timeout or self.timeout
            self.page.wait_for_url(url_pattern, timeout=t)
            return {"statuscode": 200, "data": {"url": self.page.url}, "message": "URL 已匹配"}
        except PlaywrightTimeout:
            return {"statuscode": 201, "data": {"url": self.page.url}, "message": "URL 等待超时"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"等待异常: {e}"}

    def get_page_info(self):
        """获取当前页面基本信息"""
        try:
            if not self.page:
                return {"statuscode": 404, "data": None, "message": "浏览器未启动"}
            info = {
                "url": self.page.url,
                "title": self.page.title(),
            }
            return {"statuscode": 200, "data": info, "message": "获取成功"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"获取异常: {e}"}

    # ========== 多标签页管理 ==========

    def new_tab(self, url=None):
        """打开新标签页"""
        try:
            if not self.context:
                return {"statuscode": 404, "data": None, "message": "浏览器未启动"}
            new_page = self.context.new_page()
            if url:
                new_page.goto(url, wait_until="domcontentloaded")
            return {"statuscode": 200, "data": {"page_count": len(self.context.pages)}, "message": "新标签页已打开"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"打开标签页异常: {e}"}

    def switch_to_tab(self, index):
        """切换到指定标签页（0-based）"""
        try:
            if not self.context:
                return {"statuscode": 404, "data": None, "message": "浏览器未启动"}
            pages = self.context.pages
            if index >= len(pages):
                return {"statuscode": 201, "data": None, "message": f"标签页索引 {index} 超出范围（共{len(pages)}个）"}
            self.page = pages[index]
            self.page.bring_to_front()
            return {"statuscode": 200, "data": {"url": self.page.url}, "message": f"已切换到标签页 {index}"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"切换异常: {e}"}

    def close_tab(self, index=None):
        """关闭指定标签页（默认关闭当前）"""
        try:
            if not self.context:
                return {"statuscode": 404, "data": None, "message": "浏览器未启动"}
            pages = self.context.pages
            if len(pages) <= 1:
                return {"statuscode": 201, "data": None, "message": "仅剩一个标签页，无法关闭"}
            if index is not None:
                pages[index].close()
            else:
                self.page.close()
                self.page = pages[0] if len(pages) > 0 else None
            return {"statuscode": 200, "data": {"page_count": len(self.context.pages)}, "message": "标签页已关闭"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"关闭异常: {e}"}

    # ========== 执行流程 ==========

    def execute_workflow(self, steps):
        """执行完整操作流程，返回 pressure-test 框架兼容格式

        Args:
            steps: 操作步骤列表，每步为 {"action": "navigate|click|click_text|fill|select|wait|check|screenshot", "params": {...}}
        """
        start_time = time.time()
        try:
            # 启动浏览器
            open_result = self.open()
            if open_result["statuscode"] != 200:
                return open_result

            # 执行步骤
            for i, step in enumerate(steps):
                action = step.get("action")
                params = step.get("params", {})

                if action == "navigate":
                    result = self.navigate(**params)
                elif action == "click":
                    result = self.click(**params)
                elif action == "click_text":
                    result = self.click_text(**params)
                elif action == "fill":
                    result = self.fill(**params)
                elif action == "select":
                    result = self.select_option(**params)
                elif action == "wait_for_url":
                    result = self.wait_for_url(**params)
                elif action == "check":
                    result = self.check_element_exists(**params)
                elif action == "screenshot":
                    result = self.screenshot(**params)
                elif action == "wait":
                    time.sleep(params.get("seconds", 1))
                    result = {"statuscode": 200, "data": None, "message": "等待完成"}
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
        finally:
            self.close()
```

## Selenium 版类模板（兼容性方案）

```python
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import os

class WebUIClientSelenium:
    """Web UI 自动化客户端（Selenium 版），适配 pressure-test 框架"""

    def __init__(self, config=None):
        self.config = config or {}
        self.base_url = self.config.get("base_url", "")
        self.browser_type = self.config.get("browser", "chrome")  # chrome/firefox/edge
        self.headless = self.config.get("headless", False)
        self.screenshot_dir = self.config.get("screenshot_dir", "./screenshots")
        self.timeout = self.config.get("timeout", 10)  # 秒
        self.driver = None
        self.wait = None

    def open(self):
        """启动浏览器"""
        try:
            if self.browser_type == "chrome":
                options = webdriver.ChromeOptions()
                if self.headless:
                    options.add_argument("--headless")
                options.add_argument("--no-sandbox")
                self.driver = webdriver.Chrome(options=options)
            elif self.browser_type == "firefox":
                options = webdriver.FirefoxOptions()
                if self.headless:
                    options.add_argument("--headless")
                self.driver = webdriver.Firefox(options=options)
            elif self.browser_type == "edge":
                options = webdriver.EdgeOptions()
                if self.headless:
                    options.add_argument("--headless")
                self.driver = webdriver.Edge(options=options)
            else:
                return {"statuscode": 201, "data": None, "message": f"不支持的浏览器: {self.browser_type}"}

            self.driver.maximize_window()
            self.driver.implicitly_wait(self.timeout)
            self.wait = WebDriverWait(self.driver, self.timeout)
            if self.base_url:
                self.driver.get(self.base_url)
            if not os.path.exists(self.screenshot_dir):
                os.makedirs(self.screenshot_dir)
            return {"statuscode": 200, "data": None, "message": "浏览器启动成功"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"启动异常: {e}"}

    def close(self):
        """关闭浏览器"""
        try:
            if self.driver:
                self.driver.quit()
                self.driver = None
        except Exception:
            pass

    def navigate(self, url):
        try:
            if not self.driver:
                return {"statuscode": 404, "data": None, "message": "浏览器未启动"}
            self.driver.get(url)
            return {"statuscode": 200, "data": {"url": self.driver.current_url}, "message": "导航成功"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"导航异常: {e}"}

    def click(self, by, value, timeout=None):
        try:
            if not self.driver:
                return {"statuscode": 404, "data": None, "message": "浏览器未启动"}
            t = timeout or self.timeout
            wait = WebDriverWait(self.driver, t)
            element = wait.until(EC.element_to_be_clickable((by, value)))
            element.click()
            time.sleep(0.5)
            return {"statuscode": 200, "data": None, "message": f"点击 '{value}' 成功"}
        except TimeoutException:
            return {"statuscode": 201, "data": None, "message": f"元素 '{value}' 不可点击"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"点击异常: {e}"}

    def fill(self, by, value, text, timeout=None):
        try:
            if not self.driver:
                return {"statuscode": 404, "data": None, "message": "浏览器未启动"}
            t = timeout or self.timeout
            wait = WebDriverWait(self.driver, t)
            element = wait.until(EC.presence_of_element_located((by, value)))
            element.clear()
            element.send_keys(text)
            time.sleep(0.3)
            return {"statuscode": 200, "data": None, "message": f"输入成功"}
        except TimeoutException:
            return {"statuscode": 201, "data": None, "message": f"输入框 '{value}' 未出现"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"输入异常: {e}"}

    def screenshot(self, name=None):
        try:
            if not self.driver:
                return {"statuscode": 404, "data": None, "message": "浏览器未启动"}
            filename = name or f"screenshot_{int(time.time())}.png"
            filepath = os.path.join(self.screenshot_dir, filename)
            self.driver.save_screenshot(filepath)
            return {"statuscode": 200, "data": {"path": filepath}, "message": "截图成功"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"截图异常: {e}"}

    def check_element_exists(self, by, value, timeout=None):
        try:
            if not self.driver:
                return {"statuscode": 404, "data": None, "message": "浏览器未启动"}
            t = timeout or 5
            wait = WebDriverWait(self.driver, t)
            wait.until(EC.presence_of_element_located((by, value)))
            return {"statuscode": 200, "data": {"exists": True}, "message": "元素存在"}
        except TimeoutException:
            return {"statuscode": 200, "data": {"exists": False}, "message": "元素不存在"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"检查异常: {e}"}

    def execute_workflow(self, steps):
        """执行完整操作流程"""
        start_time = time.time()
        try:
            open_result = self.open()
            if open_result["statuscode"] != 200:
                return open_result

            for i, step in enumerate(steps):
                action = step.get("action")
                params = step.get("params", {})

                if action == "navigate":
                    result = self.navigate(**params)
                elif action == "click":
                    result = self.click(**params)
                elif action == "fill":
                    result = self.fill(**params)
                elif action == "screenshot":
                    result = self.screenshot(**params)
                elif action == "check":
                    result = self.check_element_exists(**params)
                elif action == "wait":
                    time.sleep(params.get("seconds", 1))
                    result = {"statuscode": 200, "data": None, "message": "等待完成"}
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
        finally:
            self.close()
```

## 嵌入到 pressure-test 脚本

```python
class DeviceClient:
    def __init__(self, config):
        self.web = WebUIClient({
            "base_url": config.get("web_base_url", "https://example.com"),
            "browser": config.get("web_browser", "chromium"),
            "headless": config.get("web_headless", True),
        })
        self.platform = PlatformClient(...)

    def open_all(self):
        self.platform.login()
        self.web.open()
```

## 状态码映射

| Web UI 操作结果 | pressure-test 状态码 | 说明 |
|:---|:---|:---|
| 操作成功 | 200 (PASS) | 正常 |
| 元素不存在/超时 | 201 (FAIL) | 业务失败，可重试 |
| 浏览器未启动 | 404 (流程异常) | 需重启浏览器 |
| 脚本异常 | 500 (脚本异常) | 脚本错误 |

## 压力测试注意事项

1. **无头模式优先**：压力测试默认使用 headless 模式，减少资源消耗
2. **内存管理**：每轮测试后关闭浏览器实例，避免内存泄漏
3. **超时控制**：每次操作设置合理超时，避免长时间阻塞
4. **截图取证**：失败时自动截图，便于问题定位
5. **并发控制**：多个 WebUIClient 实例同时运行时注意端口冲突
6. **反爬检测**：必要时添加随机延迟、修改 User-Agent 等
7. 生成的类代码可直接嵌入到 pressure-test 脚本中
8. 所有方法返回格式与 pressure-test 框架的 `run()` 一致
