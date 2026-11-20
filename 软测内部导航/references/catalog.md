# 导航目录快照（2026-11-20）

> 静态快照，仅供快速了解全貌。**实时状态以 `python scripts/nav.py <关键词>` 为准**；写入（增删改）前用 `cat list` / `link list` 取 id。
> 图例：✅ 已有 GitHub skill 可自动化；🔗 仅链接（文档/系统，无 skill）；🚧 占位/未实现。

## 测试环境搭建（9 条）

| 入口 | 状态 | 关联 skill / 说明 |
|---|---|---|
| Outlook邮箱 | ✅ | https://github.com/venus-li-sssss/test/tree/main/msgraph-delegated-setup -- 读写 Outlook 邮件：设备码登录+令牌自动续期、新建/回复草稿（不发送）、收件箱搜索、多文件夹监控、日历 |
| Aboot烧录 | ✅ | https://github.com/venus-li-sssss/test/tree/main/flash-tools -- 烧录 CLI：Aboot/FreqChip/QFIL/QFlash 进下载模式与静默烧录<br>https://github.com/venus-li-sssss/test/tree/main/feishu-software-download -- 经「飞书云盘」：按关键词搜飞书云盘并下载文件（免扫码）；也能读 wiki/云文档正文<br>https://quectel.feishu.cn/drive/folder/Yad7fK4qDl71mjdGMIAcgTHTn7f?from=space_personal_filelist -- 资源·Aboot 烧录工具与版本包（与卡片地址同一目录，AI 可直接用这个 URL 定位） |
| FreqChip烧录 | ✅ | https://github.com/venus-li-sssss/test/tree/main/flash-tools -- 烧录 CLI：Aboot/FreqChip/QFIL/QFlash 进下载模式与静默烧录<br>https://github.com/venus-li-sssss/test/tree/main/feishu-software-download -- 经「飞书云盘」：按关键词搜飞书云盘并下载文件（免扫码）；也能读 wiki/云文档正文<br>https://quectel.feishu.cn/drive/folder/X1tPf4dHBlqq08d4QBwcQBVjnXf?from=space_personal_filelist -- 资源·FreqChip 烧录工具（FR801XH/FR30XX/FR508X）与固件（与卡片地址同一目录） |
| Jlink烧录 | ✅ | https://github.com/venus-li-sssss/test/tree/main/%E6%97%A5%E5%BF%97%E6%8A%93%E5%8F%96 -- 串口 / J-Link RTT / RTK 差分日志抓取，输出带 ms 时间戳 .log + summary |
| QFLASH烧录 | ✅ | https://github.com/venus-li-sssss/test/tree/main/qflash -- QFlash 烧录（QCMM/firehose）+ 内置 STM32/Unisoc/Rockchip CLI<br>https://github.com/venus-li-sssss/test/tree/main/flash-tools -- 烧录 CLI：Aboot/FreqChip/QFIL/QFlash 进下载模式与静默烧录<br>https://github.com/venus-li-sssss/test/tree/main/feishu-software-download -- 经「飞书云盘」：按关键词搜飞书云盘并下载文件（免扫码）；也能读 wiki/云文档正文<br>https://quectel.feishu.cn/drive/folder/VDGtf5XA8l7pnCdHjmBcjR5Anbf?from=space_personal_filelist -- 资源·QFlash 安装包（QFlash_V7.5/V8.1）（与卡片地址同一目录） |
| QFIL烧录 | ✅ | https://github.com/venus-li-sssss/test/tree/main/flash-tools -- 烧录 CLI：Aboot/FreqChip/QFIL/QFlash 进下载模式与静默烧录<br>https://github.com/venus-li-sssss/test/tree/main/qflash -- QFlash 烧录（QCMM/firehose）+ 内置 STM32/Unisoc/Rockchip CLI<br>https://github.com/venus-li-sssss/test/tree/main/feishu-software-download -- 经「飞书云盘」：按关键词搜飞书云盘并下载文件（免扫码）；也能读 wiki/云文档正文<br>https://quectel.feishu.cn/drive/folder/Ag16fe9JElm7fmdQ6AacxvF2nTh?from=space_personal_filelist -- 资源·QFIL/QPST 安装包（与卡片地址同一目录） |
| CAN日志抓取 | ✅ | https://github.com/venus-li-sssss/test/tree/main/%E6%97%A5%E5%BF%97%E6%8A%93%E5%8F%96 -- 串口 / J-Link RTT / RTK 差分日志抓取，输出带 ms 时间戳 .log + summary |
| 日志抓取 | ✅ | https://github.com/venus-li-sssss/test/tree/main/%E6%97%A5%E5%BF%97%E6%8A%93%E5%8F%96 -- 串口 / J-Link RTT / CAN(ZLG) / RTK 差分日志抓取，输出带 ms 时间戳 .log + summary<br>https://github.com/venus-li-sssss/test/tree/main/feishu-software-download -- 经「飞书云盘」：按关键词搜飞书云盘并下载文件（免扫码）；也能读 wiki/云文档正文<br>https://quectel.feishu.cn/drive/folder/Dh9WfeMqqlw99adyXMJclf9Mngg -- 资源·日志抓取 v3.10 云盘目录：日志抓取.exe / 串口日志抓取.exe(旧名同版本) / README / 源码 / zlgcan.zip(解压到 exe 同级=开 CAN)；exe 只能放 C 盘运行 |
| 做升级包 | ✅ | https://github.com/venus-li-sssss/test/tree/main/%E5%81%9A%E5%8C%85 -- FOTA 升级包制作：全量包/差分包/最小系统包，config 自动生成 + 产物自检<br>https://github.com/venus-li-sssss/test/tree/main/feishu-software-download -- 经「飞书云盘」：按关键词搜飞书云盘并下载文件（免扫码）；也能读 wiki/云文档正文<br>https://quectel.feishu.cn/drive/folder/HVQwfjtCGlXh85dBLhmcIPtWnBf -- 资源·做包工具与官方文档：adiff.exe / FBFMake_CF_V1.6-150.exe / config 与 config_app 模板 / fbfmake*.bat / 说明 PDF，缺工具从这里下（工具只能放纯 ASCII 路径） |

