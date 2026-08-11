#!/usr/bin/env python3
"""
飞书妙记字幕生成 —— 全自动流程（词级时间戳版）：
1. 上传视频到飞书云盘 → 获取 file_token
2. 用 file_token 生成妙记 → 获取 minute_token
3. 等待妙记处理完成
4. 通过妙记 subtitles_v2 API 获取词级时间戳（精确到每个词的 start/stop 毫秒）
5. 按标点拆分子句，使用实际词级时间戳（非比例估算）
6. 生成 ASS/SRT 字幕
7. 烧录字幕到视频（可选）

词级时间戳获取原理：
  - 妙记 subtitles_v2 是私有 Web API，需要 web session cookies
  - 脚本通过 CDP 从浏览器提取 cookies（无 UI 交互），然后用纯 HTTP 请求调用 API
  - 前置条件：浏览器已打开飞书页面（agent 需先 agent-browser open 妙记页面）

用法：
  python3 minutes_subtitle.py <video_file> [--burn] [--karaoke] [--output-dir DIR]
  python3 minutes_subtitle.py --minute-token <token> [--burn] [--karaoke] [--output-dir DIR]
  python3 minutes_subtitle.py --file-token <token> [--burn] [--karaoke] [--output-dir DIR]
"""
import json
import subprocess
import os
import re
import sys
import argparse
import time
import requests

# 标点拆分：中英文逗号/句号/问号/感叹号/分号/省略号
SPLIT_PUNCT = re.compile(r'[，。！？；,;!?.…]')
# 超长无标点子句的安全阈值
SAFETY_MAX_CHARS = 50
# CDP 连接地址
CDP_URL = "http://localhost:9222"


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
    
    try:
        data = json.loads(stdout)
        file_token = data.get('data', {}).get('file_token', '')
        if not file_token:
            file_token = data.get('file_token', '')
        if file_token:
            print(f"上传成功，file_token: {file_token}")
            return file_token
        else:
            print(f"上传返回但未找到 file_token: {stdout[:200]}")
            return None
    except json.JSONDecodeError:
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


def wait_minutes_ready(minute_token):
    """等待妙记处理完成"""
    print(f"等待妙记处理完成: {minute_token}")
    ok, stdout, stderr = run_lark_cli([
        'minutes', '+detail',
        '--minute-tokens', minute_token,
        '--transcript',
        '--wait-ready',
        '--as', 'user'
    ], timeout=600)
    
    if not ok:
        print(f"等待妙记完成失败: {stderr}")
        return False
    
    print("妙记处理完成")
    return True


def get_cookies_from_browser():
    """通过 CDP 从浏览器提取飞书 cookies（无 UI 交互）。
    前置条件：浏览器已打开飞书页面（agent 需先 agent-browser open 妙记页面）。
    """
    from playwright.sync_api import sync_playwright
    
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        
        all_cookies = []
        for ctx in browser.contexts:
            all_cookies.extend(ctx.cookies())
        
        # 过滤 feishu.cn 域名的 cookies
        feishu_cookies = [c for c in all_cookies if 'feishu.cn' in c.get('domain', '')]
        
        # 构建 cookie 字符串
        cookie_parts = [f"{c['name']}={c['value']}" for c in feishu_cookies]
        cookie_str = '; '.join(cookie_parts)
        
        # 提取 CSRF tokens
        bv_csrf = ''
        for c in feishu_cookies:
            if c['name'] == 'bv_csrf_token':
                bv_csrf = c['value']
                break
        
        browser.close()
        
        return {
            'cookie': cookie_str,
            'bv_csrf_token': bv_csrf,
        }


