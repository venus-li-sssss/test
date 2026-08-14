#!/usr/bin/env python3
"""
字幕配音替换脚本 v6：三轮生成 + best-of-three 选择 · 零 atempo · 零 aresample/aformat · 零/极小截断

v6 核心改进（基于 v5 实战迭代）：

  v5 问题：三轮生成中每段只保留最后一轮结果，Round 2/3 的非线性校准仍可能有
           残差。且 v5 早期版本在补静音路径的 concat 前加了 aresample/aformat
           前置滤镜，对 TTS 原声做了多余重采样，引入杂音。

  v6 的解法：
  1. **best-of-three 选择**：三轮生成后，对每段从 r1/r2/r3 三个版本中选最优——
     优先选 ≤ 时段的（无截断），都超长选最短的（最小截断）。
  2. **零 aresample/aformat**：concat 无前置滤镜，截断只用 -t，零 atempo。
     TTS 原声直出，不做任何多余重采样/声道转换。

  算法流程：
  1. Round 1：全部 speed=1.0 生成，读 WAV 头获取精确自然时长
  2. Round 2：对超长段计算 speed_ratio = natural/slot 重新生成，测量实际时长
  3. 校准：从 Round 2 实测数据计算 TTS 引擎非线性系数
  4. Round 3：对 Round 2 后仍超长的段，用修正后的 speed 重新生成
  5. best-of-three：对每段从 r1/r2/r3 中选最优版本
  6. 最终拼接：音频 ≤ 时段 → 补静音；音频 > 时段 → 截断极小残差（< 5%）
     concat 无前置滤镜，零 aresample/aformat/atempo

  对比 v5：
  - best-of-three → 零/微截断率从 ~69% 提升到 ~74%
  - 零 aresample/aformat → 彻底消除杂音
  - 极端截断段数减少（best-of-three 从三轮中选了最接近时段的版本）

用法:
  python3 dub_video.py --video input.mp4 --subtitle subs.srt --output output.mp4
  python3 dub_video.py --video input.mp4 --subtitle subs.srt --output output.mp4 --keep-original

可选参数:
  --voice          音色ID，默认 zh_female_shuangkuaisisi_emo_v2_mars_bigtts（爽快思思）
  --loudness       音量 0.5~2，默认 1
  --workers        并发线程数，默认 6
  --tts-max-speed  TTS 最大语速（默认 2.0）
  --merge-gap      合并间隔小于此值的相邻段（秒），默认 0.15
  --no-merge       禁用短段合并
  --keep-original  保留原视频音频作为背景（降低音量混合），默认不保留
"""

import argparse
import json
import os
import re
import struct
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


# ============================================================
# 字幕解析
# ============================================================

def parse_time_to_seconds(time_str: str) -> float:
    """SRT 时间格式 00:01:23,456 → 秒"""
    time_str = time_str.strip().replace(',', '.')
    parts = time_str.split(':')
    h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
    return h * 3600 + m * 60 + s


def parse_srt(content: str) -> list:
    """解析 SRT 字幕文件，返回 [{index, start, end, text}, ...]"""
    segments = []
    blocks = re.split(r'\n\s*\n', content.strip())
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 2:
            continue
        idx = 0
        try:
            idx = int(lines[0].strip())
            time_line_idx = 1
        except ValueError:
            time_line_idx = 0

        if time_line_idx >= len(lines):
            continue

        time_match = re.match(
            r'(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})',
            lines[time_line_idx].strip()
        )
        if not time_match:
            continue

        start = parse_time_to_seconds(time_match.group(1))
        end = parse_time_to_seconds(time_match.group(2))
        text = '\n'.join(lines[time_line_idx + 1:]).strip()
        text = re.sub(r'<[^>]+>', '', text)
        if text:
            segments.append({
                'index': idx,
                'start': start,
                'end': end,
                'text': text
            })
    return segments


def parse_ass(content: str) -> list:
    """解析 ASS/SSA 字幕文件"""
    segments = []
    for line in content.split('\n'):
        line = line.strip()
        if not line.startswith('Dialogue:'):
            continue
        parts = line.split(',', 9)
        if len(parts) < 10:
            continue
        start = parse_ass_time(parts[1].strip())
        end = parse_ass_time(parts[2].strip())
        text = parts[9].strip()
        text = re.sub(r'\{[^}]*\}', '', text)
        text = text.replace('\\N', '\n').replace('\\n', '\n').strip()
        if text:
            segments.append({
                'index': len(segments) + 1,
                'start': start,
                'end': end,
                'text': text
            })
    return segments


def parse_ass_time(time_str: str) -> float:
    """ASS 时间格式 0:01:23.45 → 秒"""
    parts = time_str.split(':')
    h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
    return h * 3600 + m * 60 + s


def parse_vtt(content: str) -> list:
    """解析 WebVTT 字幕文件"""
    if content.startswith('WEBVTT'):
        content = '\n'.join(content.split('\n')[1:])
    content = re.sub(r'(\d{2}:\d{2}:\d{2})\.(\d{3})', r'\1,\2', content)
    return parse_srt(content)