## 测试相关（13 条）

| 入口 | 状态 | 关联 skill / 说明 |
|---|---|---|
| 日志分析-skill | ✅ | https://github.com/venus-li-sssss/test/tree/main/log-analysis -- 设备日志/脚本日志分析：定位问题、还原执行流程 |
| 测试用例生成 | 🔗 | 输入协议文本 → AI 生成测试用例（妙搭网页应用，需人工操作；暂无 skill） |
| JIRA系统 | ✅ | https://github.com/venus-li-sssss/test/tree/main/jira-data-access -- JQL 查询、建单、改单、传附件（默认只看 ST-BUG 且未关闭） |
| 内部报告生成 | ✅ | https://github.com/venus-li-sssss/test/tree/main/%E7%89%88%E6%9C%AC%E7%B3%BB%E7%BB%9F%E6%B5%8B%E8%AF%95%E6%8A%A5%E5%91%8A%E7%94%9F%E6%88%90 -- 输入用例+JIRA+压力+路测数据 → 输出系统测试报告 docx/xlsx<br>https://github.com/venus-li-sssss/test/tree/main/%E8%B7%AF%E6%B5%8B%E5%85%A8%E6%B5%81%E7%A8%8B -- 输入设备/高精度 NMEA → 轨迹对比 KML + 截图 + CEP 表 + 路测报告<br>https://github.com/venus-li-sssss/test/tree/main/changelist2xlsx -- 修改点系统导入/导出、自动新增测试用例<br>https://github.com/venus-li-sssss/test/tree/main/jira-data-access -- JQL 查询、建单、改单、传附件（默认只看 ST-BUG 且未关闭）<br>https://github.com/venus-li-sssss/test/tree/main/%E5%86%85%E9%83%A8%E6%8A%A5%E5%91%8A%E8%BD%AC%E9%82%AE%E4%BB%B6%E8%8D%89%E7%A8%BF -- 经「内部报告转邮件草稿」：报告→邮件草稿：拿上一版邮件 HTML 改造、建 reply-all、传附件、回读校验 |
| 内部报告转邮件草稿 | ✅ | https://github.com/venus-li-sssss/test/tree/main/%E5%86%85%E9%83%A8%E6%8A%A5%E5%91%8A%E8%BD%AC%E9%82%AE%E4%BB%B6%E8%8D%89%E7%A8%BF -- 报告→邮件草稿：拿上一版邮件 HTML 改造、建 reply-all、传附件、回读校验 |
| 对外报告-skill | ✅ | https://github.com/venus-li-sssss/test/tree/main/%E5%AF%B9%E5%A4%96%E6%8A%A5%E5%91%8A -- 由内部报告或测试用例生成对外报告 |
| 修改点系统 | ✅ | https://github.com/venus-li-sssss/test/tree/main/changelist2xlsx -- 修改点系统导入/导出、自动新增测试用例 |
| 送测邮件→修改点→建用例 | ✅ | https://github.com/venus-li-sssss/test/tree/main/%E9%80%81%E6%B5%8B%E9%82%AE%E4%BB%B6%E5%88%B0%E4%BF%AE%E6%94%B9%E7%82%B9 -- 流程编排：邮件→SMOD修改点→用例→报告一站式（sendtest_flow.py，默认 dry-run）<br>https://github.com/venus-li-sssss/test/tree/main/changelist2xlsx -- 修改点导入/建用例/导报告的执行层（smod_changelist_import.py）<br>https://github.com/venus-li-sssss/test/tree/main/msgraph-delegated-setup -- 读送测邮件、取正文与附件（MS Graph 委托登录） |
| FCT自动化测试 | ✅ | https://github.com/venus-li-sssss/test/tree/main/pressure-test/pressure-test-fct -- FCT 自动化测试流程：实机跑批、写完还原(--write-restore)、结果核对与归档（archive_results.py） |
| 版本自动化测试 | ✅ | https://github.com/venus-li-sssss/test/tree/main/pressure-test/pressure-test-release -- 版本自动化测试流程：版本目录规范、六步流程、报告命名、与 FCT/报告/修改点 skill 的边界<br>https://github.com/venus-li-sssss/test/tree/main/pressure-test/pressure-test-pytest -- 用例集 → pytest 伪脚本工程：用例层只打印用例文字、基础类经 uid 注册表解耦，支持 --group-by scene 按环境场景切分 + allure 报告<br>https://github.com/venus-li-sssss/test/tree/main/%E7%89%88%E6%9C%AC%E7%B3%BB%E7%BB%9F%E6%B5%8B%E8%AF%95%E6%8A%A5%E5%91%8A%E7%94%9F%E6%88%90 -- 流程末端：用例+JIRA+压力+路测数据 → 系统测试报告 docx/xlsx（可推送妙搭报告平台） |
| Windows桌面自动化 | ✅ | https://github.com/venus-li-sssss/test/tree/main/windows-uiautomation -- Windows桌面UIA自动化：控件dump/状态判定/点击重试/独占串口交接，附可复用脚本 |
| 压力脚本编写 | ✅ | https://github.com/venus-li-sssss/test/tree/main/pressure-test -- 压测脚本总入口：基础类→超类→流程→主循环 四层架构 + 子技能路由表<br>https://github.com/venus-li-sssss/test/tree/main/pressure-test/pressure-test-generator -- 生成脚本骨架与 device.yaml（generate_script.py / generate_yaml.py）<br>https://github.com/venus-li-sssss/test/tree/main/pressure-test/pressure-test-framework -- 超类组合、流程模板、主循环、ReTry、统计与状态码口径<br>https://github.com/venus-li-sssss/test/tree/main/pressure-test/pressure-test-uiautomator -- Android APP UI 压测（uiautomator2 相对定位、组合指令、retry）<br>https://github.com/venus-li-sssss/test/tree/main/pressure-test/pressure-test-webui -- Web UI 压测（Selenium/Playwright 多定位策略、截图取证）<br>https://quectel.feishu.cn/drive/folder/I8qnfDCJilWIdhdesFYcM4gMnlf -- 经「压测脚本网盘」：资源·压测脚本云盘根目录。找脚本路径=产品线(Tracker/两轮车/CPE-MIFI/Aiot) → 项目(QDM562/QDC538/…) → 脚本类型目录(<项目>_<分支>_<功能>，如 QDM562_主分支_上位机升级压测)。每个脚本目录里固定有四样：脚本.py、device.yaml、功能脚本索引.md、测试环境搭建.md(可选)<br>https://github.com/venus-li-sssss/test/tree/main/feishu-software-download -- 经「压测脚本网盘」：经「飞书云盘」：按关键词搜/下文件，也可 tree --folder <token> 按目录列表定位脚本目录（免扫码）<br>https://github.com/venus-li-sssss/test/tree/main/pressure-test -- 经「压测脚本网盘」：没有现成脚本时，用它生成压测脚本骨架（开关机/找网/继电器等） |
| 基类编写 | ✅ | https://github.com/venus-li-sssss/test/tree/main/pressure-test/pressure-test-bases -- 基础类模板：Serial / CAN(ZLG) / CMD 窗口 / AT / Jlink-RTT / Relay / File / Platform API + 超类组合示例 + 日志规范<br>https://github.com/venus-li-sssss/test/tree/main/super-client -- 组合模式超类：平台客户端 cookie/token 管理、自动续期、接口超时重试<br>https://github.com/venus-li-sssss/test/tree/main/api-class-generator -- HAR/接口文档 → Python API 类（requests + session），平台类底座<br>https://github.com/venus-li-sssss/test/tree/main/account-login-skill -- 账号登录型类的写法：凭证不进仓库、自动续期、MFA 处理<br>https://github.com/venus-li-sssss/test/tree/main/pressure-test/pressure-test-bases -- 资源·基础类模板目录本身：模板代码块 + 超类组合 + 注意事项（AI 常漏看卡片 url 就是目录，故再留一条） |

