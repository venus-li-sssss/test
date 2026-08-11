#!/usr/bin/env python3
"""
从飞书妙记 HAR 文件提取词级时间戳，生成字幕文件并烧录到视频。
- 默认：普通字幕（按标点拆分，不按字数硬切；超长无标点子句在词间停顿处拆分）
- --karaoke：卡拉OK逐字高亮（不拆句，显示完整句子+逐词高亮，与妙记网页端一致）
- --burn：烧录到视频
"""
import json
import sys
import os
import re
import subprocess
import argparse

# 标点拆分集合：中英文逗号/句号/问号/感叹号/分号/省略号
SPLIT_PUNCT = re.compile(r'[，。！？；,;!?.…]')
# 超长无标点子句的安全阈值：超过此长度才尝试在词间停顿处拆分
SAFETY_MAX_CHARS = 50
# 词间停顿阈值（毫秒）：超过此间隔视为自然停顿，可作为拆分点
WORD_GAP_THRESHOLD = 300

def parse_har(har_path):
    """从 HAR 文件解析妙记字幕数据"""
    with open(har_path, 'r', encoding='utf-8') as f:
        har = json.load(f)
    entries = har.get('log', {}).get('entries', [])
    
    subtitles_data = None
    for entry in entries:
        url = entry.get('request', {}).get('url', '')
        if '/minutes/api/subtitles_v2' in url:
            text = entry.get('response', {}).get('content', {}).get('text', '')
            if text:
                data = json.loads(text)
                paragraphs = data.get('data', {}).get('paragraphs', [])
                if subtitles_data is None or len(paragraphs) > len(subtitles_data):
                    subtitles_data = paragraphs
    if not subtitles_data:
        raise ValueError("HAR 文件中未找到 subtitles_v2 数据")
    
    speaker_map = {}
    for entry in entries:
        url = entry.get('request', {}).get('url', '')
        if '/minutes/api/speakers' in url:
            text = entry.get('response', {}).get('content', {}).get('text', '')
            if text:
                data = json.loads(text)
                speaker_map = data.get('data', {}).get('paragraph_to_speaker', {})
                break
    return subtitles_data, speaker_map


def ms_to_ass_time(ms):
    ms = int(ms)
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    cs = (ms % 1000) // 10
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def ms_to_srt_time(ms):
    ms = int(ms)
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    ms_part = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms_part:03d}"


def split_sentence_by_punctuation(sentence):
    """按标点符号拆分句子为子句，与飞书妙记网页端字幕条逻辑一致。
    
    网页端字幕条每次显示一个标点子句（逗号/句号/问号等之间的文本），
    不是完整句子，也不是按字数硬切。本函数复现这一行为。
    
    对于极少数无标点的超长子句（>SAFETY_MAX_CHARS），尝试在词间自然停顿处
    （gap > WORD_GAP_THRESHOLD）拆分，避免破坏词义。
    
    返回 [(start_ms, stop_ms, text), ...]
    """
    contents = sentence.get('contents', [])
    sent_start = int(sentence['start_time'])
    sent_stop = int(sentence['stop_time'])
    
    if not contents:
        return [(sent_start, sent_stop, '')]
    
    # Phase 1: 按标点拆分（与网页端一致）
    segments = []
    current_words = []
    current_start = None
    
    for word in contents:
        w_text = word['content']
        w_start = int(word['start_time'])
        w_stop = int(word['stop_time'])
        
        if current_start is None:
            current_start = w_start
        current_words.append(word)
        
        if SPLIT_PUNCT.search(w_text):
            clause_text = ''.join(c['content'] for c in current_words)
            segments.append((current_start, w_stop, clause_text, current_words))
            current_words = []
            current_start = None
    
    # 处理剩余的词（末尾无标点的情况）
    if current_words:
        last_stop = int(current_words[-1]['stop_time'])
        clause_text = ''.join(c['content'] for c in current_words)
        segments.append((current_start or sent_start, last_stop, clause_text, current_words))
    
    # Phase 2: 对超长无标点子句在词间停顿处拆分（安全阀，不影响正常子句）
    final_segments = []
    for seg_start, seg_stop, seg_text, seg_words in segments:
        if len(seg_text) <= SAFETY_MAX_CHARS:
            # 正常长度，直接保留
            final_segments.append((seg_start, seg_stop, seg_text))
        else:
            # 超长子句（无标点），尝试在词间自然停顿处拆分
            split_at_gaps = _split_at_word_gaps(seg_words, seg_start)
            if len(split_at_gaps) > 1:
                final_segments.extend(split_at_gaps)
            else:
                # 没有合适的停顿点，保留原样（不破坏词义）
                final_segments.append((seg_start, seg_stop, seg_text))
    
    # Phase 3: 去除标点符号（标点仅用于拆分，不显示在字幕中）
    clean_segments = []
    for seg_start, seg_stop, seg_text in final_segments:
        clean_text = SPLIT_PUNCT.sub('', seg_text).strip()
        if clean_text:
            clean_segments.append((seg_start, seg_stop, clean_text))
    
    return clean_segments


