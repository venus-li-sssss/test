#!/usr/bin/env python3
"""
CAN Protocol Pack/Unpack Template
==================================
Template for CAN bus message pack/unpack operations.
Replace TODO sections with protocol-specific logic.

Only uses Python standard library: struct, binascii, typing

Features:
- Bidirectional pack/unpack
- Signal descriptions (信号描述) in output
- Value interpretation layer (二次解析): raw value -> human-readable meaning
  e.g., 0x00 -> "普通日期", timestamp -> "2025年06月30日14时36分00秒"
"""

import struct
import re
from datetime import datetime
from typing import Dict, Any, Tuple, Union, Optional, List


# ============================================================
# Protocol Configuration (FILL IN from user's protocol rules)
# ============================================================

CAN_CONFIG = {
    # Frame configuration
    "frame_type": "standard",       # "standard" (11-bit) or "extended" (29-bit)
    "dlc": 8,                        # Data length code (0-8)

    # Message metadata (for human-readable display)
    "msg_name": "",                  # 报文名称 e.g. "时间节日同步 / time_holiday_sync"
    "msg_description": "",           # 报文描述 (optional)

    # Signal definitions (DBC-style)
    # Each signal: name, description, start_bit, bit_length, byte_order,
    #              value_type, factor, offset, unit, value_descriptions, interpret_type
    #
    # NEW FIELDS (v2):
    #   - description:        信号描述 (Chinese) e.g. "节假日"
    #   - value_descriptions: 值映射字典 {"00": "普通日期", "01": "春节", ...}
    #   - interpret_type:     特殊解释类型: None|"enum"|"timestamp"|"date"|"time"|"bcd"
    "signals": [
        # Example signal definition (REPLACE with actual protocol signals)
        # {
        #     "name": "engine_speed",
        #     "description": "发动机转速",          # [NEW] 中文描述
        #     "start_bit": 0,
        #     "bit_length": 16,
        #     "byte_order": "intel",
        #     "value_type": "unsigned",
        #     "factor": 0.125,
        #     "offset": 0,
        #     "unit": "rpm",
        #     "value_descriptions": {},             # [NEW] 枚举值映射
        #     "interpret_type": None,                # [NEW] 特殊类型
        # },
        # TODO: Add all signals from protocol specification
    ],

    # Frame ID configuration
    "can_id": 0x123,                 # Default CAN ID (replace or make configurable)

    # Checksum (application layer, if any)
    "checksum_type": None,           # None, "xor", "sum8", or "crc8"
    "checksum_position": None,       # Byte position of checksum field
    "checksum_range": None,          # (start_offset, end_offset) or None for entire data
}


# ============================================================
# Exception Classes
# ============================================================

class CANFrameError(Exception):
    """Base exception for CAN frame errors."""
    pass


class CANFrameLengthError(CANFrameError):
    """Frame length does not match expected DLC."""
    pass


class CANChecksumError(CANFrameError):
    """Checksum verification failed."""
    pass


class CANSignalExtractionError(CANFrameError):
    """Error extracting a signal from the frame data."""
    pass


# ============================================================
# Bit Extraction Utilities
# ============================================================

def _extract_bits_intel(data: bytes, start_bit: int, bit_length: int) -> int:
    """Extract bits using Intel (little endian) byte order.

    Intel bit numbering:
        Byte 0: bits 0-7 (bit 0 = LSB)
        Byte 1: bits 8-15
        Byte 2: bits 16-23
        ...
    Start bit refers to the LSB position of the signal.
    """
    byte_index = start_bit // 8
    bit_offset = start_bit % 8

    # Calculate how many bytes we need
    total_bits_needed = bit_offset + bit_length
    num_bytes = (total_bits_needed + 7) // 8

    if byte_index + num_bytes > len(data):
        raise CANSignalExtractionError(
            f"Signal extends beyond data: start_bit={start_bit}, bit_length={bit_length}, "
            f"need bytes {byte_index}..{byte_index + num_bytes}, data length={len(data)}"
        )

    # Concatenate bytes in little-endian order
    raw = 0
    for i in range(num_bytes):
        raw |= data[byte_index + i] << (i * 8)

    # Shift and mask
    raw = (raw >> bit_offset) & ((1 << bit_length) - 1)
    return raw


