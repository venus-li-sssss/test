# QDM568做包

基于 `fota_builder.py` 制作 QDM568 FOTA 升级包。支持三种模式：差分包、全量包/整包、最小系统包。

## 触发条件

当用户提到以下关键词时使用此 skill：
- QDM568 做包、QDM568 差分包、QDM568 全量包、QDM568 整包、QDM568 最小系统包
- 做 QDM568 的包、给 QDM568 打包
- 给出两个 ZIP 包路径 + 包类型（差分包/全量包/最小系统包）

## 前置条件

- `fota_builder.py` 位于 `D:/work/QDM568/fota_tool/fota_builder.py`
- 工具目录 `D:/work/做包脚本/fota_tool/` 下必须存在：
  - `adiff.exe`（差分包和最小系统包使用）
  - `FBFMake_CF_V1.6-150.exe`（全量包使用）
  - `config_app`（全量包配置文件，默认使用）
- 两个输入 ZIP 包内必须包含 `system.img` 和 `ML307C_APP.zip`（内含 `ML307C_APP.bin`）

## 使用方式

用户给出两个 ZIP 包路径 + 包类型，直接调用 `fota_builder.py` 对应函数。

### 三种包类型

| 包类型 | 用户说法 | 对应函数 | 输出 |
|--------|---------|---------|------|
| 差分包 | 差分包、全量差分 | `make_diff_package_full(old_zip, new_zip, output_dir)` | 2个文件：system差分包A→B + system差分包B→A |
| 全量包/整包 | 全量包、整包、app整包 | `make_full_package(old_zip, new_zip, output_dir)` | 2个文件：旧版本app全量包 + 新版本app全量包 |
| 最小系统包 | 最小系统包 | `make_minimal_package(old_zip, new_zip, output_dir)` | 2个文件：system最小包A→B + system最小包B→A |

### 执行命令

直接用 `python -c` 调用：

```bash
cd /d/work/QDM568/fota_tool && python -c "
import sys
sys.path.insert(0, '.')
from fota_builder import make_diff_package_full, make_full_package, make_minimal_package

# 根据用户指定的包类型选择对应函数
result = make_diff_package_full(
    r'<旧版本ZIP路径>',
    r'<新版本ZIP路径>',
    r'D:/work/QDM568/fota_tool/result'
)
print('输出文件:', result)
"
```

### 输出目录

默认输出到 `D:/work/QDM568/fota_tool/result/`，自动创建以版本号+时间戳命名的子文件夹，格式：`{旧版本}_to_{新版本}_{时间戳}/`

## 执行流程

1. 确认用户提供的两个 ZIP 包路径存在
2. 确认用户指定的包类型（差分包/全量包/最小系统包）
3. 检查工具目录下 adiff.exe、FBFMake_CF_V1.6-150.exe、config_app 是否存在
4. 调用对应函数执行构建
5. 输出生成的包文件路径和文件大小

## 注意事项

- 旧版本 ZIP 在前，新版本 ZIP 在后
- 可以只给一个包也可以（全量包模式下两个版本都会生成各自的整包）
- 如果用户只说"做包"没指定类型，询问要做什么类型的包
- 构建日志会保存在输出目录下 `build_log_*.txt`