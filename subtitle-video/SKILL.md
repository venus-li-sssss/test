---
name: subtitle-video
label: 字幕视频生成
description: >-
  为音视频文件生成逐句精准字幕。支持两种模式：(A) 基于飞书妙记 HAR 文件的词级时间戳字幕生成（精度最高，推荐用于已有妙记录制的情况）；
  (B) 基于 ASR 语音识别的字幕生成（适用于无妙记录制的任意音视频）。
  输入视频或音频文件，输出 SRT/ASS 字幕文件（默认外挂），可选烧录硬字幕（--burn）或内嵌软字幕轨道（--embed）到视频。
  HAR 模式核心技术：解析妙记 subtitles_v2 API 的段落→句子→词三层结构→按标点+字数拆分长句→生成 ASS/SRT→烧录。
  ASR 模式核心技术：ffmpeg静音检测→在自然停顿处切块→并发转录→时间戳偏移合并→去重后处理→SRT/ASS输出。
  默认普通字幕模式；--karaoke 可选卡拉OK逐字高亮（仅 HAR 模式支持）。
  支持飞书云盘大文件分块下载（绕过 lark-cli 100MB 限制）、断点续跑。
  使用场景：(1)用户要求给视频加字幕、生成字幕、烧录字幕；(2)用户要求给音频生成文字稿/字幕；
  (3)用户提到"字幕""subtitles""captions""硬字幕""软字幕""外挂字幕"；(4)用户上传视频/音频并要求转文字或加字幕；
  (5)用户提供飞书妙记 HAR 文件要求生成精准字幕；(6)用户要求卡拉OK逐字高亮字幕。
  支持中文及多语言，支持断点续跑，支持纯音频输入（仅输出字幕文件）。
---

# 字幕视频生成

## 两种工作模式

本 skill 支持两种字幕生成方式，根据输入素材选择：

| 模式 | 输入 | 时间戳精度 | 适用场景 | 脚本 |
|------|------|-----------|---------|------|
| **HAR 模式**（推荐） | 飞书妙记 HAR 文件 + 视频 | 词级（毫秒） | 已有妙记录制的会议/培训 | `har_to_subtitles.py` |
| **ASR 模式** | 任意音视频文件 | 句级（秒） | 无妙记录制的自定义视频 | `generate_subtitled_video.py` |

**HAR 模式**直接解析飞书妙记网页端的 `subtitles_v2` API 数据（段落→句子→词三层结构），获取词级毫秒时间戳，精度远超 ASR 模式。字幕长度控制策略与妙记网页端同步：按标点符号拆分长句，无标点时按字数上限强制拆分。

**ASR 模式**通过 ffmpeg 静音检测切割音频 → 并发调用语音识别 → 合并时间戳，适用于任何音视频文件。

---

## 模式 A：HAR 字幕生成（飞书妙记词级时间戳）

### 原理

飞书妙记网页端通过私有 API `/minutes/api/subtitles_v2` 获取三层嵌套字幕数据：
- **段落（paragraph）**：按说话人切换或长停顿分段
- **句子（sentence）**：ASR 引擎在自然停顿处断句，每句有 start_time / stop_time
- **词（word/contents）**：每个词有独立的 start_time / stop_time（毫秒级），用于网页端逐字高亮

HAR 文件由用户在妙记网页端播放时通过浏览器开发者工具 → Network → Export HAR 导出，包含完整的 API 响应。

### 字幕拆分策略（与妙记网页端一致）

通过对比妙记网页端字幕条的实际显示行为，确认网页端按**标点子句**显示字幕——每次显示一个标点符号（逗号/句号/问号等）之间的文本，不是完整句子，也不是按字数硬切。

本脚本复现这一行为：

1. **按标点拆分**（主策略）：遇到 `，。！？；,;!?.…` 等标点时断句，每个子句作为一条独立字幕
2. **不按字数硬切**：避免在词义中间断句导致语义异常
3. **超长无标点子句安全阀**：仅当子句超过 50 字且无标点时，尝试在词间自然停顿处（gap > 300ms）拆分；找不到停顿点则保留原样
4. **词级时间戳精确定位**：每条字幕使用首词 start_time → 末词 stop_time，时间戳精确到毫秒

实测数据：1132 个 API 句子 → 3225 条标点子句，其中 87.4% ≤20 字，97.4% ≤25 字，仅 0.3% >50 字（均为无标点的英文 ASR 文本）。

