---
name: protocol-pack-unpack
description: "Communication protocol pack/unpack code auto-generator for CAN,
  Serial (UART), and MQTT. This skill should be used when users need to generate
  Python code for packing or unpacking binary protocol frames — including CAN
  bus messages, serial port frames (with headers, CRC checksums, length fields),
  and MQTT binary payloads. It produces production-ready Python scripts with
  both pack_frame() and unpack_frame() functions, automated bidirectional test
  cases, and an iterative self-repair loop (max 5 rounds) that fixes offset,
  endianness, checksum, and scaling errors automatically. Triggers: CAN组包,
  CAN解包, 串口协议, MQTT报文, 协议组包, 协议解包, protocol pack, protocol unpack, 帧解析, 报文解析,
  CRC校验, 帧组包, 帧解包."
agent_created: true
disable: false
---

# Protocol Pack/Unpack Auto-Generator (CAN / Serial / MQTT)

## Overview

Generate production-ready Python pack/unpack scripts for three communication protocol families:
CAN bus, Serial (UART), and MQTT. The workflow is a strict 6-step closed loop: parse rules,
generate bidirectional code, run automated tests, iterate-fix errors, verify pass, and deliver
standardized output. Only Python standard library (`struct`, `binascii`, `typing`) is used.

## Required User Input

Three items must be provided. If any is missing, prompt the user to supply it before proceeding:

1. **Protocol type** — exactly one of: `CAN`, `Serial` (串口), `MQTT`
2. **Complete protocol rule description** — frame structure, field offsets, bit widths, data
   types, endianness, checksum method, frame header/footer, special rules (scaling factors,
   reserved bits, fragmentation, etc.)
3. **Test example** — raw hexadecimal message + expected parsing result dictionary

### Excel Protocol Document Parsing (CAN Protocol)

When the user provides an Excel file containing CAN protocol definitions:

1. **Use the provided Excel parser script**: Run `scripts/excel_parser.py` to automatically
   parse the Excel file:
   ```bash
   python scripts/excel_parser.py <excel_path> <output_json_path>
   ```

2. **Validate parsed results**: After parsing, automatically verify:
   - All CAN IDs in the Excel are present in the parsed config
   - All signals for each CAN ID are correctly extracted
   - Signal `start_bit` and `bit_length` are within DLC range
   - Bitfield signals (multiple 1-bit signals in same byte) are correctly handled
   - Signals with `start_byte=None` are correctly assigned to share the previous signal's byte

3. **Auto-fix common issues**:
   - If `start_byte` is None, signal shares byte with previous signal
   - If bitfield signals overlap in same byte, verify they use different bits
   - If signals exceed DLC, remove or fix them
   - Check for duplicate signal names and rename if necessary

4. **Generate test cases from actual logs**: If user provides CAN log file (CSV, BLF, etc.),
   automatically extract test cases and run bidirectional verification

## Execution Workflow (Strict 6-Step Closed Loop)

Execute all 6 steps in order. Do not skip, simplify, or improvise.

### Step 1 — Structured Rule Extraction

Extract all structural rules from user input with precision. Consult the protocol-specific
reference in `references/` for the target protocol to ensure no field is missed.

**For Excel protocol documents:**

1. **Run the Excel parser**: Use `scripts/excel_parser.py` to automatically parse the Excel file:
   ```bash
   cd skills/protocol-pack-unpack/scripts
   python excel_parser.py <excel_path> <output_json_path>
   ```

2. **Verify parsing results**: After parsing, automatically check:
   - Run `python -c "import json; f=open('<output_json_path>'); config=json.load(f); print(f'Total messages: {len(config)}')"` to verify
   - Check that all expected CAN IDs are present
   - Check that signal counts match expectations
   - If parsing fails or is incomplete, fix the parser and re-run