## 项目信息（2 条）

| 入口 | 状态 | 关联 skill / 说明 |
|---|---|---|
| QDM562 项目知识 | ✅ | https://github.com/venus-li-sssss/test/tree/main/flash-tools -- 烧录执行层：aboot/adownload 命令与「客户信息区 customer_fs/ext_flash 不烧」规则（references/aboot-flash.md）<br>https://github.com/venus-li-sssss/test/tree/main/qdm562-project -- QDM562 项目知识：认串口（哪个 COM 是什么口）、上位机升级压测、查 GNSS 版本号 Build19128/27526、抓日志判活、免锁屏与踩坑清单 |
| 项目信息总表（云盒/中控） | 🔗 | 项目分类多维表格【项目分类】云盒/中控：后续新项目信息统一记录在这里，每个项目一个子页。 |

## 资源（11 条）

| 入口 | 状态 | 关联 skill / 说明 |
|---|---|---|
| GNSS的RTK账号信息 | ✅ | https://github.com/venus-li-sssss/test/tree/main/feishu-docs -- 飞书云文档/知识库/多维表格读写：读正文、查表、按字段过滤、导 CSV/JSON（机器人身份，免扫码） |
| GNSS资料 | ✅ | https://github.com/venus-li-sssss/test/tree/main/feishu-docs -- 飞书云文档/知识库/多维表格读写：读正文、查表、按字段过滤、导 CSV/JSON（机器人身份，免扫码） |
| 移远软件资源中心 | ✅ | https://github.com/venus-li-sssss/test/tree/main/toolhub-software -- 移远软件资源中心下载 skill：移远 SSO 账号自动登录（密码 RSA 加密、凭据外置）、按关键词搜资源、查版本、下载最新或指定版本到本地、支持断点续传 |
| 通用模组文档 | ✅ | https://github.com/venus-li-sssss/test/tree/main/feishu-software-download -- 经「飞书云盘」：按关键词搜飞书云盘并下载文件（免扫码）；也能读 wiki/云文档正文<br>https://quectel.feishu.cn/drive/folder/Clp9fJVVJlkPhnd9RkLcKcqbnYc -- 资源·通用模组指令手册与硬件文档（与卡片地址同一目录） |
| 基础软件下载 | ✅ | https://github.com/venus-li-sssss/test/tree/main/feishu-software-download -- 经「飞书云盘」：按关键词搜飞书云盘并下载文件（免扫码）；也能读 wiki/云文档正文 |
| 移远网盘 | ✅ | https://github.com/venus-li-sssss/test/tree/main/qdisk-quectel -- 移远网盘(qdisk) 浏览/下载版本与数据<br>https://qdisk.quectel.com/company/list?lang=zh-CN -- 资源·移远网盘入口，版本/项目数据在 部门文件/IKOTEK/Project/ODM Project Files/SWE/external/MOB |
| 远程服务器工具 | ✅ | https://github.com/venus-li-sssss/test/tree/main/feishu-docs -- 飞书云文档/知识库/多维表格读写：读正文、查表、按字段过滤、导 CSV/JSON（机器人身份，免扫码） |
| 飞书云盘 | ✅ | https://github.com/venus-li-sssss/test/tree/main/feishu-software-download -- 按关键词搜飞书云盘并下载文件（免扫码）；也能读 wiki/云文档正文 |
| 压测脚本网盘 | ✅ | https://quectel.feishu.cn/drive/folder/I8qnfDCJilWIdhdesFYcM4gMnlf -- 资源·压测脚本云盘根目录。找脚本路径=产品线(Tracker/两轮车/CPE-MIFI/Aiot) → 项目(QDM562/QDC538/…) → 脚本类型目录(<项目>_<分支>_<功能>，如 QDM562_主分支_上位机升级压测)。每个脚本目录里固定有四样：脚本.py、device.yaml、功能脚本索引.md、测试环境搭建.md(可选)<br>https://github.com/venus-li-sssss/test/tree/main/feishu-software-download -- 经「飞书云盘」：按关键词搜/下文件，也可 tree --folder <token> 按目录列表定位脚本目录（免扫码）<br>https://github.com/venus-li-sssss/test/tree/main/pressure-test -- 没有现成脚本时，用它生成压测脚本骨架（开关机/找网/继电器等） |
| excel插入图片或者对象 | 🔗 | excel的插件，安装后可以通过ctrl+Q插入图片或者对象，用于测试的时候放截图到excel |
| 升级包 | ✅ | https://github.com/venus-li-sssss/test/tree/main/feishu-software-download -- 经「飞书云盘」：按关键词搜/下升级包，也可 tree --folder <token> 按目录列<br>https://github.com/venus-li-sssss/test/tree/main/%E5%81%9A%E5%8C%85 -- 做升级包：全量包(app整包)/差分包(含回滚)/最小系统包，config 按 partition.bin 自动生成 + 产物自检<br>https://quectel.feishu.cn/drive/folder/TqwAf5NvelKDNvd8quMcyECbnlh -- 资源·升级包云盘根目录（与本卡地址同一目录）：项目 → 差分包/全量包 → .bin |

