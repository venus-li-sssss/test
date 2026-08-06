#!/usr/bin/env python3
"""
Serial Protocol Pack/Unpack Template
======================================
Template for serial (UART) protocol frame pack/unpack operations.
Replace TODO sections with protocol-specific logic.

Only uses Python standard library: struct, binascii, typing

Features:
- Bidirectional pack/unpack
- Field descriptions (字段描述) in output
- Value interpretation layer (二次解析): raw value -> human-readable meaning
  e.g., 0x00 -> "普通日期", timestamp -> "2025年06月30日14时36分00秒"
"""

import struct
import re
from datetime import datetime
from typing import Dict, Any, Tuple, List, Optional


# ============================================================
# Protocol Configuration (FILL IN from user's protocol rules)
# ============================================================

SERIAL_CONFIG = {
    # Frame structure
    "header": bytes([0x55, 0xAA]),       # Frame header bytes
    "footer": None,                       # Frame footer bytes or None
    "has_footer": False,

    # Length field
    "length_field_offset": 2,             # Offset from frame start (after header)
    "length_field_width": 1,              # 1 or 2 bytes
    "length_endianness": "little",        # "little" or "big"
    "length_includes_header": False,      # Does length include header bytes?
    "length_includes_checksum": False,    # Does length include checksum bytes?
    "length_includes_footer": False,      # Does length include footer bytes?
    "length_includes_length_field": False,# Does length include the length field itself?

    # Command/type field
    "cmd_field_offset": 2,                # Offset from frame start
    "cmd_field_width": 1,                 # 1 or 2 bytes

    # Checksum
    "checksum_type": "crc16_modbus",      # None, "xor", "sum8", "crc8", "crc16_modbus",
                                          # "crc16_ccitt", "crc32"
    "checksum_width": 2,                  # 1 or 2 or 4 bytes
    "checksum_endianness": "little",      # "little" or "big"
    "checksum_start_offset": 0,           # Start offset for checksum computation
    # checksum_end_offset is computed dynamically (end of payload, before checksum)

    # Payload fields (list of field definitions)
    # Each: name, offset (from payload start), format (struct format char), size, description
    # NEW FIELDS (v2):
    #   - description:        字段描述 (Chinese) e.g. "设备状态"
    #   - value_descriptions:  值映射字典 {"00": "正常", "01": "故障", ...}
    #   - interpret_type:     特殊类型: None|"enum"|"timestamp"|"date"|"time"|"bcd"
    "payload_fields": [
        # Example (REPLACE with actual fields):
        # {"name": "device_id", "offset": 0, "format": "B", "size": 1,
        #  "description": "设备ID", "value_descriptions": {}, "interpret_type": None},
        # {"name": "status", "offset": 1, "format": "B", "size": 1,
        #  "description": "设备状态",
        #  "value_descriptions": {"0": "正常", "1": "故障", "2": "离线"},
        #  "interpret_type": "enum"},
        # TODO: Add all payload fields from protocol specification
    ],
}


# ============================================================
# Exception Classes
# ============================================================

class SerialFrameError(Exception):
    """Base exception for serial frame errors."""
    pass


class SerialHeaderError(SerialFrameError):
    """Frame header mismatch."""
    pass


class SerialFooterError(SerialFrameError):
    """Frame footer mismatch."""
    pass


class SerialLengthError(SerialFrameError):
    """Frame length field invalid or inconsistent."""
    pass


class SerialChecksumError(SerialFrameError):
    """Checksum verification failed."""
    pass


class SerialFieldError(SerialFrameError):
    """Error parsing/packing a specific field."""
    pass


# ============================================================
# Checksum Utilities (inline implementations, no third-party)
# ============================================================

def _xor_checksum(data: bytes) -> int:
    """Compute XOR checksum of all bytes."""
    result = 0
    for b in data:
        result ^= b
    return result


def _sum8_checksum(data: bytes) -> int:
    """Compute sum8 checksum (sum of all bytes mod 256)."""
    return sum(data) & 0xFF


