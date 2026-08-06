#!/usr/bin/env python3
"""
MQTT Protocol Pack/Unpack Template
===================================
Template for MQTT protocol message pack/unpack operations.
Supports MQTT 3.1.1 packet types and custom payload sub-protocols.

Only uses Python standard library: struct, binascii, typing

Features:
- Bidirectional pack/unpack for all MQTT packet types
- Field descriptions in output (for custom payload)
- Value interpretation layer (二次解析): raw value -> human-readable meaning
"""

import struct
import re
from datetime import datetime
from typing import Dict, Any, Tuple, Optional, List


# ============================================================
# Protocol Configuration (FILL IN from user's protocol rules)
# ============================================================

MQTT_CONFIG = {
    "mqtt_version": 4,           # 4 = MQTT 3.1.1, 5 = MQTT 5.0

    # Custom payload sub-protocol (for PUBLISH payload parsing)
    # If the PUBLISH payload is a custom binary format, define fields here
    "has_custom_payload": False,
    "payload_fields": [
        # Example (REPLACE with actual payload field definitions):
        # {"name": "device_id", "offset": 0, "format": "B", "size": 1,
        #  "description": "设备ID", "value_descriptions": {}, "interpret_type": None},
        # {"name": "timestamp", "offset": 5, "format": "I", "size": 4,
        #  "description": "时间戳", "interpret_type": "timestamp"},
        # TODO: Add all payload fields if custom payload format is used
    ],
    "payload_endianness": "big",  # MQTT uses big endian by default

    # Topic parsing rules (if topics have structured format)
    "topic_format": None,  # e.g., "device/{device_id}/sensor/{sensor_type}"
}


# ============================================================
# Exception Classes
# ============================================================

class MQTTError(Exception):
    """Base exception for MQTT errors."""
    pass


class MQTTPacketTypeError(MQTTError):
    """Invalid or unknown MQTT packet type."""
    pass


class MQTTLengthError(MQTTError):
    """Invalid remaining length encoding."""
    pass


class MQTTFieldError(MQTTError):
    """Error parsing/packing a specific field."""
    pass


# ============================================================
# MQTT Packet Type Constants
# ============================================================

PACKET_TYPES = {
    1: "CONNECT",
    2: "CONNACK",
    3: "PUBLISH",
    4: "PUBACK",
    5: "PUBREC",
    6: "PUBREL",
    7: "PUBCOMP",
    8: "SUBSCRIBE",
    9: "SUBACK",
    10: "UNSUBSCRIBE",
    11: "UNSUBACK",
    12: "PINGREQ",
    13: "PINGRESP",
    14: "DISCONNECT",
    15: "AUTH",  # MQTT 5.0 only
}


# ============================================================
# Remaining Length Encode/Decode
# ============================================================

def encode_remaining_length(length: int) -> bytes:
    """Encode MQTT remaining length as variable byte integer.

    Args:
        length: Integer value (0 to 268435455)

    Returns:
        Encoded bytes (1-4 bytes)

    Raises:
        MQTTLengthError: If length is out of valid range.
    """
    if length < 0 or length > 268435455:
        raise MQTTLengthError(f"Invalid remaining length: {length} (must be 0-268435455)")

    encoded = bytearray()
    while True:
        byte = length % 128
        length //= 128
        if length > 0:
            byte |= 0x80
        encoded.append(byte)
        if length == 0:
            break
    return bytes(encoded)


def decode_remaining_length(data: bytes, offset: int = 1) -> Tuple[int, int]:
    """Decode MQTT remaining length from variable byte integer.

    Args:
        data: Raw bytes containing the MQTT packet
        offset: Starting position (default 1, after the fixed header byte)

    Returns:
        Tuple of (remaining_length, bytes_consumed)

    Raises:
        MQTTLengthError: If encoding is malformed or incomplete.
    """
    multiplier = 1
    value = 0
    pos = offset
    bytes_consumed = 0

    while True:
        if pos >= len(data):
            raise MQTTLengthError("Incomplete remaining length field")

        encoded_byte = data[pos]
        value += (encoded_byte & 0x7F) * multiplier
        pos += 1
        bytes_consumed += 1

        if multiplier > 128 * 128 * 128:
            raise MQTTLengthError("Malformed remaining length (too many bytes)")

        if (encoded_byte & 0x80) == 0:
            break
        multiplier *= 128

    return value, bytes_consumed