## 流程（0 条）

（空分类）

## 软测内部飞书知识库（12 条）

| 入口 | 状态 | 关联 skill / 说明 |
|---|---|---|
| BPM 领用网址 | 🔗 | 领用样机、申请采购物品等 |
| Tracker的知识库 | ✅ | https://github.com/venus-li-sssss/test/tree/main/feishu-docs -- 飞书云文档/知识库/多维表格读写：读正文、查表、按字段过滤、导 CSV/JSON（机器人身份，免扫码） |
| 两轮车项目知识库 | ✅ | https://github.com/venus-li-sssss/test/tree/main/feishu-docs -- 飞书云文档/知识库/多维表格读写：读正文、查表、按字段过滤、导 CSV/JSON（机器人身份，免扫码） |
| 压测脚本记录 | ✅ | https://github.com/venus-li-sssss/test/tree/main/feishu-docs -- 飞书云文档/知识库/多维表格读写：读正文、查表、按字段过滤、导 CSV/JSON（机器人身份，免扫码） |
| 日常工作流程 | ✅ | https://github.com/venus-li-sssss/test/tree/main/feishu-docs -- 飞书云文档/知识库/多维表格读写：读正文、查表、按字段过滤、导 CSV/JSON（机器人身份，免扫码） |
| AI方案知识库 | ✅ | https://github.com/venus-li-sssss/test/tree/main/feishu-docs -- 飞书云文档/知识库/多维表格读写：读正文、查表、按字段过滤、导 CSV/JSON（机器人身份，免扫码） |
| FWA行业知识库 | ✅ | https://github.com/venus-li-sssss/test/tree/main/feishu-docs -- 飞书云文档/知识库/多维表格读写：读正文、查表、按字段过滤、导 CSV/JSON（机器人身份，免扫码） |
| 标准模板 | ✅ | https://github.com/venus-li-sssss/test/tree/main/feishu-docs -- 飞书云文档/知识库/多维表格读写：读正文、查表、按字段过滤、导 CSV/JSON（机器人身份，免扫码）<br>https://github.com/venus-li-sssss/test/tree/main/feishu-software-download -- 经「飞书云盘」：按关键词搜飞书云盘并下载文件（免扫码）；也能读 wiki/云文档正文 |
| 新人培训计划 | ✅ | https://github.com/venus-li-sssss/test/tree/main/feishu-docs -- 飞书云文档/知识库/多维表格读写：读正文、查表、按字段过滤、导 CSV/JSON（机器人身份，免扫码） |
| 样机管理库 | ✅ | https://github.com/venus-li-sssss/test/tree/main/feishu-docs -- 飞书云文档/知识库/多维表格读写：读正文、查表、按字段过滤、导 CSV/JSON（机器人身份，免扫码） |
| 团队架构 | ✅ | https://github.com/venus-li-sssss/test/tree/main/feishu-docs -- 飞书云文档/知识库/多维表格读写：读正文、查表、按字段过滤、导 CSV/JSON（机器人身份，免扫码） |
| 物资管理 | ✅ | https://github.com/venus-li-sssss/test/tree/main/feishu-docs -- 飞书云文档/知识库/多维表格读写：读正文、查表、按字段过滤、导 CSV/JSON（机器人身份，免扫码） |