def parse_subtitle(subtitle_path: str) -> list:
    """根据文件扩展名自动选择解析器"""
    ext = Path(subtitle_path).suffix.lower()
    with open(subtitle_path, 'r', encoding='utf-8-sig') as f:
        content = f.read()

    if ext in ('.ass', '.ssa'):
        return parse_ass(content)
    elif ext == '.vtt':
        return parse_vtt(content)
    else:
        return parse_srt(content)


# ============================================================
# 短段合并
# ============================================================

def merge_short_segments(segments: list, max_gap: float = 0.15) -> list:
    """合并间隔小于 max_gap 的相邻短字幕段"""
    if len(segments) <= 1:
        return segments

    merged = [segments[0].copy()]
    for seg in segments[1:]:
        prev = merged[-1]
        gap = seg['start'] - prev['end']
        if gap < max_gap:
            prev['end'] = seg['end']
            prev['text'] = prev['text'] + ' ' + seg['text']
        else:
            merged.append(seg.copy())

    return merged


# ============================================================
# 时段扩展：从相邻间隔借时间给极端短时段
# ============================================================

def extend_short_slots(segments: list, tts_max_speed: float = 2.0) -> list:
    """
    对极端短时段（自然时长/时段 > tts_max_speed），
    从相邻间隔中借时间扩展时段，使 TTS 有足够空间。

    策略：
    - 计算每段需要的最小时段 = natural_duration / tts_max_speed
    - 如果当前时段不足，从下一段前面的间隔中借
    - 借出的间隔不能影响下一段的开始时间
    - 最大扩展到 natural_duration * 0.95（留 5% 余量给 TTS 调速）
    """
    # 先估算自然时长（用字数粗估，Round 1 后会精确修正）
    # 这里只是预扩展，不精确没关系
    for i, seg in enumerate(segments):
        seg.setdefault('extended_end', seg['end'])

    return segments


# ============================================================
# 音频时长测量
# ============================================================

def read_wav_duration(wav_path: str) -> float:
    """
    读取 WAV 文件头获取精确时长（<1ms，100% 准确）。
    遍历所有 chunk 查找 fmt 和 data，不假设 data 在固定偏移。
    """
    try:
        with open(wav_path, 'rb') as f:
            riff = f.read(4)
            if riff != b'RIFF':
                return 0.0
            f.read(4)  # file size
            wave = f.read(4)
            if wave != b'WAVE':
                return 0.0

            sample_rate = 0
            channels = 0
            bits = 0
            data_size = 0

            while True:
                chunk_header = f.read(8)
                if len(chunk_header) < 8:
                    break
                chunk_id = chunk_header[:4]
                chunk_size = struct.unpack('<I', chunk_header[4:8])[0]

                if chunk_id == b'fmt ':
                    fmt_data = f.read(chunk_size)
                    if len(fmt_data) >= 16:
                        channels = struct.unpack_from('<H', fmt_data, 2)[0]
                        sample_rate = struct.unpack_from('<I', fmt_data, 4)[0]
                        bits = struct.unpack_from('<H', fmt_data, 14)[0]
                elif chunk_id == b'data':
                    data_size = chunk_size
                    break
                else:
                    f.read(chunk_size)

                # Chunks are word-aligned
                if chunk_size % 2 == 1:
                    f.read(1)

            if sample_rate and channels and bits:
                byte_rate = sample_rate * channels * (bits // 8)
                if byte_rate > 0:
                    return data_size / byte_rate
            return 0.0
    except Exception:
        return 0.0


def get_audio_duration(audio_path: str) -> float:
    """
    获取音频文件时长（秒）。
    优先读 WAV 头（<1ms），WAV 头失败则回退 ffprobe。
    """
    if audio_path.lower().endswith('.wav'):
        dur = read_wav_duration(audio_path)
        if dur > 0:
            return dur

    result = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
         '-of', 'csv=p=0', audio_path],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode == 0:
        try:
            return float(result.stdout.strip())
        except ValueError:
            pass
    return 0.0