### 默认模式 vs 卡拉OK模式

**两种模式使用完全相同的拆分逻辑**，区别仅在显示效果：

- **默认（普通字幕）**：纯白文字 + 黑色描边
- **`--karaoke`（卡拉OK）**：在普通字幕基础上，使用 ASS `\k` 标签逐词高亮（已说过的词变灰，当前词高亮白色）
- 卡拉OK模式仅在用户明确要求时使用（如提示词中提到"卡拉OK""逐字高亮""karaoke"）

### 使用方法

```bash
# 基本用法：从 HAR 生成外挂字幕（默认普通模式）
python3 {baseDir}/scripts/har_to_subtitles.py <har_file> <video_file> --output-dir ./output

# 仅生成字幕文件（不提供视频）
python3 {baseDir}/scripts/har_to_subtitles.py <har_file> --output-dir ./output

# 生成字幕并烧录到视频（默认普通字幕）
python3 {baseDir}/scripts/har_to_subtitles.py <har_file> <video_file> --burn --output-dir ./output

# 卡拉OK逐字高亮模式（需用户明确要求，拆分逻辑与普通模式相同）
python3 {baseDir}/scripts/har_to_subtitles.py <har_file> <video_file> --burn --karaoke --output-dir ./output

# 指定视频分辨率（影响字幕字号，默认 640x360）
python3 {baseDir}/scripts/har_to_subtitles.py <har_file> <video_file> --burn --video-width 1920 --video-height 1080 --output-dir ./output
```

### HAR 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `har_file` | 必填 | HAR 文件路径（从妙记网页端导出） |
| `video_file` | 可选 | 视频文件路径（不提供则仅生成字幕文件） |
| `--output-dir` | `.` | 输出目录 |
| `--karaoke` | false | 卡拉OK逐词高亮（拆分逻辑与普通模式相同，仅添加 \k 标签） |
| `--burn` | false | 烧录字幕到视频画面 |
| `--video-width` | 640 | 视频宽度（影响字幕字号） |
| `--video-height` | 360 | 视频高度（影响字幕字号） |

### HAR 输出文件

- `subtitle.ass`：ASS 字幕文件（普通模式，纯白文字+黑描边）
- `subtitle_karaoke.ass`：ASS 字幕文件（卡拉OK模式，`--karaoke` 时生成）
- `subtitle.srt`：SRT 字幕文件（通用格式，含说话人标签）
- `<视频名>_字幕版.mp4`：烧录普通字幕的视频（`--burn` 时生成）
- `<视频名>_卡拉OK字幕版.mp4`：烧录卡拉OK字幕的视频（`--burn --karaoke` 时生成）

### 如何获取 HAR 文件

1. 在浏览器中打开飞书妙记播放页面（如 `https://quectel.feishu.cn/minutes/xxx`）
2. 按 F12 打开开发者工具 → Network 标签
3. 刷新页面，等待字幕加载完成
4. 右键网络请求列表 → Save all as HAR with content
5. 将 HAR 文件提供给本 skill

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

## 前置依赖

- `ffmpeg` / `ffprobe`（音频处理与字幕烧录/内嵌）
- `aily-speech-to-text`（语音识别转录工具）
- 中文字体 `Noto Sans CJK SC`（字幕渲染，沙箱预装）
- `lark-cli`（飞书 API 调用，大文件下载也依赖它获取认证）
- `cryptography`（大文件下载脚本 MITM 代理所需，沙箱预装）

## 大文件下载（飞书云盘 → 本地）

### 问题与方案

当输入视频/音频文件存储在飞书云盘时（用户通过 IM 发送或分享的文件），需要先下载到本地。**`lark-cli drive +download` 对 >100MB 的文件会失败**——lark-cli 内部通过 aily 网关代理飞书 API，网关对单次响应体有 ~100MB 的大小限制，大文件下载会被截断或超时。

**解决方案**：通过 MITM 代理截获 lark-cli 的认证 headers，然后用 HTTP Range 请求分块下载（10MB/块），绕过响应体大小限制。脚本已封装为 `{baseDir}/scripts/download_large_file.py`。

### 从飞书 URL 提取 file_token

```
https://quectel.feishu.cn/file/PBc1b7zksoNJvDxnWF9crC0An7g
                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                              file_token
```

### 使用方法