3. **Auto-fix common Excel issues**:
   - Signals with `start_byte=None` share byte with previous signal
   - Bitfield signals (multiple 1-bit signals in same byte) are normal
   - Signals exceeding DLC are removed (multi-frame messages)
   - Duplicate signal names are renamed with `_2`, `_3`, etc.

- **CAN**: frame ID, standard/extended frame, DLC, signal start bit, bit width, scaling,
  offset, endianness (Motorola/Intel byte order), checksum rules
- **Serial**: frame header, frame footer, length field position & width, checksum
  (CRC8/CRC16/XOR/none), endianness, fragmentation logic, field offsets
- **MQTT**: packet type, fixed header, variable header, remaining-length decoding, Topic
  parsing rules, Payload custom sub-protocol, encoding method

Auto-fill industry-default rules for anything the user did not specify, and annotate each
auto-filled rule with a code comment marking it as `[AUTO-FILLED DEFAULT]`.

### Step 2 — Bidirectional Python Script Generation

Generate two core functions simultaneously. Both must exist; generating only one is prohibited.

```python
def unpack_frame(hex_str: str) -> dict:
    """Unpack hexadecimal message into business dictionary."""
    ...

def pack_frame(data_dict: dict) -> str:
    """Pack business dictionary into standard hexadecimal message."""
    ...
```

**Mandatory code standards:**

- Only Python standard library: `struct`, `binascii`, `typing` — no third-party dependencies
- Comprehensive exception handling: frame length errors, checksum failures, index out-of-range,
  invalid values — each must raise a descriptive exception
- Every field annotated with detailed comments: offset, bit width, algorithm, source rule
- Support signed/unsigned integers, big/little endian, scaling & offset computation
- Use the CRC utilities in `scripts/crc_utils.py` when checksum computation is needed
- Use the appropriate code template from `assets/` as the starting skeleton

### Step 3 — Automated Built-in Test Cases

Append automated test code at the end of the script that performs bidirectional verification:

- **Forward check**: raw hex → `unpack_frame()` → compare result with user's expected dict
- **Reverse check**: expected dict → `pack_frame()` → compare result with original raw hex
- Automatically output a diff report: missing fields, value mismatches, endianness errors,
  checksum errors, length errors
- Use `scripts/test_framework.py` as the test harness; it provides `run_test()` and
  `compare_dicts()` helpers

### Step 4 — Intelligent Iterative Repair (Core Capability)

When verification fails, automatically enter the repair loop. Maximum 5 iterations to prevent
infinite loops.

Each repair iteration must:

1. **Carry full context**: original protocol rules + previous error code + test failure diff log
2. **Pinpoint the problem**: field offset error, endianness reversed, bit width error, checksum
   algorithm error, scaling formula error
3. **Rewrite the code and regenerate test cases**
4. **Re-run the full bidirectional test**

**Common issues to auto-fix** (based on real-world cases):

1. **Excel parsing issues**:
   - `start_byte=None` (signals share byte with previous signal) → Use previous signal's byte
   - Bitfield signals (multiple 1-bit signals in same byte) → Verify they use different bits
   - Incomplete signal extraction → Re-run parser with debug output

2. **Signal definition issues**:
   - `start_bit` calculation wrong → Recalculate from `start_byte * 8 + bit_offset`
   - `bit_length` wrong → Check Excel "Bit Position" column for range (e.g., "Bit0-15" = 16 bits)
   - Signals exceed DLC → Remove or mark as multi-frame

3. **Pack/unpack issues**:
   - Endianness wrong → Check Intel vs Motorola in Excel
   - Scaling formula wrong → Verify `physical_value = raw_value * factor + offset`
   - Signed/unsigned wrong → Check if min value < 0

If 5 repair rounds still fail: terminate iteration, output an Error Cause Summary listing
all unmatched fields and root causes, and prompt the user to supplement protocol rules or
correct the example message.

### Step 5 — Pass Determination

Both forward and reverse checks must be fully consistent. Only then is the script judged
correct and the final version locked.

