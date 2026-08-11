#!/usr/bin/env python3
"""
逐句精准字幕生成器（v4 - 静音检测切块 + 大视频优化）
输入：音视频文件路径
输出：SRT字幕文件（默认外挂）+ ASS字幕文件 + 可选烧录/内嵌视频

核心流程：
1. 提取音频（已存在则跳过）
2. 预读音频到内存（避免 FUSE 并发读取冲突）
3. ffmpeg silencedetect 检测静音停顿点
4. 在静音停顿点处切割音频为大块（默认目标 300s/块，但总是在自然停顿处下刀）
5. 并发调用 aily-speech-to-text 转录每个大块
6. 合并所有块的 SRT，时间戳偏移到全局位置
7. 后处理：去标点、切分过长句、合并过短条目
8. 输出 SRT + ASS 字幕文件（默认）
9. 可选：--burn 烧录硬字幕 / --embed 内嵌软字幕到视频容器

v4 改进（vs v3）：
- 用 ffmpeg silencedetect 检测静音停顿，在自然停顿处切块（而非固定时长切割）
- 避免句子被从中间切断，每块都是完整的语音单元
- 转录质量更高（每块输入是干净的自然语音段）
- 保留 v3 的并发转录 + 断点续跑 + 大视频优化
"""
import argparse
import subprocess
import json
import re
import os
import time
import math
import sys
import threading
import wave
import io
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


# ============ 音频提取 ============