```bash
# 小文件（<100MB）：直接用 lark-cli
lark-cli drive +download --file-token <token> --output ./small.mp4 --as user

# 大文件（>100MB）：用分块下载脚本（支持 file_token 或完整 URL）
python3 {baseDir}/scripts/download_large_file.py <token> ./video.mp4
python3 {baseDir}/scripts/download_large_file.py "https://quectel.feishu.cn/file/PBc1b7z..." ./video.mp4

# 自定义分块大小（默认 10MB，网络不稳可减小到 5MB）
python3 {baseDir}/scripts/download_large_file.py <token> ./video.mp4 --chunk-size 5

# 用 bot 身份下载
python3 {baseDir}/scripts/download_large_file.py <token> ./video.mp4 --as bot
```

### 完整工作流

```bash
# Step 1: 下载大文件（分块下载，支持断点续传）
python3 {baseDir}/scripts/download_large_file.py PBc1b7zksoNJvDxnWF9crC0An7g ./移远学院.mp4

# Step 2: 生成外挂字幕（默认，不修改视频）
python3 {baseDir}/scripts/generate_subtitled_video.py ./移远学院.mp4 --output-dir ./output --workers 8

# Step 3（可选）: 内嵌软字幕到视频容器（不重新编码，速度快）
python3 {baseDir}/scripts/generate_subtitled_video.py ./移远学院.mp4 --output-dir ./output --embed --burn-only

# Step 3（可选）: 烧录硬字幕到视频画面（重新编码，耗时较长）
python3 {baseDir}/scripts/generate_subtitled_video.py ./移远学院.mp4 --output-dir ./output --burn --burn-only
```

## 使用方法

```bash
# 默认：仅生成外挂 SRT + ASS 字幕文件（不修改视频）
python3 {baseDir}/scripts/generate_subtitled_video.py <input_file>

# 指定输出目录和语言
python3 {baseDir}/scripts/generate_subtitled_video.py <input_file> --language zh --output-dir ./output

# 并发转录（长视频推荐）
python3 {baseDir}/scripts/generate_subtitled_video.py <input_file> --workers 10 --output-dir ./output

# 生成外挂字幕 + 内嵌软字幕到视频容器（不重新编码，播放器可开关字幕）
python3 {baseDir}/scripts/generate_subtitled_video.py <input_file> --embed --output-dir ./output

# 生成外挂字幕 + 烧录硬字幕到视频画面（重新编码，字幕永远显示）
python3 {baseDir}/scripts/generate_subtitled_video.py <input_file> --burn --output-dir ./output

# 转录和视频处理分两步执行（长视频推荐）
python3 {baseDir}/scripts/generate_subtitled_video.py <input_file> --output-dir ./output          # Step1: 转录+生成字幕
python3 {baseDir}/scripts/generate_subtitled_video.py <input_file> --output-dir ./output --embed --burn-only  # Step2: 内嵌软字幕
python3 {baseDir}/scripts/generate_subtitled_video.py <input_file> --output-dir ./output --burn --burn-only   # Step2alt: 烧录硬字幕

# 自定义切割块时长（默认 60s，更大减少 API 调用但单次更慢）
python3 {baseDir}/scripts/generate_subtitled_video.py <input_file> --chunk-duration 120 --workers 8
```

## 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `input_file` | 必填 | 输入音视频文件路径 |
| `--language` | zh | 源语言代码（zh/en/ja/ko等） |
| `--max-chars` | 26 | 单行最大字符数，超出则按标点切分 |
| `--output-dir` | ./output | 输出目录 |
| `--time-budget` | 540 | 单次运行总时间预算（秒），给600秒超时留余量 |
| `--workers` | 8 | 并发转录线程数，I/O密集型任务建议8-12 |
| `--chunk-duration` | 300 | 目标切块时长秒（静音检测模式下，实际在静音点处切） |
| `--silence-noise` | -30 | 静音检测噪声阈值 dB |
| `--silence-min-dur` | 0.3 | 最小静音时长秒 |
| `--no-silence` | false | 禁用静音检测，退回固定时长切块 |
| `--burn` | false | 烧录硬字幕到视频画面（重新编码视频，耗时较长） |
| `--embed` | false | 内嵌软字幕轨道到 MP4 容器（不重新编码，播放器可开关字幕） |
| `--burn-preset` | ultrafast | 烧录预设（ultrafast/superfast/veryfast/fast/medium） |
| `--burn-only` | false | 跳过转录，仅用已有字幕烧录/内嵌视频（断点续跑视频处理步骤） |

