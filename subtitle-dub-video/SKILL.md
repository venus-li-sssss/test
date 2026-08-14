---
name: subtitle-dub-video
label: 字幕配音替换
description: >
  根据字幕文件逐句合成语音（TTS），并将合成音频按字幕时间轴替换原视频的音频。
  支持输入 SRT/ASS/VTT 字幕 + 视频文件，输出带配音的新视频。
  核心特性：三轮校准生成 + best-of-three 最优选择 · 零 atempo/aresample/aformat 无杂音 · 零/极小截断 · 并发合成 · 短段合并。
  使用场景：(1) 用户要求用字幕给视频配音、替换视频音频、语音合成配音；
  (2) 用户提到"配音""dub""替换音频""TTS视频""字幕转语音"；
  (3) 用户提供字幕文件和视频，要求生成带合成语音的视频；
  (4) 用户要求给无声视频加配音。
  触发词：配音、dub、替换音频、字幕配音、TTS视频、语音合成替换、字幕转语音。
---

# 字幕配音替换

## 功能

输入字幕文件（SRT/ASS/VTT）+ 视频文件，逐句调用豆包 TTS 合成语音，按字幕时间轴拼接成完整音轨，替换原视频音频，输出带配音的新视频。

## 核心策略（v6）

本脚本经过多轮实战迭代（v1→v11），v6 是最终稳定版本。v4 用 atempo 压缩超长音频但引入杂音；v5 三轮校准但仍有截断残差且部分版本在补静音路径加了 aresample/aformat 滤镜引入杂音；**v6 彻底解决：best-of-three 选择 + 零 aresample/aformat，纯 TTS 原声直出。**

### 算法原理

TTS `speed_ratio` 参数理论上线性（speed=2.0 → 时长减半），但实际存在非线性偏差。v6 通过**三轮生成 + 校准 + best-of-three 选择**精确补偿这个偏差并选出最优版本：

1. **Round 1（基准）**：全部 speed=1.0 生成，读 WAV 文件头获取精确自然时长
2. **Round 2（调速）**：对超长段计算 `speed_ratio = natural_duration / slot_duration`，以该速度重新生成，测量实际时长
3. **校准**：从 Round 2 实测数据计算 TTS 引擎的非线性系数
   - `实际加速比 = natural / round2_actual_duration`
   - `非线性系数 = 实际加速比 / 设置的 speed_ratio`（< 1.0 说明 TTS 实际比设置值慢）
4. **Round 3（修正）**：对 Round 2 后仍超长的段，用修正后的 speed 重新生成
   - `修正 speed = (natural / slot) / 非线性系数`
5. **best-of-three 选择**：对每段从 r1/r2/r3 三个版本中选最优——
   - 优先选 ≤ 时段的（无截断），选其中最长的（最接近时段，补静音最少）
   - 都超长 → 选最短的（最小截断）
6. **最终拼接**：音频 ≤ 时段 → 补静音；音频 > 时段 → 截断极小残差（< 5%）
   - **concat 无前置滤镜**，零 aresample/aformat/atempo → 纯 TTS 原声，无杂音

### 杂音根因与修复（v4→v6 关键教训）

| 杂音来源 | 说明 | v6 修复 |
|----------|------|---------|
| atempo 相位声码器 | even 1.06x 微调也会在频谱引入"金属感/水声"伪影 | 零 atempo，用 TTS 引擎自身调速 |
| aresample/aformat 前置滤镜 | v5 在补静音路径 concat 前加了 `aresample=44100,aformat=channel_layouts=stereo`，对 TTS 原声做了多余重采样和声道转换 | concat 无前置滤镜，直接 `[0:a][1:a]concat` |
| 多次重编码累积失真 | MP3→WAV→atempo→resample→amix→AAC 多次转换 | 最少转换步骤，TTS 原声直出 |
| 段落拼接无淡入淡出 | 波形不连续产生 click 爆音 | adelay+amix 拼接，PCM 级别对齐 |

### 对齐策略

- 音频 ≤ 时段 → 末尾补静音（自然结束，无截断）
- 音频 > 时段（Round 1）→ Round 2 用 speed_ratio = natural/slot 重新生成
- Round 2 后仍超长 → Round 3 用校准修正后的 speed 重新生成
- **best-of-three**：从三轮结果中选最优版本（≤时段选最长，都超选最短）
- best-of-three 后仍有残差 → 截断 < 5% 尾部（人耳不可感知）
- 极端短时段（natural/slot > 2.0）→ TTS 最大语速 + 截断（不可避免）