def _split_at_word_gaps(words, fallback_start):
    """在词间自然停顿处（gap > WORD_GAP_THRESHOLD）拆分超长子句。
    返回 [(start_ms, stop_ms, text), ...]
    """
    if len(words) <= 1:
        text = ''.join(w['content'] for w in words)
        start = int(words[0]['start_time']) if words else fallback_start
        stop = int(words[-1]['stop_time']) if words else fallback_start
        return [(start, stop, text)]
    
    # 找到所有 gap > threshold 的位置
    gap_positions = []
    for i in range(1, len(words)):
        prev_stop = int(words[i-1]['stop_time'])
        curr_start = int(words[i]['start_time'])
        gap = curr_start - prev_stop
        if gap >= WORD_GAP_THRESHOLD:
            gap_positions.append(i)
    
    if not gap_positions:
        return [(fallback_start, int(words[-1]['stop_time']), 
                 ''.join(w['content'] for w in words))]
    
    # 选择最接近子句中间位置的 gap 作为拆分点
    mid = len(words) // 2
    best_gap = min(gap_positions, key=lambda g: abs(g - mid))
    
    # 在 best_gap 处拆分
    part1_words = words[:best_gap]
    part2_words = words[best_gap:]
    
    result = []
    for part in [part1_words, part2_words]:
        p_start = int(part[0]['start_time'])
        p_stop = int(part[-1]['stop_time'])
        p_text = ''.join(w['content'] for w in part)
        result.append((p_start, p_stop, p_text))
    
    return result


