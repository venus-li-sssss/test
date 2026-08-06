#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
移远工时自动填写 CLI
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from work_client import WorkClient  # noqa: E402

CONF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".credentials.json")

# 润色映射表 - 使用占位符避免重复替换
POLISH_MAP = {
    '挂测': '执行自动化挂测',
    '测试': '执行测试验证',
    '修复': '修复并验证',
    '修改': '修改并完善',
    '优化': '优化并验证',
    '升级': '升级并验证',
    '降级': '降级并验证',
    '部署': '部署并确认',
    '发布': '发布并确认',
    '上线': '上线并确认',
    '联调': '联调验证',
    '集成': '集成验证',
    '回归': '回归验证',
    '复现': '复现并分析',
    '定位': '定位并处理',
    '排查': '排查并处理',
    '分析': '分析并输出结论',
    '调试': '调试并验证',
    '验证': '验证并确认',
    '确认': '确认并反馈',
    '处理': '处理并确认',
    '解决': '解决并验证',
    '完成': '完成并确认',
    '编写': '编写并输出',
    '撰写': '撰写并输出',
    '整理': '整理并输出',
    '汇总': '汇总并输出',
    '总结': '总结并输出',
    '评审': '评审并确认',
    '审核': '审核并确认',
    '审批': '审批并确认',
    '沟通': '沟通并确认',
    '讨论': '讨论并输出结论',
    '参会': '参会并输出纪要',
    '协助': '协助处理',
    '支持': '支持并处理',
    '响应': '响应并处理',
    '跟踪': '跟踪并反馈',
    '推进': '推进并确认',
    '推动': '推动并确认',
    '促进': '促进并确认',
    '保障': '保障并确认',
    '确保': '确保并确认',
    '实施': '实施并确认',
    '落实': '落实并确认',
    '执行': '执行并确认',
    '开展': '开展并确认',
    '进行': '进行并确认',
    '结束': '结束并输出结论',
    '关闭': '关闭并确认',
    '开启': '开启并确认',
    '启动': '启动并确认',
    '停止': '停止并确认',
    '暂停': '暂停并确认',
    '恢复': '恢复并确认',
    '还原': '还原并验证',
    '备份': '备份并确认',
    '迁移': '迁移并验证',
    '导出': '导出并确认',
    '导入': '导入并确认',
    '上传': '上传并确认',
    '下载': '下载并确认',
    '安装': '安装并配置',
    '配置': '配置并验证',
    '设置': '设置并确认',
    '调整': '调整并确认',
    '改进': '改进并确认',
    '完善': '完善并确认',
    '丰富': '丰富并完善',
    '补充': '补充并完善',
    '更新': '更新并确认',
    '新增': '新增并确认',
    '添加': '添加并确认',
    '删除': '删除并确认',
    '移除': '移除并确认',
    '清理': '清理并确认',
    '检查': '检查并确认',
    '检测': '检测并确认',
    '核对': '核对并确认',
    '对比': '对比并确认',
    '比较': '比较并确认',
    '研究': '研究并输出结论',
    '探索': '探索并输出结论',
    '尝试': '尝试并确认',
    '试验': '试验并确认',
    '证明': '证明并确认',
    '明确': '明确并确认',
    '规范': '规范并确认',
    '标准化': '标准化并确认',
    '统一': '统一并确认',
    '整合': '整合并确认',
    '合并': '合并并确认',
    '拆分': '拆分并确认',
    '解耦': '解耦并确认',
    '重构': '重构并确认',
    '提升': '提升并确认',
    '增强': '增强并确认',
    '强化': '强化并确认',
    '巩固': '巩固并确认',
    '稳定': '稳定并确认',
    '量化': '量化并处理',
    '状态词': {
        '进行中': '持续推进中',
        '已完成': '已完成并验证',
        '处理中': '持续处理中',
        '已处理': '已处理并确认',
        '修复中': '持续修复中',
        '已修复': '已修复并验证',
        '验证中': '持续验证中',
        '已验证': '已验证并确认',
        '测试中': '持续测试中',
        '已测试': '已测试并确认',
        '开发中': '持续开发中',
        '已开发': '已开发并确认',
        '设计中': '持续设计中',
        '已设计': '已设计并确认',
        '评审中': '持续评审中',
        '已评审': '已评审并确认',
        '审核中': '持续审核中',
        '已审核': '已审核并确认',
        '审批中': '持续审批中',
        '已审批': '已审批并确认',
        '发布中': '持续发布中',
        '已发布': '已发布并确认',
        '部署中': '持续部署中',
        '已部署': '已部署并确认',
        '上线中': '持续上线中',
        '已上线': '已上线并确认',
        '运行中': '持续运行中',
        '已运行': '已运行并确认',
        '监控中': '持续监控中',
        '已监控': '已监控并确认',
        '维护中': '持续维护中',
        '已维护': '已维护并确认',
        '支持中': '持续支持中',
        '已支持': '已支持并确认',
        '响应中': '持续响应中',
        '已响应': '已响应并确认',
    },
    '技术术语': {
        'ota': 'OTA', 'OTA': 'OTA', 'Ota': 'OTA',
        'http': 'HTTP', 'HTTP': 'HTTP', 'Http': 'HTTP',
        'mqtt': 'MQTT', 'MQTT': 'MQTT', 'Mqtt': 'MQTT',
        'tcp': 'TCP', 'TCP': 'TCP', 'Tcp': 'TCP',
        'udp': 'UDP', 'UDP': 'UDP', 'Udp': 'UDP',
        'gps': 'GPS', 'GPS': 'GPS', 'Gps': 'GPS',
        'gnss': 'GNSS', 'GNSS': 'GNSS', 'Gnss': 'GNSS',
        'wifi': 'Wi-Fi', 'WiFi': 'Wi-Fi', 'WIFI': 'Wi-Fi',
        'bt': 'BT', 'BT': 'BT', 'Bt': 'BT',
        'ble': 'BLE', 'BLE': 'BLE', 'Ble': 'BLE',
        'usb': 'USB', 'USB': 'USB', 'Usb': 'USB',
        'uart': 'UART', 'UART': 'UART', 'Uart': 'UART',
        'spi': 'SPI', 'SPI': 'SPI', 'Spi': 'SPI',
        'i2c': 'I2C', 'I2C': 'I2C', 'Iic': 'I2C',
        'can': 'CAN', 'CAN': 'CAN', 'Can': 'CAN',
        'at': 'AT', 'AT': 'AT', 'At': 'AT',
        'api': 'API', 'API': 'API', 'Api': 'API',
        'sdk': 'SDK', 'SDK': 'SDK', 'Sdk': 'SDK',
        'app': 'APP', 'APP': 'APP', 'App': 'APP',
        'pc': 'PC', 'PC': 'PC', 'Pc': 'PC',
        'web': 'Web', 'Web': 'Web', 'WEB': 'Web',
        'h5': 'H5', 'H5': 'H5',
        'bug': '问题', 'BUG': '问题', 'Bug': '问题',
    },
    '问题类型': {
        '缺陷': '问题',
        '故障': '异常',
        '异常': '异常情况',
        '错误': '问题',
        '现象': '现象',
        '情况': '情况',
        '状态': '状态',
        '表现': '表现',
        '结果': '结果',
        '效果': '效果',
        '性能': '性能指标',
        '功能': '功能',
        '特性': '特性',
    }
}


