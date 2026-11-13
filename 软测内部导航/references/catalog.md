# 导航目录快照（2026-11-13）

> 静态快照，仅供快速了解全貌。**实时状态以 `python scripts/nav.py <关键词>` 为准**；写入（增删改）前用 `cat list` / `link list` 取 id。
> 图例：✅ 已有 GitHub skill 可自动化；🔗 仅链接（文档/系统，无 skill）；🚧 占位/未实现。

## 测试环境搭建（8 条）

| 入口 | 状态 | 关联 skill / 说明 |
|---|---|---|
| Aboot烧录 | ✅ | https://github.com/venus-li-sssss/test/tree/main/flash-tools -- aboot烧录的skill<br>https://github.com/venus-li-sssss/test/tree/main/feishu-software-download -- 经「飞书云盘」：飞书云盘获取下载等skill<br>https://quectel.feishu.cn/drive/folder/NiX8f7DWllNgPMdw9Q6cKH9Jnz8 -- 经「飞书云盘」：云盘链接<br>https://quectel.feishu.cn/drive/folder/Yad7fK4qDl71mjdGMIAcgTHTn7f?from=space_personal_filelist -- 缺失Aboot软件的时候，可以到飞书云盘下载 |
| FreqChip烧录 | ✅ | https://github.com/venus-li-sssss/test/tree/main/flash-tools -- FreqChip烧录<br>https://github.com/venus-li-sssss/test/tree/main/feishu-software-download -- 经「飞书云盘」：飞书云盘获取下载等skill<br>https://quectel.feishu.cn/drive/folder/NiX8f7DWllNgPMdw9Q6cKH9Jnz8 -- 经「飞书云盘」：云盘链接<br>https://quectel.feishu.cn/drive/folder/X1tPf4dHBlqq08d4QBwcQBVjnXf?from=space_personal_filelist -- 缺失FreqChip可以到飞书云盘下载 |
| Jlink烧录 | 🚧 | Jlink烧录，还没做，先占位。没有Jlink软件通过云盘拉取https://quectel.feishu.cn/drive/folder/OcRYfpsKVl5AePdo0lxcU0conLf?from=space_personal_filelist |
| QFLASH烧录 | ✅ | https://github.com/venus-li-sssss/test/tree/main/flash-tools -- 通过skill完成QFLASH烧录<br>https://github.com/venus-li-sssss/test/tree/main/feishu-software-download -- 经「飞书云盘」：飞书云盘获取下载等skill<br>https://quectel.feishu.cn/drive/folder/NiX8f7DWllNgPMdw9Q6cKH9Jnz8 -- 经「飞书云盘」：云盘链接<br>https://quectel.feishu.cn/drive/folder/VDGtf5XA8l7pnCdHjmBcjR5Anbf?from=space_personal_filelist -- 没有QFLASH软件可以通过飞书云盘下载 |
| QFIL烧录 | ✅ | https://github.com/venus-li-sssss/test/tree/main/flash-tools -- 通过skill完成QFIL烧录<br>https://github.com/venus-li-sssss/test/tree/main/feishu-software-download -- 经「飞书云盘」：飞书云盘获取下载等skill<br>https://quectel.feishu.cn/drive/folder/NiX8f7DWllNgPMdw9Q6cKH9Jnz8 -- 经「飞书云盘」：云盘链接<br>https://quectel.feishu.cn/drive/folder/Ag16fe9JElm7fmdQ6AacxvF2nTh?from=space_personal_filelist -- 没有QFIL软件可以到飞书云盘下载 |
| CAN日志抓取 | 🔗 | CAN日志抓取，目前没有实现，代码可以抓取，但是与ZCANPRO有区别，还在看，后面应该会做，还没实现 |
| 日志抓取 | ✅ | https://github.com/venus-li-sssss/test/tree/main/feishu-software-download -- 经「飞书云盘」：飞书云盘获取下载等skill<br>https://quectel.feishu.cn/drive/folder/NiX8f7DWllNgPMdw9Q6cKH9Jnz8 -- 经「飞书云盘」：云盘链接<br>https://github.com/venus-li-sssss/test/tree/main/%E6%97%A5%E5%BF%97%E6%8A%93%E5%8F%96 -- 抓取日志的skill<br>https://quectel.feishu.cn/drive/folder/THmCfySTUlwC8mdkmcYcAJ2XnZe -- 没有串口软件可以到飞书云盘下载，注意软件只能运行在C盘 |
| 做升级包 | 🚧 | 还没做，先占位置 |

