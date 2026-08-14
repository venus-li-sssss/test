---
description: 'Use this skill when building a super-client by composing multiple independent base classes (platform clients, AI clients, etc.). Triggers: "组合模式", "超类", "super client", "基础类组合", "平台客户端", "cookie管理", "token续期", "接口重试", "组合多个API客户端". Covers: base class design (session/cookie/token management, auto-renewal, retry decorator), composition pattern, and coordination logic. Feishu Aily image recognition is just one example base class.'
name: super-client
---

# 组合模式构建超类（Super Client）

**核心主题**：先写独立的基础类，再用组合模式合成超类。每个基础类负责一个领域（平台 API、AI 能力等），超类负责协调。

飞书 Aily 图片识别只是其中一个基础类的示例，不是核心。

---

## 一、基础类设计经验（核心）

### 1.1 Session / Cookie 管理

平台类客户端必须管理好 session 和 cookie，这是后续所有调用的基础。

```python
class PlatformClient:
    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        
        # 关键：使用 requests.Session() 自动管理 cookie 和连接池
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 ...',
            # 平台特有的 header（如 forward-service-ip）
        })
```

**要点**：
- 用 `requests.Session()` 而不是单独的 `requests.get/post`，自动携带 cookie
- 在 `__init__` 里设置通用 header，避免每个方法重复设置
- `base_url` 在 `__init__` 里 `rstrip('/')`，拼接路径时统一加 `/`

### 1.2 Token 生命周期管理

Token 有过期时间，必须在每次 API 调用前检测，过期自动续期。

```python
class PlatformClient:
    def __init__(self, ..., token_ttl: int = 3600):
        self.token_ttl = token_ttl          # 可配置，默认 1 小时
        self.token: Optional[str] = None
        self.token_expiry_time: float = 0   # 过期时间戳
        self._username: Optional[str] = None  # 保存凭据用于自动续期
        self._password: Optional[str] = None

    def is_token_expired(self) -> bool:
        """检查 token 是否过期"""
        if not self.token:
            return True
        return time.time() >= self.token_expiry_time

    def ensure_login(self, username=None, password=None):
        """每次 API 调用前自动检测，过期则重新登录"""
        if not self.is_token_expired():
            return  # token 有效，直接返回
        # 保存凭据
        if username: self._username = username
        if password: self._password = password
        if not self._username or not self._password:
            raise Exception("Token 已过期，需要提供凭据重新登录")
        self.login(username=self._username, password=self._password)
```

**在业务方法中调用**：
```python
def query_device_info(self, device_key):
    self.ensure_login()  # ← 每次调用前自动检测
    # ... 执行查询
```

**要点**：
- `token_ttl` 做成可配置参数（默认 1 小时，可按需改）
- 登录成功后记录 `token_expiry_time = time.time() + self.token_ttl`
- 保存 username/password 用于自动续期，用户无感知
- `ensure_login()` 放在每个需要认证的业务方法开头

### 1.3 Token 格式陷阱（已验证的坑）

**某些平台的 token 必须保持 URL-encoded 原始格式，不能解码！**

```python
# ✅ 正确：保持原始格式
auth_header = response.headers.get('authorization', '')
self.token = auth_header  # 不要 unquote！
self.session.headers.update({'Authorization': self.token})

# ❌ 错误：解码后会导致后续请求认证失败
self.token = unquote(auth_header)  # 401 认证失败
```

这个坑在 HWBus 平台上验证过：解码后所有后续请求都返回 401。

### 1.4 接口重试机制（重要）

网络不稳定时自动重试，指数退避 + 日志记录。

```python
import time, logging
from functools import wraps

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def retry_on_failure(max_retries=3, delay=1, backoff=2, exceptions=(Exception,)):
    """重试装饰器：指数退避 + 日志"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            f"{func.__name__} 失败 (尝试 {attempt+1}/{max_retries+1}): {e}，"
                            f"{current_delay}s 后重试..."
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(f"{func.__name__} 失败，已重试 {max_retries} 次: {e}")
            raise last_exception
        return wrapper
    return decorator
```

**使用方式**：
```python
class PlatformClient:
    @retry_on_failure(max_retries=3, delay=1, backoff=2,
                     exceptions=(requests.RequestException, requests.Timeout))
    def query_device_info(self, device_key):
        self.ensure_login()
        resp = self.session.post(url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()
```

**要点**：
- 只重试**网络异常**（`RequestException`, `Timeout`），不重试业务错误（401/403/业务 code != 0）
- 指数退避：1s → 2s → 4s → 8s，避免雪崩
- 装饰器不侵入业务代码
- 文件上传等耗时操作可加大重试次数和延迟

---

## 二、组合模式构建超类（核心）

### 2.1 原则

- **先写独立的基础类**：每个类负责一个领域，各自维护状态和逻辑
- **超类通过创建对象组合**：不继承、不融合，保持各自独立性
- **超类负责协调**：提供高层接口，协调多个基础类协作

### 2.2 结构

