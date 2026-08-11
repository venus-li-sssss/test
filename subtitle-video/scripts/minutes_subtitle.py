#!/usr/bin/env python3
"""
飞书妙记字幕生成 —— 全自动流程：
1. 上传视频到飞书云盘 → 获取 file_token
2. 用 file_token 生成妙记 → 获取 minute_token
3. 等待妙记处理完成 → 获取逐字稿（段落级时间戳）
4. 按标点拆分子句 + 比例估算时间戳 → 生成 ASS/SRT
5. 烧录字幕到视频（可选）

用法：
  python3 minutes_subtitle.py <video_file> [--burn] [--karaoke] [--output-dir DIR]
  python3 minutes_subtitle.py --minute-token <token> [--burn] [--karaoke] [--output-dir DIR]
  python3 minutes_subtitle.py --file-token <token> [--burn] [--karaoke] [--output-dir DIR]

如果已有 minute_token（妙记已存在），可跳过上传步骤直接获取字幕。
如果已有 file_token（视频已在云盘），可跳过 drive 上传步骤。
"""
import json
import subprocess
import os
import re
import sys
import argparse
import time

# 标点拆分：中英文逗号/句号/问号/感叹号/分号/省略号
SPLIT_PUNCT = re.compile(r'[，。！？；,;!?.…]')
# 超长无标点子句的安全阈值
SAFETY_MAX_CHARS = 50


def run_lark_cli(args, timeout=120):
    """执行 lark-cli 命令，返回 (success, stdout, stderr)"""
    cmd = ['lark-cli'] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, '', 'Timeout'
    except Exception as e:
        return False, '', str(e)


def upload_to_drive(video_path):
    """上传视频到飞书云盘，返回 file_token"""
    print(f"上传视频到飞书云盘: {video_path}")
    filename = os.path.basename(video_path)
    ok, stdout, stderr = run_lark_cli([
        'drive', '+upload',
        '--file', video_path,
        '--name', filename,
        '--as', 'user'
    ], timeout=600)
    
    if not ok:
        print(f"上传失败: {stderr}")
        return None
    
    # 解析返回的 file_token
    try:
        data = json.loads(stdout)
        file_token = data.get('data', {}).get('file_token', '')
        if not file_token:
            # 尝试其他字段
            file_token = data.get('file_token', '')
        if file_token:
            print(f"上传成功，file_token: {file_token}")
            return file_token
        else:
            print(f"上传返回但未找到 file_token: {stdout[:200]}")
            return None
    except json.JSONDecodeError:
        # 尝试从文本中提取
        m = re.search(r'file_token["\s:]+([a-zA-Z0-9_-]+)', stdout)
        if m:
            print(f"上传成功，file_token: {m.group(1)}")
            return m.group(1)
        print(f"无法解析上传结果: {stdout[:200]}")
        return None


def create_minutes(file_token):
    """用 file_token 生成妙记，返回 minute_token"""
    print(f"生成妙记: file_token={file_token}")
    ok, stdout, stderr = run_lark_cli([
        'minutes', '+upload',
        '--file-token', file_token,
        '--as', 'user'
    ], timeout=60)
    
    if not ok:
        print(f"生成妙记失败: {stderr}")
        return None
    
    try:
        data = json.loads(stdout)
        minute_url = data.get('data', {}).get('minute_url', '')
        minute_token = data.get('data', {}).get('minute_token', '')
        if not minute_token and minute_url:
            # 从 URL 提取 token
            minute_token = minute_url.rstrip('/').split('/')[-1]
        if minute_token:
            print(f"妙记生成成功，minute_token: {minute_token}")
            print(f"妙记链接: {minute_url}")
            return minute_token
        else:
            print(f"无法解析妙记生成结果: {stdout[:200]}")
            return None
    except json.JSONDecodeError:
        m = re.search(r'minute_token["\s:]+([a-zA-Z0-9_-]+)', stdout)
        if m:
            return m.group(1)
        print(f"无法解析妙记生成结果: {stdout[:200]}")
        return None


def get_transcript(minute_token, output_dir='.'):
    """获取妙记逐字稿，返回 transcript 文件路径"""
    print(f"获取逐字稿: minute_token={minute_token}")
    
    # 使用 --wait-ready 等待妙记处理完成
    ok, stdout, stderr = run_lark_cli([
        'minutes', '+detail',
        '--minute-tokens', minute_token,
        '--transcript',
        '--wait-ready',
        '--as', 'user'
    ], timeout=600)
    
    if not ok:
        print(f"获取逐字稿失败: {stderr}")
        return None
    
    try:
        data = json.loads(stdout)
        minutes = data.get('data', {}).get('minutes', [])
        if minutes:
            transcript_file = minutes[0].get('artifacts', {}).get('transcript_file', '')
            if transcript_file:
                print(f"逐字稿文件: {transcript_file}")
                return transcript_file
        print(f"未找到逐字稿文件路径: {stdout[:200]}")
        return None
    except json.JSONDecodeError:
        print(f"无法解析逐字稿结果: {stdout[:200]}")
        return None