# ============================================================
# MQTT String Encode/Decode (length-prefixed UTF-8)
# ============================================================

def encode_mqtt_string(s: str) -> bytes:
    """Encode a UTF-8 string with 2-byte big-endian length prefix.

    Args:
        s: String to encode

    Returns:
        2-byte length prefix + UTF-8 encoded string bytes
    """
    encoded = s.encode('utf-8')
    if len(encoded) > 65535:
        raise MQTTFieldError(f"String too long: {len(encoded)} bytes (max 65535)")
    return struct.pack('>H', len(encoded)) + encoded


def decode_mqtt_string(data: bytes, offset: int) -> Tuple[str, int]:
    """Decode a length-prefixed UTF-8 string from MQTT data.

    Args:
        data: Raw bytes
        offset: Starting position

    Returns:
        Tuple of (decoded_string, new_offset)

    Raises:
        MQTTFieldError: If string data is incomplete or invalid UTF-8.
    """
    if offset + 2 > len(data):
        raise MQTTFieldError("Incomplete string length field")

    length = struct.unpack('>H', data[offset:offset+2])[0]
    offset += 2

    if offset + length > len(data):
        raise MQTTFieldError(f"Incomplete string data: need {length} bytes, "
                            f"only {len(data) - offset} available")

    try:
        s = data[offset:offset+length].decode('utf-8')
    except UnicodeDecodeError as e:
        raise MQTTFieldError(f"Invalid UTF-8 string: {e}")

    return s, offset + length


def encode_mqtt_binary(data_bytes: bytes) -> bytes:
    """Encode binary data with 2-byte big-endian length prefix."""
    if len(data_bytes) > 65535:
        raise MQTTFieldError(f"Binary data too long: {len(data_bytes)} bytes (max 65535)")
    return struct.pack('>H', len(data_bytes)) + data_bytes


def decode_mqtt_binary(data: bytes, offset: int) -> Tuple[bytes, int]:
    """Decode length-prefixed binary data from MQTT data."""
    if offset + 2 > len(data):
        raise MQTTFieldError("Incomplete binary length field")

    length = struct.unpack('>H', data[offset:offset+2])[0]
    offset += 2

    if offset + length > len(data):
        raise MQTTFieldError(f"Incomplete binary data: need {length} bytes, "
                            f"only {len(data) - offset} available")

    return data[offset:offset+length], offset + length


# ============================================================
# Value Interpretation Layer (二次解析)
# ============================================================

def _interpret_mqtt_value(raw_value: int, field: Dict[str, Any]) -> str:
    """Convert raw value to human-readable string for MQTT payload fields."""
    interpret_type = field.get("interpret_type")
    value_descs = field.get("value_descriptions", {})

    if interpret_type == "timestamp":
        try:
            if raw_value > 1e9:
                dt = datetime.fromtimestamp(raw_value)
                return dt.strftime("%Y年%m月%d日%H时%M分%S秒")
            elif raw_value > 1e6:
                dt = datetime.fromtimestamp(raw_value / 1000)
                return dt.strftime("%Y年%m月%d日%H时%M分%S秒")
        except (ValueError, OSError):
            pass
        return f"{raw_value}"

    if value_descs:
        for key in [format(raw_value, 'x'), format(raw_value, 'X'), str(raw_value)]:
            if key in value_descs:
                return value_descs[key]
        return f"{raw_value} (枚举:无匹配)"

    return f"{raw_value}"


