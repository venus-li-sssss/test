from scripts.jira_client import generate_report

# 使用默认账号密码查询QDM559相关的缺陷数据
report_path = generate_report(
    account="venus.li@ikotek.com",
    password="@@@@@Aa13106680957",
    jql_query="issuetype = ST-BUG AND text ~ 'QDM559' ORDER BY status ASC",
    version="QDM559缺陷查询",
    output_file=r"C:\Users\venus.li\WorkBuddy\2026-06-25-14-05-34\QDM559缺陷报告.docx",
    output_format="docx"
)

print(f"报告已生成: {report_path}")