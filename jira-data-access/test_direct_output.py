from scripts.jira_client import generate_markdown

result = generate_markdown(
    account='venus.li@ikotek.com',
    password='@@@@@Aa13106680957',
    jql_query="issuetype = ST-BUG AND text ~ 'QDM565' ORDER BY status ASC",
    version='QDM565'
)

print(result)