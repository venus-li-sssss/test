# 九号项目 Skill 优化建议

**生成时间**: 2026-08-06  
**当前版本**: 1.7.5

---

## 一、已完成的优化

### 1.1 文档优化（SKILL.md）

| 优化项 | 优化前 | 优化后 | 收益 |
|---|---|---|---|
| 总行数 | 564 行 | ~200 行 | 减少 65%，更易阅读 |
| 结构 | 线性叙述，历史踩坑混杂 | 分层结构（快速开始→平台→APP→注意事项） | 查找效率提升 |
| 重复信息 | 内网连接说明出现 3 次 | 统一在「注意事项」章节 | 减少冗余 |
| 命令示例 | 分散在各章节 | 集中在「快速开始」 | 一目了然 |

### 1.2 配置提取

**新增文件**: `config.json`

提取的配置项：
- 平台 URL 和前缀
- S3 上传参数
- 代理配置
- 认证信息（账号/密码/Cookie 文件）
- 设备默认序列号
- 页面导航树（PAGE_TREE）
- 模块映射表（APP↔平台）

**收益**:
- 改配置不用改代码
- 多环境部署更方便（测试/生产）
- 配置变更可追溯

### 1.3 配置加载模块

**新增文件**: `scripts/config_loader.py`

提供类型安全的配置访问函数：
```python
from config_loader import get_base_url, get_account, get_page_tree

BASE = get_base_url()
ACCOUNT = get_account()
PAGE_TREE = get_page_tree()
```

---

## 二、建议的后续优化

### 2.1 脚本重构（优先级：中）

#### ninebot_ota.py 优化点

| 问题 | 当前状态 | 建议改进 |
|---|---|---|
| 全局变量 | 约 15 个全局配置变量 | 改用 `config_loader` 模块 |
| 类型提示 | 无 | 添加函数签名类型提示 |
| 错误处理 | 不统一（有的 raise，有的 print） | 统一异常类 + 结构化错误输出 |
| 函数长度 | 部分函数超过 100 行 | 拆分大函数，提高可读性 |
| 日志 | 无日志系统 | 添加 logging 模块，支持 DEBUG/INFO 级别 |

**示例改进**：
```python
# 改进前
def resolve_device(imei):
    s = _session()
    r = s.post(f"{CONSOLE_BASE}/device/list", json={...})
    j = r.json()
    if j.get("resultCode") != "1000":
        raise RuntimeError(f"设备查询失败：{j}")
    ...

# 改进后
def resolve_device(imei: str) -> Dict[str, Any]:
    """按 IMEI/SN 查询设备信息和零部件版本"""
    try:
        s = _session()
        r = s.post(f"{CONSOLE_BASE}/device/list", json={...}, timeout=30)
        r.raise_for_status()
        data = r.json()
        if data.get("resultCode") != "1000":
            raise PlatformError(data.get("resultDesc", "未知错误"))
        return _parse_device_response(data)
    except requests.RequestException as e:
        raise NetworkError(f"网络请求失败：{e}") from e
```

#### device_control.py 优化点

| 问题 | 当前状态 | 建议改进 |
|---|---|---|
| PAGE_TREE | 硬编码在脚本中（约 50 行） | 已从 config.json 加载 |
| 设备连接 | 每次调用都 `u2.connect()` | 添加连接池/复用机制 |
| 元素定位 | xpath 字符串拼接 | 封装为定位器类 |
| 截图管理 | 手动指定路径 | 自动按时间戳命名 |

### 2.2 测试覆盖（优先级：高）

**当前状态**: 无自动化测试

**建议添加**:
```
tests/
├── test_config_loader.py      # 配置加载测试
├── test_ninebot_ota.py        # 平台接口测试（mock）
├── test_device_control.py     # APP 控制测试（需要真机）
└── conftest.py                # pytest 配置
```

