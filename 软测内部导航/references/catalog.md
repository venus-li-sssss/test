# 导航目录快照（2026-11-18）

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
| 日志抓取 | ✅ | https://github.com/venus-li-sssss/test/tree/main/%E6%97%A5%E5%BF%97%E6%8A%93%E5%8F%96 -- 串口 / J-Link RTT / RTK 差分日志抓取，输出带 ms 时间戳 .log + summary<br>https://github.com/venus-li-sssss/test/tree/main/feishu-software-download -- 经「飞书云盘」：按关键词搜飞书云盘并下载文件（免扫码）；也能读 wiki/云文档正文<br>https://quectel.feishu.cn/drive/folder/THmCfySTUlwC8mdkmcYcAJ2XnZe -- 资源·串口抓取工具（日志抓取.exe）云盘目录；exe 只能放 C 盘运行 |
| 做升级包 | ✅ | https://github.com/venus-li-sssss/test/tree/main/%E5%81%9A%E5%8C%85 -- FOTA 升级包制作：全量包/差分包/最小系统包，config 自动生成 + 产物自检<br>https://github.com/venus-li-sssss/test/tree/main/feishu-software-download -- 经「飞书云盘」：按关键词搜飞书云盘并下载文件（免扫码）；也能读 wiki/云文档正文<br>https://quectel.feishu.cn/drive/folder/HVQwfjtCGlXh85dBLhmcIPtWnBf -- 资源·做包工具与官方文档：adiff.exe / FBFMake_CF_V1.6-150.exe / config 与 config_app 模板 / fbfmake*.bat / 说明 PDF，缺工具从这里下（工具只能放纯 ASCII 路径） |

## 测试相关（7 条）

| 入口 | 状态 | 关联 skill / 说明 |
|---|---|---|
| 日志分析-skill | ✅ | https://github.com/venus-li-sssss/test/tree/main/log-analysis -- 设备日志/脚本日志分析：定位问题、还原执行流程 |
| 测试用例生成 | 🔗 | 输入协议文本 → AI 生成测试用例（妙搭网页应用，需人工操作；暂无 skill） |
| JIRA系统 | ✅ | https://github.com/venus-li-sssss/test/tree/main/jira-data-access -- JQL 查询、建单、改单、传附件（默认只看 ST-BUG 且未关闭） |
| 内部报告生成 | ✅ | https://github.com/venus-li-sssss/test/tree/main/%E7%89%88%E6%9C%AC%E7%B3%BB%E7%BB%9F%E6%B5%8B%E8%AF%95%E6%8A%A5%E5%91%8A%E7%94%9F%E6%88%90 -- 输入用例+JIRA+压力+路测数据 → 输出系统测试报告 docx/xlsx<br>https://github.com/venus-li-sssss/test/tree/main/%E8%B7%AF%E6%B5%8B%E5%85%A8%E6%B5%81%E7%A8%8B -- 输入设备/高精度 NMEA → 轨迹对比 KML + 截图 + CEP 表 + 路测报告<br>https://github.com/venus-li-sssss/test/tree/main/changelist2xlsx -- 修改点系统导入/导出、自动新增测试用例<br>https://github.com/venus-li-sssss/test/tree/main/jira-data-access -- JQL 查询、建单、改单、传附件（默认只看 ST-BUG 且未关闭）<br>https://github.com/venus-li-sssss/test/tree/main/%E5%86%85%E9%83%A8%E6%8A%A5%E5%91%8A%E8%BD%AC%E9%82%AE%E4%BB%B6%E8%8D%89%E7%A8%BF -- 经「内部报告转邮件草稿」：报告→邮件草稿：拿上一版邮件 HTML 改造、建 reply-all、传附件、回读校验 |
| 修改点系统 | ✅ | https://github.com/venus-li-sssss/test/tree/main/changelist2xlsx -- 修改点系统导入/导出、自动新增测试用例 |
| 对外报告-skill | ✅ | https://github.com/venus-li-sssss/test/tree/main/%E5%AF%B9%E5%A4%96%E6%8A%A5%E5%91%8A -- 由内部报告或测试用例生成对外报告 |
| 内部报告转邮件草稿 | ✅ | https://github.com/venus-li-sssss/test/tree/main/%E5%86%85%E9%83%A8%E6%8A%A5%E5%91%8A%E8%BD%AC%E9%82%AE%E4%BB%B6%E8%8D%89%E7%A8%BF -- 报告→邮件草稿：拿上一版邮件 HTML 改造、建 reply-all、传附件、回读校验 |

## 项目信息（2 条）

| 入口 | 状态 | 关联 skill / 说明 |
|---|---|---|
| QDM562 项目知识 | 🔗 | 云盒/中控 QDM562 项目知识：Aboot 烧录（去掉 customer_fs/ext_flash）、串口/DIAG CAT/debug 日志抓取、测试计划与用例。 |
| 项目信息总表（云盒/中控） | 🔗 | 项目分类多维表格【项目分类】云盒/中控：后续新项目信息统一记录在这里，每个项目一个子页。 |

## 资源（10 条）

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
| 压测脚本网盘 | ✅ | https://github.com/venus-li-sssss/test/tree/main/pressure-test -- 生成/运行压力测试脚本（开关机、找网、继电器压测等）<br>https://github.com/venus-li-sssss/test/tree/main/feishu-software-download -- 经「飞书云盘」：按关键词搜飞书云盘并下载文件（免扫码）；也能读 wiki/云文档正文<br>https://quectel.feishu.cn/drive/folder/I8qnfDCJilWIdhdesFYcM4gMnlf -- 资源·压测脚本存放目录（与卡片地址同一目录） |
| excel插入图片或者对象 | 🔗 | excel的插件，安装后可以通过ctrl+Q插入图片或者对象，用于测试的时候放截图到excel |

## 流程（1 条）

| 入口 | 状态 | 关联 skill / 说明 |
|---|---|---|
| 送测邮件→修改点→建用例 | ✅ | https://github.com/venus-li-sssss/test/tree/main/%E9%80%81%E6%B5%8B%E9%82%AE%E4%BB%B6%E5%88%B0%E4%BF%AE%E6%94%B9%E7%82%B9 -- 流程编排：邮件→SMOD修改点→用例→报告一站式（sendtest_flow.py，默认 dry-run）<br>https://github.com/venus-li-sssss/test/tree/main/changelist2xlsx -- 修改点导入/建用例/导报告的执行层（smod_changelist_import.py）<br>https://github.com/venus-li-sssss/test/tree/main/msgraph-delegated-setup -- 读送测邮件、取正文与附件（MS Graph 委托登录） |

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
| 九号平台 | ✅ | https://github.com/venus-li-sssss/test/tree/main/ninebot-project -- 九号 IoT 平台固件包管理与 FOTA 升级/回滚 + APP UI 自动化 |

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