def fetch_word_level_subtitles(minute_token, tenant_domain=None):
    """通过妙记 subtitles_v2 API 获取词级时间戳。
    
    流程：
    1. 从浏览器提取 cookies（CDP，无 UI 交互）
    2. 调用 /minutes/api/subtitles/paragraph-ids 获取所有段落 ID
    3. 分页调用 /minutes/api/subtitles_v2 获取每个段落的词级时间戳
    
    返回结构：[{pid, start_time, stop_time, sentences: [{start_time, stop_time, contents: [{content, start_time, stop_time}]}]}]
    """
    # 确定 API 基础域名
    if tenant_domain:
        base = f"https://{tenant_domain}"
    else:
        # 从 cookies 中提取域名
        base = "https://quectel.feishu.cn"  # 默认值，可被 tenant_domain 覆盖
    
    # Step 1: 提取 cookies
    print("提取浏览器 cookies（CDP，无 UI 交互）...")
    auth = get_cookies_from_browser()
    if not auth['cookie']:
        print("错误：无法从浏览器提取 cookies。请确保浏览器已打开飞书页面。")
        return None
    print(f"  Cookie 长度: {len(auth['cookie'])}")
    
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "bv-csrf-token": auth['bv_csrf_token'],
        "cookie": auth['cookie'],
        "platform": "web",
        "referer": f"{base}/minutes/{minute_token}",
        "user-agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Edg/151.0.0.0 Mobile",
        "utc-bias": "480",
        "x-lgw-os-type": "4",
        "x-lgw-terminal-type": "2",
        "x-lsc-bizid": "16",
        "x-lsc-terminal": "web",
        "x-lsc-version": "1",
    }
    
    # Step 2: 获取所有段落 ID
    print("获取段落 ID 列表...")
    resp = requests.get(
        f"{base}/minutes/api/subtitles/paragraph-ids",
        params={
            "object_token": minute_token,
            "language": "zh_cn",
            "page_size": 10000,
            "page_num": 0,
        },
        headers=headers,
        timeout=15
    )
    
    if resp.status_code != 200:
        print(f"  错误: HTTP {resp.status_code} - {resp.text[:300]}")
        return None
    
    pid_data = resp.json()
    if pid_data.get("code") != 0:
        print(f"  API 错误: {pid_data.get('msg')}")
        return None
    
    paragraph_ids = [item["pid"] for item in pid_data.get("data", {}).get("list", [])]
    print(f"  获取到 {len(paragraph_ids)} 个段落 ID")
    
    if not paragraph_ids:
        print("  错误：未找到段落 ID")
        return None
    
    # Step 3: 分页获取词级时间戳
    print(f"分页获取词级时间戳（每页 100 段）...")
    all_paragraphs = []
    page_size = 100
    current_pid = paragraph_ids[0]
    
    while True:
        resp = requests.get(
            f"{base}/minutes/api/subtitles_v2",
            params={
                "object_token": minute_token,
                "paragraph_id": current_pid,
                "size": page_size,
                "translate_lang": "default",
                "is_fluent": "false",
                "filter_speaker": "true",
                "language": "zh_cn"
            },
            headers=headers,
            timeout=15
        )
        
        if resp.status_code != 200:
            print(f"  错误 at pid {current_pid}: HTTP {resp.status_code}")
            break
        
        data = resp.json()
        if data.get("code") != 0:
            print(f"  API 错误 at pid {current_pid}: {data.get('msg')}")
            break
        
        paragraphs = data.get("data", {}).get("paragraphs", [])
        if not paragraphs:
            break
        
        all_paragraphs.extend(paragraphs)
        print(f"  已获取 {len(paragraphs)} 段（累计 {len(all_paragraphs)}/{len(paragraph_ids)}）")
        
        if len(paragraphs) < page_size:
            break
        
        current_pid = paragraphs[-1].get("pid", "")
        if not current_pid:
            break
        
        time.sleep(0.1)
    
    # 统计
    total_sentences = sum(len(p.get("sentences", [])) for p in all_paragraphs)
    total_words = sum(len(s.get("contents", [])) for p in all_paragraphs for s in p.get("sentences", []))
    print(f"获取完成: {len(all_paragraphs)} 段落, {total_sentences} 句子, {total_words} 词")
    
    return all_paragraphs


def split_by_punctuation_with_real_timestamps(paragraphs):
    """按标点拆分子句，使用实际词级时间戳。
    
    每个子句的 start_ms = 子句第一个词的 start_time
    每个子句的 stop_ms = 子句最后一个词的 stop_time
    
    返回 [(start_ms, stop_ms, text, speaker, words), ...]
    其中 words = [(content, start_ms, stop_ms), ...] 用于卡拉OK
    """
    all_clauses = []
    
    for para in paragraphs:
        sentences = para.get("sentences", [])
        if not sentences:
            continue
        
        # 获取段落说话人编号（从 pid 或 start_time 推断，暂用 0/1 交替或从句子数据推断）
        # subtitles_v2 不直接返回说话人编号，需要从 paragraph_type 或外部获取
        # 这里使用段落序号作为临时 speaker 标识
        
        for sentence in sentences:
            words = sentence.get("contents", [])
            if not words:
                continue
            
            # 将所有词的文本拼接，同时记录每个词的时间戳
            # 按标点拆分：遍历词，遇到标点就断句
            clauses = []
            current_clause_words = []
            
            for word in words:
                content = word.get("content", "")
                word_start = int(word.get("start_time", 0))
                word_stop = int(word.get("stop_time", 0))
                
                current_clause_words.append((content, word_start, word_stop))
                
                # 检查这个词是否以标点结尾
                if content and SPLIT_PUNCT.search(content[-1]):
                    clauses.append(current_clause_words)
                    current_clause_words = []
            
            if current_clause_words:
                clauses.append(current_clause_words)
            
            # 为每个子句生成 (start_ms, stop_ms, text, speaker, words)
            for clause_words in clauses:
                # 去除标点后的文本
                text_parts = []
                clean_words = []
                for content, w_start, w_stop in clause_words:
                    clean = SPLIT_PUNCT.sub('', content).strip()
                    if clean:
                        text_parts.append(clean)
                        clean_words.append((clean, w_start, w_stop))
                
                text = ''.join(text_parts)
                if not text or not clean_words:
                    continue
                
                # 超长无标点子句安全检查
                if len(text) > SAFETY_MAX_CHARS:
                    # 尝试在空格处拆分
                    parts = text.split(' ')
                    if len(parts) > 1:
                        mid = len(parts) // 2
                        # 重新分配词到两个子句
                        part1_words = []
                        part2_words = []
                        char_count = 0
                        split_point = len(' '.join(parts[:mid]))
                        
                        for clean, w_start, w_stop in clean_words:
                            if char_count < split_point:
                                part1_words.append((clean, w_start, w_stop))
                            else:
                                part2_words.append((clean, w_start, w_stop))
                            char_count += len(clean)
                        
                        for part_words in [part1_words, part2_words]:
                            if part_words:
                                p_text = ''.join(w[0] for w in part_words)
                                p_start = part_words[0][1]
                                p_stop = part_words[-1][2]
                                all_clauses.append((p_start, p_stop, p_text, 0, part_words))
                        continue
                
                start_ms = clean_words[0][1]
                stop_ms = clean_words[-1][2]
                all_clauses.append((start_ms, stop_ms, text, 0, clean_words))
    
    return all_clauses


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