## 测试相关（6 条）

| 入口 | 状态 | 关联 skill / 说明 |
|---|---|---|
| 日志分析-skill | ✅ | https://github.com/venus-li-sssss/test/tree/main/log-analysis -- 分析日志，一般是脚本日志+设备日志。有时候只有设备日志，定位问题或者分析执行流程 |
| 测试用例生成 | 🔗 | 输入协议，AI生成测试用例 |
| JIRA系统 | ✅ | https://github.com/venus-li-sssss/test/tree/main/jira-data-access -- 提交、修改、获取JIRA数据均可 |
| 内部报告生成 | ✅ | https://github.com/venus-li-sssss/test/tree/main/%E7%89%88%E6%9C%AC%E7%B3%BB%E7%BB%9F%E6%B5%8B%E8%AF%95%E6%8A%A5%E5%91%8A%E7%94%9F%E6%88%90 -- 内部报告生成<br>https://github.com/venus-li-sssss/test/tree/main/%E8%B7%AF%E6%B5%8B%E5%85%A8%E6%B5%81%E7%A8%8B -- 路测报告生成,内部报告的一部分。输入NMEA，输出截图和路测报告<br>https://github.com/venus-li-sssss/test/tree/main/changelist2xlsx -- 修改点系统数据获取<br>https://github.com/venus-li-sssss/test/tree/main/jira-data-access -- JIRA数据获取 |
| 修改点系统 | ✅ | https://github.com/venus-li-sssss/test/tree/main/changelist2xlsx -- 修改、获取等操作均可通过该skill完成 |
| 对外报告-skill | ✅ | https://github.com/venus-li-sssss/test/tree/main/%E5%AF%B9%E5%A4%96%E6%8A%A5%E5%91%8A -- 生成对外报告的，可以输入内部报告来生成，也可以输入测试用例去生成 |

## 资源（9 条）

| 入口 | 状态 | 关联 skill / 说明 |
|---|---|---|
| GNSS的RTK账号信息 | ✅ | https://github.com/venus-li-sssss/test/tree/main/feishu-software-download -- 经「飞书云盘」：飞书云盘获取下载等skill<br>https://quectel.feishu.cn/drive/folder/NiX8f7DWllNgPMdw9Q6cKH9Jnz8 -- 经「飞书云盘」：云盘链接 |
| GNSS资料 | 🔗 | GNSS定位资料，具体资料在它的子目录 https://quectel.feishu.cn/wiki/RGvhwoRqHiAdJkkyvRDcemzbnef https://quectel.feishu.cn/wiki/Avr6w7Y91iX8vvkMazpcNDK1nKe https://quectel.feishu.cn/wiki/H2r6whjaRior8lkEqUQcH4Ponge |
| 通用模组文档 | ✅ | https://github.com/venus-li-sssss/test/tree/main/feishu-software-download -- 经「飞书云盘」：飞书云盘获取下载等skill<br>https://quectel.feishu.cn/drive/folder/NiX8f7DWllNgPMdw9Q6cKH9Jnz8 -- 经「飞书云盘」：云盘链接 |
| 基础软件下载 | ✅ | https://github.com/venus-li-sssss/test/tree/main/feishu-software-download -- 经「飞书云盘」：飞书云盘获取下载等skill<br>https://quectel.feishu.cn/drive/folder/NiX8f7DWllNgPMdw9Q6cKH9Jnz8 -- 经「飞书云盘」：云盘链接 |
| 移远网盘 | ✅ | https://github.com/venus-li-sssss/test/tree/main/qdisk-quectel -- 执行下载数据等操作，拉取数据<br>https://qdisk.quectel.com/company/list?lang=zh-CN -- 移远网盘链接 |
| 远程服务器工具 | 🔗 | 远程服务器工具，从服务器拉取数据或者提交数据到服务器。可以用于window和linux的文件传输 |
| 飞书云盘 | ✅ | https://github.com/venus-li-sssss/test/tree/main/feishu-software-download -- 飞书云盘获取下载等skill<br>https://quectel.feishu.cn/drive/folder/NiX8f7DWllNgPMdw9Q6cKH9Jnz8 -- 云盘链接 |
| 压测脚本网盘 | ✅ | https://github.com/venus-li-sssss/test/tree/main/feishu-software-download -- 经「飞书云盘」：飞书云盘获取下载等skill<br>https://quectel.feishu.cn/drive/folder/NiX8f7DWllNgPMdw9Q6cKH9Jnz8 -- 经「飞书云盘」：云盘链接 |
| excel插入图片或者对象 | 🔗 | excel的插件，安装后可以通过ctrl+Q插入图片或者对象，用于测试的时候放截图到excel |