## 公司官网（5 条）

| 入口 | 状态 | 关联 skill / 说明 |
|---|---|---|
| EIP官网 | 🔗 | 公司网页的导航页面 |
| 绩效系统 | 🔗 | 绩效系统 |
| 移远社区 | 🔗 | 移远社区，公司内部论坛 |
| 移远会议 | ✅ | https://github.com/venus-li-sssss/test/tree/main/qmeeting-rooms -- 查/订/取消会议室，能出会议室与导航图片 |
| 工位系统 | 🔗 | 查看工位位置 |

## 软件下载网址（0 条）

（空分类）

## 软测内部应用（1 条）

| 入口 | 状态 | 关联 skill / 说明 |
|---|---|---|
| AI任务管理平台 | 🔗 | 用来下发无人值守任务，或者查看当前正在用平台上的SKill执行的AI任务 |

## skill仓库（3 条）

| 入口 | 状态 | 关联 skill / 说明 |
|---|---|---|
| skill仓库-github | ✅ | https://github.com/venus-li-sssss/test/tree/main/skill%E4%BB%93%E5%BA%93%E5%90%8C%E6%AD%A5 -- GitHub 仓库 venus-li-sssss/test 的读写：push/pull/tree/rm |
| skill仓库-妙搭 | ✅ | https://github.com/venus-li-sssss/test/tree/main/%E5%A6%99%E6%90%AD%E4%BB%93%E5%BA%93%E5%90%8C%E6%AD%A5 -- 上传、下载、修改 妙搭的skill仓库 |
| 共享导航页面-skill | ✅ | https://github.com/venus-li-sssss/test/tree/main/%E8%BD%AF%E6%B5%8B%E5%86%85%E9%83%A8%E5%AF%BC%E8%88%AA -- 软测内部导航skill，用于修改//添加/删除本导航页面的数据 |