def time_to_ms(t):
    """将 HH:MM:SS.mmm 转为毫秒"""
    h, m, s = t.split(':')
    return int(float(h) * 3600000 + float(m) * 60000 + float(s) * 1000)


def ms_to_ass_time(ms):
    """将毫秒转为 ASS 时间格式 H:MM:SS.cc"""
    hours = ms // 3600000
    minutes = (ms % 3600000) // 60000
    seconds = (ms % 60000) // 1000
    centiseconds = (ms % 1000) // 10
    return f'{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}'


def ms_to_srt_time(ms):
    """将毫秒转为 SRT 时间格式 HH:MM:SS,mmm"""
    hours = ms // 3600000
    minutes = (ms % 3600000) // 60000
    seconds = (ms % 60000) // 1000
    millis = ms % 1000
    return f'{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}'


def parse_transcript(transcript_file):
    """解析逐字稿文件，返回 [(speaker, start_ms, text), ...]"""
    with open(transcript_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    entries = []
    current_speaker = None
    current_time = None
    current_text = []
    
    for line in lines:
        m = re.match(r'^(?:Speaker|说话人)\s+(\d+)\s+(\d{2}:\d{2}:\d{2}\.\d{3})\s*$', line.strip())
        if m:
            if current_speaker is not None:
                entries.append({
                    'speaker': int(current_speaker),
                    'start_ms': time_to_ms(current_time),
                    'text': '\n'.join(current_text).strip()
                })
            current_speaker = m.group(1)
            current_time = m.group(2)
            current_text = []
        elif current_speaker is not None:
            if line.strip() == '' and current_text:
                entries.append({
                    'speaker': int(current_speaker),
                    'start_ms': time_to_ms(current_time),
                    'text': '\n'.join(current_text).strip()
                })
                current_speaker = None
                current_time = None
                current_text = []
            else:
                current_text.append(line)
    
    if current_speaker is not None:
        entries.append({
            'speaker': int(current_speaker),
            'start_ms': time_to_ms(current_time),
            'text': '\n'.join(current_text).strip()
        })
    
    return entries


def split_and_estimate_timestamps(entries):
    """按标点拆分子句，用比例估算时间戳。
    返回 [(start_ms, stop_ms, text, speaker), ...]
    """
    # 首先计算每个段落的结束时间（= 下一段落开始时间）
    for i, entry in enumerate(entries):
        if i + 1 < len(entries):
            entry['end_ms'] = entries[i + 1]['start_ms']
        else:
            # 最后一段，假设 30 秒
            entry['end_ms'] = entry['start_ms'] + 30000
    
    # 对每个段落按标点拆分，比例估算时间戳
    all_clauses = []
    for entry in entries:
        text = entry['text']
        start_ms = entry['start_ms']
        end_ms = entry['end_ms']
        duration_ms = end_ms - start_ms
        speaker = entry['speaker']
        
        if not text or duration_ms <= 0:
            continue
        
        # 按标点拆分
        clauses = []
        current = ''
        for char in text:
            current += char
            if SPLIT_PUNCT.search(char):
                clauses.append(current)
                current = ''
        if current:
            clauses.append(current)
        
        # 比例估算时间戳
        total_chars = len(text)
        chars_before = 0
        for clause in clauses:
            clause_text = SPLIT_PUNCT.sub('', clause).strip()
            if not clause_text:
                chars_before += len(clause)
                continue
            
            # 超长无标点子句安全检查
            if len(clause_text) > SAFETY_MAX_CHARS:
                # 尝试在空格处拆分
                parts = clause_text.split(' ')
                if len(parts) > 1:
                    mid = len(parts) // 2
                    part1 = ' '.join(parts[:mid])
                    part2 = ' '.join(parts[mid:])
                    for part in [part1, part2]:
                        if part.strip():
                            p_start = start_ms + int(chars_before / total_chars * duration_ms)
                            chars_before += len(part)
                            p_end = start_ms + int(chars_before / total_chars * duration_ms)
                            all_clauses.append((p_start, p_end, part.strip(), speaker))
                    continue
            
            clause_start = start_ms + int(chars_before / total_chars * duration_ms)
            chars_before += len(clause)
            clause_end = start_ms + int(chars_before / total_chars * duration_ms)
            all_clauses.append((clause_start, clause_end, clause_text, speaker))
    
    return all_clauses


def generate_ass(clauses, output_path, video_w=640, video_h=360, karaoke=False):
    """生成 ASS 字幕文件"""
    # 字体大小根据视频分辨率调整
    font_size = max(16, min(video_w, video_h) // 12)
    
    header = f"""[Script Info]
Title: Subtitles
ScriptType: v4.00+
PlayResX: {video_w}
PlayResY: {video_h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,{font_size},&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,20,20,{video_h // 12},1
Style: Karaoke,Microsoft YaHei,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,20,20,{video_h // 12},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(header)
        for start_ms, stop_ms, text, speaker in clauses:
            start = ms_to_ass_time(start_ms)
            end = ms_to_ass_time(stop_ms)
            style = 'Karaoke' if karaoke else 'Default'
            
            if karaoke:
                # 卡拉OK：将文本按字符拆分，均匀分配 \k 标签
                dur = max(1, (stop_ms - start_ms) // 10)
                char_count = len(text)
                if char_count > 0:
                    per_char = max(1, dur // char_count)
                    karaoke_text = ''.join(f'{{\\k{per_char}}}{c}' for c in text)
                else:
                    karaoke_text = text
                f.write(f'Dialogue: 0,{start},{end},{style},Speaker {speaker},0,0,0,,{karaoke_text}\n')
            else:
                f.write(f'Dialogue: 0,{start},{end},{style},Speaker {speaker},0,0,0,,{text}\n')
    
    print(f"ASS 已生成: {output_path} ({'卡拉OK' if karaoke else '普通'}模式, {len(clauses)} 条)")


def generate_srt(clauses, output_path):
    """生成 SRT 字幕文件"""
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        for i, (start_ms, stop_ms, text, speaker) in enumerate(clauses, 1):
            start = ms_to_srt_time(start_ms)
            end = ms_to_srt_time(stop_ms)
            f.write(f'{i}\n')
            f.write(f'{start} --> {end}\n')
            f.write(f'[Speaker {speaker}] {text}\n')
            f.write('\n')
    
    print(f"SRT 已生成: {output_path} ({len(clauses)} 条)")


def burn_subtitles(video_path, ass_path, output_path):
    """用 ffmpeg 烧录 ASS 字幕到视频"""
    cmd = [
        'ffmpeg', '-y',
        '-i', video_path,
        '-vf', f'ass={ass_path}',
        '-c:v', 'libx264',
        '-preset', 'ultrafast',
        '-crf', '23',
        '-c:a', 'copy',
        output_path
    ]
    print(f"烧录字幕: {video_path} → {output_path}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if result.returncode == 0:
        print(f"烧录完成: {output_path}")
        return True
    else:
        print(f"烧录失败: {result.stderr[-500:]}")
        return False


def main():
    parser = argparse.ArgumentParser(description='飞书妙记字幕生成（全自动流程）')
    parser.add_argument('video_file', nargs='?', help='本地视频文件路径')
    parser.add_argument('--minute-token', help='已有妙记 token（跳过上传）')
    parser.add_argument('--file-token', help='已有云盘 file_token（跳过 drive 上传）')
    parser.add_argument('--output-dir', default='.', help='输出目录')
    parser.add_argument('--karaoke', action='store_true', help='卡拉OK逐词高亮（拆分逻辑相同）')
    parser.add_argument('--burn', action='store_true', help='烧录字幕到视频')
    parser.add_argument('--video-width', type=int, default=640, help='视频宽度')
    parser.add_argument('--video-height', type=int, default=360, help='视频高度')
    args = parser.parse_args()
    
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Step 1: 获取 minute_token
    minute_token = args.minute_token
    
    if not minute_token:
        file_token = args.file_token
        
        if not file_token:
            if not args.video_file:
                print("错误：需要提供 video_file、--file-token 或 --minute-token")
                sys.exit(1)
            
            # 1a. 上传视频到云盘
            file_token = upload_to_drive(args.video_file)
            if not file_token:
                print("上传云盘失败，退出")
                sys.exit(1)
        
        # 1b. 生成妙记
        minute_token = create_minutes(file_token)
        if not minute_token:
            print("生成妙记失败，退出")
            sys.exit(1)
    
    # Step 2: 获取逐字稿
    transcript_file = get_transcript(minute_token, args.output_dir)
    if not transcript_file:
        print("获取逐字稿失败，退出")
        sys.exit(1)
    
    # Step 3: 解析逐字稿
    print(f"\n解析逐字稿: {transcript_file}")
    entries = parse_transcript(transcript_file)
    print(f"解析结果: {len(entries)} 个段落")
    
    # Step 4: 按标点拆分 + 估算时间戳
    clauses = split_and_estimate_timestamps(entries)
    print(f"标点拆分后: {len(clauses)} 条字幕")
    
    # Step 5: 生成字幕文件
    ass_name = 'subtitle_karaoke.ass' if args.karaoke else 'subtitle.ass'
    ass_path = os.path.join(args.output_dir, ass_name)
    generate_ass(clauses, ass_path, args.video_width, args.video_height, args.karaoke)
    
    srt_path = os.path.join(args.output_dir, 'subtitle.srt')
    generate_srt(clauses, srt_path)
    
    # Step 6: 烧录（可选）
    if args.burn and args.video_file:
        suffix = '_卡拉OK字幕版' if args.karaoke else '_字幕版'
        out_name = os.path.splitext(os.path.basename(args.video_file))[0] + suffix + '.mp4'
        out_path = os.path.join(args.output_dir, out_name)
        burn_subtitles(args.video_file, ass_path, out_path)
    
    print("\n完成！")
    if not args.burn:
        print(f"  字幕文件: {ass_path}")
        print(f"  字幕文件: {srt_path}")
        print("  （使用 --burn 可同时烧录到视频）")


if __name__ == '__main__':
    main()
