---
name: api-class-generator
description: 根据 HAR 文件（浏览器网络请求导出）或手动整理的接口文档，结合操作流程描述，自动生成 Python 类。类中使用 requests 库，自动处理 session/cookie，包含完整的 API 方法和执行流程，以及 main() 使用示例。触发场景：(1) 用户提供了 HAR 文件或接口文档 + 操作流程描述，需要生成 Python 类；(2) 用户说"生成 API 类"、"生成接口类"、"根据接口生成 Python 类"等。
agent_created: true
---

# API Class Generator

根据 HAR 文件或手动整理的接口文档，结合操作流程描述，自动生成 Python 类。

## 概述

此 skill 用于：
1. 分析 HAR 文件或手动整理的接口文档，提取接口信息（URL、方法、参数、请求头、请求体等）
2. 结合操作流程描述，生成完整的 Python 类
3. 类中包含每个接口对应的方法，以及按照操作流程组织的执行方法
4. 自动处理 session/cookie，使用 `requests` 库
5. 包含 `main()` 函数和使用示例

## 输入格式

### 输入 1：接口信息

支持两种格式：

**格式 A：HAR 文件**
- HAR（HTTP Archive）文件是浏览器导出的 JSON 格式网络请求记录
- 用户可能提供 `.har` 文件或 `.txt` 文件（内容为 HAR JSON）
- 需要从 HAR 文件中提取：`request.url`、`request.method`、`request.headers`、`request.queryString`、`request.postData` 等

**格式 B：手动整理的接口文档**
- 用户手动整理的接口信息，可以是：
  - 纯文本描述（如：`GET https://api.example.com/users`，参数：`id=123`）
  - 表格形式
  - cURL 命令
- 需要从中提取：URL、HTTP 方法、请求头、查询参数、请求体

### 输入 2：操作流程描述

用户用文字描述的操作流程，例如：
```
1. 下发日志上报任务，要么下发成功，如果任务下发失败。返回已经有任务在执行，就终止任务再下发。
2. 日志指令下发DIS日志
3. 获取任务ID
4. 轮询查看任务的状态，任务成功就成功，超时就返回失败。超时时间设置为30min
```

## 工作流程

### 步骤 1：分析文件，提取接口信息

根据用户提供的输入 1（HAR 文件或手动接口文档），提取所有接口的信息。

**如果是 HAR 文件：**
- 读取文件内容（JSON 格式）
- 遍历 `log.entries` 数组
- 对每个 entry 提取：
  - `request.url`：接口 URL
  - `request.method`：HTTP 方法（GET/POST/PUT/DELETE 等）
  - `request.headers`：请求头（转换为字典）
  - `request.queryString`：查询参数（如果有）
  - `request.postData`：请求体（如果有，可能是 `params` 或 `text`）
  - `response.status`：响应状态码（用于了解成功/失败）
  - `response.content.text`：响应内容（用于了解响应结构）

**如果是手动接口文档：**
- 分析用户提供的文本，识别出每个接口的信息
- 如果信息不完整，向用户确认关键字段

**输出：** 结构化的接口信息列表，每个接口包含：
- `name`：接口名称（根据 URL 或功能推断，如 `submit_log_task`、`get_task_status`）
- `url`：接口 URL（可能是完整的，或需要 base_url + path）
- `method`：HTTP 方法
- `headers`：默认请求头
- `params`：查询参数（如果有）
- `data`：请求体（如果有，可能是 JSON 或 form-data）
- `response_type`：响应类型（JSON/text/binary）

### 步骤 2：解析操作流程，设计类结构

根据用户提供的操作流程描述，设计 Python 类的结构。

**识别操作类型：**
- **顺序操作**：步骤 1 → 步骤 2 → 步骤 3
- **条件操作**：如果 A 成功则 B，否则 C
- **循环/轮询操作**：重复执行某个操作直到满足条件
- **错误处理**：失败时重试、终止、或返回错误

**设计类方法：**
- 每个接口对应一个方法（如 `submit_log_task()`、`get_task_status()`）
- 方法名根据接口功能命名，使用 snake_case
- 方法参数根据接口的参数设计
- 方法返回响应对象或解析后的数据

**设计执行流程方法：**
- 创建一个高级方法（如 `execute_workflow()` 或根据功能命名）来实现操作流程
- 该方法按顺序调用各个接口方法
- 包含条件判断、循环、错误处理等逻辑
- 包含超时处理（如用户提到的 30 分钟超时）

### 步骤 3：生成 Python 类

生成完整的 Python 类代码。

**类结构模板：**