```
SuperClient（超类）
├── self.platform = PlatformClient()    ← 独立对象：平台 API
│   ├── login() / logout()
│   ├── ensure_login()（token 自动续期）
│   ├── query_xxx()
│   └── get_user_detail()
│
└── self.aily = AilyClient()            ← 独立对象：AI 能力
    └── recognize_image()
```

### 2.3 超类实现

```python
class SuperClient:
    def __init__(self, base_url, token_ttl=3600,
                 aily_app_id=None, aily_app_secret=None,
                 aily_spring_id=None, aily_skill_id=None):
        # 创建平台客户端对象
        self.platform = PlatformClient(base_url=base_url, token_ttl=token_ttl)
        
        # 创建 AI 客户端对象（可选）
        self.aily = None
        if aily_app_id and aily_app_secret and aily_spring_id:
            self.aily = AilyClient(
                app_id=aily_app_id, app_secret=aily_app_secret,
                spring_id=aily_spring_id, skill_id=aily_skill_id
            )

    # 委托给子对象
    def query_device_info(self, device_key):
        return self.platform.query_device_info(device_key)

    def recognize_image(self, image_path, query="OCR 识别"):
        if not self.aily:
            return {"success": False, "error": "未配置 AI"}
        return self.aily.recognize_image(image_path, query)

    # 超类的协调逻辑：login 时自动用 AI 识别验证码
    def login(self, username, password, captcha_code=None):
        if captcha_code is None and self.aily:
            captcha = self.platform.get_captcha()
            img_path = self.platform.save_captcha_image(captcha)
            ai_result = self.aily.recognize_image(img_path, query="数学题答案")
            captcha_code = ai_result["messages"][0]
        return self.platform.login(username, password, captcha_code)
```

### 2.4 关键优势

| 优势 | 说明 |
|------|------|
| **独立维护** | 修改 PlatformClient 不影响 AilyClient，反之亦然 |
| **灵活组合** | 可以只创建 platform 不创建 aily，按需组合 |
| **易于测试** | 每个基础类可单独测试 |
| **协调逻辑集中** | 超类负责跨类协调（如 login 自动调 AI 识别验证码） |
| **后续扩展** | 加新能力只需新增基础类，在超类里加一个对象 |

---

## 三、飞书 Aily 图片识别（示例基础类）

这只是"AI 能力基础类"的一个具体实现示例。

### 3.1 所需参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `app_id` | 飞书应用 APP ID | `<your_app_id>` |
| `app_secret` | 飞书应用 APP Secret | `<your_app_secret>` |
| `spring_id` | Aily Spring 应用 ID | `<your_spring_id>` |
| `skill_id` | Skill ID | `<your_skill_id>` |

### 3.2 工作流（7 步）

1. 获取 Access Token → `POST /auth/v3/app_access_token/internal`
2. 创建会话 → `POST /aily/v1/sessions`
3. 上传文件 → `POST /aily/v1/files`（multipart/form-data，**不设 Content-Type**）
4. 创建消息 → `POST /aily/v1/sessions/{id}/messages`
5. 触发执行 → `POST /aily/v1/sessions/{id}/runs`
6. 轮询状态 → `GET /aily/v1/sessions/{id}/runs/{id}` 直到 COMPLETED
7. 获取结果 → `GET /aily/v1/sessions/{id}/messages` 提取 ASSISTANT 消息

### 3.3 脚本调用

```bash
python <skill_dir>/scripts/call_aily_workflow.py \
  --app-id "<app_id>" --app-secret "<app_secret>" \
  --spring-id "<spring_id>" --skill-id "<skill_id>" \
  --file "<file_path>" --query "<query>" --timeout 60
```

---

## 四、完整使用示例

```python
from super_client import SuperClient

client = SuperClient(
    base_url="https://hwbustest.tailgvip.com",
    token_ttl=3600,
    aily_app_id="<your_app_id>",
    aily_app_secret="<your_app_secret>",
    aily_spring_id="<your_spring_id>",
    aily_skill_id="<your_skill_id>"
)

# AI 图片识别（委托给 aily 对象）
result = client.recognize_image("image.jpg", query="OCR 识别")

# 登录（超类协调：自动用 AI 识别验证码）
client.login(username="<your_username>", password="<your_password>")

# 查询设备（platform 对象自动检测 token 过期 + 自动重试）
device = client.get_device_online_status("868471088459890")

# 登出
client.logout()
```

---

## 五、经验清单（快速查阅）

| # | 经验 | 要点 |
|---|------|------|
| 1 | Session 管理 | 用 `requests.Session()`，`__init__` 设通用 header |
| 2 | Token 过期检测 | `is_token_expired()` + `ensure_login()` 每次调用前检测 |
| 3 | Token 自动续期 | 保存 username/password，过期自动重新登录 |
| 4 | Token 格式 | **保持 URL-encoded 原始格式，不要 unquote** |
| 5 | 重试机制 | 装饰器 + 指数退避 + 只重试网络异常 + 日志记录 |
| 6 | 组合模式 | 超类通过创建对象组合，不继承不融合 |
| 7 | 协调逻辑 | 超类负责跨类协调（如 login 自动调 AI） |
| 8 | 灵活组合 | 基础类可选创建（如 aily 可不配） |