def _crc8_checksum(data: bytes, polynomial: int = 0x07, init: int = 0x00) -> int:
    """Compute CRC8 checksum."""
    crc = init
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ polynomial) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def _crc16_modbus(data: bytes) -> int:
    """Compute CRC16-Modbus checksum (polynomial 0xA001, init 0xFFFF)."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def _crc16_ccitt(data: bytes, init: int = 0xFFFF) -> int:
    """Compute CRC16-CCITT checksum (polynomial 0x1021)."""
    crc = init
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def _compute_checksum(data: bytes) -> int:
    """Compute checksum based on configured checksum type."""
    ck_type = SERIAL_CONFIG["checksum_type"]
    if ck_type == "xor":
        return _xor_checksum(data)
    elif ck_type == "sum8":
        return _sum8_checksum(data)
    elif ck_type == "crc8":
        return _crc8_checksum(data)
    elif ck_type == "crc16_modbus":
        return _crc16_modbus(data)
    elif ck_type == "crc16_ccitt":
        return _crc16_ccitt(data)
    elif ck_type is None:
        return 0
    else:
        raise SerialChecksumError(f"Unknown checksum type: {ck_type}")


def _pack_checksum(value: int) -> bytes:
    """Pack checksum value into bytes based on width and endianness."""
    width = SERIAL_CONFIG["checksum_width"]
    endian = SERIAL_CONFIG["checksum_endianness"]
    fmt = "<" if endian == "little" else ">"
    if width == 1:
        return struct.pack(f"{fmt}B", value & 0xFF)
    elif width == 2:
        return struct.pack(f"{fmt}H", value & 0xFFFF)
    elif width == 4:
        return struct.pack(f"{fmt}I", value & 0xFFFFFFFF)
    else:
        raise SerialChecksumError(f"Invalid checksum width: {width}")


def _unpack_checksum(data: bytes) -> int:
    """Unpack checksum from bytes."""
    width = SERIAL_CONFIG["checksum_width"]
    endian = SERIAL_CONFIG["checksum_endianness"]
    fmt = "<" if endian == "little" else ">"
    if width == 1:
        return struct.unpack(f"{fmt}B", data)[0]
    elif width == 2:
        return struct.unpack(f"{fmt}H", data)[0]
    elif width == 4:
        return struct.unpack(f"{fmt}I", data)[0]
    else:
        raise SerialChecksumError(f"Invalid checksum width: {width}")


# ============================================================
# Value Interpretation Layer (二次解析)
# ============================================================

def _interpret_serial_value(raw_value: int, field: Dict[str, Any]) -> str:
    """Convert raw value to human-readable string for serial fields."""
    interpret_type = field.get("interpret_type")
    value_descs = field.get("value_descriptions", {})
    scale = field.get("scale", 1.0)
    offset_val = field.get("offset_val", 0)
    physical = raw_value * scale + offset_val

    if interpret_type == "timestamp":
        try:
            if physical > 1e9:
                dt = datetime.fromtimestamp(physical)
                return dt.strftime("%Y年%m月%d日%H时%M分%S秒")
        except (ValueError, OSError):
            pass
        return f"{physical}"

    if interpret_type == "date":
        try:
            val = int(raw_value)
            if val > 100000:
                return f"{val//10000:04d}年{(val//100)%100:02d}月{val%100:02d}日"
        except (ValueError, TypeError):
            pass
        return f"{physical}"

    if interpret_type == "time":
        try:
            val = int(raw_value)
            if val >= 0:
                return f"{(val//10000)%100:02d}时{(val//100)%100:02d}分{val%100:02d}秒"
        except (ValueError, TypeError):
            pass
        return f"{physical}"

    # Enum lookup
    if value_descs:
        for key in [format(raw_value, 'x'), format(raw_value, 'X'), str(raw_value)]:
            if key in value_descs:
                return value_descs[key]
        return f"{int(physical)} (枚举:无匹配)"

    result = f"{physical}"
    if scale != 1.0 or offset_val != 0:
        result = f"{physical}"
    return result


def _build_field_label(field: Dict[str, Any]) -> str:
    """Build display label combining name and description."""
    name = field["name"]
    desc = field.get("description", "")
    if desc:
        return f"{name} ({desc})"
    return name


# ============================================================
# Unpack Function (hex string -> business dictionary)
# ============================================================

def unpack_frame(hex_str: str) -> dict:
    """Unpack serial protocol hexadecimal message into business dictionary.

    Args:
        hex_str: Hexadecimal string (e.g., "55AA0101..." for a serial frame)

    Returns:
        Dictionary with field names as keys and parsed values.

    Raises:
        SerialHeaderError: If frame header doesn't match.
        SerialFooterError: If frame footer doesn't match.
        SerialLengthError: If length field is invalid.
        SerialChecksumError: If checksum verification fails.
        SerialFieldError: If a field can't be parsed.
    """
    # Clean hex string
    hex_str = hex_str.replace(" ", "").replace("0x", "").replace("0X", "")

    try:
        data = bytes.fromhex(hex_str)
    except ValueError as e:
        raise SerialFrameError(f"Invalid hex string: {e}")

    # --- Verify Header ---
    header = SERIAL_CONFIG["header"]
    if len(data) < len(header):
        raise SerialHeaderError(f"Frame too short: {len(data)} bytes, header is {len(header)} bytes")
    if data[:len(header)] != header:
        raise SerialHeaderError(
            f"Header mismatch: expected {header.hex().upper()}, got {data[:len(header)].hex().upper()}"
        )

    # --- Parse Length Field ---
    len_offset = SERIAL_CONFIG["length_field_offset"]
    len_width = SERIAL_CONFIG["length_field_width"]
    len_endian = SERIAL_CONFIG["length_endianness"]

    if len_offset + len_width > len(data):
        raise SerialLengthError("Frame too short to contain length field")

    len_fmt = "<" if len_endian == "little" else ">"
    if len_width == 1:
        length_value = struct.unpack(f"{len_fmt}B", data[len_offset:len_offset+1])[0]
    elif len_width == 2:
        length_value = struct.unpack(f"{len_fmt}H", data[len_offset:len_offset+2])[0]
    else:
        raise SerialLengthError(f"Unsupported length field width: {len_width}")

    # Calculate expected total frame length
    total_frame_len = length_value
    if not SERIAL_CONFIG["length_includes_header"]:
        total_frame_len += len(header)
    if not SERIAL_CONFIG["length_includes_length_field"]:
        total_frame_len += len_width
    if not SERIAL_CONFIG["length_includes_checksum"]:
        total_frame_len += SERIAL_CONFIG["checksum_width"] if SERIAL_CONFIG["checksum_type"] else 0
    if not SERIAL_CONFIG["length_includes_footer"] and SERIAL_CONFIG["has_footer"]:
        total_frame_len += len(SERIAL_CONFIG["footer"])

    if total_frame_len != len(data):
        raise SerialLengthError(
            f"Length mismatch: length field says {length_value}, "
            f"computed total {total_frame_len}, actual frame {len(data)} bytes"
        )

    # --- Parse Command Field ---
    cmd_offset = SERIAL_CONFIG["cmd_field_offset"]
    cmd_width = SERIAL_CONFIG["cmd_field_width"]
    if cmd_width == 1:
        cmd_value = data[cmd_offset]
    elif cmd_width == 2:
        cmd_value = struct.unpack(f"{len_endian}H", data[cmd_offset:cmd_offset+2])[0]

    # --- Verify Checksum ---
    if SERIAL_CONFIG["checksum_type"] is not None:
        ck_width = SERIAL_CONFIG["checksum_width"]
        ck_start = SERIAL_CONFIG["checksum_start_offset"]
        ck_end = len(data) - ck_width
        if SERIAL_CONFIG["has_footer"]:
            ck_end -= len(SERIAL_CONFIG["footer"])

        # Extract received checksum
        ck_bytes = data[ck_end:ck_end + ck_width]
        received_ck = _unpack_checksum(ck_bytes)

        # Compute expected checksum
        computed_ck = _compute_checksum(data[ck_start:ck_end])

        if received_ck != computed_ck:
            raise SerialChecksumError(
                f"Checksum mismatch: received 0x{received_ck:04X}, computed 0x{computed_ck:04X}"
            )

    # --- Verify Footer ---
    if SERIAL_CONFIG["has_footer"]:
        footer = SERIAL_CONFIG["footer"]
        if data[-len(footer):] != footer:
            raise SerialFooterError(
                f"Footer mismatch: expected {footer.hex().upper()}, "
                f"got {data[-len(footer):].hex().upper()}"
            )

    # --- Parse Payload Fields ---
    # Payload starts after header + length field + command field
    payload_start = len(header) + len_width + cmd_width
    # Payload ends before checksum (and footer if present)
    payload_end = len(data)
    if SERIAL_CONFIG["checksum_type"] is not None:
        payload_end -= SERIAL_CONFIG["checksum_width"]
    if SERIAL_CONFIG["has_footer"]:
        payload_end -= len(SERIAL_CONFIG["footer"])

    payload = data[payload_start:payload_end]

    result = {
        "command": cmd_value,
        "length": length_value,
        "payload_raw": payload.hex().upper(),
    }

    interpreted = {}  # 二次解析结果

    for field in SERIAL_CONFIG["payload_fields"]:
        name = field["name"]
        offset = field["offset"]
        fmt = field["format"]
        size = field["size"]
        scale = field.get("scale", 1.0)
        offset_val = field.get("offset_val", 0)

        if offset + size > len(payload):
            raise SerialFieldError(
                f"Field '{name}' extends beyond payload: "
                f"offset={offset}, size={size}, payload_length={len(payload)}"
            )

        endian_fmt = "<" if SERIAL_CONFIG.get("payload_endianness", "little") == "little" else ">"
        raw_value = struct.unpack(f"{endian_fmt}{fmt}", payload[offset:offset+size])[0]

        physical_value = raw_value * scale + offset_val
        if scale == 1.0 and offset_val == 0:
            result[name] = int(physical_value)
        else:
            result[name] = physical_value

        # 二次解析
        label = _build_field_label(field)
        interpreted[label] = _interpret_serial_value(raw_value, field)

    result["_hex"] = hex_str.upper()
    result["_interpreted"] = interpreted
    return result


# ============================================================
# Pretty Print Display (美化显示)
# ============================================================

def pretty_print(result: dict) -> str:
    """Format unpack result as human-readable multi-line string."""
    lines = []
    interpreted = result.get("_interpreted", {})

    lines.append("╔" + "═" * 68 + "╗")
    lines.append(f"║  串口帧  |  命令: {result.get('command', '?')}  |  长度: {result.get('length', '?')}")
    lines.append(f"║  数据: {result.get('_hex', '')}")
    lines.append("╠" + "─" * 68 + "╣")
    lines.append("║  字段名                           值           二次解析结果")
    lines.append("╠" + "─" * 68 + "╣")

    for field in SERIAL_CONFIG["payload_fields"]:
        name = field["name"]
        label = _build_field_label(field)
        val = result.get(name, "?")
        interp_val = interpreted.get(label, "-")

        val_str = f"{val}" if not isinstance(val, float) or val == int(val) else f"{val:.4f}"
        display_label = label[:32] if len(label) > 32 else label
        lines.append(f"║  {display_label:<33s} {val_str:<12s} {interp_val}")

    lines.append("╚" + "═" * 68 + "╝")
    return "\n".join(lines)


def print_result(hex_str: str) -> dict:
    """Convenience function: unpack and pretty-print."""
    result = unpack_frame(hex_str)
    print(pretty_print(result))
    return result


# ============================================================
# Pack Function (business dictionary -> hex string)
# ============================================================

def pack_frame(data_dict: dict) -> str:
    """Pack business dictionary into serial protocol hexadecimal message.

    Args:
        data_dict: Dictionary with field names and values.

    Returns:
        Hexadecimal string representing the serial frame.

    Raises:
        SerialFieldError: If a field can't be packed.
        SerialLengthError: If computed length is invalid.
    """
    header = SERIAL_CONFIG["header"]
    len_width = SERIAL_CONFIG["length_field_width"]
    cmd_width = SERIAL_CONFIG["cmd_field_width"]
    len_endian = SERIAL_CONFIG["length_endianness"]

    # --- Pack Command Field ---
    cmd_value = data_dict.get("command", 0)
    if cmd_width == 1:
        cmd_bytes = struct.pack("B", cmd_value & 0xFF)
    elif cmd_width == 2:
        cmd_bytes = struct.pack(f"{'<' if len_endian == 'little' else '>'}H", cmd_value & 0xFFFF)

    # --- Pack Payload ---
    # First pass: determine payload size
    payload_size = 0
    for field in SERIAL_CONFIG["payload_fields"]:
        end = field["offset"] + field["size"]
        if end > payload_size:
            payload_size = end

    payload = bytearray(payload_size)

    endian_fmt = "<" if SERIAL_CONFIG.get("payload_endianness", "little") == "little" else ">"
    for field in SERIAL_CONFIG["payload_fields"]:
        name = field["name"]
        offset = field["offset"]
        fmt = field["format"]
        size = field["size"]
        scale = field.get("scale", 1.0)
        offset_val = field.get("offset_val", 0)

        if name not in data_dict:
            raise SerialFieldError(f"Field '{name}' missing from input dictionary")

        physical_value = data_dict[name]
        raw_value = int(round((physical_value - offset_val) / scale))

        packed = struct.pack(f"{endian_fmt}{fmt}", raw_value)
        payload[offset:offset+size] = packed

    # --- Compute Length Field ---
    # Length value depends on what it includes
    length_value = 0
    if SERIAL_CONFIG["length_includes_header"]:
        length_value += len(header)
    if SERIAL_CONFIG["length_includes_length_field"]:
        length_value += len_width
    length_value += cmd_width  # Command always included
    length_value += len(payload)
    if SERIAL_CONFIG["length_includes_checksum"] and SERIAL_CONFIG["checksum_type"]:
        length_value += SERIAL_CONFIG["checksum_width"]
    if SERIAL_CONFIG["length_includes_footer"] and SERIAL_CONFIG["has_footer"]:
        length_value += len(SERIAL_CONFIG["footer"])

    if len_width == 1:
        if length_value > 255:
            raise SerialLengthError(f"Length {length_value} exceeds 1-byte range")
        len_bytes = struct.pack("B", length_value)
    elif len_width == 2:
        len_bytes = struct.pack(f"{'<' if len_endian == 'little' else '>'}H", length_value)

    # --- Assemble Frame ---
    frame = bytearray()
    frame.extend(header)
    frame.extend(len_bytes)
    frame.extend(cmd_bytes)
    frame.extend(payload)

    # --- Compute and Append Checksum ---
    if SERIAL_CONFIG["checksum_type"] is not None:
        ck_start = SERIAL_CONFIG["checksum_start_offset"]
        computed_ck = _compute_checksum(frame[ck_start:])
        frame.extend(_pack_checksum(computed_ck))

    # --- Append Footer ---
    if SERIAL_CONFIG["has_footer"]:
        frame.extend(SERIAL_CONFIG["footer"])

    return frame.hex().upper()


# ============================================================
# Automated Test Cases (FILL IN with user's test example)
# ============================================================

def run_tests():
    """Run automated bidirectional tests."""
    # TODO: Replace with user's test data
    test_raw_hex = ""  # e.g., "55AA0101..."
    test_expected = {}  # e.g., {"command": 1, "temperature": 25.6}

    if not test_raw_hex or not test_expected:
        print("[SKIP] No test data provided. Fill in test_raw_hex and test_expected.")
        return

    print("=" * 60)
    print("Serial Protocol Bidirectional Test")
    print("=" * 60)

    all_passed = True

    # --- Forward Test ---
    print("\n[Forward] Raw hex -> unpack -> expected dict")
    print(f"  Input hex:     {test_raw_hex}")
    try:
        result = unpack_frame(test_raw_hex)
        result_clean = {k: v for k, v in result.items() if not k.startswith("_") and k != "payload_raw"}
        print(f"  Unpacked dict: {result_clean}")
        print(f"  Expected dict: {test_expected}")

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
    except Exception as e:
        print(f"  [ERROR] unpack_frame failed: {e}")
        all_passed = False

    # --- Reverse Test ---
    print("\n[Reverse] Expected dict -> pack -> raw hex")
    print(f"  Input dict: {test_expected}")
    try:
        packed_hex = pack_frame(test_expected)
        print(f"  Packed hex: {packed_hex}")
        print(f"  Expected:   {test_raw_hex.upper().replace(' ', '')}")

        if packed_hex == test_raw_hex.upper().replace(" ", ""):
            print("  [PASS] Hex match!")
        else:
            print("  [FAIL] Hex mismatch!")
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
