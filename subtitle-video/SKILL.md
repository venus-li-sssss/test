---
name: subtitle-video
label: 字幕视频生成
description: >-
  为音视频文件生成逐句精准字幕。支持两种模式：(A) 飞书妙记模式（推荐）——自动上传视频到妙记获取逐字稿，按标点拆分子句，生成字幕并烧录；
  (B) ASR 语音识别模式——适用于无妙记录制的任意音视频，通过 ffmpeg 静音检测+并发转录生成字幕。
  妙记模式流程：上传视频到云盘→生成妙记→获取逐字稿（段落级时间戳）→按标点拆分子句+比例估算时间戳→去除标点→生成 ASS/SRT→烧录。
  ASR 模式流程：ffmpeg 静音检测→在自然停顿处切块→并发转录→时间戳偏移合并→去重后处理→SRT/ASS 输出。
  默认普通字幕模式；--karaoke 可选逐字高亮。可选 --burn 烧录硬字幕、--embed 内嵌软字幕轨道。
  使用场景：(1)用户要求给视频加字幕、生成字幕、烧录字幕；(2)用户要求给音频生成文字稿/字幕；
  (3)用户提到"字幕""subtitles""captions""硬字幕""软字幕""外挂字幕"；(4)用户上传视频/音频并要求转文字或加字幕；
  (5)用户提供飞书妙记链接要求生成字幕；(6)用户要求卡拉OK逐字高亮字幕。
  支持中文及多语言，支持断点续跑，支持纯音频输入（仅输出字幕文件）。
---

# 字幕视频生成

## 两种工作模式

| 模式 | 输入 | 时间戳精度 | 适用场景 | 脚本 |
|------|------|-----------|---------|------|
| **妙记模式**（推荐） | 视频文件（本地或云盘） | 段落级（秒） | 有飞书妙记的会议/培训录制 | `minutes_subtitle.py` |
| **ASR 模式** | 任意音视频文件 | 句级（秒） | 无妙记录制的自定义视频 | `generate_subtitled_video.py` |

**妙记模式**自动上传视频到飞书妙记，利用妙记的 ASR 引擎获取逐字稿（含段落级时间戳），然后按标点拆分子句、比例估算子句时间戳、去除标点符号，生成 ASS/SRT 字幕并可选烧录到视频。全程自动，无需手动导出文件。

**ASR 模式**通过 ffmpeg 静音检测切割音频 → 并发调用语音识别 → 合并时间戳，适用于任何音视频文件。

---

## 模式 A：飞书妙记字幕生成（推荐）

### 工作流程

1. **上传视频到飞书云盘**（如已有 file_token 可跳过）：`lark-cli drive +upload` → 获取 `file_token`
2. **生成妙记**：`lark-cli minutes +upload --file-token <token>` → 获取 `minute_token`
3. **等待处理并获取逐字稿**：`lark-cli minutes +detail --minute-tokens <token> --wait-ready --transcript` → 获取 `transcript.txt`
4. **解析逐字稿**：提取每个段落的说话人、开始时间戳、文本内容
5. **按标点拆分子句**：与妙记网页端一致，按 `，。！？；,;!?.…` 拆分，去除标点符号
6. **比例估算时间戳**：段落级时间戳为精确值（来自妙记 API），子句时间戳按字符数比例估算
7. **生成字幕**：输出 ASS（普通模式/卡拉OK模式）+ SRT（含说话人标签）
8. **烧录到视频**（可选）：`ffmpeg -vf ass=subtitle.ass` 烧录硬字幕

### 字幕拆分策略（与妙记网页端一致）

通过对比妙记网页端字幕条的实际显示行为，确认网页端按**标点子句**显示字幕——每次显示一个标点符号之间的文本。本脚本复现这一行为：

1. **按标点拆分**（主策略）：遇到 `，。！？；,;!?.…` 等标点时断句
2. **去除标点符号**：标点仅用于拆分，不显示在字幕画面中
3. **超长无标点子句安全阀**：超过 50 字且无标点时，尝试在空格处拆分
4. **比例估算时间戳**：段落开始时间为 API 精确值，子句时间戳按字符数比例估算

### 使用方法

```bash
# 全自动：上传视频→生成妙记→获取字幕→生成字幕文件
python3 {baseDir}/scripts/minutes_subtitle.py <video_file> --output-dir ./output

# 全自动 + 烧录到视频
python3 {baseDir}/scripts/minutes_subtitle.py <video_file> --burn --output-dir ./output

# 已有妙记 token（跳过上传，直接获取字幕）
python3 {baseDir}/scripts/minutes_subtitle.py --minute-token <token> --output-dir ./output

# 已有妙记 token + 烧录到已有视频
python3 {baseDir}/scripts/minutes_subtitle.py --minute-token <token> <video_file> --burn --output-dir ./output

# 已有云盘 file_token（跳过 drive 上传）
python3 {baseDir}/scripts/minutes_subtitle.py --file-token <token> --output-dir ./output

# 卡拉OK逐字高亮模式
python3 {baseDir}/scripts/minutes_subtitle.py <video_file> --burn --karaoke --output-dir ./output
```

### 参数说明

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

### 输出文件

- `subtitle.ass`：ASS 字幕文件（普通模式，纯白文字+黑描边）
- `subtitle_karaoke.ass`：ASS 字幕文件（卡拉OK模式，`--karaoke` 时生成）
- `subtitle.srt`：SRT 字幕文件（通用格式，含说话人标签）
- `<视频名>_字幕版.mp4`：烧录普通字幕的视频（`--burn` 时生成）
- `<视频名>_卡拉OK字幕版.mp4`：烧录卡拉OK字幕的视频（`--burn --karaoke` 时生成）