def extract_audio(input_file, audio_file):
    """从音视频文件提取音频（mono, 16kHz, PCM），已存在则跳过"""
    if os.path.exists(audio_file):
        try:
            result = subprocess.run([
                "ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", audio_file
            ], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                dur = float(json.loads(result.stdout).get("format", {}).get("duration", 0))
                if dur > 60:
                    print(f"  音频已存在 ({dur:.0f}s)，跳过提取")
                    return
        except Exception:
            pass
    print("=== 提取音频 ===")
    subprocess.run([
        "ffmpeg", "-y", "-i", input_file,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        audio_file
    ], check=True, capture_output=True)


def get_audio_duration(audio_file):
    """获取音频时长"""
    result = subprocess.run([
        "ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", audio_file
    ], capture_output=True, text=True)
    return float(json.loads(result.stdout)["format"]["duration"])


# ============ 静音检测 ============

def detect_silence(audio_file, noise_db=-30, min_duration=0.3):
    """
    用 ffmpeg silencedetect 检测音频中的静音停顿点。
    返回: list of {start, end, mid, duration}，按时间排序。
    """
    print(f"=== 静音检测 (noise={noise_db}dB, min_dur={min_duration}s) ===")
    result = subprocess.run([
        "ffmpeg", "-i", audio_file,
        "-af", f"silencedetect=noise={noise_db}dB:d={min_duration}",
        "-f", "null", "-"
    ], capture_output=True, text=True, timeout=300)

    silence_points = []
    # 解析 stderr 中的 silence_start / silence_end 对
    starts = re.findall(r'silence_start:\s*([\d.-]+)', result.stderr)
    ends = re.findall(r'silence_end:\s*([\d.]+)', result.stderr)

    for i in range(min(len(starts), len(ends))):
        s = float(starts[i])
        e = float(ends[i])
        if s < 0:
            s = 0
        mid = (s + e) / 2
        dur = e - s
        silence_points.append({
            'start': s,
            'end': e,
            'mid': mid,
            'duration': dur
        })

    print(f"  检测到 {len(silence_points)} 个静音停顿点")
    if silence_points:
        durs = [p['duration'] for p in silence_points]
        print(f"  停顿时长: min={min(durs):.2f}s, max={max(durs):.2f}s, avg={sum(durs)/len(durs):.2f}s")
    return silence_points


def compute_silence_based_chunks(total_duration, silence_points, target_chunk_dur=300, min_chunk_dur=60):
    """
    用静音停顿点作为切块边界，生成切块列表。
    策略：
    - 目标每块约 target_chunk_dur 秒
    - 总是在静音停顿点处下刀（不在说话中间切断）
    - 如果两个静音点之间间隔太长（> target_chunk_dur * 1.5），在目标时长处强制切（找最近的静音点）
    - 第一块从 0 开始，最后一块到 total_duration 结束

    返回: list of (start, duration) 元组
    """
    # 筛选适合作为切块边界的静音点（duration >= 0.3s，已在 detect_silence 中过滤）
    boundaries = [0.0]
    last_boundary = 0.0

    for sp in silence_points:
        mid = sp['mid']
        gap = mid - last_boundary

        # 如果距离上一个边界已经超过目标时长，在此静音点切
        if gap >= target_chunk_dur:
            boundaries.append(mid)
            last_boundary = mid
        # 如果距离已经接近目标时长的 1.5 倍且还没找到静音点，强制在此切（即使短了点）
        elif gap >= target_chunk_dur * 0.8 and gap >= min_chunk_dur:
            # 检查后面是否还有更合适的静音点（更接近 target）
            boundaries.append(mid)
            last_boundary = mid

    # 确保最后到 total_duration
    if boundaries[-1] < total_duration - 1:
        boundaries.append(total_duration)
    elif abs(boundaries[-1] - total_duration) < 1:
        boundaries[-1] = total_duration

    # 生成 (start, duration) 列表
    chunks = []
    for i in range(len(boundaries) - 1):
        start = boundaries[i]
        end = boundaries[i + 1]
        dur = end - start
        if dur >= 1.0:  # 忽略过短的块
            chunks.append((start, dur))

    # 合并过短的块（< min_chunk_dur 且不是唯一块）
    merged = []
    for start, dur in chunks:
        if merged and dur < min_chunk_dur and len(merged) + 1 < len(chunks):
            # 合并到前一块
            merged[-1] = (merged[-1][0], merged[-1][1] + dur)
        else:
            merged.append((start, dur))

    return merged if merged else [(0, total_duration)]


# ============ 预读音频到内存 + 并发转录 ============

_audio_buffer = None
_audio_framerate = None
_audio_sampwidth = None
_audio_n_channels = None
_audio_n_frames = None


def preload_audio(audio_file):
    """预读整个 WAV 文件到内存"""
    global _audio_buffer, _audio_framerate, _audio_sampwidth, _audio_n_channels, _audio_n_frames
    with wave.open(audio_file, 'rb') as wf:
        _audio_framerate = wf.getframerate()
        _audio_sampwidth = wf.getsampwidth()
        _audio_n_channels = wf.getnchannels()
        _audio_n_frames = wf.getnframes()
        _audio_buffer = wf.readframes(_audio_n_frames)
    size_mb = len(_audio_buffer) / 1024 / 1024
    print(f"  音频预读到内存: {size_mb:.1f}MB ({_audio_n_frames} frames, {_audio_framerate}Hz)")


def cut_wav_from_buffer(start, dur, chunk_file):
    """从内存缓冲切片并写入 WAV 文件"""
    start_frame = max(0, int(start * _audio_framerate))
    n_frames = max(1, int(dur * _audio_framerate))

    if start_frame >= _audio_n_frames:
        return False
    if start_frame + n_frames > _audio_n_frames:
        n_frames = _audio_n_frames - start_frame
    if n_frames < 1:
        return False

    frame_size = _audio_sampwidth * _audio_n_channels
    byte_start = start_frame * frame_size
    byte_end = byte_start + n_frames * frame_size
    chunk_data = _audio_buffer[byte_start:byte_end]

    with wave.open(chunk_file, 'wb') as wf_out:
        wf_out.setnchannels(_audio_n_channels)
        wf_out.setsampwidth(_audio_sampwidth)
        wf_out.setframerate(_audio_framerate)
        wf_out.writeframes(chunk_data)
    return True


def transcribe_chunk(chunk_start, chunk_dur, chunk_dir, chunk_idx, language="zh"):
    """转录一个大块：从内存切片 → 调 aily-speech-to-text → 返回 SRT 条目（已偏移到全局时间）"""
    chunk_wav = os.path.join(chunk_dir, f"chunk_{chunk_idx:04d}.wav")
    chunk_srt = os.path.join(chunk_dir, f"chunk_{chunk_idx:04d}.srt")

    try:
        if not cut_wav_from_buffer(chunk_start, chunk_dur, chunk_wav):
            return [], f"chunk_{chunk_idx}: cut failed (out of range)"
    except Exception as e:
        return [], f"chunk_{chunk_idx}: cut error: {e}"

    transcribe_timeout = max(120, int(chunk_dur * 1.5 + 60))
    result = subprocess.run([
        "aily-speech-to-text", chunk_wav,
        "--language", language, "--format", "srt",
        "--output-dir", chunk_dir,
        "--output-name", f"chunk_{chunk_idx:04d}"
    ], capture_output=True, text=True, timeout=transcribe_timeout)

    try:
        os.remove(chunk_wav)
    except Exception:
        pass

    if result.returncode != 0 or not os.path.exists(chunk_srt):
        err = result.stderr[-200:] if result.stderr else "unknown"
        return [], f"chunk_{chunk_idx}: transcribe failed: {err}"

    with open(chunk_srt, 'r', encoding='utf-8') as f:
        srt_content = f.read()

    entries = parse_srt_with_offset(srt_content, chunk_start)
    return entries, None


def parse_srt_with_offset(srt_content, time_offset):
    """解析 SRT 内容，将时间戳偏移 time_offset 秒"""
    entries = []
    blocks = srt_content.strip().split('\n\n')
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 2:
            continue
        time_line = None
        text_lines = []
        for line in lines:
            if '-->' in line:
                time_line = line
            elif not line.strip().isdigit() and time_line is not None:
                text_lines.append(line.strip())
        if not time_line or not text_lines:
            continue
        m = re.match(r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})', time_line)
        if not m:
            continue
        h1, m1, s1, ms1, h2, m2, s2, ms2 = m.groups()
        start = int(h1)*3600 + int(m1)*60 + int(s1) + int(ms1)/1000 + time_offset
        end = int(h2)*3600 + int(m2)*60 + int(s2) + int(ms2)/1000 + time_offset
        text = ' '.join(text_lines)
        entries.append({'start': start, 'end': end, 'text': text})
    return entries