## IT（1 条）

| 入口 | 状态 | 关联 skill / 说明 |
|---|---|---|
| 工单系统 | 🔗 | IT工单，电脑故障、邮件故障、软件故障等IT问题均可访问该网址提交工单 |

## 产品项目（0 条）

（空分类）

## 人事（1 条）

| 入口 | 状态 | 关联 skill / 说明 |
|---|---|---|
| QHR | 🔗 | 人事各种事情，包括考勤、请假等流程 |

## 行政（1 条）

| 入口 | 状态 | 关联 skill / 说明 |
|---|---|---|
| 移远快递 | 🔗 | 快递寄件 |

## 客户网址（1 条）

| 入口 | 状态 | 关联 skill / 说明 |
|---|---|---|
| 九号平台 | ✅ | https://github.com/venus-li-sssss/test/tree/main/ninebot-project -- 九号 IoT 平台固件包管理与 FOTA 升级/回滚 + APP UI 自动化（uiautomator2 页面导航）<br>https://github.com/venus-li-sssss/test/tree/main/pressure-test/pressure-test-pytest -- 用例集 → pytest 伪脚本 + 真机执行层（APP 页面模式 / 平台 / 上位机三通道 + 升级流程模板）<br>https://quectel.feishu.cn/drive/folder/FJmxfeR5PlTaZxdawlKc0ukpnuf -- 资源·九号内网代理（SOCKS5 127.0.0.1:1080）：连接九号内网_V01.bat 用 ssh -D 建隧道、掉线 5 秒自动重连；隧道没起时平台的任何接口都连不上<br>https://quectel.feishu.cn/drive/folder/OfccfrVr5lcFVBd6i58c336QnCc -- 资源·九号出行 APP 安装包目录（基础软件存放/手机APP）：九号出行APP_v6.10.12.apk（363,371KB，取自现网手机 cn.ninebot.ninebot versionCode 610124275），换机/重装从这里取<br>https://quectel.feishu.cn/file/NdnkbgElXoPvjExGp4Bc4XYQngc -- 资源·九号出行APP_v6.10.12.apk 直链（380,713,031 字节，2026-11-20 从 adb 拉取并上传，Content-Length 已校验一致） |