def generate_ass(clauses, output_path, video_w=640, video_h=360, karaoke=False):
    """生成 ASS 字幕文件
    
    clauses: [(start_ms, stop_ms, text, speaker, words), ...]
    words: [(content, start_ms, stop_ms), ...] 用于卡拉OK
    """
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
        for start_ms, stop_ms, text, speaker, words in clauses:
            start = ms_to_ass_time(start_ms)
            end = ms_to_ass_time(stop_ms)
            style = 'Karaoke' if karaoke else 'Default'
            
            if karaoke:
                # 卡拉OK：使用实际词级时间戳生成 \k 标签
                karaoke_parts = []
                for i, (char_text, w_start, w_stop) in enumerate(words):
                    # 计算这个字相对于子句开始时间的偏移（百分秒）
                    if i == 0:
                        # 第一个词：从子句开始到第一个词结束
                        dur_cs = max(1, (w_stop - start_ms) // 10)
                        karaoke_parts.append(f'{{\\k{dur_cs}}}{char_text}')
                    else:
                        # 计算与前一个词的间隔
                        prev_w_stop = words[i-1][2]
                        gap_cs = max(0, (w_start - prev_w_stop) // 10)
                        dur_cs = max(1, (w_stop - w_start) // 10)
                        if gap_cs > 0:
                            # 词间停顿：用 \k0 表示
                            karaoke_parts.append(f'{{\\k{gap_cs}}}{{\\k{dur_cs}}}{char_text}')
                        else:
                            karaoke_parts.append(f'{{\\k{dur_cs}}}{char_text}')
                
                karaoke_text = ''.join(karaoke_parts)
                f.write(f'Dialogue: 0,{start},{end},{style},Speaker {speaker},0,0,0,,{karaoke_text}\n')
            else:
                f.write(f'Dialogue: 0,{start},{end},{style},Speaker {speaker},0,0,0,,{text}\n')
    
    print(f"ASS 已生成: {output_path} ({'卡拉OK' if karaoke else '普通'}模式, {len(clauses)} 条)")


def generate_srt(clauses, output_path):
    """生成 SRT 字幕文件"""
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        for i, (start_ms, stop_ms, text, speaker, words) in enumerate(clauses, 1):
            start = ms_to_srt_time(start_ms)
            end = ms_to_srt_time(stop_ms)
            f.write(f'{i}\n')
            f.write(f'{start} --> {end}\n')
            f.write(f'{text}\n')
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
    parser = argparse.ArgumentParser(description='飞书妙记字幕生成（词级时间戳版）')
    parser.add_argument('video_file', nargs='?', help='本地视频文件路径')
    parser.add_argument('--minute-token', help='已有妙记 token（跳过上传）')
    parser.add_argument('--file-token', help='已有云盘 file_token（跳过 drive 上传）')
    parser.add_argument('--output-dir', default='.', help='输出目录')
    parser.add_argument('--karaoke', action='store_true', help='卡拉OK逐词高亮（使用实际词级时间戳）')
    parser.add_argument('--burn', action='store_true', help='烧录字幕到视频')
    parser.add_argument('--video-width', type=int, default=640, help='视频宽度')
    parser.add_argument('--video-height', type=int, default=360, help='视频高度')
    parser.add_argument('--tenant-domain', default=None, help='飞书租户域名（如 quectel.feishu.cn）')
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
    
    # Step 2: 等待妙记处理完成
    if not wait_minutes_ready(minute_token):
        print("等待妙记完成失败，退出")
        sys.exit(1)
    
    # Step 3: 获取词级时间戳（通过 subtitles_v2 API）
    print(f"\n获取词级时间戳: minute_token={minute_token}")
    paragraphs = fetch_word_level_subtitles(minute_token, args.tenant_domain)
    if not paragraphs:
        print("获取词级时间戳失败，退出")
        sys.exit(1)
    
    # Step 4: 按标点拆分（使用实际词级时间戳）
    print(f"\n按标点拆分子句（使用实际词级时间戳）...")
    clauses = split_by_punctuation_with_real_timestamps(paragraphs)
    print(f"拆分结果: {len(clauses)} 条字幕")
    
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