```python
import requests
import time
import json
from typing import Optional, Dict, Any


class ApiClient:
    """API 客户端类，自动处理 session 和 cookie"""

    def __init__(self, base_url: str, timeout: int = 30):
        """初始化客户端

        Args:
            base_url: API 基础 URL
            timeout: 请求超时时间（秒）
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'Python ApiClient'
        })

    # ========== 接口方法 ==========

    def api_method_1(self, param1: str, param2: Optional[int] = None) -> Dict[str, Any]:
        """接口方法 1 的描述

        Args:
            param1: 参数 1 说明
            param2: 参数 2 说明（可选）

        Returns:
            响应数据字典

        Raises:
            requests.HTTPError: HTTP 请求失败
        """
        url = f"{self.base_url}/api/endpoint1"
        params = {'param1': param1}
        if param2 is not None:
            params['param2'] = param2

        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def api_method_2(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """接口方法 2 的描述

        Args:
            data: 请求数据

        Returns:
            响应数据字典
        """
        url = f"{self.base_url}/api/endpoint2"
        response = self.session.post(url, json=data, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    # ========== 执行流程 ==========

    def execute_workflow(self, param1: str) -> bool:
        """执行完整操作流程

        Args:
            param1: 参数说明

        Returns:
            是否执行成功
        """
        try:
            # 步骤 1：下发任务
            print("步骤 1：下发任务...")
            result = self.api_method_1(param1)
            print(f"下发结果：{result}")

            # 步骤 2：条件判断
            if not result.get('success'):
                if 'already running' in result.get('message', '').lower():
                    print("任务已在执行，终止任务...")
                    self.stop_task()
                    print("重新下发任务...")
                    result = self.api_method_1(param1)

            # 步骤 3：获取任务 ID
            task_id = result.get('task_id')
            if not task_id:
                print("获取任务 ID 失败")
                return False

            # 步骤 4：轮询任务状态（超时 30 分钟）
            print(f"开始轮询任务状态，任务 ID：{task_id}")
            start_time = time.time()
            timeout = 30 * 60  # 30 分钟

            while True:
                if time.time() - start_time > timeout:
                    print("任务执行超时")
                    return False

                status = self.api_method_2(task_id)
                print(f"当前状态：{status}")

                if status.get('status') == 'success':
                    print("任务执行成功")
                    return True
                elif status.get('status') == 'failed':
                    print("任务执行失败")
                    return False

                time.sleep(10)  # 每 10 秒轮询一次

        except Exception as e:
            print(f"执行流程失败：{e}")
            return False


# ========== 使用示例 ==========

def main():
    """主函数，使用示例"""
    # 创建客户端实例
    client = ApiClient(base_url="https://api.example.com", timeout=30)

    # 设置认证信息（如果需要）
    # client.session.headers.update({'Authorization': 'Bearer YOUR_TOKEN'})

    # 执行操作流程
    success = client.execute_workflow(param1="value1")

    if success:
        print("操作流程执行成功")
    else:
        print("操作流程执行失败")


if __name__ == "__main__":
    main()
```

**生成规则：**
1. 使用 `requests.Session()` 自动处理 cookie 和连接池
2. 在 `__init__` 中设置基础 URL 和默认请求头
3. 每个接口方法使用 `self.session` 发起请求
4. 使用 `response.raise_for_status()` 处理 HTTP 错误
5. 返回 `response.json()` 或解析后的数据
6. 执行流程方法包含完整的逻辑：顺序、条件、循环、超时
7. `main()` 函数包含完整的使用示例，有中文注释

### 步骤 4：输出和说明

将生成的 Python 类代码输出给用户，并附带说明：
- 类的功能概述
- 如何配置 base_url 和认证信息
- 如何调用执行流程方法
- 可能的自定义点（如超时时间、轮询间隔等）

## 注意事项

1. **URL 处理**：如果 HAR 文件中的 URL 包含完整域名，提取出 base_url 和 endpoint path
2. **参数处理**：区分查询参数（params）和请求体（json/data）
3. **响应处理**：根据 Content-Type 决定如何解析响应
4. **错误处理**：生成适当的异常处理代码
5. **超时设置**：根据用户描述的超时时间设置循环超时
6. **轮询间隔**：如果用户未指定，默认使用 5-10 秒的轮询间隔

## 示例

### 输入示例

**接口信息（HAR 文件）：**
```json
{
  "log": {
    "entries": [
      {
        "request": {
          "url": "https://iot-test.ninebot.com/api/log/submit",
          "method": "POST",
          "headers": [{"name": "Content-Type", "value": "application/json"}],
          "postData": {"mimeType": "application/json", "text": "{\"type\":\"dis\",\"level\":\"debug\"}"}
        }
      },
      {
        "request": {
          "url": "https://iot-test.ninebot.com/api/task/status?task_id=123",
          "method": "GET"
        }
      }
    ]
  }
}
```

**操作流程描述：**
```
1. 下发日志上报任务，要么下发成功，如果任务下发失败。返回已经有任务在执行，就终止任务再下发。
2. 日志指令下发DIS日志
3. 获取任务ID
4. 轮询查看任务的状态，任务成功就成功，超时就返回失败。超时时间设置为30min
```

### 输出示例

生成的 Python 类应包含：
- `submit_log_task()` 方法
- `stop_task()` 方法
- `get_task_status()` 方法
- `execute_workflow()` 方法（实现上述 4 个步骤）
- `main()` 函数（使用示例）

## Resources

### references/

此 skill 不包含额外的 reference 文件。所有必要的指导已包含在 SKILL.md 中。

### scripts/

此 skill 不包含可执行脚本。所有代码生成逻辑由 Claude 直接完成。

### assets/

此 skill 不包含资产文件。
