#!/usr/bin/env python3
"""
逐句精准字幕生成器
输入：音视频文件路径
输出：带硬字幕的视频文件 + ASS字幕文件 + SRT字幕文件

流程：
1. 提取音频
2. ffmpeg静音检测 → 切成1-4秒短段
3. 每段独立调用 aily-speech-to-text 转录（时间戳=实际音频位置）
4. 合并碎片、去末尾标点、单行≤26字
5. 生成ASS字幕
6. ffmpeg烧录到视频（纯音频输入则跳过烧录）
7. 支持断点续跑（进度文件）

用法：
  python3 generate_subtitled_video.py <input_file> [--language zh] [--max-chars 26] [--output-dir ./output]
"""
import argparse
import subprocess
import json
import re
import os
import time
import math
import sys
from pathlib import Path


def extract_audio(input_file, audio_file):
    """从音视频文件提取音频（mono, 16kHz, PCM）"""
    print("=== 提取音频 ===")
    subprocess.run([
        "ffmpeg", "-y", "-i", input_file,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        audio_file
    ], check=True, capture_output=True)


def get_duration(audio_file):
    """获取音频时长"""
    result = subprocess.run([
        "ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", audio_file
    ], capture_output=True, text=True)
    return float(json.loads(result.stdout)["format"]["duration"])


def detect_speech_segments(audio_file, noise_db=-30, min_silence=0.25):
    """用ffmpeg静音检测找出语音段落"""
    print("=== 检测语音段落 ===")
    result = subprocess.run([
        "ffmpeg", "-i", audio_file,
        "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}",
        "-f", "null", "-"
    ], capture_output=True, text=True)

    silence_starts = []
    silence_ends = []
    for line in result.stderr.split('\n'):
        if 'silence_start:' in line:
            m = re.search(r'silence_start:\s*([\d.]+)', line)
            if m:
                silence_starts.append(float(m.group(1)))
        elif 'silence_end:' in line:
            m = re.search(r'silence_end:\s*([\d.]+)', line)
            if m:
                silence_ends.append(float(m.group(1)))

    total_duration = get_duration(audio_file)

    speech_segments = []
    prev_end = 0.0
    for s_start, s_end in zip(silence_starts, silence_ends):
        if s_start - prev_end > 0.3:
            speech_segments.append((prev_end, s_start))
        prev_end = s_end
    if total_duration - prev_end > 0.3:
        speech_segments.append((prev_end, total_duration))

    return speech_segments, total_duration


def merge_and_split_segments(speech_segments, max_dur=4.0, min_dur=0.8):
    """合并过短段、拆分过长段"""
    # 合并过短段
    merged = []
    for seg in speech_segments:
        if merged and (seg[1] - seg[0]) < min_dur:
            prev = merged[-1]
            merged[-1] = (prev[0], seg[1])
        elif merged and (seg[0] - merged[-1][1]) < 0.3:
            prev = merged[-1]
            merged[-1] = (prev[0], seg[1])
        else:
            merged.append(seg)

    # 拆分过长段
    final = []
    for start, end in merged:
        dur = end - start
        if dur > max_dur:
            n = math.ceil(dur / max_dur)
            split_dur = dur / n
            for i in range(n):
                final.append((start + i * split_dur, min(start + (i + 1) * split_dur, end)))
        else:
            final.append((start, end))

    return final


def transcribe_segment(audio_file, seg_start, seg_end, chunk_dir, idx, language="zh"):
    """转录单个音频片段"""
    chunk_file = os.path.join(chunk_dir, f"seg_{idx:04d}.wav")
    chunk_srt = os.path.join(chunk_dir, f"seg_{idx:04d}.srt")
    seg_dur = seg_end - seg_start

    subprocess.run([
        "ffmpeg", "-y", "-i", audio_file,
        "-ss", str(seg_start), "-t", str(seg_dur),
        "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        chunk_file
    ], check=True, capture_output=True)

    result = subprocess.run([
        "aily-speech-to-text", chunk_file,
        "--language", language, "--format", "srt",
        "--output-dir", chunk_dir,
        "--output-name", f"seg_{idx:04d}"
    ], capture_output=True, text=True, timeout=30)

    if result.returncode == 0 and os.path.exists(chunk_srt):
        with open(chunk_srt, 'r', encoding='utf-8') as f:
            srt_content = f.read()
        lines = srt_content.strip().split('\n')
        texts = [l for l in lines if l and not l.isdigit() and '-->' not in l]
        return ''.join(texts)
    return ""