### Step 6 — Standardized Output Delivery

Output all of the following in one final delivery:

1. Structured protocol rule summary
2. Complete runnable Python pack+unpack code
3. Automated test result report
4. Code usage instructions (parameters, return values)
5. Exception scenario adaptation notes

## Protocol-Specific Adaptation Rules

Detailed knowledge bases live in `references/`. Load the matching reference file before
generating code:

| Protocol | Reference File | Key Concepts |
|----------|---------------|--------------|
| CAN | `references/can_protocol_rules.md` | Bit offset parsing, signal bit width, Motorola/Intel byte order, physical value scaling formula, data segment truncation, CAN ID filtering, stuff bit handling |
| Serial | `references/serial_protocol_rules.md` | Frame header/footer matching, dynamic length field, auto-fragmentation, CRC/XOR checksum, sticky-packet tolerance, byte order conversion |
| MQTT | `references/mqtt_protocol_rules.md` | MQTT remaining-length variable encoding/decoding, packet type parsing, Topic string decoding, Payload custom binary sub-unpacking, fixed header validation |

## Code Templates

Pre-built skeleton templates are in `assets/`. Use them as the starting point, then fill in
protocol-specific logic:

| Protocol | Template File |
|----------|--------------|
| CAN | `assets/can_template.py` |
| Serial | `assets/serial_template.py` |
| MQTT | `assets/mqtt_template.py` |

Each template already contains: the `unpack_frame()` / `pack_frame()` interface, exception
classes, field annotation patterns, and a test case block.

## Utility Scripts

| Script | Purpose |
|--------|---------|
| `scripts/crc_utils.py` | CRC8, CRC16, CRC32, XOR checksum calculators — import and call directly |
| `scripts/test_framework.py` | Test harness with `run_test()`, `compare_dicts()`, `generate_diff_report()` — use for bidirectional test automation |

## Prohibited Behaviors

- Do NOT generate unpack without pack (or vice versa) — both must always be produced together
- Do NOT omit automated test cases
- Do NOT manually judge results — code must self-verify
- Do NOT iterate beyond 5 repair rounds
- Do NOT use third-party libraries — standard library only

## Output Speech Conventions

1. **First generation**: output rule parsing results + full code + test log
2. **Repair iteration**: explicitly state the fix applied (e.g., "fixed endianness",
   "corrected scaling formula", "fixed CRC algorithm")
3. **Final success**: state "Bidirectional verification passed, script is ready for
   production engineering use"
4. **Repair failure**: list unmatched fields and root causes precisely, guide user to
   supplement protocol rules or correct example messages

## 二次解析层 (Value Interpretation Layer) — v2 新增功能

### 核心问题

用户反馈：解析出来的数据只有英文信号名和原始数值（如 `00`, `0x0A`），不知道代表什么含义。

### 解决方案

在 raw value 之外，增加**二次解析**输出，自动将原始值转换为人类可读的含义。

### 两个关键改进

#### 1. 显示名称（报文名称 + 信号描述）

解析结果中每个信号不再只有英文名 `holiday_status`，而是显示：
```
holiday_status (节假日)    ← 信号名 + 中文描述
```

Excel 解析器 (`excel_parser.py`) 现在会额外提取：
- **列 I — Signal Description (信号描述)**: 如 `节假日`、`时间`、`经度`
- **列 N — Signal Value Description (信号值描述)**: 如 `0x00:普通日期\n0x01:春节\n...`

#### 2. 二次解析值（原始值 → 含义值）

对每个信号的原始值，自动进行第二层解释：

| 类型 | 原始值 | 二次解析结果 |
|------|---------------------|
| 枚举/状态码 | `0x00` | `普通日期` |
| 枚举/状态码 | `0x01` | `春节` |
| 时间戳 | `1719705600` | `2025年06月30日14时00分00秒` |
| 日期(BCD) | `250630` | `2025年06月30日` |
| 时间(BCD) | `143600` | `14时36分00秒秒` |
| 普通数值 | `3.14` | `3.14 V` |