def _extract_bits_motorola(data: bytes, start_bit: int, bit_length: int) -> int:
    """Extract bits using Motorola (big endian) byte order.

    Motorola bit numbering (MSB first within each byte):
        Byte 0: bits 7,6,5,4,3,2,1,0 (bit 7 = MSB)
        Byte 1: bits 15,14,13,12,11,10,9,8
        ...
    Start bit refers to the MSB position of the signal.

    The start_bit in DBC format for Motorola:
        byte_idx = start_bit // 8
        bit_in_byte = start_bit % 8  (where 7=MSB, 0=LSB)
    """
    byte_index = start_bit // 8
    bit_pos = start_bit % 8  # Position within byte, 7=MSB

    # Convert to a linear bit position (MSB-first numbering)
    # bit_pos 7 = MSB of byte, bit_pos 0 = LSB of byte
    # We want to start reading from bit_pos going down, then wrap to next byte's MSB

    raw = 0
    bits_remaining = bit_length
    current_byte = byte_index
    current_bit = bit_pos  # Start from MSB side

    while bits_remaining > 0:
        if current_byte >= len(data):
            raise CANSignalExtractionError(
                f"Signal extends beyond data: start_bit={start_bit}, bit_length={bit_length}"
            )
        # How many bits can we read from current byte?
        bits_available = current_bit + 1  # If bit_pos=7, we can read 8 bits (0..7)
        bits_to_read = min(bits_available, bits_remaining)

        # Create mask for bits_to_read bits starting from current_bit
        mask = ((1 << bits_to_read) - 1) << (current_bit - bits_to_read + 1)
        byte_val = (data[current_byte] & mask) >> (current_bit - bits_to_read + 1)

        # Shift existing raw and add new bits
        raw = (raw << bits_to_read) | byte_val

        bits_remaining -= bits_to_read
        current_byte += 1
        current_bit = 7  # Next byte starts from MSB

    return raw


def _apply_signed(raw_value: int, bit_length: int) -> int:
    """Convert raw unsigned value to signed (two's complement)."""
    if raw_value >= (1 << (bit_length - 1)):
        return raw_value - (1 << bit_length)
    return raw_value


def _apply_scaling(raw_value: int, factor: float, offset: float) -> float:
    """Apply scaling: physical = raw * factor + offset."""
    return raw_value * factor + offset


def _reverse_scaling(physical_value: float, factor: float, offset: float) -> int:
    """Reverse scaling: raw = (physical - offset) / factor."""
    return int(round((physical_value - offset) / factor))


# ============================================================
# Value Interpretation Layer (二次解析)
# ============================================================