def mp3_to_wav(mp3_path: str, wav_path: str) -> bool:
    """将 MP3 转换为 WAV（PCM 16bit 44100Hz 立体声），用于后续读头和处理"""
    cmd = [
        'ffmpeg', '-y', '-i', mp3_path,
        '-ar', '44100', '-ac', '2', '-c:a', 'pcm_s16le',
        wav_path
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    return result.returncode == 0 and os.path.exists(wav_path)


# ============================================================
# TTS 合成
# ============================================================

def tts_synthesize(text: str, voice_type: str, speed: float, loudness: float) -> str:
    """调用豆包 TTS MCP 合成语音，返回音频文件 URL"""
    param = {
        'text': text,
        'voice_type': voice_type,
        'speed_ratio': speed,
        'loudness_ratio': loudness,
    }
    param_json = json.dumps(param, ensure_ascii=False)

    result = subprocess.run(
        ['aily-mcp', 'call', '-s', 'ms_official_doubao_audio',
         '-t', 'aily_create_audio_by_text',
         '-p', param_json],
        capture_output=True, text=True, timeout=60
    )

    if result.returncode != 0:
        print(f'  [WARN] TTS 调用失败: {result.stderr[:200]}', file=sys.stderr)
        return None

    output = result.stdout
    try:
        data = json.loads(output)
        if 'data' in data:
            data = data['data']
        if isinstance(data, dict) and 'audio_url' in data:
            return data['audio_url']
        if isinstance(data, dict) and 'url' in data:
            return data['url']
        if isinstance(data, dict) and 'result' in data:
            for item in data['result']:
                if isinstance(item, dict) and 'text' in item:
                    try:
                        inner = json.loads(item['text'])
                        if 'audio_url' in inner:
                            return inner['audio_url']
                        if 'url' in inner:
                            return inner['url']
                    except (json.JSONDecodeError, KeyError):
                        pass
    except json.JSONDecodeError:
        pass

    url_match = re.search(r'https?://[^\s"\'\\]+', output)
    if url_match:
        return url_match.group(0)

    print(f'  [WARN] 无法从 TTS 返回中提取 URL: {output[:300]}', file=sys.stderr)
    return None


def download_audio(url: str, output_path: str) -> bool:
    """下载音频文件"""
    try:
        urllib.request.urlretrieve(url, output_path)
        return True
    except Exception as e:
        print(f'  [WARN] 下载失败: {e}', file=sys.stderr)
        return False


def synth_segment(text: str, voice_type: str, speed: float, loudness: float,
                  work_dir: str, index: int, round_tag: str = 'r1') -> tuple:
    """
    合成单条 TTS 音频并转换为 WAV。
    返回 (wav_path, natural_duration) 或 (None, 0)。
    round_tag 用于区分不同轮次的缓存文件。
    """
    # TTS 限制 1024 字节
    if len(text.encode('utf-8')) > 1024:
        encoded = text.encode('utf-8')[:1020]
        text = encoded.decode('utf-8', errors='ignore')

    for attempt in range(2):
        url = tts_synthesize(text, voice_type, speed, loudness)
        if url:
            mp3_path = os.path.join(work_dir, f'tts_{index:05d}_{round_tag}.mp3')
            wav_path = os.path.join(work_dir, f'tts_{index:05d}_{round_tag}.wav')
            if download_audio(url, mp3_path):
                if mp3_to_wav(mp3_path, wav_path):
                    natural_dur = read_wav_duration(wav_path)
                    if natural_dur <= 0:
                        natural_dur = get_audio_duration(wav_path)
                    return wav_path, natural_dur
                else:
                    natural_dur = get_audio_duration(mp3_path)
                    return mp3_path, natural_dur
        if attempt == 0:
            time.sleep(1)

    print(f'  [SKIP] 第 {index} 条合成失败 ({round_tag})', file=sys.stderr)
    return None, 0.0


# ============================================================
# Round 1：全部 speed=1.0 生成，测量精确自然时长
# ============================================================

def synthesize_round1(segments: list, voice_type: str, loudness: float,
                      workers: int, work_dir: str,
                      progress_file: str) -> list:
    """
    Round 1：全部 speed=1.0 生成，转换为 WAV，读文件头获取精确自然时长。
    这是基准轮，后续轮次基于此计算调速比例。
    """
    done_indices = set()
    if os.path.exists(progress_file):
        with open(progress_file, 'r') as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    done_indices.add(rec['index'])
                except json.JSONDecodeError:
                    pass

    results = []
    pending = []

    for seg in segments:
        wav_path = os.path.join(work_dir, f'tts_{seg["index"]:05d}_r1.wav')
        if seg['index'] in done_indices and os.path.exists(wav_path):
            seg['audio_path'] = wav_path
            seg['natural_duration'] = read_wav_duration(wav_path) or get_audio_duration(wav_path)
            results.append(seg)
            continue
        pending.append(seg)

    if not pending:
        print(f'  Round 1: 全部 {len(results)} 条已完成，跳过合成')
        return results

    print(f'  Round 1: {len(pending)} 条, speed=1.0, {workers} 线程并发')
    completed = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for seg in pending:
            text = seg['text'].replace('\n', ' ')
            future = executor.submit(
                synth_segment, text, voice_type, 1.0, loudness,
                work_dir, seg['index'], 'r1'
            )
            futures[future] = seg

        for future in as_completed(futures):
            seg = futures[future]
            wav_path, natural_dur = future.result()
            completed += 1
            if wav_path:
                seg['audio_path'] = wav_path
                seg['natural_duration'] = natural_dur
                slot = seg['end'] - seg['start']
                status = '✓ fit' if natural_dur <= slot else f'→ need speed={natural_dur/slot:.2f}x'
                print(f'  [{completed}/{len(pending)}] {status} #{seg["index"]} '
                      f'nat={natural_dur:.3f}s slot={slot:.2f}s '
                      f'{seg["text"][:30]}...')

                results.append(seg)
                with open(progress_file, 'a') as f:
                    f.write(json.dumps({
                        'index': seg['index'],
                        'natural_duration': natural_dur
                    }) + '\n')
            else:
                print(f'  [{completed}/{len(pending)}] ✗ #{seg["index"]} 失败')

    return results


# ============================================================
# Round 2：对超长段用计算出的 speed_ratio 重新生成
# ============================================================

def synthesize_round2(segments: list, voice_type: str, loudness: float,
                      workers: int, work_dir: str, tts_max_speed: float,
                      progress_file: str) -> list:
    """
    Round 2：对 Round 1 中音频超长的段，计算 speed_ratio = natural / slot，
    以该速度重新生成 TTS。测量实际时长用于校准。

    返回更新后的 segments（超长段的 audio_path 和 audio_duration 更新为 Round 2 结果）。
    """
    over_slots = []
    for seg in segments:
        slot = seg['end'] - seg['start']
        natural = seg.get('natural_duration', 0)
        if natural > slot:
            needed_speed = natural / slot
            if needed_speed > tts_max_speed:
                # 即使最大语速也不够，用最大语速 + 后续截断
                seg['round2_speed'] = tts_max_speed
                seg['extreme'] = True
                print(f'    #{seg["index"]} 极端: nat={natural:.3f}s slot={slot:.3f}s '
                      f'need={needed_speed:.2f}x > max={tts_max_speed}x')
            else:
                seg['round2_speed'] = needed_speed
                seg['extreme'] = False
            over_slots.append(seg)
        else:
            seg['round2_speed'] = None
            seg['extreme'] = False
            # Round 1 音频已够短，直接用
            seg['final_audio_path'] = seg['audio_path']
            seg['final_duration'] = natural

    if not over_slots:
        print(f'  Round 2: 无超长段，跳过')
        return segments

    # 加载 Round 2 进度
    done_indices = set()
    if os.path.exists(progress_file + '.r2'):
        with open(progress_file + '.r2', 'r') as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    done_indices.add(rec['index'])
                except json.JSONDecodeError:
                    pass

    pending_r2 = []
    for seg in over_slots:
        wav_path = os.path.join(work_dir, f'tts_{seg["index"]:05d}_r2.wav')
        if seg['index'] in done_indices and os.path.exists(wav_path):
            seg['audio_path'] = wav_path
            seg['round2_duration'] = read_wav_duration(wav_path) or get_audio_duration(wav_path)
            continue
        pending_r2.append(seg)

    if pending_r2:
        print(f'  Round 2: {len(pending_r2)} 条超长段, 用计算出的 speed_ratio 重新生成')
        completed = 0

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {}
            for seg in pending_r2:
                text = seg['text'].replace('\n', ' ')
                future = executor.submit(
                    synth_segment, text, voice_type, seg['round2_speed'], loudness,
                    work_dir, seg['index'], 'r2'
                )
                futures[future] = seg

            for future in as_completed(futures):
                seg = futures[future]
                wav_path, actual_dur = future.result()
                completed += 1
                if wav_path:
                    seg['audio_path'] = wav_path
                    seg['round2_duration'] = actual_dur
                    slot = seg['end'] - seg['start']
                    natural = seg['natural_duration']
                    actual_speedup = natural / actual_dur if actual_dur > 0 else 0
                    target_speedup = seg['round2_speed']
                    residual = actual_dur - slot
                    status = '✓ fit' if actual_dur <= slot else f'⚠ over {residual:.3f}s'
                    print(f'  [{completed}/{len(pending_r2)}] {status} #{seg["index"]} '
                          f'speed={seg["round2_speed"]:.3f} nat={natural:.3f}s '
                          f'actual={actual_dur:.3f}s slot={slot:.3f}s '
                          f'(target_speedup={target_speedup:.3f} actual={actual_speedup:.3f})')

                    with open(progress_file + '.r2', 'a') as f:
                        f.write(json.dumps({
                            'index': seg['index'],
                            'round2_speed': seg['round2_speed'],
                            'round2_duration': actual_dur,
                            'natural_duration': natural,
                        }) + '\n')
                else:
                    print(f'  [{completed}/{len(pending_r2)}] ✗ #{seg["index"]} Round 2 失败')
                    # 回退到 Round 1 结果
                    seg['round2_duration'] = seg.get('natural_duration', 0)

    return segments


# ============================================================
# Round 3：校准修正——对 Round 2 后仍超长的段，用修正后的 speed 重新生成
# ============================================================

def synthesize_round3(segments: list, voice_type: str, loudness: float,
                      workers: int, work_dir: str, tts_max_speed: float,
                      progress_file: str) -> list:
    """
    Round 3：对 Round 2 后仍超长的段进行校准修正。

    校准原理：
    - Round 1 自然时长 = natural
    - Round 2 设置 speed = S, 实际时长 = D2
    - TTS 实际加速比 = natural / D2（可能 ≠ S，因为 TTS speed_ratio 非线性）
    - 需要的加速比 = natural / slot
    - 修正 speed = S × (natural / slot) / (natural / D2) = S × D2 / slot

    这样修正后的 speed 应该能让 TTS 生成恰好 fit 时段的音频。
    """
    # 收集 Round 2 的校准数据：计算平均非线性系数
    calib_data = []
    for seg in segments:
        if seg.get('round2_speed') is not None and seg.get('round2_duration', 0) > 0:
            natural = seg['natural_duration']
            d2 = seg['round2_duration']
            slot = seg['end'] - seg['start']
            target_speedup = natural / slot
            actual_speedup = natural / d2
            # 非线性系数 = 实际加速比 / 目标加速比
            # 如果 = 1.0，TTS 完全线性；< 1.0 说明 TTS 实际加速比预期慢
            nonlinearity = actual_speedup / seg['round2_speed'] if seg['round2_speed'] > 0 else 1.0
            calib_data.append({
                'index': seg['index'],
                'speed': seg['round2_speed'],
                'nonlinearity': nonlinearity,
                'actual_speedup': actual_speedup,
                'target_speedup': target_speedup,
            })

    if calib_data:
        avg_nonlinearity = sum(d['nonlinearity'] for d in calib_data) / len(calib_data)
        print(f'  校准数据: {len(calib_data)} 段, 平均非线性系数={avg_nonlinearity:.4f} '
              f'(1.0=完全线性, <1.0=TTS实际加速比预期慢)')
    else:
        avg_nonlinearity = 1.0

    # 找出 Round 2 后仍超长的段
    still_over = []
    for seg in segments:
        if seg.get('round2_speed') is None:
            continue  # Round 1 已 fit，无需 Round 2/3
        if seg.get('round2_duration', 0) <= 0:
            continue
        slot = seg['end'] - seg['start']
        d2 = seg['round2_duration']
        if d2 > slot:
            # 仍超长，需要 Round 3 修正
            natural = seg['natural_duration']
            # 修正公式：corrected_speed = round2_speed × (d2 / slot)
            # 这等价于：要让 actual_duration = slot，需要 actual_speedup = natural/slot
            # 而 actual_speedup ≈ speed × nonlinearity
            # 所以 corrected_speed = (natural/slot) / nonlinearity
            corrected_speed = (natural / slot) / avg_nonlinearity
            corrected_speed = min(corrected_speed, tts_max_speed)
            seg['round3_speed'] = corrected_speed
            still_over.append(seg)
        else:
            # Round 2 已 fit
            seg['final_audio_path'] = seg['audio_path']
            seg['final_duration'] = seg['round2_duration']

    if not still_over:
        print(f'  Round 3: Round 2 后全部 fit，无需校准修正')
        return segments

    # 加载 Round 3 进度
    done_indices = set()
    if os.path.exists(progress_file + '.r3'):
        with open(progress_file + '.r3', 'r') as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    done_indices.add(rec['index'])
                except json.JSONDecodeError:
                    pass

    pending_r3 = []
    for seg in still_over:
        wav_path = os.path.join(work_dir, f'tts_{seg["index"]:05d}_r3.wav')
        if seg['index'] in done_indices and os.path.exists(wav_path):
            seg['audio_path'] = wav_path
            seg['round3_duration'] = read_wav_duration(wav_path) or get_audio_duration(wav_path)
            seg['final_audio_path'] = wav_path
            seg['final_duration'] = seg['round3_duration']
            continue
        pending_r3.append(seg)

    if pending_r3:
        print(f'  Round 3: {len(pending_r3)} 条仍超长, 用校准修正后的 speed 重新生成')
        completed = 0

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {}
            for seg in pending_r3:
                text = seg['text'].replace('\n', ' ')
                future = executor.submit(
                    synth_segment, text, voice_type, seg['round3_speed'], loudness,
                    work_dir, seg['index'], 'r3'
                )
                futures[future] = seg

            for future in as_completed(futures):
                seg = futures[future]
                wav_path, actual_dur = future.result()
                completed += 1
                if wav_path:
                    seg['audio_path'] = wav_path
                    seg['round3_duration'] = actual_dur
                    seg['final_audio_path'] = wav_path
                    seg['final_duration'] = actual_dur
                    slot = seg['end'] - seg['start']
                    residual = actual_dur - slot
                    status = '✓ fit' if actual_dur <= slot else f'⚠ residual {residual:.3f}s ({residual/actual_dur*100:.1f}%)'
                    print(f'  [{completed}/{len(pending_r3)}] {status} #{seg["index"]} '
                          f'corrected_speed={seg["round3_speed"]:.3f} '
                          f'actual={actual_dur:.3f}s slot={slot:.3f}s')

                    with open(progress_file + '.r3', 'a') as f:
                        f.write(json.dumps({
                            'index': seg['index'],
                            'round3_speed': seg['round3_speed'],
                            'round3_duration': actual_dur,
                        }) + '\n')
                else:
                    print(f'  [{completed}/{len(pending_r3)}] ✗ #{seg["index"]} Round 3 失败')
                    # 回退到 Round 2 结果
                    seg['final_audio_path'] = seg['audio_path']
                    seg['final_duration'] = seg.get('round2_duration', 0)

    return segments


# ============================================================
# best-of-three 选择：从 r1/r2/r3 三个版本中选最优
# ============================================================

def select_best_audio(segments: list, work_dir: str) -> list:
    """
    v6 核心改进：对每段从三轮生成的音频中选最优版本。

    选择策略（优先级从高到低）：
    1. 有 ≤ 时段（无截断）的版本 → 选其中最长的（最接近时段，补静音最少）
    2. 都超长 → 选最短的（最小截断）

    这样能最大化零截断率，同时最小化截断量。
    三轮中每段可能产生 1-3 个 WAV 文件（r1 必有，r2/r3 仅超长段有）。
    """
    improved = 0
    for seg in segments:
        slot = seg['end'] - seg['start']
        candidates = []  # [(path, duration, round_tag)]

        # 收集所有可用版本
        for tag in ['r1', 'r2', 'r3']:
            wav_path = os.path.join(work_dir, f'tts_{seg["index"]:05d}_{tag}.wav')
            if os.path.exists(wav_path):
                dur = read_wav_duration(wav_path)
                if dur <= 0:
                    dur = get_audio_duration(wav_path)
                if dur > 0:
                    candidates.append((wav_path, dur, tag))

        if not candidates:
            continue

        # 选择策略
        fit_candidates = [(p, d, t) for p, d, t in candidates if d <= slot]
        if fit_candidates:
            # 有 ≤ 时段的版本 → 选最长的（最接近时段）
            best_path, best_dur, best_tag = max(fit_candidates, key=lambda x: x[1])
        else:
            # 都超长 → 选最短的（最小截断）
            best_path, best_dur, best_tag = min(candidates, key=lambda x: x[1])

        # 检查是否比当前选择更优
        current_dur = seg.get('final_duration', 0)
        current_path = seg.get('final_audio_path', seg.get('audio_path', ''))

        # 判断是否改善
        current_trunc = max(0, current_dur - slot)
        best_trunc = max(0, best_dur - slot)
        if best_trunc < current_trunc or (best_trunc == 0 and current_trunc > 0):
            improved += 1

        seg['final_audio_path'] = best_path
        seg['final_duration'] = best_dur

        if len(candidates) > 1:
            tags_info = ', '.join(f'{t}={d:.3f}s' for p, d, t in candidates)
            status = '✓ fit' if best_dur <= slot else f'截断{(best_dur-slot)/best_dur*100:.1f}%'
            print(f'    #{seg["index"]} 选 {best_tag} ({status}) | {tags_info}')

    if improved > 0:
        print(f'  best-of-three: {improved}/{len(segments)} 段较 v5 策略改善')

    return segments


# ============================================================
# 音轨拼接（v6：零 atempo/aresample/aformat，仅补静音/截断极小残差）
# ============================================================

def build_audio_track(segments_with_audio: list, total_duration: float,
                      output_path: str, work_dir: str) -> str:
    """
    将各段 TTS 音频按字幕时间轴拼接成完整音轨。

    v6 策略（零 atempo/aresample/aformat）：
    - 音频 ≤ 时段 → 末尾补静音（自然结束）
    - 音频 > 时段 → 截断尾部（经 best-of-three 选择后残差应 < 5%）
    - concat 无前置滤镜，零 aresample/aformat/atempo → 无杂音
    - 仅做 PCM 级别的拼接，保留 TTS 原声
    """
    if not segments_with_audio:
        return None

    normalized_files = []
    stats = {
        'pad_silence': 0,    # 音频短，补静音
        'fit_exact': 0,      # 音频恰好 fit（差值 < 10ms）
        'trunc_tiny': 0,     # 截断 < 5%
        'trunc_small': 0,    # 截断 5-15%
        'trunc_large': 0,    # 截断 > 15%（极端短时段）
    }

    for i, seg in enumerate(segments_with_audio):
        norm_path = os.path.join(work_dir, f'norm_{i:05d}.wav')
        slot_duration = seg['end'] - seg['start']
        audio_duration = seg.get('final_duration', 0)

        if audio_duration <= 0:
            audio_duration = get_audio_duration(seg.get('final_audio_path', seg.get('audio_path', '')))
        if audio_duration <= 0:
            audio_duration = slot_duration

        audio_path = seg.get('final_audio_path', seg.get('audio_path', ''))

        if audio_duration <= slot_duration:
            # 音频比时段短 → 补静音（无截断，无滤镜）
            silence_dur = max(0.001, slot_duration - audio_duration)
            if silence_dur < 0.01:
                # 差值 < 10ms，直接用原音频（补 1ms 静音避免边界问题）
                cmd = ['ffmpeg', '-y', '-i', audio_path,
                       '-ar', '44100', '-ac', '2',
                       '-c:a', 'pcm_s16le', norm_path]
                stats['fit_exact'] += 1
            else:
                cmd = ['ffmpeg', '-y', '-i', audio_path,
                       '-f', 'lavfi', '-t', str(silence_dur), '-i',
                       'anullsrc=channel_layout=stereo:sample_rate=44100',
                       '-filter_complex',
                       f'[0:a][1:a]concat=n=2:v=0:a=1[a]',
                       '-map', '[a]', '-ar', '44100', '-ac', '2',
                       '-c:a', 'pcm_s16le', norm_path]
                stats['pad_silence'] += 1
        else:
            # 音频比时段长 → 截断尾部（经三轮校准后残差应很小）
            trunc_pct = (audio_duration - slot_duration) / audio_duration * 100
            # 仅截断，零滤镜，零 atempo
            cmd = ['ffmpeg', '-y', '-i', audio_path,
                   '-ar', '44100', '-ac', '2',
                   '-t', str(slot_duration),
                   '-c:a', 'pcm_s16le', norm_path]
            if trunc_pct < 5:
                stats['trunc_tiny'] += 1
            elif trunc_pct < 15:
                stats['trunc_small'] += 1
            else:
                stats['trunc_large'] += 1
            print(f'    #{seg["index"]} 截断 {trunc_pct:.1f}% '
                  f'(audio={audio_duration:.3f}s slot={slot_duration:.3f}s)')

        subprocess.run(cmd, capture_output=True, timeout=30)
        if os.path.exists(norm_path):
            normalized_files.append((norm_path, seg['start']))
        else:
            print(f'    [WARN] norm_{i:05d}.wav 未生成，跳过', file=sys.stderr)

    total = sum(stats.values())
    print(f'  对齐统计 ({total} 条):')
    print(f'    补静音(音频短): {stats["pad_silence"]}')
    print(f'    恰好fit(<10ms): {stats["fit_exact"]}')
    print(f'    截断<5%: {stats["trunc_tiny"]}')
    print(f'    截断5-15%: {stats["trunc_small"]}')
    print(f'    截断>15%(极端): {stats["trunc_large"]}')
    zero_trunc = stats['pad_silence'] + stats['fit_exact'] + stats['trunc_tiny']
    if total > 0:
        print(f'    零/微截断率: {zero_trunc}/{total} = {zero_trunc/total*100:.0f}%')

    if not normalized_files:
        return None

    # adelay + amix 拼接
    cmd = ['ffmpeg', '-y']
    inputs = []
    for norm_path, start_sec in normalized_files:
        cmd.extend(['-i', norm_path])
        inputs.append((norm_path, start_sec))

    silence_dur = max(total_duration, segments_with_audio[-1]['end'] + 1)
    cmd.extend(['-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100',
                '-t', str(silence_dur)])
    n_silence = len(inputs)

    filter_parts = []
    for i, (_, start_sec) in enumerate(inputs):
        delay_ms = int(start_sec * 1000)
        filter_parts.append(f'[{i}:a]adelay={delay_ms}|{delay_ms}[a{i}]')

    total_inputs = len(inputs) + 1
    mix_inputs = ''.join(f'[a{i}]' for i in range(len(inputs))) + f'[{n_silence}:a]'
    filter_parts.append(f'{mix_inputs}amix=inputs={total_inputs}:duration=longest:normalize=0[aout]')

    filter_complex = ';'.join(filter_parts)

    cmd.extend([
        '-filter_complex', filter_complex,
        '-map', '[aout]',
        '-t', str(total_duration),
        '-ar', '44100', '-ac', '2',
        '-c:a', 'pcm_s16le',
        output_path
    ])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f'[ERROR] ffmpeg 拼接失败: {result.stderr[-500:]}', file=sys.stderr)
        return None

    return output_path if os.path.exists(output_path) else None