## 输出文件

- `<文件名>_subtitle.srt`：SRT 字幕文件（通用格式，外挂字幕首选）
- `<文件名>_subtitle.ass`：ASS 字幕文件（含精确排版样式）
- `<文件名>_软字幕版.mp4`：内嵌软字幕轨道的 MP4（`--embed` 时生成，播放器可开关字幕）
- `<文件名>_硬字幕版.mp4`：烧录硬字幕的 MP4（`--burn` 时生成，字幕永远显示）
- `chunks/`：中间音频片段（转录完成后可删除）
- `progress.jsonl`：转录进度（断点续跑用，完成后可删除）

## 字幕模式对比

| 模式 | 命令 | 速度 | 字幕可开关 | 文件大小 | 适用场景 |
|------|------|------|-----------|---------|---------|
| 外挂 SRT（默认） | 无需额外参数 | 最快（不处理视频） | 播放器加载 SRT 即可 | 原视频不变 | 大视频首选，灵活 |
| 内嵌软字幕 | `--embed` | 很快（仅容器复用） | ✅ 播放器内开关 | 略增（字幕轨） | 需要单文件分发 |
| 烧录硬字幕 | `--burn` | 慢（重新编码视频） | ❌ 永远显示 | 取决于编码 | 兼容性最高 |

## 断点续跑

长时间视频转录可能超过单次执行时限。脚本支持断点续跑：
- 转录进度保存在 `progress.jsonl`，重新运行同一命令即可从断点继续转录
- 音频文件已存在时自动跳过提取
- 视频处理（烧录/内嵌）采用**临时文件 + ffprobe 校验 + 原子重命名**，被中断时不会产出损坏的视频
- 视频处理前自动检查剩余时间预算，不足时跳过并提示用 `--burn-only` 单独完成
- 长视频推荐分两步执行：先转录生成字幕，再用 `--burn-only` / `--embed --burn-only` 处理视频

## 工作流程（v4 - 静音检测切块 + 外挂字幕）

1. **提取音频**：ffmpeg 从输入文件提取 mono 16kHz PCM 音频（已存在则跳过）
2. **预读音频到内存**：一次性读取整个 WAV 到内存缓冲，所有工作线程共享只读
3. **静音检测**：用 ffmpeg `silencedetect` 扫描音频，找到所有自然停顿点（≥0.3s）
4. **静音点切块**：在自然停顿处将音频切成大块（目标 ~300s/块，但总是在静音点下刀）
   - 不会从句子中间切断，每块都是完整的语音单元
   - 转录质量更高（输入是干净的自然语音段）
   - `--no-silence` 可退回固定时长切块（v3 行为）
5. **并发转录**：单一 ThreadPoolExecutor 全量提交，每块独立调用 aily-speech-to-text
   - aily-speech-to-text 返回 SRT 格式（含逐句时间戳）
   - 解析 SRT 并将时间戳偏移到全局位置
   - 默认 12 线程，网络等待型不受 CPU 核数限制
6. **去重后处理**：检测并去除转录引擎产生的重叠/重复条目，去末尾标点，切分过长句，合并过短条目
7. **生成字幕**：输出 SRT（通用格式）+ ASS（含精确排版）
8. **视频处理**（可选）：`--burn` 烧录硬字幕 / `--embed` 内嵌软字幕轨道

## 注意事项

- **默认不修改视频**：脚本默认仅输出 SRT + ASS 外挂字幕文件，原视频不变
- **外挂字幕使用**：将 SRT 文件与视频放在同一目录、同名，大多数播放器会自动加载；也可在播放器中手动加载
- **内嵌软字幕**（`--embed`）：不重新编码视频音频，仅做容器复用 + 字幕轨写入，速度快；支持在播放器中开关字幕
- **烧录硬字幕**（`--burn`）：重新编码视频，字幕烧入画面无法关闭；默认 ultrafast 预设，可通过 `--burn-preset` 调整
- **并发转录**：`--workers` 默认 8，网络等待型任务建议 8-12，不受 CPU 核数限制
- **大视频优化**：音频预读到内存后并发切片，避免 FUSE 并发读取冲突；切片文件用完即删
- **音频复用**：音频文件已存在时自动跳过提取
- 长视频（>10分钟）建议分两步执行：先转录生成字幕，再用 `--burn-only` / `--embed --burn-only` 处理视频