def _interpret_value(raw_value: int, physical_value: Union[int, float],
                     signal: Dict[str, Any]) -> str:
    """
    Convert raw/physical value to human-readable string.

    Interpretation priority:
    1. interpret_type special handling: timestamp, date, time, bcd
    2. value_descriptions enum lookup
    3. Fallback: formatted number with unit

    Args:
        raw_value: The raw integer value extracted from bits
        physical_value: The scaled physical value (raw * factor + offset)
        signal: Signal definition dict

    Returns:
        Human-readable string representation of the value.
    """
    interpret_type = signal.get("interpret_type")
    value_descs = signal.get("value_descriptions", {})
    unit = signal.get("unit", "")

    # --- Special type handlers ---

    # Timestamp: Unix timestamp or seconds-since-epoch -> formatted datetime
    if interpret_type == "timestamp":
        try:
            if physical_value > 1e9:  # Looks like Unix timestamp (seconds)
                dt = datetime.fromtimestamp(physical_value)
                return dt.strftime("%Y年%m月%d日%H时%M分%S秒")
            elif physical_value > 1e6:  # Could be milliseconds
                dt = datetime.fromtimestamp(physical_value / 1000)
                return dt.strftime("%Y年%m月%d日%H时%M分%S秒") + f".{int(physical_value % 1000):03d}"
            else:
                return f"{physical_value} {unit}".strip()
        except (ValueError, OSError):
            return f"{physical_value} {unit}".strip()

    # Date fields: packed BCD or integer date -> formatted date
    if interpret_type == "date":
        try:
            val = int(raw_value)
            # Try common packed formats
            # Format: 0xYYMMDD or YYMMDD as integer
            if val > 100000:
                day = val % 100
                month = (val // 100) % 100
                year = val // 10000
                return f"{year:04d}年{month:02d}月{day:02d}日"
            elif val > 10000:
                day = val % 100
                month = (val // 100) % 100
                year = 2000 + (val // 10000)
                return f"{year:04d}年{month:02d}月{day:02d}日"
            else:
                return f"{val:08d} [需确认日期格式]".format(val)
        except (ValueError, TypeError):
            return f"{physical_value} {unit}".strip()

    # Time fields: packed time -> HH:MM:SS
    if interpret_type == "time":
        try:
            val = int(raw_value)
            # Common format: HHMMSS as integer
            if val >= 0:
                second = val % 100
                minute = (val // 100) % 100
                hour = (val // 10000) % 100
                return f"{hour:02d}时{minute:02d}分{second:02d}秒"
        except (ValueError, TypeError):
            pass
        return f"{physical_value} {unit}".strip()

    # BCD encoded values
    if interpret_type == "bcd":
        try:
            bcd_str = format(raw_value, 'X')
            return f"BCD:{bcd_str}"
        except (ValueError, TypeError):
            return f"{physical_value} {unit}".strip()

    # --- Enum/description lookup ---
    if value_descs:
        # Try multiple key formats to match
        hex_key = format(raw_value, 'X')      # Uppercase hex without 0x
        hex_key_lower = format(raw_value, 'x')  # Lowercase hex
        dec_key = str(raw_value)              # Decimal string
        zero_padded_hex = format(raw_value, '02X')

        for key in [hex_key_lower, hex_key, dec_key, zero_padded_hex]:
            if key in value_descs:
                return value_descs[key]

        # No exact match found - show closest info
        return f"{physical_value} {unit}".strip() + f" (枚举:无匹配)"

    # --- Default fallback ---
    result = f"{physical_value}"
    if unit:
        result += f" {unit}"
    return result


def _build_signal_label(signal: Dict[str, Any]) -> str:
    """Build display label combining name and description.

    Format: "signal_name (信号描述)" or just "signal_name"
    """
    name = signal["name"]
    desc = signal.get("description", "")
    if desc:
        return f"{name} ({desc})"
    return name


# ============================================================
# Unpack Function (hex string -> business dictionary)
# ============================================================

def unpack_frame(hex_str: str) -> dict:
    """Unpack CAN hexadecimal message into business dictionary.

    Args:
        hex_str: Hexadecimal string (e.g., "0123456789ABCDEF" for 8-byte CAN data)

    Returns:
        Dictionary containing:
        - Signal names (English) as keys -> physical values
        - "_interpreted": dict mapping signal labels to interpreted strings
        - "_raw": raw integer values before scaling
        - "_hex": original hex string
        - "_can_id": CAN ID
        - "_msg_name": message name (报文名称)

        The "_interpreted" dict is the key new feature:
        keys are "signal_name (中文描述)" format,
        values are human-readable strings (e.g., "普通日期", "2025年06月30日14时36分00秒")

    Raises:
        CANFrameLengthError: If hex string length doesn't match expected DLC.
        CANSignalExtractionError: If signal extraction fails.
        CANChecksumError: If checksum verification fails.
    """
    # Clean hex string (remove spaces, 0x prefixes)
    hex_str = hex_str.replace(" ", "").replace("0x", "").replace("0X", "")

    # Convert to bytes
    try:
        data = bytes.fromhex(hex_str)
    except ValueError as e:
        raise CANFrameError(f"Invalid hex string: {e}")

    # Validate data length against DLC
    expected_len = CAN_CONFIG["dlc"]
    if len(data) != expected_len:
        raise CANFrameLengthError(
            f"Data length mismatch: expected {expected_len} bytes, got {len(data)} bytes"
        )

    # TODO: Verify checksum if configured (uncomment and fill in)
    # if CAN_CONFIG["checksum_type"] is not None:
    #     _verify_checksum(data)

    result = {}
    raw_values = {}
    interpreted = {}  # 二次解析结果

    for signal in CAN_CONFIG["signals"]:
        name = signal["name"]
        start_bit = signal["start_bit"]
        bit_length = signal["bit_length"]
        byte_order = signal.get("byte_order", "intel")
        value_type = signal.get("value_type", "unsigned")
        factor = signal.get("factor", 1.0)
        offset = signal.get("offset", 0)

        try:
            # Extract raw bits
            if byte_order == "intel":
                raw = _extract_bits_intel(data, start_bit, bit_length)
            elif byte_order == "motorola":
                raw = _extract_bits_motorola(data, start_bit, bit_length)
            else:
                raise CANSignalExtractionError(
                    f"Unknown byte_order '{byte_order}' for signal '{name}'"
                )

            # Apply signed conversion
            if value_type == "signed":
                raw = _apply_signed(raw, bit_length)

            raw_values[name] = raw

            # Apply scaling
            physical = _apply_scaling(raw, factor, offset)

            # Store in result (int if factor is 1 and offset is 0, else float)
            if factor == 1 and offset == 0:
                result[name] = int(physical)
            else:
                result[name] = physical

            # ===== 二次解析：生成人类可读的值 =====
            label = _build_signal_label(signal)
            interpreted[label] = _interpret_value(raw, physical, signal)

        except Exception as e:
            raise CANSignalExtractionError(
                f"Error extracting signal '{name}' "
                f"(start_bit={start_bit}, bit_length={bit_length}): {e}"
            )

    # Store metadata
    result["_raw"] = raw_values
    result["_hex"] = hex_str.upper()
    result["_can_id"] = CAN_CONFIG["can_id"]
    result["_msg_name"] = CAN_CONFIG.get("msg_name", "")
    result["_interpreted"] = interpreted  # 二次解析结果

    return result


# ============================================================
# Pretty Print Display (美化显示)
# ============================================================

def pretty_print(result: dict) -> str:
    """Format unpack result as human-readable multi-line string.

    Displays:
    - Message header (报文名称 + CAN ID)
    - Each signal with: description label, raw value, interpreted value
    - Clear separation between raw data and meaning

    Args:
        result: Dictionary returned by unpack_frame()

    Returns:
        Formatted multi-line string for console display.
    """
    lines = []
    interpreted = result.get("_interpreted", {})
    raw_values = result.get("_raw", {})

    # Header
    msg_name = result.get("_msg_name", "Unknown")
    can_id = result.get("_can_id", 0)
    hex_data = result.get("_hex", "")
    lines.append("╔" + "═" * 68 + "╗")
    lines.append(f"║  报文: {msg_name}")
    lines.append(f"║  CAN ID: 0x{can_id:08X}  |  数据: {hex_data}")
    lines.append("╠" + "─" * 68 + "╣")
    lines.append("║  信号名                          原始值      二次解析结果")
    lines.append("╠" + "─" * 68 + "╣")

    # Signals in config order (to preserve signal order)
    for signal in CAN_CONFIG["signals"]:
        name = signal["name"]
        label = _build_signal_label(signal)

        raw_val = raw_values.get(name, "?")
        interp_val = interpreted.get(label, "-")

        # Format raw value
        if isinstance(raw_val, int):
            raw_str = f"0x{raw_val:X} ({raw_val})"
        else:
            raw_str = str(raw_val)

        # Truncate long labels
        display_label = label[:32] if len(label) > 32 else label
        lines.append(f"║  {display_label:<33s} {raw_str:<11s} {interp_val}")

    lines.append("╚" + "═" * 68 + "╝")

    return "\n".join(lines)


def print_result(hex_str: str) -> dict:
    """Convenience function: unpack and pretty-print in one call.

    Args:
        hex_str: Hexadecimal string to unpack

    Returns:
        The result dictionary from unpack_frame()
    """
    result = unpack_frame(hex_str)
    print(pretty_print(result))
    return result


# ============================================================
# Pack Function (business dictionary -> hex string)
# ============================================================

def pack_frame(data_dict: dict) -> str:
    """Pack business dictionary into CAN hexadecimal message.

    Args:
        data_dict: Dictionary with signal names and physical values.

    Returns:
        Hexadecimal string representing the CAN data frame.

    Raises:
        CANFrameLengthError: If packed data doesn't match expected DLC.
        CANSignalExtractionError: If signal packing fails.
    """
    dlc = CAN_CONFIG["dlc"]
    data = bytearray(dlc)

    for signal in CAN_CONFIG["signals"]:
        name = signal["name"]
        start_bit = signal["start_bit"]
        bit_length = signal["bit_length"]
        byte_order = signal.get("byte_order", "intel")
        value_type = signal.get("value_type", "unsigned")
        factor = signal.get("factor", 1.0)
        offset = signal.get("offset", 0)

        if name not in data_dict:
            raise CANSignalExtractionError(f"Signal '{name}' missing from input dictionary")

        physical_value = data_dict[name]

        # Reverse scaling to get raw value
        raw = _reverse_scaling(physical_value, factor, offset)

        # Validate range
        if value_type == "signed":
            min_val = -(1 << (bit_length - 1))
            max_val = (1 << (bit_length - 1)) - 1
        else:
            min_val = 0
            max_val = (1 << bit_length) - 1

        if raw < min_val or raw > max_val:
            raise CANSignalExtractionError(
                f"Signal '{name}' value {physical_value} (raw={raw}) out of range "
                f"[{min_val}, {max_val}]"
            )

        # Convert signed to unsigned representation
        if value_type == "signed" and raw < 0:
            raw += (1 << bit_length)

        # Pack bits into data
        if byte_order == "intel":
            _pack_bits_intel(data, raw, start_bit, bit_length)
        elif byte_order == "motorola":
            _pack_bits_motorola(data, raw, start_bit, bit_length)
        else:
            raise CANSignalExtractionError(
                f"Unknown byte_order '{byte_order}' for signal '{name}'"
            )

    # TODO: Compute and insert checksum if configured
    # if CAN_CONFIG["checksum_type"] is not None:
    #     _insert_checksum(data)

    return data.hex().upper()


def _pack_bits_intel(data: bytearray, raw_value: int, start_bit: int, bit_length: int):
    """Pack raw value into data using Intel (little endian) byte order."""
    byte_index = start_bit // 8
    bit_offset = start_bit % 8

    total_bits_needed = bit_offset + bit_length
    num_bytes = (total_bits_needed + 7) // 8

    if byte_index + num_bytes > len(data):
        raise CANSignalExtractionError(
            f"Signal extends beyond data: start_bit={start_bit}, bit_length={bit_length}"
        )

    # Read current bytes
    current = 0
    for i in range(num_bytes):
        current |= data[byte_index + i] << (i * 8)

    # Clear the target bits
    mask = ((1 << bit_length) - 1) << bit_offset
    current &= ~mask

    # Set new value
    current |= (raw_value << bit_offset) & mask

    # Write back
    for i in range(num_bytes):
        data[byte_index + i] = (current >> (i * 8)) & 0xFF


def _pack_bits_motorola(data: bytearray, raw_value: int, start_bit: int, bit_length: int):
    """Pack raw value into data using Motorola (big endian) byte order."""
    byte_index = start_bit // 8
    bit_pos = start_bit % 8

    bits_remaining = bit_length
    current_byte = byte_index
    current_bit = bit_pos
    value = raw_value

    while bits_remaining > 0:
        if current_byte >= len(data):
            raise CANSignalExtractionError(
                f"Signal extends beyond data: start_bit={start_bit}, bit_length={bit_length}"
            )

        bits_available = current_bit + 1
        bits_to_write = min(bits_available, bits_remaining)

        # Extract the top bits_to_write bits from value
        shift = bits_remaining - bits_to_write
        bits_val = (value >> shift) & ((1 << bits_to_write) - 1)

        # Clear target bits in byte
        mask = ((1 << bits_to_write) - 1) << (current_bit - bits_to_write + 1)
        data[current_byte] = (data[current_byte] & ~mask) | (bits_val << (current_bit - bits_to_write + 1))

        bits_remaining -= bits_to_write
        current_byte += 1
        current_bit = 7
        # Keep remaining lower bits of value
        value = value & ((1 << shift) - 1) if shift > 0 else 0


# ============================================================
# Automated Test Cases (FILL IN with user's test example)
# ============================================================

def run_tests():
    """Run automated bidirectional tests.

    Forward:  raw hex -> unpack_frame() -> compare with expected dict
    Reverse:  expected dict -> pack_frame() -> compare with original hex
    Also shows interpreted (二次解析) output for human readability.
    """
    # TODO: Replace with user's test data
    test_raw_hex = ""  # e.g., "0123456789ABCDEF"
    test_expected = {}  # e.g., {"engine_speed": 1234.5, "throttle": 50}

    if not test_raw_hex or not test_expected:
        print("[SKIP] No test data provided. Fill in test_raw_hex and test_expected.")
        return

    print("=" * 60)
    print("CAN Protocol Bidirectional Test")
    print("=" * 60)

    all_passed = True

    # --- Forward Test: hex -> dict ---
    print("\n[Forward] Raw hex -> unpack -> expected dict")
    print(f"  Input hex:     {test_raw_hex}")
    try:
        result = unpack_frame(test_raw_hex)
        result_clean = {k: v for k, v in result.items()
                        if not k.startswith("_")}
        print(f"  Unpacked dict: {result_clean}")
        print(f"  Expected dict: {test_expected}")

        # Show interpreted values
        if "_interpreted" in result:
            print(f"\n  --- 二次解析结果 (Interpreted) ---")
            for label, interp_val in result["_interpreted"].items():
                print(f"    {label}: {interp_val}")

        for key, expected_val in test_expected.items():
            if key not in result_clean:
                print(f"  [FAIL] Missing field: {key}")
                all_passed = False
            elif isinstance(expected_val, float) or isinstance(result_clean.get(key), float):
                if abs(result_clean[key] - expected_val) > 1e-6:
                    print(f"  [FAIL] {key}: expected {expected_val}, got {result_clean[key]}")
                    all_passed = False
                else:
                    print(f"  [PASS] {key}: {result_clean[key]}")
            else:
                if result_clean[key] != expected_val:
                    print(f"  [FAIL] {key}: expected {expected_val}, got {result_clean[key]}")
                    all_passed = False
                else:
                    print(f"  [PASS] {key}: {result_clean[key]}")

        # Show pretty-print
        print(f"\n  --- 美化显示 (Pretty Print) ---")
        print(pretty_print(result))

    except Exception as e:
        print(f"  [ERROR] unpack_frame failed: {e}")
        all_passed = False

    # --- Reverse Test: dict -> hex ---
    print("\n[Reverse] Expected dict -> pack -> raw hex")
    print(f"  Input dict: {test_expected}")
    try:
        packed_hex = pack_frame(test_expected)
        print(f"  Packed hex: {packed_hex}")
        print(f"  Expected:   {test_raw_hex.upper()}")

        if packed_hex == test_raw_hex.upper().replace(" ", ""):
            print("  [PASS] Hex match!")
        else:
            print("  [FAIL] Hex mismatch!")
            # Show byte-by-byte diff
            for i, (a, b) in enumerate(zip(packed_hex, test_raw_hex.upper().replace(" ", ""))):
                if a != b:
                    byte_idx = i // 2
                    print(f"    Diff at byte {byte_idx}: got 0x{packed_hex[byte_idx*2:byte_idx*2+2]}, "
                          f"expected 0x{test_raw_hex.upper().replace(' ', '')[byte_idx*2:byte_idx*2+2]}")
            all_passed = False
    except Exception as e:
        print(f"  [ERROR] pack_frame failed: {e}")
        all_passed = False

    # --- Summary ---
    print("\n" + "=" * 60)
    if all_passed:
        print("RESULT: ALL TESTS PASSED - Bidirectional verification OK")
    else:
        print("RESULT: TESTS FAILED - See errors above")
    print("=" * 60)


if __name__ == "__main__":
    run_tests()