def polish_description(desc: str, status: str = "已完成") -> str:
    """润色工作内容描述，使其更专业规范
    
    Args:
        desc: 工作内容描述
        status: 状态后缀，默认"已完成"，可选"进行中"、"未开始"等
    """
    if not desc:
        return desc

    lines = desc.strip().split("\n")
    polished_lines = []

    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue

        # 移除已有的序号
        line = re.sub(r'^\d+[\.\、\)]\s*', '', line)
        line = re.sub(r'^[\-\*\•]\s*', '', line)
        # 移除已有的状态后缀
        line = re.sub(r'---\S+$', '', line)

        # 使用占位符机制避免重复替换
        placeholders = {}
        counter = [0]

        def replace_with_placeholder(match):
            key = match.group(0)
            if key not in placeholders:
                counter[0] += 1
                placeholder = f"__PLACEHOLDER_{counter[0]}__"
                placeholders[placeholder] = POLISH_MAP.get(key, key)
                return placeholder
            return match.group(0)

        # 按长度降序匹配，避免短词先匹配
        sorted_keys = sorted(POLISH_MAP.keys() - {'状态词', '技术术语', '问题类型'}, key=len, reverse=True)
        pattern = '|'.join(re.escape(k) for k in sorted_keys if k in line)
        if pattern:
            line = re.sub(pattern, replace_with_placeholder, line)

        # 替换状态词
        for old, new in POLISH_MAP['状态词'].items():
            if old in line:
                counter[0] += 1
                placeholder = f"__PLACEHOLDER_{counter[0]}__"
                placeholders[placeholder] = new
                line = line.replace(old, placeholder)

        # 替换技术术语
        for old, new in POLISH_MAP['技术术语'].items():
            if old in line:
                counter[0] += 1
                placeholder = f"__PLACEHOLDER_{counter[0]}__"
                placeholders[placeholder] = new
                line = line.replace(old, placeholder)

        # 替换问题类型
        for old, new in POLISH_MAP['问题类型'].items():
            if old in line:
                counter[0] += 1
                placeholder = f"__PLACEHOLDER_{counter[0]}__"
                placeholders[placeholder] = new
                line = line.replace(old, placeholder)

        # 恢复占位符
        for placeholder, value in placeholders.items():
            line = line.replace(placeholder, value)

        # 添加序号和状态后缀（序号后加空格，确保 markdown 正确渲染为有序列表）
        polished_lines.append(f"{i}. {line}---{status}")

    return "\n".join(polished_lines)