**测试用例示例**:
- 配置加载：文件不存在、格式错误、字段缺失
- 版本解析：`normalize_version("032E")` → `("032E", "V0.3.2.E")`
- MD5 计算：已知文件的 MD5 校验
- 页面导航：PAGE_TREE BFS 路径计算

### 2.3 文档完善（优先级：中）

**新增文档**:
```
docs/
├── troubleshooting.md         # 常见问题排查
├── api_changes.md             # API 变更记录
└── development_guide.md       # 开发者指南
```

**troubleshooting.md 内容示例**:
- 内网连不通：检查隧道、代理、防火墙
- 登录失败：账号密码、Cookie 过期、SSO 变更
- 4025 错误：文件名格式、MD5 校验
- APP 控制失败：设备连接、uiautomator2 初始化

### 2.4 性能优化（优先级：低）

| 优化点 | 当前状态 | 建议改进 |
|---|---|---|
| HTTP 连接 | 每次请求新建 Session | 复用 Session，添加连接池 |
| Cookie 刷新 | 过期后重新登录 | 提前 5 分钟刷新，避免请求中断 |
| 文件上传 | 单线程分片 | 多线程并发上传（大文件） |
| 设备轮询 | 固定间隔 | 自适应间隔（快速失败 + 指数退避） |

### 2.5 安全改进（优先级：高）

**当前风险**:
- 账号密码明文写在代码中
- Cookie 文件无权限控制
- 敏感信息可能提交到 Git

**建议改进**:
1. **环境变量优先**：
   ```python
   ACCOUNT = os.getenv("NINEBOT_ACCOUNT", get_auth_config().get("account"))
   PASSWORD = os.getenv("NINEBOT_PASSWORD", get_auth_config().get("password"))
   ```

2. **Cookie 文件权限**：
   ```python
   os.chmod(cookie_file, 0o600)  # 仅所有者可读写
   ```

3. **.gitignore 添加**：
   ```
   ninebot_cookies.json
   config.json  # 如果包含敏感信息
   ```

4. **敏感信息加密**（可选）：
   - 使用 `keyring` 模块存储密码
   - Cookie 文件加密存储

---

## 三、优化实施计划

### Phase 1: 基础优化（已完成 ✅）
- [x] SKILL.md 精简和结构化
- [x] 配置提取到 config.json
- [x] 配置加载模块 config_loader.py

### Phase 2: 脚本改进（建议 1-2 天）
- [ ] ninebot_ota.py 改用 config_loader
- [ ] device_control.py 改用 config_loader 的 PAGE_TREE
- [ ] 添加基础类型提示
- [ ] 统一错误处理框架

### Phase 3: 测试和安全（建议 2-3 天）
- [ ] 添加 pytest 测试框架
- [ ] 核心函数单元测试
- [ ] 敏感信息环境变量化
- [ ] Cookie 文件权限控制

### Phase 4: 文档和性能（建议 1-2 天）
- [ ] 添加 troubleshooting.md
- [ ] HTTP 连接池优化
- [ ] 文件上传多线程（可选）

---

## 四、优化效果预估

| 指标 | 优化前 | 优化后（Phase 2 完成） | 提升 |
|---|---|---|---|
| SKILL.md 可读性 | ⭐⭐ | ⭐⭐⭐⭐ | +100% |
| 配置修改便利性 | ⭐ | ⭐⭐⭐⭐⭐ | +150% |
| 代码可维护性 | ⭐⭐ | ⭐⭐⭐⭐ | +100% |
| 测试覆盖率 | 0% | 60%+ | +60% |
| 安全风险 | 中高 | 低 | -70% |

---

## 五、快速验证

优化后可用以下命令验证：

```bash
# 1. 配置加载测试
python scripts/config_loader.py

# 2. SKILL.md 结构检查
# 确认包含：快速开始、平台操作、APP 控制、注意事项

# 3. 原有功能回归测试
python scripts/ninebot_ota.py query-device 868105049574252
python scripts/device_control.py status
```

---

**维护者**: QA Agent  
**最后更新**: 2026-08-06