## 路测（0 条）

（空分类）

## 工时+考勤（1 条）

| 入口 | 状态 | 关联 skill / 说明 |
|---|---|---|
| 工时系统 | ✅ | https://github.com/venus-li-sssss/test/tree/main/quectel-workhours -- 工时的创建/修改/提交/撤销（work.ikotek.com）<br>https://github.com/venus-li-sssss/test/tree/main/quectel-attendance -- 按 QHR 打卡记录算每天工时（双班次规则） |

## 防锁屏（1 条）

| 入口 | 状态 | 关联 skill / 说明 |
|---|---|---|
| 防锁屏 | 🔗 | 每 30s 发送 F15 的桌面防锁屏小工具，在飞书云盘。无 skill，需人工下载安装运行 |

## 写入接口速查

读、写**同一把 Key、同一个前缀** `https://scnrhostplnc.feishuapp.com/app/app_17fwfnp4pvy/openapi/nav`，写库后页面立即生效。

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/links` | 新增链接，分类必须已存在 |
| PATCH | `/links/{id}` | 修改链接，只改传入字段 |
| DELETE | `/links/{id}` | 删除链接，被引用时拒绝 |
| GET | `/categories` | 分类列表，拿分类 id |
| POST | `/categories` | 新增分类 |
| PATCH | `/categories/{id}` | 分类改名，链接自动跟随 |
| DELETE | `/categories/{id}` | 删除空分类 |

脚本封装：`nav.py cat add|rename|delete`、`nav.py link add|update|delete`。