def _build_payload_label(field: Dict[str, Any]) -> str:
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
    """Unpack MQTT hexadecimal message into business dictionary.

    Args:
        hex_str: Hexadecimal string of the complete MQTT packet

    Returns:
        Dictionary with packet type, fields, and parsed payload.

    Raises:
        MQTTPacketTypeError: If packet type is invalid.
        MQTTLengthError: If remaining length is malformed.
        MQTTFieldError: If a field can't be parsed.
    """
    # Clean hex string
    hex_str = hex_str.replace(" ", "").replace("0x", "").replace("0X", "")

    try:
        data = bytes.fromhex(hex_str)
    except ValueError as e:
        raise MQTTError(f"Invalid hex string: {e}")

    if len(data) < 2:
        raise MQTTError("Frame too short: minimum 2 bytes for MQTT packet")

    # --- Parse Fixed Header ---
    byte1 = data[0]
    packet_type_code = (byte1 >> 4) & 0x0F
    flags = byte1 & 0x0F

    if packet_type_code not in PACKET_TYPES:
        raise MQTTPacketTypeError(f"Unknown packet type: {packet_type_code}")

    packet_type = PACKET_TYPES[packet_type_code]

    # Decode remaining length
    remaining_length, rl_bytes = decode_remaining_length(data, 1)
    var_header_start = 1 + rl_bytes
    var_header_end = var_header_start + remaining_length

    if var_header_end > len(data):
        raise MQTTLengthError(
            f"Remaining length ({remaining_length}) exceeds available data "
            f"({len(data) - var_header_start} bytes)"
        )

    result = {
        "packet_type": packet_type,
        "packet_type_code": packet_type_code,
        "flags": flags,
        "remaining_length": remaining_length,
    }

    # --- Parse by Packet Type ---
    if packet_type == "PUBLISH":
        result.update(_unpack_publish(data, var_header_start, var_header_end, flags))
    elif packet_type == "CONNECT":
        result.update(_unpack_connect(data, var_header_start, var_header_end))
    elif packet_type == "CONNACK":
        result.update(_unpack_connack(data, var_header_start, var_header_end))
    elif packet_type in ("PUBACK", "PUBREC", "PUBREL", "PUBCOMP",
                         "UNSUBACK"):
        result.update(_unpack_packet_id_only(data, var_header_start, var_header_end))
    elif packet_type == "SUBSCRIBE":
        result.update(_unpack_subscribe(data, var_header_start, var_header_end))
    elif packet_type == "SUBACK":
        result.update(_unpack_suback(data, var_header_start, var_header_end))
    elif packet_type in ("PINGREQ", "PINGRESP", "DISCONNECT"):
        pass  # No variable header or payload
    else:
        # Store raw variable header + payload for unsupported types
        result["raw_data"] = data[var_header_start:var_header_end].hex().upper()

    result["_hex"] = hex_str.upper()
    return result


def _unpack_publish(data: bytes, start: int, end: int, flags: int) -> dict:
    """Unpack PUBLISH packet variable header and payload."""
    pos = start
    result = {}

    # Flags
    result["dup"] = (flags >> 3) & 0x01
    result["qos"] = (flags >> 1) & 0x03
    result["retain"] = flags & 0x01

    # Topic Name
    topic, pos = decode_mqtt_string(data, pos)
    result["topic"] = topic

    # Packet Identifier (only for QoS 1 and 2)
    if result["qos"] > 0:
        if pos + 2 > end:
            raise MQTTFieldError("Missing packet ID in PUBLISH (QoS > 0)")
        result["packet_id"] = struct.unpack('>H', data[pos:pos+2])[0]
        pos += 2

    # Payload
    payload = data[pos:end]
    result["payload_length"] = len(payload)

    # Parse custom payload if configured
    if MQTT_CONFIG["has_custom_payload"] and MQTT_CONFIG["payload_fields"]:
        result.update(_unpack_custom_payload(payload))
    else:
        # Try to decode as UTF-8 string, fall back to hex
        try:
            result["payload"] = payload.decode('utf-8')
        except UnicodeDecodeError:
            result["payload"] = payload.hex().upper()

    return result