def get_creds():
    u, p = os.environ.get("WORK_USER"), os.environ.get("WORK_PASS")
    if u and p:
        return u, p
    if os.path.exists(CONF):
        c = json.load(open(CONF, encoding="utf-8"))
        return c["username"], c["password"]
    raise SystemExit("缺少凭据：设置 WORK_USER / WORK_PASS 环境变量，或创建 .credentials.json")


def get_month_range(month_str=None):
    """获取月份范围"""
    if month_str:
        y, m = map(int, month_str.split("-"))
    else:
        today = date.today()
        y, m = today.year, today.month
    start = f"{y:04d}-{m:02d}-01"
    if m == 12:
        end = f"{y+1:02d}-01-01"
    else:
        end = f"{y:04d}-{m+1:02d}-01"
    return start, end


def list_work(client, month=None):
    """列出工时"""
    start, end = get_month_range(month)
    works = client.get_work_list(start, end)
    if not works:
        print("无工时记录")
        return

    print(f"{'日期':<12}{'状态':<8}{'工时':<8}{'加班':<8}{'类型':<6}{'摘要'}")
    print("-" * 80)
    for w in works:
        status = "已提交" if w.get("status") == "2" else "未提交"
        wtype = "工作日" if w.get("type") == "0" else "休息日" if w.get("type") == "1" else "其他"
        summary = (w.get("summary") or "")[:30]
        print(f"{w['reportDate']:<12}{status:<8}{w['workTime']:<8}{w['overtime']:<8}{wtype:<6}{summary}")