# ============ 进度管理 ============

_progress_lock = threading.Lock()


def load_completed_chunks(progress_file):
    """加载已完成的 chunk 索引"""
    completed = {}
    if os.path.exists(progress_file):
        with open(progress_file, 'r') as f:
            for line in f:
                try:
                    d = json.loads(line)
                    if d.get('type') == 'chunk':
                        completed[d['idx']] = d.get('entries', [])
                except:
                    pass
    return completed


def save_chunk_progress(progress_file, idx, entries):
    """保存 chunk 转录进度"""
    with _progress_lock:
        with open(progress_file, 'a') as f:
            f.write(json.dumps({'type': 'chunk', 'idx': idx, 'entries': entries}) + '\n')


# ============ 字幕后处理 ============

def strip_trailing_punct(text):
    """去掉末尾标点"""
    return re.sub(r'[。！？，；：、…\.\,\!\?\;\s]+$', '', text.strip())


def split_long(text, max_chars):
    """切分过长文本"""
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
                while len(part) > max_chars:
                    result.append(part[:max_chars])
                    part = part[max_chars:]
                current = part
            else:
                current = part
    if current:
        result.append(current)
    return [r for r in result if r]


def deduplicate_entries(entries):
    """
    去除重叠/重复的字幕条目。
    策略：
    1. 按开始时间排序
    2. 对每条新条目，检查与结果列表中最近几条的时间重叠
    3. 如果重叠比例高（max(双方向) > 50%）且文本有包含关系 → 去重
    4. 如果重叠比例很高（max(双方向) > 65%）→ 去重（大概率重复转录）
    """
    if not entries:
        return []

    entries = sorted(entries, key=lambda e: e['start'])
    result = [entries[0]]

    for e in entries[1:]:
        should_skip = False
        # 检查与最近 5 条结果的重叠
        check_range = result[-5:] if len(result) >= 5 else result
        for j, prev in enumerate(check_range):
            actual_idx = len(result) - len(check_range) + j
            overlap_start = max(e['start'], prev['start'])
            overlap_end = min(e['end'], prev['end'])
            overlap = max(0, overlap_end - overlap_start)
            prev_dur = prev['end'] - prev['start']
            e_dur = e['end'] - e['start']
            overlap_ratio_prev = overlap / prev_dur if prev_dur > 0 else 0
            overlap_ratio_e = overlap / e_dur if e_dur > 0 else 0
            max_ratio = max(overlap_ratio_prev, overlap_ratio_e)

            prev_text = prev['text'].replace(' ', '').lower()
            e_text = e['text'].replace(' ', '').lower()
            text_subset = (e_text in prev_text) or (prev_text in e_text)

            if (max_ratio > 0.5 and text_subset) or max_ratio > 0.65:
                # 重复，保留文本更长的
                if len(e_text) > len(prev_text):
                    result[actual_idx] = e
                should_skip = True
                break

        if not should_skip:
            result.append(e)

    return result


