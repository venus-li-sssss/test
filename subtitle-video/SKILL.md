---
name: subtitle-video
label: 字幕视频生成
description: >-
  为音视频文件生成逐句精准字幕并烧录到视频。输入视频或音频文件，输出带硬字幕的视频（+ASS/SRT字幕文件）。
  核心技术：ffmpeg静音检测切分→逐段独立转录→时间戳=实际音频位置（非按字数猜算）。
  使用场景：(1)用户要求给视频加字幕、生成字幕、烧录字幕；(2)用户要求给音频生成文字稿/字幕；
  (3)用户提到"字幕""subtitles"" captions""硬字幕""软字幕"；(4)用户上传视频/音频并要求转文字或加字幕。
  支持中文及多语言，支持断点续跑，支持纯音频输入（仅输出字幕文件不烧录）。
---

# 字幕视频生成

## 能力

- 输入：任意音视频文件（mp4/mov/avi/mkv/wav/mp3/m4a 等）
- 输出：带硬字幕的视频（ASS烧录）+ ASS字幕文件 + SRT字幕文件
- 纯音频输入：仅输出字幕文件，不烧录
- 时间戳精准：基于实际音频静音检测切分，每段独立转录，时间戳=真实音频位置
- 逐句字幕：一句话一条，单行显示，无末尾标点
- 支持断点续跑：长时间任务中断后重新运行可继续

## 前置依赖

- `ffmpeg` / `ffprobe`（音频处理与字幕烧录）
- `aily-speech-to-text`（语音识别转录工具）
- 中文字体 `Noto Sans CJK SC`（字幕渲染，沙箱预装）

## 使用方法

```bash
# 基本用法（视频→字幕视频）
python3 {baseDir}/scripts/generate_subtitled_video.py <input_file>

# 指定输出目录和语言
python3 {baseDir}/scripts/generate_subtitled_video.py <input_file> --language zh --output-dir ./output

# 自定义单行最大字符数和分段时长
python3 {baseDir}/scripts/generate_subtitled_video.py <input_file> --max-chars 26 --max-segment 4.0

# 调整静音检测灵敏度（嘈杂环境用更低如-40，安静环境用更高如-25）
python3 {baseDir}/scripts/generate_subtitled_video.py <input_file> --noise-db -30

# 转录和烧录分两步执行（长视频推荐）
python3 {baseDir}/scripts/generate_subtitled_video.py <input_file> --skip-burn   # 仅转录+生成字幕
python3 {baseDir}/scripts/generate_subtitled_video.py <input_file> --burn-only    # 仅用已有字幕烧录
```

## 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `input_file` | 必填 | 输入音视频文件路径 |
| `--language` | zh | 语言代码（zh/en/ja/ko等） |
| `--max-chars` | 26 | 单行最大字符数，超出则按标点切分 |
| `--output-dir` | ./output | 输出目录 |
| `--noise-db` | -30 | 静音检测阈值dB，越低越严格 |
| `--max-segment` | 4.0 | 最大分段时长（秒），超出则均分 |
| `--burn-only` | false | 跳过转录，仅用已有ASS字幕烧录视频（断点续跑烧录步骤） |
| `--skip-burn` | false | 跳过烧录，仅生成字幕文件 |
| `--time-budget` | 540 | 单次运行总时间预算（秒），给600秒超时留余量 |

## 输出文件

- `<文件名>_字幕版.mp4`：带硬字幕的视频
- `<文件名>_subtitle.ass`：ASS字幕文件（可用于其他工具软字幕）
- `<文件名>_subtitle.srt`：SRT字幕文件（通用格式）
- `chunks/`：中间音频片段（可删除）
- `progress.jsonl`：转录进度（断点续跑用，完成后可删除）

## 字幕样式

- 字体：Noto Sans CJK SC，48px
- 颜色：白色文字 + 黑色描边（2.5px）
- 位置：底部居中，MarginV=60
- 单行显示，无末尾标点

## 断点续跑

长时间视频转录可能超过单次执行时限。脚本支持断点续跑：
- 转录进度保存在 `progress.jsonl`，重新运行同一命令即可从断点继续转录
- 烧录步骤采用**临时文件 + ffprobe 校验 + 原子重命名**，被中断时不会产出损坏的视频文件
- 烧录前自动检查剩余时间预算，不足时跳过烧录并提示用 `--burn-only` 单独完成
- 已存在完好的字幕视频时自动跳过烧录（可用 `--burn-only` 强制重新烧录）
- 长视频推荐分两步执行：先 `--skip-burn` 转录，再 `--burn-only` 烧录

## 工作流程

1. **提取音频**：ffmpeg 从输入文件提取 mono 16kHz PCM 音频
2. **静音检测**：ffmpeg silencedetect 找出自然停顿点
3. **分段**：按停顿切成 1-4 秒短段（合并过短段、拆分过长段）
4. **逐段转录**：每段独立调用 aily-speech-to-text，时间戳=实际音频位置
5. **后处理**：去末尾标点、合并碎片、超长句按标点切分确保单行
6. **生成字幕**：输出 ASS（含精确排版）和 SRT（通用格式）
7. **时间预算检查**：预估烧录耗时，剩余时间不足则跳过烧录并提示
8. **烧录字幕**：ffmpeg 将 ASS 字幕烧录到视频画面（纯音频跳过此步）
   - 先写入 `.tmp.mp4` 临时文件
   - ffprobe 校验完整性
   - 校验通过后原子重命名为最终文件
   - 失败或被中断时清理临时文件，不会产出损坏的输出

## 注意事项

- 转录速度约 3 段/秒，10 分钟视频约需 5-8 分钟
- `aily-speech-to-text` 对单段短音频（1-4秒）转录效果最佳
- 字幕烧录为硬字幕（烧入画面），任何播放器均可显示
- 如需软字幕（可开关），直接使用输出的 .srt 或 .ass 文件
- 长视频（>10分钟）建议用 `--skip-burn` 和 `--burn-only` 分两步执行，避免单次超时
