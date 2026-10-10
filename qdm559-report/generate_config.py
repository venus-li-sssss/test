"""
从原始数据生成 config.json

输入：
1. 测试用例执行表（xlsx 文件列表）
2. 修改点 changelist（txt 文件）
3. JIRA 数据（xlsx 或 csv 文件）

输出：
- config.json
"""

import json
import openpyxl
from pathlib import Path
from datetime import datetime

# ============================================================
# 配置
# ============================================================
OUTPUT_CONFIG = Path(__file__).parent / "config.json"

# ============================================================
# 1. 解析测试用例执行表
# ============================================================

def parse_test_cases(xlsx_files):
    """
    解析测试用例执行表，提取测试结果
    
    返回：
    {
        "basic_tests": [...],
        "stability_tests": [...]
    }
    """
    basic_tests = []
    stability_tests = []
    
    for xlsx_file in xlsx_files:
        wb = openpyxl.load_workbook(xlsx_file, data_only=True)
        
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            
            # 找到表头行
            header_row = None
            for ri, row in enumerate(ws.iter_rows(min_row=1, max_row=10, values_only=False), 1):
                vals = [c.value for c in row]
                if any(v and ("用例编号" in str(v) or "Case ID" in str(v)) for v in vals):
                    header_row = ri
                    break
            
            if header_row is None:
                continue
            
            # 解析测试用例
            # ... (根据实际格式解析)
            pass
        
        wb.close()
    
    return {
        "basic_tests": basic_tests,
        "stability_tests": stability_tests
    }

# ============================================================
# 2. 解析修改点 changelist
# ============================================================

def parse_changelist(txt_file):
    """
    解析 Git commit 格式的 changelist
    
    返回：
    {
        "modification_tests": [...]
    }
    """
    modification_tests = []
    
    with open(txt_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 解析 commit 块
    commits = content.split('commit ')[1:]  # 跳过第一个空块
    
    for commit in commits:
        lines = commit.strip().split('\n')
        
        # 提取 JIRA ID
        jira_id = None
        title = None
        test_proposal = None
        
        for line in lines:
            if '<Jira ID>:' in line:
                jira_id = line.split('<Jira ID>:')[1].strip()
            elif '<Test-Proposal>:' in line:
                test_proposal = line.split('<Test-Proposal>:')[1].strip()
            elif line.strip() and not line.startswith('Author:') and not line.startswith('Date:'):
                if title is None and '<QDM' in line:
                    title = line.strip()
        
        if jira_id and title:
            modification_tests.append({
                "title": f"2.2.{len(modification_tests)+1} {title[:50]}",
                "steps": [test_proposal] if test_proposal else [],
                "result": "PASS",  # 默认 PASS，需要根据实际测试结果调整
                "remark": test_proposal or ""
            })
    
    return {
        "modification_tests": modification_tests
    }

# ============================================================
# 3. 查询 JIRA
# ============================================================

def query_jira(project_key, status_filter="未关闭"):
    """
    查询 JIRA 获取未关闭问题
    
    返回：
    {
        "test_summary": [...],
        "bugs": [...]
    }
    """
    # 这里需要调用 JIRA API 或解析 JIRA 导出文件
    # 暂时返回示例数据
    return {
        "test_summary": [
            "1）示例问题 1（BUG-001）",
            "2）示例问题 2（BUG-002）"
        ],
        "bugs": [
            {
                "id": "BUG-001",
                "severity": "B-Major",
                "description": "示例 Bug 描述",
                "remark": "备注信息"
            }
        ]
    }

# ============================================================
# 4. 生成配置文件
# ============================================================

def generate_config(test_data, changelist_data, jira_data, test_info):
    """
    生成完整的 config.json
    """
    config = {
        "report": {
            "title": "QDM559 测试报告",
            "version": test_info.get("version", "0x0242"),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "status": "受控文件",
            "company": "上海安科联科技有限公司",
            "address": "上海市闵行区田林路 1016 号科技绿洲 3 期（B 区）5 号楼",
            "zip": "200233",
            "phone": "+86 21 5108 6236",
            "email": "info@ikotek.com"
        },
        "test_info": test_info,
        "components": test_info.get("components", {
            "ECU": "0242",
            "DIS": "0115",
            "MCU": "0836",
            "BMS": "2008",
            "TFT": "0317",
            "CHG": "050E",
            "HW": "QDM559_EA_V1.1"
        }),
        "modification_tests": changelist_data.get("modification_tests", []),
        "basic_tests": test_data.get("basic_tests", []),
        "stability_tests": test_data.get("stability_tests", []),
        "test_summary": jira_data.get("test_summary", []),
        "bugs": jira_data.get("bugs", [])
    }
    
    return config

# ============================================================
# 主流程
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("从原始数据生成 config.json")
    print("=" * 60)
    
    # 示例：从命令行参数获取输入文件
    import sys
    
    if len(sys.argv) < 4:
        print("\n使用方法:")
        print("  python generate_config.py <测试用例 xlsx> <changelist txt> <JIRA 数据文件>")
        print("\n示例:")
        print('  python generate_config.py test_cases.xlsx changelist.txt jira_data.csv')
        print("\n或者手动编辑 config_template.json 后运行:")
        print("  python generate_report.py")
        exit(1)
    
    xlsx_files = sys.argv[1].split(',')
    changelist_file = sys.argv[2]
    jira_file = sys.argv[3]
    
    # 1. 解析测试用例
    print("\n[1/4] 解析测试用例执行表...")
    test_data = parse_test_cases(xlsx_files)
    print(f"  解析了 {len(xlsx_files)} 个文件")
    
    # 2. 解析 changelist
    print("\n[2/4] 解析修改点 changelist...")
    changelist_data = parse_changelist(changelist_file)
    print(f"  解析了 {len(changelist_data.get('modification_tests', []))} 个修改点")
    
    # 3. 查询 JIRA
    print("\n[3/4] 查询 JIRA 数据...")
    jira_data = query_jira("QDM559")
    print(f"  获取了 {len(jira_data.get('bugs', []))} 个 Bug")
    
    # 4. 生成配置文件
    print("\n[4/4] 生成配置文件...")
    test_info = {
        "project": "QDM559",
        "tester": "Venus",
        "location": "佛山",
        "period": f"{datetime.now().strftime('%Y/%m/%d')} 09:00 – {datetime.now().strftime('%Y/%m/%d')} 18:00",
        "samples": "2PCS",
        "imei": "868105049574252",
        "version": "0x0242"
    }
    
    config = generate_config(test_data, changelist_data, jira_data, test_info)
    
    with open(OUTPUT_CONFIG, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 配置文件已生成：{OUTPUT_CONFIG}")
    print(f"   - 修改点测试：{len(config['modification_tests'])} 项")
    print(f"   - 基本功能测试：{len(config['basic_tests'])} 项")
    print(f"   - 稳定性测试：{len(config['stability_tests'])} 项")
    print(f"   - Bug 数量：{len(config['bugs'])} 条")
    print(f"\n下一步：运行 python generate_report.py 生成报告")