def submit_work_interactive(client, date_str=None, project_id=None, work_hours=None, description=None, summary=None):
    """交互式提交工时"""
    # 1. 获取项目列表
    projects = client.get_projects()
    if not projects:
        print("无法获取项目列表")
        return False

    # 2. 选择项目
    if not project_id:
        print("\n可用项目:")
        for i, p in enumerate(projects):
            print(f"  {i+1}. {p['projectName']} ({p['projectPhase']}) - {p['projectManager']}")
        idx = input("\n选择项目 (输入序号): ").strip()
        if not idx.isdigit() or int(idx) < 1 or int(idx) > len(projects):
            print("无效选择")
            return False
        project = projects[int(idx) - 1]
    else:
        project = next((p for p in projects if p["id"] == str(project_id)), None)
        if not project:
            print(f"项目 {project_id} 不存在")
            return False

    # 3. 输入工时
    if not work_hours:
        work_hours = input(f"\n工时 (小时，默认 9.0): ").strip() or "9.0"

    # 4. 输入工作内容
    if not description:
        description = input("\n工作内容描述（详细内容，每行一条）：").strip()
        if not description:
            print("工作内容不能为空")
            return False

    # 4.2 输入工作流描述（简洁）
    if not summary:
        summary = input("\n工作流描述（简洁，如：测试 QDM559 版本）：").strip()
        if not summary:
            print("工作流描述不能为空")
            return False

    # 4.3 选择状态
    print("\n可选状态：1) 已完成  2) 进行中  3) 未开始")
    status_choice = input("选择状态 (默认 1): ").strip() or "1"
    status_map = {"1": "已完成", "2": "进行中", "3": "未开始"}
    status = status_map.get(status_choice, "已完成")

    # 4.5 润色工作内容
    polished_desc = polish_description(description, status)
    print(f"\n原始描述：{description}")
    print(f"润色后：{polished_desc}")
    use_polished = input("\n使用润色后的描述？(y/n，默认 y): ").strip().lower()
    if use_polished != "n":
        description = polished_desc

    # 5. 构建提交数据
    today = date_str or date.today().strftime("%Y-%m-%d")
    # summary 用简洁描述，description 用详细列表
    summary_html = f"<p>{summary}</p>"
    payload = {
        "userId": "18178",
        "type": "2",
        "summary": summary_html,
        "workTime": str(work_hours),
        "overTime": 0,
        "remark": "",
        "detailVos": [{
            "projectId": project["id"],
            "productNameId": project["productNameId"],
            "projectName": project["projectName"],
            "workTime": str(work_hours),
            "projectPhase": project["projectPhase"],
            "productLine": project["productLineName"],
            "overtime": "0.0",
            "description": description,
            "projectManager": project["projectManager"],
            "coManager": project.get("coManager", ""),
            "options": []
        }],
        "status": "1",
        "isBatch": False
    }

    # 6. 确认并提交
    print(f"\n=== 确认提交 ===")
    print(f"日期：{today}")
    print(f"项目：{project['projectName']}")
    print(f"工时：{work_hours}h")
    print(f"内容：{description}")
    confirm = input("\n确认提交？(y/n): ").strip().lower()
    if confirm != "y":
        print("已取消")
        return False

    resp = client.submit_work(payload)
    if resp.get("success"):
        print("\n✓ 提交成功!")
        return True
    else:
        print(f"\n✗ 提交失败：{resp.get('msg', '未知错误')}")
        return False


def withdraw_work(client, date_str=None):
    """撤销已提交的工时"""
    # 获取工时列表
    start, end = get_month_range()
    works = client.get_work_list(start, end)
    
    # 筛选已提交的工时 (status=2)
    submitted = [w for w in works if w.get("status") == "2"]
    if not submitted:
        print("没有已提交的工时记录")
        return False
    
    # 如果指定了日期，筛选该日期
    if date_str:
        submitted = [w for w in submitted if w["reportDate"] == date_str]
    
    if not submitted:
        print(f"{'日期':<12}{'状态':<8}{'工时':<8}{'加班':<8}{'项目'}")
        print("-" * 60)
        for w in submitted:
            print(f"{w['reportDate']:<12}{'已提交':<8}{w['workTime']:<8}{w['overtime']:<8}{w.get('summary', '')[:20]}")
        return False
    
    print(f"{'日期':<12}{'状态':<8}{'工时':<8}{'加班':<8}{'项目'}")
    print("-" * 60)
    for i, w in enumerate(submitted, 1):
        print(f"{i}. {w['reportDate']:<10}{'已提交':<8}{w['workTime']:<8}{w['overtime']:<8}{w.get('summary', '')[:20]}")
    
    idx = input("\n选择要撤销的记录 (输入序号，多个用逗号分隔): ").strip()
    try:
        indices = [int(x.strip()) for x in idx.split(",")]
        selected = [submitted[i-1] for i in indices if 1 <= i <= len(submitted)]
    except (ValueError, IndexError):
        print("无效选择")
        return False
    
    for w in selected:
        print(f"\n撤销 {w['reportDate']} 的工时记录...")
        resp = client.withdraw_work(w["id"])
        if resp.get("success"):
            print(f"  ✓ {w['reportDate']} 撤销成功")
        else:
            print(f"  ✗ {w['reportDate']} 撤销失败：{resp.get('msg', '未知错误')}")
    
    return True