def generate_ass(paragraphs, speaker_map, output_path, video_w=640, video_h=360, karaoke=False):
    """生成 ASS 字幕文件"""
    font_size = max(16, int(video_h * 0.065))
    margin_v = int(video_h * 0.08)
    
    lines = []
    lines.append("[Script Info]")
    lines.append("Title: 飞书妙记字幕")
    lines.append("ScriptType: v4.00+")
    lines.append(f"PlayResX: {video_w}")
    lines.append(f"PlayResY: {video_h}")
    lines.append("WrapStyle: 2")
    lines.append("ScaledBorderAndShadow: yes")
    lines.append("")
    lines.append("[V4+ Styles]")
    lines.append("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding")
    
    if karaoke:
        # 卡拉OK模式：PrimaryColour=已高亮(白), SecondaryColour=未高亮(灰)
        lines.append(f"Style: Default,Microsoft YaHei,{font_size},&H00FFFFFF,&H00808080,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,2,10,10,{margin_v},1")
    else:
        # 普通模式：纯白字黑边
        lines.append(f"Style: Default,Microsoft YaHei,{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,2,10,10,{margin_v},1")
    
    lines.append(f"Style: Speaker,Microsoft YaHei,{max(12, font_size - 6)},&H0000FFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,1,0,2,10,10,{margin_v + font_size + 4},1")
    lines.append("")
    lines.append("[Events]")
    lines.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")
    
    for p in paragraphs:
        pid = p.get('pid', '')
        speaker_id = speaker_map.get(pid, '1')
        
        for sent in p.get('sentences', []):
            sent_start = int(sent['start_time'])
            sent_stop = int(sent['stop_time'])
            if sent_start >= sent_stop:
                continue
            
            # 拆分长句
            segments = split_sentence_by_punctuation(sent)
            
            for seg_start, seg_stop, seg_text in segments:
                if not seg_text.strip():
                    continue
                
                if karaoke:
                    # 卡拉OK：每个词一个 {\kN} 标签
                    # 用严格时间范围过滤属于当前子句的词（容差仅 50ms）
                    seg_words = [w for w in sent.get('contents', [])
                                 if int(w['start_time']) >= seg_start - 50 
                                 and int(w['stop_time']) <= seg_stop + 50]
                    if not seg_words:
                        # 回退到普通文本
                        lines.append(f"Dialogue: 0,{ms_to_ass_time(seg_start)},{ms_to_ass_time(seg_stop)},Default,,0,0,0,,{seg_text}")
                        continue
                    
                    karaoke_parts = []
                    for i, word in enumerate(seg_words):
                        w_start = int(word['start_time'])
                        w_stop = int(word['stop_time'])
                        w_text = SPLIT_PUNCT.sub('', word['content'])
                        if not w_text:
                            continue
                        if i == 0:
                            gap = w_start - seg_start
                            dur = (w_stop - w_start) + max(0, gap)
                        else:
                            dur = w_stop - w_start
                        k_val = max(1, dur // 10)
                        karaoke_parts.append((k_val, w_text))
                    
                    # 词间间隙加到前一个词
                    for i in range(1, len(seg_words)):
                        prev_stop = int(seg_words[i-1]['stop_time'])
                        curr_start = int(seg_words[i]['start_time'])
                        gap = curr_start - prev_stop
                        if gap > 0:
                            karaoke_parts[i-1] = (karaoke_parts[i-1][0] + gap // 10, karaoke_parts[i-1][1])
                    
                    # 最后一个词补齐到 seg_stop
                    last_stop = int(seg_words[-1]['stop_time'])
                    if last_stop < seg_stop:
                        extra = (seg_stop - last_stop) // 10
                        karaoke_parts[-1] = (karaoke_parts[-1][0] + max(1, extra), karaoke_parts[-1][1])
                    
                    karaoke_text = ''.join(f'{{\\k{k}}}{t}' for k, t in karaoke_parts)
                    lines.append(f"Dialogue: 0,{ms_to_ass_time(seg_start)},{ms_to_ass_time(seg_stop)},Default,,0,0,0,,{karaoke_text}")
                else:
                    # 普通模式：纯文本
                    lines.append(f"Dialogue: 0,{ms_to_ass_time(seg_start)},{ms_to_ass_time(seg_stop)},Default,,0,0,0,,{seg_text}")
        
        # 说话人标签
        first_sent_start = None
        for sent in p.get('sentences', []):
            if int(sent['start_time']) < int(sent['stop_time']):
                first_sent_start = int(sent['start_time'])
                break
        if first_sent_start is not None:
            spk_end = min(first_sent_start + 3000, first_sent_start + 5000)
            lines.append(f"Dialogue: 1,{ms_to_ass_time(first_sent_start)},{ms_to_ass_time(spk_end)},Speaker,,0,0,0,,说话人 {speaker_id}")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    return len(paragraphs)


def generate_srt(paragraphs, speaker_map, output_path):
    """生成 SRT 字幕文件（拆分后的短句）"""
    lines = []
    idx = 1
    for p in paragraphs:
        pid = p.get('pid', '')
        speaker_id = speaker_map.get(pid, '1')
        for sent in p.get('sentences', []):
            if int(sent['start_time']) >= int(sent['stop_time']):
                continue
            segments = split_sentence_by_punctuation(sent)
            for seg_start, seg_stop, seg_text in segments:
                if not seg_text.strip():
                    continue
                lines.append(str(idx))
                lines.append(f"{ms_to_srt_time(seg_start)} --> {ms_to_srt_time(seg_stop)}")
                lines.append(f"[说话人{speaker_id}] {seg_text}")
                lines.append("")
                idx += 1
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    return idx - 1


def burn_subtitles(video_path, ass_path, output_path, preset='ultrafast', crf=23):
    """用 ffmpeg 将 ASS 字幕烧录到视频"""
    cmd = [
        'ffmpeg', '-y',
        '-i', video_path,
        '-vf', f'ass={ass_path}',
        '-c:v', 'libx264', '-preset', preset, '-crf', str(crf),
        '-c:a', 'copy',
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ffmpeg error: {result.stderr[-500:]}")
        return False
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='从 HAR 文件生成字幕并烧录到视频')
    parser.add_argument('har_file', help='HAR 文件路径')
    parser.add_argument('video_file', nargs='?', help='视频文件路径（不提供则只生成字幕）')
    parser.add_argument('--output-dir', default='.', help='输出目录')
    parser.add_argument('--karaoke', action='store_true', help='卡拉OK逐字高亮（默认普通字幕，拆分逻辑相同）')
    parser.add_argument('--burn', action='store_true', help='烧录字幕到视频')
    parser.add_argument('--video-width', type=int, default=640, help='视频宽度')
    parser.add_argument('--video-height', type=int, default=360, help='视频高度')
    args = parser.parse_args()
    
    print(f"解析 HAR 文件: {args.har_file}")
    paragraphs, speaker_map = parse_har(args.har_file)
    total_sentences = sum(len(p.get('sentences', [])) for p in paragraphs)
    total_words = sum(len(s.get('contents', [])) for p in paragraphs for s in p.get('sentences', []))
    print(f"解析结果: {len(paragraphs)} 段, {total_sentences} 句, {total_words} 词")
    
    # 拆分后统计
    split_count = 0
    for p in paragraphs:
        for s in p.get('sentences', []):
            split_count += len(split_sentence_by_punctuation(s))
    print(f"标点拆分后字幕条数: {split_count} (原句数: {total_sentences})")
    
    os.makedirs(args.output_dir, exist_ok=True)
    
    # 生成 ASS（默认普通模式，--karaoke 添加逐词高亮）
    ass_name = 'subtitle_karaoke.ass' if args.karaoke else 'subtitle.ass'
    ass_path = os.path.join(args.output_dir, ass_name)
    generate_ass(paragraphs, speaker_map, ass_path, args.video_width, args.video_height, args.karaoke)
    print(f"ASS 已生成: {ass_path} ({'卡拉OK' if args.karaoke else '普通'}模式)")
    
    # 生成 SRT
    srt_path = os.path.join(args.output_dir, 'subtitle.srt')
    count = generate_srt(paragraphs, speaker_map, srt_path)
    print(f"SRT 已生成: {srt_path} ({count} 条)")
    
    # 烧录
    if args.burn and args.video_file:
        suffix = '_卡拉OK字幕版' if args.karaoke else '_字幕版'
        out_name = os.path.splitext(os.path.basename(args.video_file))[0] + suffix + '.mp4'
        out_path = os.path.join(args.output_dir, out_name)
        print(f"开始烧录: {out_path}")
        if burn_subtitles(args.video_file, ass_path, out_path):
            print(f"烧录完成: {out_path}")
        else:
            print("烧录失败!")
