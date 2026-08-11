---
name: subtitle-video
label: 字幕视频生成
description: >-
  为音视频文件生成逐句精准字幕（基于飞书妙记词级时间戳）。自动上传视频到妙记，通过 subtitles_v2 API 获取词级时间戳（精确到每个词的毫秒级 start/stop），按标点拆分子句，去除标点，生成 ASS/SRT 字幕并烧录到视频。
  支持三种输入：(1)本地视频文件；(2)飞书云盘文件 URL（自动下载）；(3)会话附件。
  流程：获取视频→上传云盘→生成妙记→通过 subtitles_v2 API 获取词级时间戳→按标点拆分子句（使用实际词级时间戳）→去除标点→生成 ASS/SRT→烧录。
  默认普通字幕模式；--karaoke 可选逐词高亮（使用实际词级时间戳）。可选 --burn 烧录硬字幕。
  使用场景：(1)用户要求给视频加字幕、生成字幕、烧录字幕；(2)用户要求给音频生成文字稿/字幕；
  (3)用户提到"字幕""subtitles""captions""硬字幕""软字幕""外挂字幕"；(4)用户上传视频/音频并要求转文字或加字幕；
  (5)用户提供飞书妙记链接要求生成字幕；(6)用户要求卡拉OK逐字高亮字幕。
  支持中文及多语言，支持纯音频输入（仅输出字幕文件）。
---

# 字幕视频生成

## 概述

基于飞书妙记 ASR 引擎，为音视频文件生成逐句精准字幕。全程自动：获取视频 → 上传到妙记 → 获取词级时间戳 → 按标点拆分子句 → 去除标点 → 生成字幕 → 烧录到视频。

**核心优势**：直接调用妙记 `subtitles_v2` API 获取每个词的精确时间戳（毫秒级），子句的起止时间完全精确，不使用比例估算。

## 输入方式

| 输入类型 | 处理方式 |
|---------|---------|
| **本地视频文件** | 直接上传到飞书云盘 |
| **飞书云盘文件 URL** | 先 `lark-cli drive +download` 下载到本地，再上传 |
| **会话附件** | 附件已在本地沙箱，直接使用 |

支持的格式：mp4/mov/avi/mkv/wav/mp3/m4a 等常见音视频格式，时长 ≤6 小时，文件 ≤6GB。

## 工作流程

1. **获取视频文件到本地**（如已是本地文件则跳过）
   - 飞书云盘 URL：用 `lark-cli drive +inspect --url '<URL>'` 解析 type/token → `lark-cli drive +download --file-token <token> --output ./video.mp4 --as user`
   - >100MB 文件：使用 `download_large_file.py` 分块下载

2. **上传视频到飞书云盘**：`lark-cli drive +upload --file <path> --name <name> --as user` → 获取 `file_token`

3. **生成妙记**：`lark-cli minutes +upload --file-token <file_token> --as user` → 获取 `minute_token`

4. **等待妙记处理完成**：`lark-cli minutes +detail --minute-tokens <token> --wait-ready --transcript --as user`
   - 妙记处理需要时间（1小时视频约3-5分钟），`--wait-ready` 会阻塞等待

5. **打开妙记页面建立浏览器会话**：`agent-browser open "https://<tenant>.feishu.cn/minutes/<minute_token>"`
   - subtitles_v2 API 需要 web session cookies，浏览器需先打开飞书页面
   - 这一步仅建立会话，不进行任何 UI 交互

6. **生成字幕**：`python3 {baseDir}/scripts/minutes_subtitle.py --minute-token <token> <video_file> --burn --output-dir ./output --tenant-domain <tenant>.feishu.cn`
   - 脚本通过 CDP 从浏览器提取 cookies（无 UI 交互）
   - 用纯 HTTP API 调用 subtitles_v2 获取词级时间戳
   - 按标点拆分子句，使用实际词级时间戳（每个子句的 start = 第一个词的 start_time，stop = 最后一个词的 stop_time）
   - 去除标点符号（标点仅用于拆分，不显示）
   - 生成 ASS（普通/卡拉OK）+ SRT

7. **上传产物到飞书云盘**：将烧录后的视频和 SRT 上传，以链接交付

## 词级时间戳获取原理

妙记 `subtitles_v2` 是私有 Web API，返回三层结构的数据：

```
paragraphs → sentences → words (contents)
```

每个 word 都有精确的 `start_time` 和 `stop_time`（毫秒级），例如：
```json
{"content": "喂，", "start_time": "10550", "stop_time": "10750"}
```

**API 调用流程**：
1. 从浏览器提取 feishu.cn 域名的 cookies（通过 CDP，无 UI 交互）
2. `GET /minutes/api/subtitles/paragraph-ids` — 获取所有段落 ID
3. `GET /minutes/api/subtitles_v2?paragraph_id=<pid>&size=100` — 分页获取词级时间戳

**前置条件**：浏览器已打开飞书妙记页面（agent 需先执行 `agent-browser open` 打开妙记页面建立会话）。

## 字幕拆分策略

1. **按标点拆分**：遇到 `，。！？；,;!?.…` 等标点时断句
2. **去除标点符号**：标点仅用于拆分，不显示在字幕画面中
3. **使用实际词级时间戳**：每个子句的 start_ms = 子句第一个词的 start_time，stop_ms = 子句最后一个词的 stop_time（精确值，非比例估算）
4. **超长无标点子句安全阀**：超过 50 字且无标点时，尝试在空格处拆分