def resubmit_work(client, date_str=None):
    """重新提交已撤销的工时"""
    # 获取工时列表
    start, end = get_month_range()
    works = client.get_work_list(start, end)
    
    # 筛选未提交的工时 (status=1)
    pending = [w for w in works if w.get("status") == "1"]
    if not pending:
        print("没有待提交的工时记录")
        return False
    
    # 如果指定了日期，筛选该日期
    if date_str:
        pending = [w for w in pending if w["reportDate"] == date_str]
    
    if not pending:
        print("没有匹配的待提交记录")
        return False
    
    print(f"{'日期':<12}{'状态':<8}{'工时':<8}{'加班':<8}")
    print("-" * 40)
    for i, w in enumerate(pending, 1):
        print(f"{i}. {w['reportDate']:<10}{'未提交':<8}{w['workTime']:<8}{w['overtime']:<8}")
    
    idx = input("\n选择要重新提交的记录 (输入序号，多个用逗号分隔): ").strip()
    try:
        indices = [int(x.strip()) for x in idx.split(",")]
        selected = [pending[i-1] for i in indices if 1 <= i <= len(pending)]
    except (ValueError, IndexError):
        print("无效选择")
        return False
    
    for w in selected:
        print(f"\n重新提交 {w['reportDate']}...")
        # 获取编辑详情
        detail = client.get_edit_detail(w["id"])
        if not detail:
            print(f"  ✗ {w['reportDate']} 获取详情失败")
            continue
        
        # 构建提交数据
        payload = {
            "id": w["id"],
            "userId": w["userId"],
            "type": w.get("type", "2"),
            "summary": w.get("summary", ""),
            "workTime": str(w.get("workTime", "0")),
            "overTime": w.get("overtime", 0),
            "remark": w.get("remark", ""),
            "detailVos": detail.get("detailVos", []),
            "status": "1",
            "isBatch": False
        }
        
        resp = client.submit_work(payload)
        if resp.get("success"):
            print(f"  ✓ {w['reportDate']} 重新提交成功")
        else:
            print(f"  ✗ {w['reportDate']} 重新提交失败：{resp.get('msg', '未知错误')}")
    
    return True


def main():
    ap = argparse.ArgumentParser(description="移远工时自动填写")
    ap.add_argument("--list", action="store_true", help="查看工时列表")
    ap.add_argument("--submit", action="store_true", help="提交工时")
    ap.add_argument("--withdraw", action="store_true", help="撤销已提交的工时")
    ap.add_argument("--resubmit", action="store_true", help="重新提交已撤销的工时")
    ap.add_argument("--month", help="YYYY-MM 指定月份")
    ap.add_argument("--date", help="YYYY-MM-DD 指定日期")
    ap.add_argument("--project", help="项目 ID")
    ap.add_argument("--hours", help="工时 (小时)")
    ap.add_argument("--desc", help="工作内容描述（详细）")
    ap.add_argument("--summary", help="工作流描述（简洁）")
    ap.add_argument("--auto", action="store_true", help="自动模式（跳过确认）")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    a = ap.parse_args()

    u, p = get_creds()
    client = WorkClient(u, p).login()

    if a.list:
        list_work(client, a.month)
    elif a.submit:
        submit_work_interactive(client, a.date, a.project, a.hours, a.desc, a.summary)
    elif a.withdraw:
        withdraw_work(client, a.date)
    elif a.resubmit:
        resubmit_work(client, a.date)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