### Agent 执行流程

当使用本 skill 为用户生成字幕时，按以下步骤执行：

1. **判断输入**：
   - 用户提供本地视频文件 → 从 Step 2 开始
   - 用户提供妙记 URL（`feishu.cn/minutes/xxx`）→ 提取 minute_token，从 Step 5 开始
   - 用户提供飞书云盘文件 → 先 `lark-cli drive +download` 下载到本地，从 Step 2 开始

2. **上传视频到云盘**：`lark-cli drive +upload --file <path> --name <name> --as user` → 获取 `file_token`

3. **生成妙记**：`lark-cli minutes +upload --file-token <file_token> --as user` → 获取 `minute_token`

4. **等待并获取逐字稿**：`lark-cli minutes +detail --minute-tokens <minute_token> --wait-ready --transcript --as user` → 获取 `transcript.txt` 路径
   - 注意：妙记处理可能需要几分钟（1小时视频约3-5分钟），`--wait-ready` 会阻塞等待

5. **生成字幕**：`python3 {baseDir}/scripts/minutes_subtitle.py --minute-token <token> <video_file> --burn --output-dir ./output`
   - 如果有本地视频文件，加上 `--burn` 一步到位
   - 如果只有妙记 token 无视频文件，仅生成字幕文件

6. **上传产物**：将烧录后的视频和 SRT 文件上传到飞书云盘，以链接交付给用户

---

## 模式 B：ASR 语音识别字幕生成

### 能力

- 输入：任意音视频文件（mp4/mov/avi/mkv/wav/mp3/m4a 等）
- **默认输出**：SRT + ASS 外挂字幕文件（不修改原视频）
- 可选 `--burn`：烧录硬字幕到视频画面（重新编码，耗时较长）
- 可选 `--embed`：内嵌软字幕轨道到 MP4 容器（不重新编码，播放器可开关字幕）
- 纯音频输入：仅输出字幕文件
- 大视频优化：音频预读内存→大块切割→并发转录，2 小时视频约 7 分钟完成转录
- 支持断点续跑：长时间任务中断后重新运行可继续

### 工作流程

1. **提取音频**：ffmpeg 从输入文件提取 mono 16kHz PCM 音频（已存在则跳过）
2. **预读音频到内存**：一次性读取整个 WAV 到内存缓冲，所有工作线程共享只读
3. **静音检测**：用 ffmpeg `silencedetect` 扫描音频，找到所有自然停顿点（≥0.3s）
4. **静音点切块**：在自然停顿处将音频切成大块（目标~300s/块，但总是在静音点下刀）
5. **并发转录**：单一 ThreadPoolExecutor 全量提交，每块独立调用 aily-speech-to-text
6. **去重后处理**：检测并去除转录引擎产生的重叠/重复条目，去末尾标点，切分过长句
7. **生成字幕**：输出 SRT（通用格式）+ ASS（含精确排版）
8. **视频处理（可选）**：`--burn` 烧录硬字幕 / `--embed` 内嵌软字幕轨道

### 使用方法

```bash
# 基本用法：生成外挂字幕文件
python3 {baseDir}/scripts/generate_subtitled_video.py <video_or_audio_file>

# 烧录硬字幕到视频
python3 {baseDir}/scripts/generate_subtitled_video.py <video_file> --burn

# 内嵌软字幕轨道到 MP4
python3 {baseDir}/scripts/generate_subtitled_video.py <video_file> --embed

# 自定义并发数和切块时长
python3 {baseDir}/scripts/generate_subtitled_video.py <video_file> --workers 8 --chunk-duration 180
```

### ASR 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `input_file` | 必填 | 音视频文件路径 |
| `--burn` | false | 烧录硬字幕到视频画面 |
| `--embed` | false | 内嵌软字幕轨道到 MP4 |
| `--burn-only` | false | 仅烧录（使用已有 SRT 文件） |
| `--workers` | 12 | 并发转录线程数 |
| `--chunk-duration` | 300 | 目标切块时长（秒） |
| `--silence-noise` | 0.3 | 静音检测噪声阈值（dB） |
| `--silence-min-dur` | 0.3 | 最小静音持续时间（秒） |
| `--no-silence` | false | 禁用静音检测，退回固定时长切块 |

### ASR 注意事项

- 默认不修改视频：脚本默认仅输出 SRT + ASS 外挂字幕文件
- 外挂字幕使用：将 SRT 文件与视频放在同一目录、同名，大多数播放器会自动加载
- 飞书播放器不支持 mov_text 软字幕：`--embed` 在飞书网页播放器中不可见，建议用 `--burn`
- 大文件下载：飞书云盘 >100MB 文件需用 `download_large_file.py` 分块下载

---

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

---

## 注意事项

- **妙记模式 vs ASR 模式**：妙记模式利用飞书妙记的 ASR 引擎，中文识别精度更高，支持说话人区分；ASR 模式适用于任意音视频但精度略低
- **字幕标点**：两种模式均去除标点符号，标点仅用于拆分子句
- **卡拉OK模式**：妙记模式的卡拉OK基于字符均匀分配时间；如需词级精度，需手动从妙记网页端导出 HAR 文件并使用 `har_to_subtitles.py`
- **飞书播放器**：飞书网页播放器不支持 mov_text 软字幕渲染，建议使用 `--burn` 烧录硬字幕
- **处理时间**：妙记模式需等待妙记处理（1小时视频约3-5分钟）；ASR 模式约7分钟（2小时视频）