def post_process_entries(entries, max_chars=26):
    """后处理字幕条目：去末尾标点、去重、切分过长句、合并过短条目"""
    # 先去重（去除重叠/重复条目）
    entries = deduplicate_entries(entries)

    processed = []
    for e in entries:
        text = strip_trailing_punct(e['text'])
        if not text:
            continue
        if len(text) > max_chars:
            parts = split_long(text, max_chars)
            total_chars = sum(len(p) for p in parts)
            seg_dur = e['end'] - e['start']
            cur = e['start']
            for part in parts:
                part_dur = (len(part) / total_chars) * seg_dur if total_chars > 0 else seg_dur / len(parts)
                processed.append({'start': cur, 'end': cur + part_dur, 'text': strip_trailing_punct(part)})
                cur += part_dur
        else:
            processed.append({'start': e['start'], 'end': e['end'], 'text': text})

    # 再次去重（切分后可能产生新的重叠）
    processed = deduplicate_entries(processed)

    # 合并过短条目
    merged = []
    for e in processed:
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


# ============ 字幕输出 ============

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
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        for i, e in enumerate(entries, 1):
            f.write(f"{i}\r\n")
            f.write(f"{sec_to_srt(e['start'])} --> {sec_to_srt(e['end'])}\r\n")
            f.write(f"{e['text']}\r\n\r\n")


# ============ 视频处理 ============

def verify_video(file_path):
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