def strip_trailing_punct(text):
    """去掉末尾标点"""
    return re.sub(r'[。！？，；：、…\.\,\!\?\;\s]+$', '', text.strip())


def split_long(text, max_chars):
    """切分过长文本，保持英文单词完整"""
    if len(text) <= max_chars:
        return [text]
    parts = re.split(r'(?<=[，,。！？；：、])', text)
    result = []
    current = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(current) + len(part) <= max_chars:
            current += part
        else:
            if current:
                result.append(current)
            if len(part) > max_chars:
                tokens = re.split(r'(\s+)', part)
                cur = ""
                for tok in tokens:
                    if len(cur) + len(tok) <= max_chars:
                        cur += tok
                    else:
                        if cur.strip():
                            result.append(cur.strip())
                        cur = tok
                        while len(cur) > max_chars:
                            result.append(cur[:max_chars])
                            cur = cur[max_chars:]
                if cur.strip():
                    result.append(cur.strip())
            else:
                current = part
    if current:
        result.append(current)
    return [r for r in result if r]


def build_subtitle_entries(segments, results, max_chars=26):
    """构建字幕条目"""
    all_entries = []
    for idx, (seg_start, seg_end) in enumerate(segments):
        text = results.get(idx, "").strip()
        if not text:
            continue
        text = strip_trailing_punct(text)
        if not text:
            continue

        if len(text) > max_chars:
            parts = split_long(text, max_chars)
            total_chars = sum(len(p) for p in parts)
            seg_dur = seg_end - seg_start
            cur = seg_start
            for part in parts:
                part_dur = (len(part) / total_chars) * seg_dur if total_chars > 0 else seg_dur / len(parts)
                all_entries.append({'start': cur, 'end': cur + part_dur, 'text': strip_trailing_punct(part)})
                cur += part_dur
        else:
            all_entries.append({'start': seg_start, 'end': seg_end, 'text': text})

    # 合并过短条目
    merged = []
    for e in all_entries:
        dur = e['end'] - e['start']
        if (len(e['text']) < 3 or dur < 0.5) and merged:
            merged[-1]['text'] += e['text']
            merged[-1]['end'] = e['end']
        else:
            merged.append(e.copy())

    for e in merged:
        e['text'] = strip_trailing_punct(e['text'])
    merged = [e for e in merged if e['text']]

    return merged


def sec_to_ass(sec):
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def sec_to_srt(sec):
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{int(s):02d},{int((s % 1) * 1000):03d}"


