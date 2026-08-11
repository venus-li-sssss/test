---
name: subtitle-video
label: 字幕视频生成
description: >-
  为音视频文件生成逐句精准字幕（基于飞书妙记）。自动上传视频到妙记获取逐字稿，按标点拆分子句，去除标点，生成 ASS/SRT 字幕并烧录到视频。
  支持三种输入：(1)本地视频文件；(2)飞书云盘文件 URL（自动下载）；(3)会话附件。
  流程：获取视频→上传云盘→生成妙记→获取逐字稿（段落级时间戳）→按标点拆分子句+比例估算时间戳→去除标点→生成 ASS/SRT→烧录。
  默认普通字幕模式；--karaoke 可选逐字高亮。可选 --burn 烧录硬字幕。
  使用场景：(1)用户要求给视频加字幕、生成字幕、烧录字幕；(2)用户要求给音频生成文字稿/字幕；
  (3)用户提到"字幕""subtitles""captions""硬字幕""软字幕""外挂字幕"；(4)用户上传视频/音频并要求转文字或加字幕；
  (5)用户提供飞书妙记链接要求生成字幕；(6)用户要求卡拉OK逐字高亮字幕。
  支持中文及多语言，支持纯音频输入（仅输出字幕文件）。
---

# 字幕视频生成

## 概述

基于飞书妙记 ASR 引擎，为音视频文件生成逐句精准字幕。全程自动：获取视频 → 上传到妙记 → 获取逐字稿 → 按标点拆分子句 → 去除标点 → 生成字幕 → 烧录到视频。

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

4. **等待处理并获取逐字稿**：`lark-cli minutes +detail --minute-tokens <token> --wait-ready --transcript --as user` → 获取 `transcript.txt`
   - 妙记处理需要时间（1小时视频约3-5分钟），`--wait-ready` 会阻塞等待

5. **生成字幕**：`python3 {baseDir}/scripts/minutes_subtitle.py --minute-token <token> <video_file> --burn --output-dir ./output`
   - 解析逐字稿（段落级时间戳 + 说话人标签 + 文本）
   - 按标点拆分子句（与妙记网页端一致）
   - 去除标点符号（标点仅用于拆分，不显示）
   - 比例估算子句时间戳（段落开始为精确值，子句按字符数比例分配）
   - 生成 ASS（普通/卡拉OK）+ SRT（含说话人标签）

6. **上传产物到飞书云盘**：将烧录后的视频和 SRT 上传，以链接交付

## 字幕拆分策略（与妙记网页端一致）

通过对比妙记网页端字幕条的实际显示行为，确认网页端按**标点子句**显示字幕——每次显示一个标点符号之间的文本。本脚本复现这一行为：

1. **按标点拆分**：遇到 `，。！？；,;!?.…` 等标点时断句
2. **去除标点符号**：标点仅用于拆分，不显示在字幕画面中
3. **超长无标点子句安全阀**：超过 50 字且无标点时，尝试在空格处拆分
4. **比例估算时间戳**：段落开始时间为 API 精确值，子句时间戳按字符数比例估算

## 使用方法

```bash
# 已有妙记 token + 本地视频 → 生成字幕并烧录
python3 {baseDir}/scripts/minutes_subtitle.py --minute-token <token> <video_file> --burn --output-dir ./output

# 已有妙记 token，仅生成字幕文件（不烧录）
python3 {baseDir}/scripts/minutes_subtitle.py --minute-token <token> --output-dir ./output

# 全自动：本地视频 → 上传 → 妙记 → 字幕 → 烧录
python3 {baseDir}/scripts/minutes_subtitle.py <video_file> --burn --output-dir ./output

# 卡拉OK逐字高亮模式（需用户明确要求）
python3 {baseDir}/scripts/minutes_subtitle.py <video_file> --burn --karaoke --output-dir ./output

# 已有云盘 file_token（跳过 drive 上传）
python3 {baseDir}/scripts/minutes_subtitle.py --file-token <token> <video_file> --burn --output-dir ./output
```

## 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `video_file` | 可选 | 本地视频文件路径（烧录时必填） |
| `--minute-token` | - | 已有妙记 token，跳过上传步骤 |
| `--file-token` | - | 已有云盘 file_token，跳过 drive 上传 |
| `--output-dir` | `.` | 输出目录 |
| `--karaoke` | false | 卡拉OK逐字高亮（拆分逻辑与普通模式相同） |
| `--burn` | false | 烧录字幕到视频画面 |
| `--video-width` | 640 | 视频宽度（影响字幕字号） |
| `--video-height` | 360 | 视频高度（影响字幕字号） |

## 输出文件

- `subtitle.ass`：ASS 字幕文件（普通模式，纯白文字+黑描边）
- `subtitle_karaoke.ass`：ASS 字幕文件（卡拉OK模式，`--karaoke` 时生成）
- `subtitle.srt`：SRT 字幕文件（通用格式，含说话人标签）
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

4. **等待并获取逐字稿**：`lark-cli minutes +detail --minute-tokens <minute_token> --wait-ready --transcript --as user` → 获取 `transcript.txt`

5. **生成字幕并烧录**：`python3 {baseDir}/scripts/minutes_subtitle.py --minute-token <token> <video_file> --burn --output-dir ./output`

6. **上传产物**：将烧录后的视频和 SRT 文件上传到飞书云盘，以链接交付给用户

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
- **字幕标点**：标点符号仅用于拆分子句，不显示在字幕画面中
- **卡拉OK模式**：基于字符均匀分配时间；默认不启用，需用户明确要求
- **飞书播放器**：飞书网页播放器不支持软字幕渲染，建议使用 `--burn` 烧录硬字幕
- **纯音频输入**：仅输出字幕文件，不烧录视频
