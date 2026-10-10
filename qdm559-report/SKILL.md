# QDM559 对外报告生成器

## 触发词
"生成对外报告" / "QDM559 报告" / "测试报告" / "/qdm559-report"

## 输入
1. **测试用例执行表** (xlsx) - 各模块测试结果
2. **修改点 changelist** (txt) - Git commit 格式
3. **JIRA 数据** - 未关闭问题列表
4. **内部测试报告** (xlsx) - 压力测试数据来源

## 输出
`Ikotek_QDM559_V22_测试报告_*.docx`

## 快速使用

### 方式一：有配置文件
```bash
cd skills/qdm559-report
python generate_report.py
```

### 方式二：从原始数据生成
```bash
python generate_config.py <测试用例.xlsx> <changelist.txt> <jira.csv>
python generate_report.py
```

## 配置文件格式

```json
{
  "report": {"title": "QDM559 测试报告", "version": "0x0242", "date": "2026-10-09"},
  "test_info": {"project": "QDM559", "tester": "Venus", "location": "佛山", "period": "...", "samples": "1片", "imei": "..."},
  "components": {"ECU": "0242", "DIS": "0115", "MCU": "0836", "BMS": "2008", "TFT": "0317", "CHG": "050E", "HW": "QDM559_EA_V1.1"},
  "modification_tests": [{"title": "...", "steps": [...], "result": "PASS/FAIL", "remark": "..."}],
  "basic_tests": [...],
  "stability_tests": [...],
  "test_summary": ["1）...", "2）..."],
  "bugs": [{"id": "...", "severity": "...", "description": "...", "remark": "..."}]
}
```

**注意**：
- `samples` 字段使用中文格式（如 `"1片"`、`"2片"`），不要用 `"1PCS"` / `"2PCS"`
- 页眉会自动从模板的 `QDM551-EA-QNA` 修改为 `QDM559-EA-NA`

## 备注规则
- **压力测试 PASS**: 备注写测试数据（如"ECU 升级 100 次成功 100 次 (100/0)，平均耗时 80.9s"）
- **其他 PASS**: 备注留空
- **FAIL**: 备注写 JIRA 问题描述（红色）

## 测试步骤规则
- 测试步骤必须对应测试用例或压力测试脚本
- **ECU 升级**步骤写"平台查看 ECU 版本号"，不要写"T-BOX"
- **组合升级**步骤写"平台进行组合升级（ECU、DIS、MCU、BMS、TFT、CHG）"

## 文件结构
```
skills/qdm559-report/
├── SKILL.md
├── generate_report.py      # 核心脚本（使用自定义标题，无列表编号）
├── generate_config.py      # 配置生成（可选）
├── config_template.json
├── media/
│   ├── base_template.docx  # 基础模板（勿修改）
│   └── env_image.png       # 测试环境图片
└── output/
```

## 依赖
```bash
pip install python-docx Pillow openpyxl
```

## 注意事项
1. **不要修改** `base_template.docx`
2. **目录会自动更新**：脚本使用 `win32com` 自动打开 Word 并更新 TOC 字段（需要安装 Word）
3. 所有数据来自 `config.json`，不会残留模板旧数据
4. 标题使用自定义格式（outlineLvl），不依赖模板 Heading 样式，避免列表编号干扰
5. **页眉自动修改**：脚本会自动将页眉从 `QDM551-EA-QNA` 改为 `QDM559-EA-NA`（包括奇数页、偶数页、首页）
6. **样品数量格式**：config 中 `samples` 字段使用中文格式（如 `"1片"`），不要用 `"1PCS"`
7. 依赖：`pip install python-docx Pillow openpyxl pywin32`