def embed_soft_subtitles(input_file, srt_file, output_file):
    print("=== 内嵌软字幕到视频容器 ===")
    temp_file = output_file + ".tmp.mp4"
    if os.path.exists(temp_file):
        os.remove(temp_file)
    cmd = [
        "ffmpeg", "-y", "-i", input_file, "-i", srt_file,
        "-map", "0:v:0", "-map", "0:a:0", "-map", "1:s:0",
        "-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text",
        "-metadata:s:s:0", "language=chi", "-disposition:s:0", "default",
        "-movflags", "+faststart", temp_file
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        if os.path.exists(temp_file):
            os.remove(temp_file)
        print(f"  内嵌失败: {result.stderr[-500:]}")
        return False
    if not verify_video(temp_file):
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False
    os.rename(temp_file, output_file)
    return True


def estimate_burn_time(input_file, preset="ultrafast"):
    try:
        result = subprocess.run([
            "ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", input_file
        ], capture_output=True, text=True, timeout=10)
        streams = json.loads(result.stdout).get("streams", [])
        v = next((s for s in streams if s.get("codec_type") == "video"), None)
        if not v:
            return 300
        duration = float(v.get("duration", v.get("tags", {}).get("duration", 0)) or 0)
        if duration == 0:
            return 300
        height = int(v.get("height", 1080))
        preset_speeds = {
            "ultrafast": 25, "superfast": 20, "veryfast": 15,
            "faster": 10, "fast": 8, "medium": 5, "slow": 3
        }
        base_speed = preset_speeds.get(preset, 15)
        if height >= 1080:
            res_factor = 0.4
        elif height >= 720:
            res_factor = 0.7
        elif height >= 480:
            res_factor = 1.0
        else:
            res_factor = 1.5
        speed = base_speed * res_factor
        return duration / speed + 10
    except Exception:
        return 300


def burn_subtitles(input_file, ass_file, output_file, preset="ultrafast"):
    print(f"=== 烧录硬字幕到视频（预设: {preset}）===")
    temp_file = output_file + ".tmp.mp4"
    if os.path.exists(temp_file):
        os.remove(temp_file)
    cmd = [
        "ffmpeg", "-y", "-i", input_file,
        "-vf", f"ass={ass_file}",
        "-c:v", "libx264", "-preset", preset, "-crf", "23",
        "-c:a", "copy", "-movflags", "+faststart", temp_file
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        if os.path.exists(temp_file):
            os.remove(temp_file)
        print(f"  烧录失败: {result.stderr[-500:]}")
        return False
    if not verify_video(temp_file):
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False
    os.rename(temp_file, output_file)
    return True


# ============ 主流程 ============

def main():
    parser = argparse.ArgumentParser(
        description="字幕生成器（v4 - 静音检测切块 + 大视频优化）\n"
                    "用 ffmpeg silencedetect 在自然停顿处切块，并发转录，输出精准字幕。",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input_file", help="输入音视频文件路径")
    parser.add_argument("--language", default="zh", help="语言代码 (默认: zh)")
    parser.add_argument("--max-chars", type=int, default=26, help="单行最大字符数 (默认: 26)")
    parser.add_argument("--output-dir", default="./output", help="输出目录 (默认: ./output)")
    parser.add_argument("--time-budget", type=int, default=540, help="单次运行总时间预算秒 (默认: 540)")
    parser.add_argument("--workers", type=int, default=12, help="并发转录线程数 (默认: 12)")
    parser.add_argument("--chunk-duration", type=int, default=300,
                        help="目标切块时长秒 (默认: 300，实际在静音点处切)")
    parser.add_argument("--silence-noise", type=int, default=-30,
                        help="静音检测噪声阈值 dB (默认: -30)")
    parser.add_argument("--silence-min-dur", type=float, default=0.3,
                        help="最小静音时长秒 (默认: 0.3)")
    parser.add_argument("--no-silence", action="store_true",
                        help="禁用静音检测，退回固定时长切块（v3 行为）")
    parser.add_argument("--burn", action="store_true", help="烧录硬字幕到视频画面")
    parser.add_argument("--embed", action="store_true", help="内嵌软字幕轨道到 MP4 容器")
    parser.add_argument("--burn-preset", default="ultrafast", help="烧录预设 (默认: ultrafast)")
    parser.add_argument("--burn-only", action="store_true", help="跳过转录，仅用已有字幕烧录/内嵌")
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

    probe = subprocess.run([
        "ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", input_file
    ], capture_output=True, text=True)
    streams = json.loads(probe.stdout).get("streams", [])
    has_video = any(s.get("codec_type") == "video" for s in streams)

    if args.burn_only:
        target_ass = ass_file if os.path.exists(ass_file) else None
        target_srt = srt_file if os.path.exists(srt_file) else None
        if args.burn and not target_ass:
            print(f"错误：--burn --burn-only 需要 ASS 字幕文件已存在: {ass_file}")
            sys.exit(1)
        if args.embed and not target_srt:
            print(f"错误：--embed --burn-only 需要 SRT 字幕文件已存在: {srt_file}")
            sys.exit(1)
        if not target_ass and not target_srt:
            print(f"错误：--burn-only 需要字幕文件已存在: {ass_file} 或 {srt_file}")
            sys.exit(1)
        print(f"--burn-only 模式：跳过转录，直接处理视频")
        entries = []
        start_time = time.time()
    else:
        # Step 1: 提取音频
        extract_audio(input_file, audio_file)

        # Step 2: 预读音频到内存
        print("=== 预读音频 ===")
        preload_audio(audio_file)

        total_duration = get_audio_duration(audio_file)

        # Step 3: 静音检测 + 基于静音点的切块
        if args.no_silence:
            print("=== 固定时长切块（--no-silence）===")
            chunk_dur = args.chunk_duration
            num_chunks = math.ceil(total_duration / chunk_dur)
            chunks = []
            for i in range(num_chunks):
                start = i * chunk_dur
                dur = min(chunk_dur, total_duration - start)
                chunks.append((start, dur))
        else:
            silence_points = detect_silence(
                audio_file, args.silence_noise, args.silence_min_dur
            )
            chunks = compute_silence_based_chunks(
                total_duration, silence_points, args.chunk_duration
            )

        num_chunks = len(chunks)
        print(f"=== 音频切块（静音检测）===")
        print(f"  总时长: {total_duration:.1f}s = {total_duration/60:.1f}min")
        print(f"  切割块: {num_chunks} 块")
        for i, (s, d) in enumerate(chunks):
            print(f"    块 {i}: {s:.1f}s - {s+d:.1f}s ({d:.1f}s)")

        # Step 4: 加载已完成的块（断点续跑）
        completed_chunks = load_completed_chunks(progress_file)
        print(f"  已完成: {len(completed_chunks)}/{num_chunks} 块")

        pending = [i for i in range(num_chunks) if i not in completed_chunks]
        if not pending:
            print(f"  全部 {num_chunks} 块已转录（断点续跑命中）")
            all_entries = []
            for i in range(num_chunks):
                all_entries.extend(completed_chunks[i])
        else:
            print(f"=== 并发转录 ===")
            print(f"  待转录: {len(pending)} 块，并发数: {args.workers}")

            if args.burn and has_video:
                post_budget = estimate_burn_time(input_file, args.burn_preset)
            elif args.embed and has_video:
                post_budget = 30
            else:
                post_budget = 0
            transcribe_budget = args.time_budget - post_budget
            if transcribe_budget < 60:
                transcribe_budget = 60

            start_time = time.time()
            all_entries = []

            for i in range(num_chunks):
                if i in completed_chunks:
                    all_entries.extend(completed_chunks[i])

            total = len(pending)
            done_count = 0

            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                future_to_idx = {}
                for idx in pending:
                    chunk_start, chunk_dur = chunks[idx]
                    future = executor.submit(
                        transcribe_chunk, chunk_start, chunk_dur,
                        chunk_dir, idx, args.language
                    )
                    future_to_idx[future] = idx

                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    try:
                        entries, err = future.result()
                        if err:
                            print(f"  ⚠️ 块 {idx} 失败: {err}")
                            entries = []
                        all_entries.extend(entries)
                        save_chunk_progress(progress_file, idx, entries)
                    except Exception as e:
                        print(f"  ⚠️ 块 {idx} 异常: {e}")
                        save_chunk_progress(progress_file, idx, [])

                    done_count += 1
                    if done_count % 5 == 0 or done_count == total:
                        elapsed = time.time() - start_time
                        rate = done_count / elapsed if elapsed > 0 else 0
                        remaining = (total - done_count) / rate if rate > 0 else 0
                        print(f"  进度: {done_count}/{total} ({rate:.1f}/s, 预计剩余 {remaining:.0f}s)")

                    if time.time() - start_time > transcribe_budget:
                        print(f"  接近时间限制（已用 {time.time()-start_time:.0f}s / 预算 {transcribe_budget}s），"
                              f"已转录 {done_count}/{total}，取消剩余任务")
                        for f in future_to_idx:
                            if not f.done():
                                f.cancel()
                        break

            completed_chunks = load_completed_chunks(progress_file)
            all_entries = []
            for i in range(num_chunks):
                if i in completed_chunks:
                    all_entries.extend(completed_chunks[i])

            print(f"  已转录 {len(completed_chunks)}/{num_chunks} 块，共 {len(all_entries)} 条原始字幕")

            if len(completed_chunks) < num_chunks:
                print(f"  ⚠️ 转录未完成，字幕覆盖部分视频")

        global _audio_buffer
        _audio_buffer = None

        # Step 5: 后处理字幕
        all_entries.sort(key=lambda e: e['start'])
        entries = post_process_entries(all_entries, args.max_chars)
        print(f"  生成 {len(entries)} 条字幕（后处理后）")

        # Step 6: 写入字幕文件
        write_ass(entries, ass_file)
        write_srt(entries, srt_file)
        print(f"\n=== 字幕文件已生成 ===")
        print(f"  SRT: {srt_file}")
        print(f"  ASS: {ass_file}")

    # Step 7: 视频处理
    if has_video and (args.burn or args.embed):
        elapsed = time.time() - start_time
        remaining_budget = args.time_budget - elapsed

        if args.burn:
            output_video = os.path.join(output_dir, f"{base_name}_硬字幕版.mp4")
            burn_estimate = estimate_burn_time(input_file, args.burn_preset)
            print(f"\n=== 烧录硬字幕 ===")
            print(f"  已用 {elapsed:.0f}s / 预算 {args.time_budget}s，剩余 {remaining_budget:.0f}s")
            print(f"  预估烧录耗时 {burn_estimate:.0f}s（预设: {args.burn_preset}）")
            if remaining_budget < burn_estimate:
                print(f"  ⚠️ 剩余时间不足，跳过烧录")
                print(f"  请用: python3 {sys.argv[0]} {input_file} --output-dir {args.output_dir} --burn --burn-only")
            else:
                success = burn_subtitles(input_file, ass_file, output_video, args.burn_preset)
                if success:
                    print(f"  硬字幕视频: {output_video}")
                    print(f"  ✓ 烧录完成且通过完整性校验")
                else:
                    print(f"  ✗ 烧录失败")
                    print(f"  请用: python3 {sys.argv[0]} {input_file} --output-dir {args.output_dir} --burn --burn-only")

        if args.embed:
            output_video = os.path.join(output_dir, f"{base_name}_软字幕版.mp4")
            print(f"\n=== 内嵌软字幕 ===")
            print(f"  已用 {elapsed:.0f}s / 预算 {args.time_budget}s，剩余 {remaining_budget:.0f}s")
            if remaining_budget < 30:
                print(f"  ⚠️ 剩余时间不足，跳过内嵌")
                print(f"  请用: python3 {sys.argv[0]} {input_file} --output-dir {args.output_dir} --embed --burn-only")
            else:
                success = embed_soft_subtitles(input_file, srt_file, output_video)
                if success:
                    print(f"  软字幕视频: {output_video}")
                    print(f"  ✓ 内嵌完成且通过完整性校验")
                else:
                    print(f"  ✗ 内嵌失败")
                    print(f"  请用: python3 {sys.argv[0]} {input_file} --output-dir {args.output_dir} --embed --burn-only")
    elif not args.burn and not args.embed:
        print(f"\n  默认模式：仅输出外挂字幕文件（SRT + ASS）")
        print(f"  如需烧录硬字幕: 加 --burn")
        print(f"  如需内嵌软字幕: 加 --embed")

    if entries:
        print(f"\n=== 前10条字幕 ===")
        for i, e in enumerate(entries[:10], 1):
            print(f"  {i}. [{e['start']:.1f}-{e['end']:.1f}s] {e['text']}")

        print(f"\n=== 最后5条字幕 ===")
        for i, e in enumerate(entries[-5:], len(entries)-4):
            print(f"  {i}. [{e['start']:.1f}-{e['end']:.1f}s] {e['text']}")

        print(f"\n完成！共 {len(entries)} 条字幕")


if __name__ == "__main__":
    main()