## 使用方法

```bash
# 已有妙记 token + 本地视频 → 生成字幕并烧录
python3 {baseDir}/scripts/minutes_subtitle.py --minute-token <token> <video_file> --burn --output-dir ./output --tenant-domain <tenant>.feishu.cn

# 已有妙记 token，仅生成字幕文件（不烧录）
python3 {baseDir}/scripts/minutes_subtitle.py --minute-token <token> --output-dir ./output --tenant-domain <tenant>.feishu.cn

# 全自动：本地视频 → 上传 → 妙记 → 字幕 → 烧录
python3 {baseDir}/scripts/minutes_subtitle.py <video_file> --burn --output-dir ./output --tenant-domain <tenant>.feishu.cn

# 卡拉OK逐字高亮模式（使用实际词级时间戳）
python3 {baseDir}/scripts/minutes_subtitle.py <video_file> --burn --karaoke --output-dir ./output --tenant-domain <tenant>.feishu.cn

# 已有云盘 file_token（跳过 drive 上传）
python3 {baseDir}/scripts/minutes_subtitle.py --file-token <token> <video_file> --burn --output-dir ./output --tenant-domain <tenant>.feishu.cn
```

## 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `video_file` | 可选 | 本地视频文件路径（烧录时必填） |
| `--minute-token` | - | 已有妙记 token，跳过上传步骤 |
| `--file-token` | - | 已有云盘 file_token，跳过 drive 上传 |
| `--output-dir` | `.` | 输出目录 |
| `--karaoke` | false | 卡拉OK逐词高亮（使用实际词级时间戳） |
| `--burn` | false | 烧录字幕到视频画面 |
| `--video-width` | 640 | 视频宽度（影响字幕字号） |
| `--video-height` | 360 | 视频高度（影响字幕字号） |
| `--tenant-domain` | - | 飞书租户域名（如 quectel.feishu.cn），用于 API 调用 |

## 输出文件

- `subtitle.ass`：ASS 字幕文件（普通模式，纯白文字+黑描边）
- `subtitle_karaoke.ass`：ASS 字幕文件（卡拉OK模式，`--karaoke` 时生成，使用实际词级 \k 标签）
- `subtitle.srt`：SRT 字幕文件（通用格式）
- `<视频名>_字幕版.mp4`：烧录普通字幕的视频（`--burn` 时生成）
- `<视频名>_卡拉OK字幕版.mp4`：烧录卡拉OK字幕的视频（`--burn --karaoke` 时生成）

## Agent 执行流程

当使用本 skill 为用户生成字幕时，按以下步骤执行：

1. **判断输入**：
   - 用户提供本地视频文件 → Step 2
   - 用户提供飞书云盘 URL → `lark-cli drive +inspect --url '<URL>'` 解析 → `lark-cli drive +download` 下载到本地 → Step 2
   - 用户提供妙记 URL（`feishu.cn/minutes/xxx`）→ 提取 minute_token → Step 4
   - 用户上传附件 → 附件已在本地 → Step 2

2. **上传视频到云盘**：`lark-cli drive +upload --file <path> --name <name> --as user` → 获取 `file_token`

3. **生成妙记**：`lark-cli minutes +upload --file-token <file_token> --as user` → 获取 `minute_token`

4. **等待妙记处理完成**：`lark-cli minutes +detail --minute-tokens <minute_token> --wait-ready --transcript --as user`

5. **打开妙记页面建立浏览器会话**：`agent-browser open "https://<tenant>.feishu.cn/minutes/<minute_token>"` — 仅建立会话，不进行 UI 交互

6. **生成字幕并烧录**：`python3 {baseDir}/scripts/minutes_subtitle.py --minute-token <token> <video_file> --burn --output-dir ./output --tenant-domain <tenant>.feishu.cn`

7. **上传产物**：将烧录后的视频和 SRT 文件上传到飞书云盘，以链接交付给用户

## 大文件处理

### 下载飞书云盘大文件（>100MB）

`lark-cli drive +download` 对 >100MB 文件有响应体限制，使用分块下载脚本：

```bash
python3 {baseDir}/scripts/download_large_file.py <file_token> <output_path> --as user
```

### 上传大文件到飞书云盘

`lark-cli drive +upload` 支持分块上传，可直接处理 >20MB 的文件：

```bash
lark-cli drive +upload --file <path> --name <name> --as user
```

## 注意事项

- **妙记处理时间**：妙记 ASR 需要处理时间（1小时视频约3-5分钟），`--wait-ready` 会阻塞等待
- **词级时间戳**：通过 subtitles_v2 API 获取每个词的精确毫秒级时间戳，子句起止时间完全精确
- **浏览器会话**：subtitles_v2 API 需要 web session cookies，脚本通过 CDP 从浏览器提取（无 UI 交互），agent 需先 `agent-browser open` 打开妙记页面
- **字幕标点**：标点符号仅用于拆分子句，不显示在字幕画面中
- **卡拉OK模式**：使用实际词级时间戳生成 \k 标签，每字高亮时长精确到毫秒
- **飞书播放器**：飞书网页播放器不支持软字幕渲染，建议使用 `--burn` 烧录硬字幕
- **纯音频输入**：仅输出字幕文件，不烧录视频