def _unpack_connect(data: bytes, start: int, end: int) -> dict:
    """Unpack CONNECT packet."""
    pos = start
    result = {}

    # Protocol Name
    proto_name, pos = decode_mqtt_string(data, pos)
    result["protocol_name"] = proto_name

    # Protocol Level
    result["protocol_level"] = data[pos]
    pos += 1

    # Connect Flags
    connect_flags = data[pos]
    pos += 1
    result["username_flag"] = (connect_flags >> 7) & 0x01
    result["password_flag"] = (connect_flags >> 6) & 0x01
    result["will_retain"] = (connect_flags >> 5) & 0x01
    result["will_qos"] = (connect_flags >> 3) & 0x03
    result["will_flag"] = (connect_flags >> 2) & 0x01
    result["clean_session"] = (connect_flags >> 1) & 0x01

    # Keep Alive
    result["keep_alive"] = struct.unpack('>H', data[pos:pos+2])[0]
    pos += 2

    # Payload
    # Client ID
    client_id, pos = decode_mqtt_string(data, pos)
    result["client_id"] = client_id

    # Will Topic and Message
    if result["will_flag"]:
        will_topic, pos = decode_mqtt_string(data, pos)
        result["will_topic"] = will_topic
        will_msg, pos = decode_mqtt_binary(data, pos)
        result["will_message"] = will_msg.hex().upper()

    # Username
    if result["username_flag"]:
        username, pos = decode_mqtt_string(data, pos)
        result["username"] = username

    # Password
    if result["password_flag"]:
        password, pos = decode_mqtt_binary(data, pos)
        result["password"] = password.hex().upper()

    return result


def _unpack_connack(data: bytes, start: int, end: int) -> dict:
    """Unpack CONNACK packet."""
    result = {}
    result["session_present"] = data[start] & 0x01
    result["return_code"] = data[start + 1]

    return_codes = {
        0: "Connection Accepted",
        1: "Unacceptable Protocol Version",
        2: "Identifier Rejected",
        3: "Server Unavailable",
        4: "Bad Username or Password",
        5: "Not Authorized",
    }
    result["return_code_desc"] = return_codes.get(result["return_code"], "Unknown")
    return result


def _unpack_packet_id_only(data: bytes, start: int, end: int) -> dict:
    """Unpack packets that only contain a Packet ID (PUBACK, PUBREC, etc.)."""
    result = {}
    result["packet_id"] = struct.unpack('>H', data[start:start+2])[0]
    return result


def _unpack_subscribe(data: bytes, start: int, end: int) -> dict:
    """Unpack SUBSCRIBE packet."""
    pos = start
    result = {}
    result["packet_id"] = struct.unpack('>H', data[pos:pos+2])[0]
    pos += 2

    topics = []
    while pos < end:
        topic, pos = decode_mqtt_string(data, pos)
        qos = data[pos]
        pos += 1
        topics.append({"topic": topic, "qos": qos})

    result["topics"] = topics
    return result


def _unpack_suback(data: bytes, start: int, end: int) -> dict:
    """Unpack SUBACK packet."""
    pos = start
    result = {}
    result["packet_id"] = struct.unpack('>H', data[pos:pos+2])[0]
    pos += 2

    return_codes = []
    while pos < end:
        return_codes.append(data[pos])
        pos += 1

    result["return_codes"] = return_codes
    return result


def _unpack_custom_payload(payload: bytes) -> dict:
    """Unpack custom binary payload sub-protocol."""
    result = {}
    interpreted = {}  # 二次解析
    endian = "<" if MQTT_CONFIG["payload_endianness"] == "little" else ">"

    for field in MQTT_CONFIG["payload_fields"]:
        name = field["name"]
        offset = field["offset"]
        fmt = field["format"]
        size = field["size"]

        if offset + size > len(payload):
            raise MQTTFieldError(
                f"Payload field '{name}' extends beyond payload: "
                f"offset={offset}, size={size}, payload_length={len(payload)}"
            )

        value = struct.unpack(f"{endian}{fmt}", payload[offset:offset+size])[0]
        result[name] = value

        # 二次解析
        label = _build_payload_label(field)
        interpreted[label] = _interpret_mqtt_value(value, field)

    result["_interpreted"] = interpreted
    return result


# ============================================================
# Pack Function (business dictionary -> hex string)
# ============================================================