## 前置条件

- ffmpeg / ffprobe（沙箱预装）
- 豆包语音合成 MCP（`ms_official_doubao_audio`，工具 `aily_create_audio_by_text`）
- TTS 限制：每次合成文本 ≤ 1024 字节（约 500 汉字），超长自动截断

## 使用方法

### 基本流程

1. 确认用户提供了视频文件路径和字幕文件路径（若用户给的是会话附件，先下载到 workdir）
2. 运行脚本：

```bash
python3 <skill_dir>/scripts/dub_video.py \
  --video <视频路径> \
  --subtitle <字幕路径> \
  --output <输出视频路径> \
  [--voice <音色ID>] \
  [--loudness <音量 0.5~2>] \
  [--workers <并发数>] \
  [--keep-original]
```

3. 脚本自动完成：解析字幕 → 短段合并 → Round 1 基准生成 → Round 2 调速生成 → Round 3 校准修正 → best-of-three 选择 → 拼接音轨 → 替换视频音频
4. 输出文件上传云盘后以链接交付用户

### 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--voice` | 音色ID，见下方常用音色表 | 爽快思思 |
| `--loudness` | 音量倍率，0.5~2 | 1.0 |
| `--workers` | 并发线程数 | 6 |
| `--tts-max-speed` | TTS 最大语速，超过此值的段用最大语速+截断 | 2.0 |
| `--merge-gap` | 合并间隔小于此值的相邻段（秒） | 0.15 |
| `--no-merge` | 禁用短段合并 | 不禁用 |
| `--keep-original` | 保留原视频音频为背景（降至 20% 音量混合） | 不保留 |

### 常用音色

| 音色名 | voice_type |
|--------|-----------|
| 爽快思思（女） | `zh_female_shuangkuaisisi_emo_v2_mars_bigtts` |
| 阳光男声 | `zh_male_MoonFox_cluess_emo_v2_mars_bigtts` |
| 温柔小夏（女） | `zh_female_wanwanxiaohe_moon_bigtts` |
| 沉稳讲述（男） | `zh_male_M392_conversation_wvae_bigtts` |
| 亲切导游（女） | `zh_female_qingxinnvsheng_moon_bigtts` |

用户未指定音色时使用默认「爽快思思」；如需更多音色可查询豆包 TTS 文档。

## 脚本特性

- **三轮校准生成 + best-of-three 选择**：Round 1 基准 → Round 2 调速 → Round 3 校准修正 → 从三轮中选最优版本，零/微截断率 ~74%
- **零 atempo/aresample/aformat**：不使用任何相位声码器或多余重采样滤镜，纯 TTS 原声，无杂音
- **WAV 头读时长**：MP3 → WAV 转换后读 RIFF 头，<1ms 获取 100% 精确时长
- **断点续跑**：每轮结果独立缓存（progress.jsonl / .r2 / .r3），中断后自动跳过已完成段
- **并发合成**：默认 6 线程并发，可调 `--workers`
- **短段合并**：gap < 0.15s 的相邻段自动合并
- **自动截断**：超过 1024 字节的字幕文本自动截断到安全长度
- **格式兼容**：支持 SRT、ASS/SSA、WebVTT 三种字幕格式，自动识别 BOM
- **对齐统计**：输出补静音/恰好fit/截断各级别的段数统计

## 注意事项

- 脚本会在输出目录下创建 `_tts_work/` 临时目录存放中间音频文件（每轮 MP3 + WAV + 归一化 WAV）
- v6 不再使用 `--atempo-max` 参数（v4 遗留），改用 `--tts-max-speed` 控制 TTS 最大语速
- 合成失败的单条字幕会自动跳过（重试 1 次），不影响其他段
- `--keep-original` 模式下原音频降至 20% 音量作为背景，适合保留原声氛围的场景
- Round 2/3 仅对 Round 1 中超长的段执行，fit 的段不重复生成，节省 TTS 调用
- 极端短时段（如 0.3s 的"好"）即使 speed=2.0 仍可能超出，会有少量截断（不可避免）
- **杂音排查要点**：如遇杂音，首先检查 `build_audio_track` 的补静音路径是否误加 `aresample`/`aformat` 前置滤镜——这是 v5 的杂音根因，v6 已彻底去除
