from scripts.jira_client import generate_report

try:
    report_path = generate_report(
        account='venus.li@ikotek.com',
        password='@@@@@Aa13106680957',
        jql_query="issuetype = ST-BUG AND text ~ 'QDM565' ORDER BY status ASC",
        version='QDM565',
        output_file='C:/Users/venus.li/WorkBuddy/2026-06-25-10-04-10/QDM565_JIRA缺陷报告.docx'
    )
    print(f'报告生成成功：{report_path}')
except Exception as e:
    print(f'执行失败：{e}')
    import traceback
    traceback.print_exc()