def pack_frame(data_dict: dict) -> str:
    """Pack business dictionary into MQTT hexadecimal message.

    Args:
        data_dict: Dictionary with packet type and field values.

    Returns:
        Hexadecimal string representing the MQTT packet.

    Raises:
        MQTTPacketTypeError: If packet type is invalid.
        MQTTFieldError: If a field is missing or invalid.
    """
    packet_type = data_dict.get("packet_type", "").upper()
    if not packet_type:
        raise MQTTPacketTypeError("Missing 'packet_type' in input dictionary")

    # Find packet type code
    type_code = None
    for code, name in PACKET_TYPES.items():
        if name == packet_type:
            type_code = code
            break
    if type_code is None:
        raise MQTTPacketTypeError(f"Unknown packet type: {packet_type}")

    # Build variable header + payload
    if packet_type == "PUBLISH":
        var_header_payload = _pack_publish(data_dict)
        flags = ((data_dict.get("dup", 0) & 0x01) << 3) | \
                ((data_dict.get("qos", 0) & 0x03) << 1) | \
                (data_dict.get("retain", 0) & 0x01)
    elif packet_type == "CONNECT":
        var_header_payload = _pack_connect(data_dict)
        flags = 0
    elif packet_type == "CONNACK":
        var_header_payload = _pack_connack(data_dict)
        flags = 0
    elif packet_type in ("PUBACK", "PUBREC", "PUBREL", "PUBCOMP",
                         "UNSUBACK"):
        var_header_payload = _pack_packet_id_only(data_dict)
        flags = 0x02 if packet_type in ("PUBREL",) else 0
    elif packet_type == "SUBSCRIBE":
        var_header_payload = _pack_subscribe(data_dict)
        flags = 0x02
    elif packet_type == "UNSUBSCRIBE":
        var_header_payload = _pack_unsubscribe(data_dict)
        flags = 0x02
    elif packet_type in ("PINGREQ", "PINGRESP", "DISCONNECT"):
        var_header_payload = b""
        flags = 0
    else:
        raise MQTTPacketTypeError(f"Packing not implemented for: {packet_type}")

    # Build fixed header
    byte1 = (type_code << 4) | (flags & 0x0F)
    remaining_length_bytes = encode_remaining_length(len(var_header_payload))

    frame = bytes([byte1]) + remaining_length_bytes + var_header_payload
    return frame.hex().upper()


def _pack_publish(data_dict: dict) -> bytes:
    """Pack PUBLISH variable header and payload."""
    result = bytearray()

    # Topic Name
    topic = data_dict.get("topic", "")
    if not topic:
        raise MQTTFieldError("Missing 'topic' in PUBLISH data")
    result.extend(encode_mqtt_string(topic))

    # Packet ID (QoS 1 or 2)
    qos = data_dict.get("qos", 0)
    if qos > 0:
        packet_id = data_dict.get("packet_id", 0)
        result.extend(struct.pack('>H', packet_id & 0xFFFF))

    # Payload
    if MQTT_CONFIG["has_custom_payload"] and MQTT_CONFIG["payload_fields"]:
        result.extend(_pack_custom_payload(data_dict))
    else:
        payload = data_dict.get("payload", "")
        if isinstance(payload, str):
            result.extend(payload.encode('utf-8'))
        elif isinstance(payload, bytes):
            result.extend(payload)
        elif isinstance(payload, str) and all(c in "0123456789ABCDEFabcdef" for c in payload):
            result.extend(bytes.fromhex(payload))

    return bytes(result)


def _pack_connect(data_dict: dict) -> bytes:
    """Pack CONNECT variable header and payload."""
    result = bytearray()

    # Protocol Name
    result.extend(encode_mqtt_string("MQTT"))

    # Protocol Level
    result.append(data_dict.get("protocol_level", 4))

    # Connect Flags
    flags = 0
    if data_dict.get("username_flag", 0): flags |= 0x80
    if data_dict.get("password_flag", 0): flags |= 0x40
    if data_dict.get("will_retain", 0): flags |= 0x20
    flags |= (data_dict.get("will_qos", 0) & 0x03) << 3
    if data_dict.get("will_flag", 0): flags |= 0x04
    if data_dict.get("clean_session", 1): flags |= 0x02
    result.append(flags)

    # Keep Alive
    result.extend(struct.pack('>H', data_dict.get("keep_alive", 60)))

    # Payload: Client ID
    result.extend(encode_mqtt_string(data_dict.get("client_id", "")))

    # Will Topic and Message
    if data_dict.get("will_flag", 0):
        result.extend(encode_mqtt_string(data_dict.get("will_topic", "")))
        will_msg = data_dict.get("will_message", "")
        if isinstance(will_msg, str):
            will_bytes = bytes.fromhex(will_msg) if all(c in "0123456789ABCDEFabcdef" for c in will_msg) else will_msg.encode('utf-8')
        else:
            will_bytes = will_msg
        result.extend(encode_mqtt_binary(will_bytes))

    # Username
    if data_dict.get("username_flag", 0):
        result.extend(encode_mqtt_string(data_dict.get("username", "")))

    # Password
    if data_dict.get("password_flag", 0):
        password = data_dict.get("password", "")
        if isinstance(password, str):
            pw_bytes = bytes.fromhex(password) if all(c in "0123456789ABCDEFabcdef" for c in password) else password.encode('utf-8')
        else:
            pw_bytes = password
        result.extend(encode_mqtt_binary(pw_bytes))

    return bytes(result)