### interpret_type 特殊类型说明

生成代码时，为每个信号设置 `interpret_type`：

| 值 | 含义 | 示例输入 → 输出 |
|----|------|-----------------|
| `"enum"` | 枚举查表（基于 value_descriptions） | `0 → "正常"` |
| `"timestamp"` | Unix 时间戳 | `1719705600 → "2025年06月30日..."` |
| `"date"` | 打包日期 (YYMMDD 或 YYYYMMDD) | `250630 → "2025年06月30日"` |
| `"time"` | 打包时间 (HHMMSS) | `143600 → "14时36分00秒"` |
| `"bcd"` | BCD 编码值 | `0x12 → "BCD:12"` |
| `None` / 不设置 | 默认：显示物理值+单位 | `25.6 → "25.6 ℃"` |

### 输出格式

`unpack_frame()` 返回的 dict 新增以下字段：

```python
result = unpack_frame("0102030405060708")
# 常规字段（不变）
result["gps_speed"]       # 物理值: 0
result["_raw"]            # {"gps_speed": 0, ...}
result["_hex"]            # "0102030405060708"

# ===== 新增字段 =====
result["_msg_name"]       # "时间节日同步"  ← 报文名称
result["_interpreted"]    # {              ← 二次解析字典
#     "gps_speed (GPS速度)": "0 km/h",
#     "holiday_status (节假日)": "普通日期",
#     "system_time (时间)": "2025年06月30日14时36分00秒",
# }
```

### 美化显示函数

模板新增 `pretty_print(result)` 和 `print_result(hex_str)` 函数：

```python
from can_template import print_result
result = print_result("0000000000000000")

# 输出：
# ═══════════════════════════════════════════════════════════════════
# ╔══════════════════════════════════════════════════════════════╗
# ║  报文: 时间节日同步
# ║  CAN ID: 0x1BE8E515  |  数据: 0000000000000000
# ╠──────────────────────────────────────────────────────────────╣
# ║  信号名                          原始值      二次解析结果
# ╠──────────────────────────────────────────────────────────────╣
# ║  gps_speed (GPS速度)             0x0 (0)    0 km/h
# ║  system_time (时间)              0x0 (0)    需确认时间格式...
# ║  holiday_status (节假日)         0x0 (0)    普通日期
# ╚══════════════════════════════════════════════════════════════╝
```

### Excel 列映射（更新）

| Excel 列 | 字段名 | 说明 | 是否必须 |
|----------|--------|------|---------|
| A | Num 序号 | 报文序号 | 参考 |
| B | Message Name 报文名称 | 如 `time_holiday_sync` | ✅ |
| C | Direction 收发方向 | Tx/Rx | 参考 |
| E | ID 报文标识符 | CAN ID (hex) | ✅ |
| F | Cycle Time 周期 | 发送周期 | 参考 |
| G | Message Length 报文长度 | DLC | ✅ |
| H | **Signal Name 信号名称** | 如 `holiday_status` | ✅ |
| I | **Signal Description 信号描述** ⬆️NEW | 如 `节假日` | 推荐 |
| J | Start Byte 起始字节 | 起始字节位置 | ✅ |
| K | Bit Position 位位置 | 如 `Bit0-7` | ✅ |
| L | Bit Length 位长度 | 位数 | ✅ |
| M | Byte Order 字节序 | Intel/Motorola | ✅ |
| N | **Signal Value Description 信号值描述** ⬆️NEW | 如 `0x00:普通日期\n0x01:春节` | 推荐 |
| R-Q | Factor/Offset 缩放因子/偏移量 | 物理值换算 | 可选 |
| U | Unit 单位 | 工程单位 | 可选 |

> ⬆️NEW = v2 版本新增支持的列，之前被忽略，现在会被正确解析并用于二次解析。
