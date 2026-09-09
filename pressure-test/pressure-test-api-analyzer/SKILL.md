---
description: 从 HAR 文件或接口文档中提取接口信息，生成适配 pressure-test 框架的 Platform API 基础类代码。当 pressure-test-generator 遇到接口自动化场景（Platform API 类）时，可加载此子 skill 进行接口分析。触发场景：(1) 用户提供了 HAR 文件或接口文档，需要生成 Platform API 基础类；(2) pressure-test 流程中需要为接口自动化生成 Layer 1 基础类；(3) 用户说"分析接口"、"根据 HAR 生成 API 类"等。
name: pressure-test-api-analyzer
---

# pressure-test-api-analyzer — 接口分析器

从 HAR 文件或接口文档中提取接口信息，生成适配 **pressure-test 框架** 的 Platform API 基础类代码。

## 定位

本 skill 是 pressure-test-generator 的细化子 skill，专门负责 **Layer 1 — Platform API 基础类** 的生成。不生成完整的压力测试脚本，只生成基础类代码。

生成的类可直接嵌入到 pressure-test 脚本中，作为 `DeviceClient` 超类的组成部分。

## 输入格式

### 输入 1：接口信息

支持两种格式：

**格式 A：HAR 文件**
- HAR（HTTP Archive）文件是浏览器导出的 JSON 格式网络请求记录
- 需要从 HAR 文件中提取：`request.url`、`request.method`、`request.headers`、`request.queryString`、`request.postData` 等

**格式 B：手动整理的接口文档**
- 纯文本描述、表格形式、或 cURL 命令
- 需要从中提取：URL、HTTP 方法、请求头、查询参数、请求体

### 输入 2：操作流程描述（可选）

用户用文字描述的操作流程，例如：
```
1. 登录平台获取 token
2. 查询设备在线状态
3. 如果在线则下发升级指令
4. 轮询升级状态直到完成或超时
```

## 工作流程

### 步骤 1：分析文件，提取接口信息

**如果是 HAR 文件：**
- 读取文件内容（JSON 格式）
- 遍历 `log.entries` 数组
- 对每个 entry 提取：
  - `request.url`：接口 URL
  - `request.method`：HTTP 方法
  - `request.headers`：请求头（转换为字典）
  - `request.queryString`：查询参数
  - `request.postData`：请求体（可能是 `params` 或 `text`）
  - `response.status`：响应状态码
  - `response.content.text`：响应内容（了解响应结构）

**如果是手动接口文档：**
- 分析文本，识别每个接口的信息
- 信息不完整时向用户确认

**输出：** 结构化的接口信息列表，每个接口包含：
- `name`：接口名称（如 `login`、`query_device`、`submit_task`）
- `url`：接口 URL 或 path
- `method`：HTTP 方法
- `headers`：默认请求头
- `params`：查询参数
- `data`：请求体

### 步骤 2：生成 Platform API 基础类

根据提取的接口信息，生成一个完整的 Python 类。**必须适配 pressure-test 框架**。

**类生成规则：**

1. **使用 `requests.Session()`** 自动处理 cookie 和连接池
2. **每个接口对应一个方法**，方法名使用 snake_case
3. **方法返回值适配 pressure-test 状态码体系**：
   - 成功返回 `{"statuscode": 200, "data": ..., "message": "..."}`
   - 失败返回 `{"statuscode": 201, "data": None, "message": "错误原因"}`
   - 超时/异常返回 `{"statuscode": 404, "data": None, "message": "..."}`
4. **支持 session 复用**：通过 `__init__` 初始化 session
5. **包含操作流程方法**（如果用户提供了流程描述）：
   - 方法名如 `execute_workflow()` 或 `run_flow()`
   - 按顺序调用各接口方法
   - 包含条件判断、循环、超时处理
   - 返回格式与 pressure-test 框架的 `run()` 方法一致

**类模板：**

```python
import requests
import time

class PlatformClient:
    """平台 API 客户端，适配 pressure-test 框架"""

    def __init__(self, base_url, username=None, password=None, timeout=30):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'PressureTest/1.0'
        })
        self.username = username
        self.password = password

    # ========== 接口方法 ==========

    def login(self):
        """登录平台"""
        try:
            url = f"{self.base_url}/api/login"
            resp = self.session.post(url, json={
                "username": self.username,
                "password": self.password
            }, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            return {"statuscode": 200, "data": data, "message": "登录成功"}
        except requests.HTTPError as e:
            return {"statuscode": 201, "data": None, "message": f"HTTP错误: {e}"}
        except requests.Timeout:
            return {"statuscode": 404, "data": None, "message": "登录超时"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"脚本异常: {e}"}

    def query_device(self, device_key):
        """查询设备信息"""
        try:
            url = f"{self.base_url}/api/device/{device_key}"
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            return {"statuscode": 200, "data": resp.json(), "message": "查询成功"}
        except requests.HTTPError as e:
            return {"statuscode": 201, "data": None, "message": f"HTTP错误: {e}"}
        except requests.Timeout:
            return {"statuscode": 404, "data": None, "message": "查询超时"}
        except Exception as e:
            return {"statuscode": 500, "data": None, "message": f"脚本异常: {e}"}

    # ========== 执行流程（可选） ==========

    def execute_workflow(self, device_key):
        """执行完整操作流程，返回 pressure-test 框架兼容格式"""
        start_time = time.time()
        try:
            # 步骤 1：登录
            login_result = self.login()
            if login_result["statuscode"] != 200:
                return login_result

            # 步骤 2：查询设备
            query_result = self.query_device(device_key)
            if query_result["statuscode"] != 200:
                return query_result

            duration = time.time() - start_time
            return {
                "statuscode": 200,
                "duration": duration,
                "data": query_result["data"],
                "message": "流程执行成功"
            }
        except Exception as e:
            duration = time.time() - start_time
            return {
                "statuscode": 500,
                "duration": duration,
                "data": None,
                "message": f"流程异常: {e}"
            }
```

### 步骤 3：嵌入到 pressure-test 脚本

生成的 Platform API 基础类将作为 `DeviceClient` 超类的一个组成部分：

```python
class DeviceClient:
    def __init__(self, config):
        self.platform = PlatformClient(
            config['platform_base_url'],
            config['platform_username'],
            config['platform_password']
        )
        # 其他基础类...
        self.serial = SerialClient(config.get('serial_port', 'COM1'))

    def open_all(self):
        self.platform.login()
        self.serial.open()
```

## 状态码映射

| HTTP 响应 | pressure-test 状态码 | 说明 |
|:---|:---|:---|
| 2xx 成功 | 200 (PASS) | 正常 |
| 4xx/5xx 错误 | 201 (FAIL) | 业务失败 |
| 超时 | 404 (流程异常) | 可重试 |
| 其他异常 | 500 (脚本异常) | 脚本错误 |

## 注意事项

1. 生成的类代码可直接嵌入到 pressure-test 脚本中，无需额外 import
2. 所有方法返回格式与 pressure-test 框架的 `run()` 一致
3. 使用 `requests.Session()` 自动管理 cookie，适合需要登录态的场景
4. 如果用户提供了操作流程描述，生成 `execute_workflow()` 方法
5. 如果用户只提供了接口信息无流程描述，仅生成接口方法