def _pack_connack(data_dict: dict) -> bytes:
    """Pack CONNACK variable header."""
    session_present = data_dict.get("session_present", 0) & 0x01
    return_code = data_dict.get("return_code", 0) & 0xFF
    return bytes([session_present, return_code])


def _pack_packet_id_only(data_dict: dict) -> bytes:
    """Pack packets with only a Packet ID."""
    packet_id = data_dict.get("packet_id", 0)
    return struct.pack('>H', packet_id & 0xFFFF)


def _pack_subscribe(data_dict: dict) -> bytes:
    """Pack SUBSCRIBE variable header and payload."""
    result = bytearray()
    result.extend(struct.pack('>H', data_dict.get("packet_id", 0) & 0xFFFF))

    for topic_entry in data_dict.get("topics", []):
        result.extend(encode_mqtt_string(topic_entry["topic"]))
        result.append(topic_entry.get("qos", 0) & 0xFF)

    return bytes(result)


def _pack_unsubscribe(data_dict: dict) -> bytes:
    """Pack UNSUBSCRIBE variable header and payload."""
    result = bytearray()
    result.extend(struct.pack('>H', data_dict.get("packet_id", 0) & 0xFFFF))

    for topic in data_dict.get("topics", []):
        if isinstance(topic, str):
            result.extend(encode_mqtt_string(topic))
        else:
            result.extend(encode_mqtt_string(topic["topic"]))

    return bytes(result)


def _pack_custom_payload(data_dict: dict) -> bytes:
    """Pack custom binary payload sub-protocol."""
    endian = "<" if MQTT_CONFIG["payload_endianness"] == "little" else ">"
    payload = bytearray()

    # Calculate total size
    total_size = 0
    for field in MQTT_CONFIG["payload_fields"]:
        end = field["offset"] + field["size"]
        if end > total_size:
            total_size = end

    payload = bytearray(total_size)

    for field in MQTT_CONFIG["payload_fields"]:
        name = field["name"]
        if name not in data_dict:
            raise MQTTFieldError(f"Field '{name}' missing from input dictionary")
        offset = field["offset"]
        fmt = field["format"]
        size = field["size"]
        value = data_dict[name]
        payload[offset:offset+size] = struct.pack(f"{endian}{fmt}", value)

    return bytes(payload)


# ============================================================
# Automated Test Cases (FILL IN with user's test example)
# ============================================================

def run_tests():
    """Run automated bidirectional tests."""
    # TODO: Replace with user's test data
    test_raw_hex = ""  # e.g., "301000047465737448656C6C6F"
    test_expected = {}  # e.g., {"packet_type": "PUBLISH", "topic": "test", "payload": "Hello"}

    if not test_raw_hex or not test_expected:
        print("[SKIP] No test data provided. Fill in test_raw_hex and test_expected.")
        return

    print("=" * 60)
    print("MQTT Protocol Bidirectional Test")
    print("=" * 60)

    all_passed = True

    # --- Forward Test ---
    print("\n[Forward] Raw hex -> unpack -> expected dict")
    print(f"  Input hex:     {test_raw_hex}")
    try:
        result = unpack_frame(test_raw_hex)
        result_clean = {k: v for k, v in result.items() if not k.startswith("_")}
        print(f"  Unpacked dict: {result_clean}")
        print(f"  Expected dict: {test_expected}")

        for key, expected_val in test_expected.items():
            if key not in result_clean:
                print(f"  [FAIL] Missing field: {key}")
                all_passed = False
            elif result_clean[key] != expected_val:
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