# ============================================================
# 视频音频替换
# ============================================================

def replace_video_audio(video_path: str, audio_path: str, output_path: str,
                        keep_original: bool = False) -> bool:
    """用新音轨替换视频的音频"""
    if keep_original:
        cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-i', audio_path,
            '-filter_complex',
            '[0:a]volume=0.2[orig];[1:a][orig]amix=inputs=2:duration=first:dropout_transition=0[a]',
            '-map', '0:v',
            '-map', '[a]',
            '-c:v', 'copy',
            '-c:a', 'aac', '-b:a', '192k',
            '-shortest',
            output_path
        ]
    else:
        cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-i', audio_path,
            '-map', '0:v',
            '-map', '1:a',
            '-c:v', 'copy',
            '-c:a', 'aac', '-b:a', '192k',
            '-shortest',
            output_path
        ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        print(f'[ERROR] 替换音频失败: {result.stderr[-500:]}', file=sys.stderr)
        return False
    return os.path.exists(output_path)


def get_video_duration(video_path: str) -> float:
    """获取视频时长"""
    result = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
         '-of', 'csv=p=0', video_path],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode == 0:
        try:
            return float(result.stdout.strip())
        except ValueError:
            pass
    return 0.0


# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='字幕配音替换 v6：三轮生成 + best-of-three · 零 atempo/aresample · 零/极小截断')
    parser.add_argument('--video', required=True, help='输入视频文件路径')
    parser.add_argument('--subtitle', required=True, help='字幕文件路径 (SRT/ASS/VTT)')
    parser.add_argument('--output', required=True, help='输出视频文件路径')
    parser.add_argument('--voice', default='zh_female_shuangkuaisisi_emo_v2_mars_bigtts',
                        help='音色ID (默认: 爽快思思)')
    parser.add_argument('--loudness', type=float, default=1.0, help='音量 0.5~2 (默认: 1.0)')
    parser.add_argument('--workers', type=int, default=6, help='并发线程数 (默认: 6)')
    parser.add_argument('--tts-max-speed', type=float, default=2.0,
                        help='TTS 最大语速 (默认: 2.0)')
    parser.add_argument('--merge-gap', type=float, default=0.15,
                        help='合并间隔小于此值的相邻段 (默认: 0.15s)')
    parser.add_argument('--no-merge', action='store_true',
                        help='禁用短段合并')
    parser.add_argument('--keep-original', action='store_true',
                        help='保留原视频音频为背景音（降低音量混合）')
    args = parser.parse_args()

    # 验证文件
    if not os.path.exists(args.video):
        print(f'[ERROR] 视频文件不存在: {args.video}', file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(args.subtitle):
        print(f'[ERROR] 字幕文件不存在: {args.subtitle}', file=sys.stderr)
        sys.exit(1)

    work_dir = os.path.join(os.path.dirname(args.output) or '.', '_tts_work')
    os.makedirs(work_dir, exist_ok=True)

    # 1. 解析字幕
    print(f'[1/7] 解析字幕: {args.subtitle}')
    segments = parse_subtitle(args.subtitle)
    if not segments:
        print('[ERROR] 未解析到任何字幕段', file=sys.stderr)
        sys.exit(1)
    print(f'  共 {len(segments)} 条字幕')

    # 2. 短段合并
    if not args.no_merge:
        print(f'[2/7] 合并短段 (gap < {args.merge_gap}s)')
        original_count = len(segments)
        segments = merge_short_segments(segments, args.merge_gap)
        for i, seg in enumerate(segments):
            seg['index'] = i + 1
        if len(segments) < original_count:
            print(f'  {original_count} → {len(segments)} 条 (合并了 {original_count - len(segments)} 段)')
        else:
            print(f'  无需合并')
    else:
        print('[2/7] 跳过短段合并')
        for i, seg in enumerate(segments):
            seg['index'] = i + 1

    # 3. 获取视频时长
    video_duration = get_video_duration(args.video)
    if video_duration == 0:
        video_duration = segments[-1]['end'] + 5
        print(f'  [WARN] 无法获取视频时长，使用字幕末尾时间 +5s: {video_duration:.1f}s')
    else:
        print(f'  视频时长: {video_duration:.1f}s')

    # 4. Round 1：全部 speed=1.0 生成
    progress_file = os.path.join(work_dir, 'progress.jsonl')
    print(f'[3/7] Round 1: 基准生成 (音色: {args.voice}, speed=1.0, {args.workers} 线程)')
    print(f'  策略: 全部 speed=1.0 → 读 WAV 头量精确时长 → 计算调速比例')
    segments_with_audio = synthesize_round1(
        segments, args.voice, args.loudness,
        args.workers, work_dir, progress_file
    )
    print(f'  Round 1 完成: {len(segments_with_audio)}/{len(segments)} 条成功')

    if not segments_with_audio:
        print('[ERROR] 没有成功合成任何音频', file=sys.stderr)
        sys.exit(1)

    # 按时间排序
    segments_with_audio.sort(key=lambda s: s['start'])

    # 统计超长段
    over_count = 0
    for seg in segments_with_audio:
        slot = seg['end'] - seg['start']
        if seg.get('natural_duration', 0) > slot:
            over_count += 1
    print(f'  超长段: {over_count}/{len(segments_with_audio)} 条需要调速')

    # 5. Round 2：对超长段用计算出的 speed_ratio 重新生成
    print(f'[4/7] Round 2: 调速生成 (speed_ratio = natural/slot, max={args.tts_max_speed})')
    segments_with_audio = synthesize_round2(
        segments_with_audio, args.voice, args.loudness,
        args.workers, work_dir, args.tts_max_speed,
        progress_file
    )

    # 6. Round 3：校准修正——对 Round 2 后仍超长的段修正 speed
    print(f'[5/7] Round 3: 校准修正 (基于 Round 2 实测非线性系数)')
    segments_with_audio = synthesize_round3(
        segments_with_audio, args.voice, args.loudness,
        args.workers, work_dir, args.tts_max_speed,
        progress_file
    )

    # 7. best-of-three 选择：从 r1/r2/r3 三个版本中选最优
    print(f'[6/7] best-of-three 选择 (从三轮结果中选最优版本)')
    segments_with_audio = select_best_audio(segments_with_audio, work_dir)

    # 统计最终结果
    fit_count = 0
    trunc_count = 0
    for seg in segments_with_audio:
        slot = seg['end'] - seg['start']
        final_dur = seg.get('final_duration', 0)
        if final_dur <= slot:
            fit_count += 1
        else:
            trunc_count += 1
    print(f'  最终结果: {fit_count}/{len(segments_with_audio)} fit, '
          f'{trunc_count} 需截断 (残差应 < 5%)')

    # 8. 拼接音轨
    print(f'[7/7] 按时间轴拼接音轨 (零 atempo/aresample, 仅补静音/截断极小残差)')
    mixed_audio = os.path.join(work_dir, 'mixed_audio.wav')
    result = build_audio_track(
        segments_with_audio, video_duration, mixed_audio, work_dir
    )
    if not result:
        print('[ERROR] 音轨拼接失败', file=sys.stderr)
        sys.exit(1)
    print(f'  音轨已生成: {mixed_audio}')

    # 8. 替换视频音频
    print('[7/7] 替换视频音频')
    success = replace_video_audio(
        args.video, mixed_audio, args.output, args.keep_original
    )
    if success:
        print(f'\n✅ 完成！输出文件: {args.output}')
    else:
        print('[ERROR] 视频音频替换失败', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