def write_ass(entries, output_path):
    """生成ASS字幕文件"""
    ass_header = """[Script Info]
Title: Subtitles
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Noto Sans CJK SC,48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2.5,1,2,80,80,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(ass_header)
        for e in entries:
            text = e['text'].replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}')
            f.write(f"Dialogue: 0,{sec_to_ass(e['start'])},{sec_to_ass(e['end'])},Default,,0,0,0,,{text}\n")


def write_srt(entries, output_path):
    """生成SRT字幕文件"""
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, e in enumerate(entries, 1):
            f.write(f"{i}\n")
            f.write(f"{sec_to_srt(e['start'])} --> {sec_to_srt(e['end'])}\n")
            f.write(f"{e['text']}\n\n")


def estimate_burn_time(input_file):
    """根据视频时长和分辨率估算烧录耗时（秒）"""
    try:
        result = subprocess.run([
            "ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", input_file
        ], capture_output=True, text=True, timeout=10)
        streams = json.loads(result.stdout).get("streams", [])
        v = next((s for s in streams if s.get("codec_type") == "video"), None)
        if not v:
            return 300  # 保守默认值
        duration = float(v.get("duration", v.get("tags", {}).get("duration", 0)) or 0)
        if duration == 0:
            return 300
        # 1080p 约 2x 实时速度，720p 约 3x，480p 约 5x
        height = int(v.get("height", 1080))
        if height >= 1080:
            speed = 2.0
        elif height >= 720:
            speed = 3.0
        else:
            speed = 5.0
        return duration / speed + 10  # +10s 安全余量
    except Exception:
        return 300


def verify_video(file_path):
    """验证视频文件完整性（ffprobe 能正常解析即视为完好）"""
    try:
        result = subprocess.run([
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", file_path
        ], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return False
        data = json.loads(result.stdout)
        return "format" in data and "streams" in data and len(data["streams"]) > 0
    except Exception:
        return False


def burn_subtitles(input_file, ass_file, output_file):
    """将ASS字幕烧录到视频（写临时文件→校验→重命名，防止产出损坏文件）"""
    print("=== 烧录字幕到视频 ===")
    temp_file = output_file + ".tmp.mp4"

    # 如果已有临时文件残留，先清理
    if os.path.exists(temp_file):
        os.remove(temp_file)

    # 烧录到临时文件，加 faststart 优化 MP4 容器
    cmd = [
        "ffmpeg", "-y", "-i", input_file,
        "-vf", f"ass={ass_file}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "copy",
        "-movflags", "+faststart",
        temp_file
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        # 烧录失败，清理临时文件
        if os.path.exists(temp_file):
            os.remove(temp_file)
        print(f"  烧录失败: {result.stderr[-500:]}")
        return False

    # 校验临时文件完整性
    if not verify_video(temp_file):
        print("  烧录输出文件校验失败（损坏），已丢弃")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False

    # 校验通过，原子重命名到最终路径
    os.rename(temp_file, output_file)
    return True


def main():
    parser = argparse.ArgumentParser(description="逐句精准字幕生成器")
    parser.add_argument("input_file", help="输入音视频文件路径")
    parser.add_argument("--language", default="zh", help="语言代码 (默认: zh)")
    parser.add_argument("--max-chars", type=int, default=26, help="单行最大字符数 (默认: 26)")
    parser.add_argument("--output-dir", default="./output", help="输出目录 (默认: ./output)")
    parser.add_argument("--noise-db", type=int, default=-30, help="静音检测阈值dB (默认: -30)")
    parser.add_argument("--max-segment", type=float, default=4.0, help="最大分段时长秒 (默认: 4.0)")
    parser.add_argument("--burn-only", action="store_true", help="跳过转录，仅用已有字幕文件烧录视频（用于断点续跑烧录步骤）")
    parser.add_argument("--skip-burn", action="store_true", help="跳过烧录步骤，仅生成字幕文件")
    parser.add_argument("--time-budget", type=int, default=540, help="单次运行总时间预算秒 (默认: 540，给600秒超时留余量)")
    args = parser.parse_args()

    input_file = args.input_file
    if not os.path.exists(input_file):
        print(f"错误：文件不存在: {input_file}")
        sys.exit(1)

    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)
    chunk_dir = os.path.join(output_dir, "chunks")
    os.makedirs(chunk_dir, exist_ok=True)
    progress_file = os.path.join(output_dir, "progress.jsonl")

    base_name = Path(input_file).stem
    audio_file = os.path.join(output_dir, f"{base_name}_audio.wav")
    ass_file = os.path.join(output_dir, f"{base_name}_subtitle.ass")
    srt_file = os.path.join(output_dir, f"{base_name}_subtitle.srt")

    # 判断是纯音频还是视频
    probe = subprocess.run([
        "ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", input_file
    ], capture_output=True, text=True)
    streams = json.loads(probe.stdout).get("streams", [])
    has_video = any(s.get("codec_type") == "video" for s in streams)

    # Step 1: 提取音频
    extract_audio(input_file, audio_file)

    # Step 2: 检测语音段落
    speech_segments, total_duration = detect_speech_segments(audio_file, args.noise_db)
    segments = merge_and_split_segments(speech_segments, max_dur=args.max_segment)
    print(f"  共 {len(segments)} 个语音段落，平均时长 {sum(e-s for s,e in segments)/len(segments):.1f}s")

    # Step 3: 逐段转录（带断点续跑）
    # --burn-only 模式跳过转录，直接用已有字幕烧录
    if args.burn_only:
        if not os.path.exists(ass_file):
            print(f"错误：--burn-only 需要 ASS 字幕文件已存在: {ass_file}")
            print("请先不带 --burn-only 运行以生成字幕")
            sys.exit(1)
        print(f"--burn-only 模式：跳过转录，直接用已有字幕烧录")
        entries = []
        # 跳到烧录步骤
        has_video = True  # burn-only 仅用于视频
        segments = []
        results = {}
        start_time = time.time()
    else:
        print("=== 逐段转录 ===")
        completed = set()
        if os.path.exists(progress_file):
            with open(progress_file, 'r') as f:
                for line in f:
                    try:
                        d = json.loads(line)
                        completed.add(d['idx'])
                    except:
                        pass

        results = {}
        start_time = time.time()
        # 转录时间预算：总预算减去留给烧录的时间（至少留 estimate_burn_time 返回值）
        burn_estimate = estimate_burn_time(input_file) if has_video else 0
        transcribe_budget = args.time_budget - burn_estimate
        if transcribe_budget < 60:
            transcribe_budget = 60  # 至少给转录 60 秒

        for idx, (seg_start, seg_end) in enumerate(segments):
            if idx in completed:
                chunk_srt = os.path.join(chunk_dir, f"seg_{idx:04d}.srt")
                if os.path.exists(chunk_srt):
                    with open(chunk_srt, 'r', encoding='utf-8') as f:
                        srt_content = f.read()
                    lines = srt_content.strip().split('\n')
                    texts = [l for l in lines if l and not l.isdigit() and '-->' not in l]
                    results[idx] = ''.join(texts)
                continue

            text = transcribe_segment(audio_file, seg_start, seg_end, chunk_dir, idx, args.language)
            results[idx] = text

            with open(progress_file, 'a') as f:
                f.write(json.dumps({'idx': idx, 'text': text}) + '\n')

            if (idx + 1) % 10 == 0:
                elapsed = time.time() - start_time
                rate = (idx + 1) / elapsed if elapsed > 0 else 0
                remaining = (len(segments) - idx - 1) / rate if rate > 0 else 0
                print(f"  进度: {idx+1}/{len(segments)} ({rate:.1f}/s, 预计剩余 {remaining:.0f}s)")

            if time.time() - start_time > transcribe_budget:
                print(f"  接近时间限制（已用 {time.time()-start_time:.0f}s / 预算 {transcribe_budget}s），已保存进度 {idx+1}/{len(segments)}")
                print(f"  烧录预算 {burn_estimate}s，重新运行可继续转录+烧录")
                break

        print(f"  已转录 {len(results)}/{len(segments)} 段")

        # Step 4: 构建字幕
        entries = build_subtitle_entries(segments, results, args.max_chars)
        print(f"  生成 {len(entries)} 条字幕")

        # Step 5: 写入字幕文件
        write_ass(entries, ass_file)
        write_srt(entries, srt_file)
        print(f"  ASS: {ass_file}")
        print(f"  SRT: {srt_file}")

    # Step 6: 烧录字幕（仅视频）
    if has_video and not args.skip_burn:
        # burn-only 模式下直接用已有的 ass_file；否则检查转录是否完成
        if not args.burn_only:
            all_transcribed = len(results) >= len(segments)
            if not all_transcribed:
                print(f"  转录未完成（{len(results)}/{len(segments)}），但先生成字幕文件")
                print(f"  可稍后用 --burn-only 单独完成烧录")

        output_video = os.path.join(output_dir, f"{base_name}_字幕版.mp4")

        # 检查是否已有完好的烧录输出（断点续跑场景）
        if os.path.exists(output_video) and verify_video(output_video):
            print(f"  已存在完好的字幕视频: {output_video}（跳过烧录）")
        else:
            elapsed = time.time() - start_time
            remaining_budget = args.time_budget - elapsed
            burn_estimate = estimate_burn_time(input_file)
            print(f"  已用 {elapsed:.0f}s / 预算 {args.time_budget}s，剩余 {remaining_budget:.0f}s")
            print(f"  预估烧录耗时 {burn_estimate:.0f}s")

            if remaining_budget < burn_estimate:
                print(f"  ⚠️ 剩余时间不足（{remaining_budget:.0f}s < 需要 {burn_estimate:.0f}s），跳过烧录")
                print(f"  字幕文件已生成: {ass_file}")
                print(f"  请用以下命令单独烧录: python3 {sys.argv[0]} {input_file} --output-dir {args.output_dir} --burn-only")
            else:
                success = burn_subtitles(input_file, ass_file, output_video)
                if success:
                    print(f"  字幕视频: {output_video}")
                    print(f"  ✓ 烧录完成且通过完整性校验")
                else:
                    print(f"  ✗ 烧录失败，未生成输出视频")
                    print(f"  字幕文件已生成: {ass_file}")
                    print(f"  请用以下命令重试烧录: python3 {sys.argv[0]} {input_file} --output-dir {args.output_dir} --burn-only")
    elif args.skip_burn:
        print("  --skip-burn 模式：跳过字幕烧录")
    else:
        print("  输入为纯音频，跳过字幕烧录")

    # 预览
    print(f"\n=== 前10条字幕 ===")
    for i, e in enumerate(entries[:10], 1):
        dur = e['end'] - e['start']
        print(f"  {i}. [{e['start']:.1f}-{e['end']:.1f}s] {e['text']}")

    print(f"\n完成！共 {len(entries)} 条字幕")


if __name__ == "__main__":
    main()