## 软测内部飞书知识库（12 条）

| 入口 | 状态 | 关联 skill / 说明 |
|---|---|---|
| BPM 领用网址 | 🔗 | 领用样机、申请采购物品等 |
| Tracker的知识库 | 🔗 | Tracker的知识库 |
| 两轮车项目知识库 | 🔗 | 佛山项目知识,里面是飞书云文档格式的导航页面，具体的知识需要进入到对应的页面才能搜索到。各种项目上的知识，比如烧录、硬件接口、抓取日志、升级、协议等信息都可以进去里面查找 |
| 压测脚本记录 | 🔗 | 记录需求以及压测脚本的存放地址。找脚本以及需求的主要网址 |
| 日常工作流程 | 🔗 | 包含 如何使用JIRA系统、经验文档编写与归档、出差申请、样机测试、样机管理等SOP，可以知晓各种流程 |
| AI方案知识库 | 🔗 | 记录AI方案 |
| FWA行业知识库 | 🔗 | 关于FWA项目及相关资料存档 |
| 标准模板 | 🔗 | 主要存储是各种报告或者测试用例模板 |
| 新人培训计划 | 🔗 | 包含新人培训的大部分信息和流程以及指引 |
| 样机管理库 | 🔗 | 样机管理库，存储各个项目的样机数据 |
| 团队架构 | 🔗 | 简述团队的架构信息，主要是什么人负责什么工作，可以知道什么事情找什么人 |
| 物资管理 | 🔗 | 管理物资的页面，比如继电器、串口、稳压电源等资源管理 |

## 公司官网（5 条）

| 入口 | 状态 | 关联 skill / 说明 |
|---|---|---|
| EIP官网 | 🔗 | 公司网页的导航页面 |
| 绩效系统 | 🔗 | 绩效系统 |
| 移远社区 | 🔗 | 移远社区，公司内部论坛 |
| 移远会议 | ✅ | https://github.com/venus-li-sssss/test/tree/main/qmeeting-rooms -- 查询、取消、预定会议室 |
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
| skill仓库-github | 🔗 | github仓库，主要包含工时系统、JIRA系统、九号项目、自动烧录、自动做包的skill。token/key是***已脱敏（原值见导航页面该条目）*** |
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
| 九号平台 | ✅ | https://github.com/venus-li-sssss/test/tree/main/ninebot-project --  |

## 路测（0 条）

（空分类）

## 工时+考勤（1 条）

| 入口 | 状态 | 关联 skill / 说明 |
|---|---|---|
| 工时系统 | ✅ | https://github.com/venus-li-sssss/test/tree/main/quectel-attendance -- 获取考勤skill<br>https://github.com/venus-li-sssss/test/tree/main/quectel-workhours -- 工时skill，用于创建、修改提交工时 |

## 防锁屏（1 条）

| 入口 | 状态 | 关联 skill / 说明 |
|---|---|---|
| 防锁屏 | 🔗 | 防锁屏软件，每30s输入F15防锁屏，放在飞书网盘 |

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
