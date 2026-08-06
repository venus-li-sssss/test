#!/usr/bin/env python3
"""
CRC & Checksum Utility Library
===============================
Pure Python standard library implementation of common CRC and checksum algorithms
used in CAN, serial, and MQTT communication protocols.

Usage:
    from crc_utils import crc16_modbus, crc8, xor_checksum
    checksum = crc16_modbus(data_bytes)

Or run directly to see self-test results:
    python crc_utils.py
"""

import struct
from typing import Union


# ============================================================
# XOR Checksum
# ============================================================

def xor_checksum(data: Union[bytes, bytearray]) -> int:
    """Compute XOR checksum of all bytes.

    Args:
        data: Input bytes

    Returns:
        Single-byte XOR checksum (0x00 - 0xFF)
    """
    result = 0
    for b in data:
        result ^= b
    return result & 0xFF


# ============================================================
# Sum Checksums
# ============================================================

def sum8_checksum(data: Union[bytes, bytearray]) -> int:
    """Compute Sum8 checksum (sum of all bytes mod 256).

    Args:
        data: Input bytes

    Returns:
        Single-byte sum checksum (0x00 - 0xFF)
    """
    return sum(data) & 0xFF


def sum16_checksum(data: Union[bytes, bytearray]) -> int:
    """Compute Sum16 checksum (sum of all bytes mod 65536).

    Args:
        data: Input bytes

    Returns:
        Two-byte sum checksum (0x0000 - 0xFFFF)
    """
    return sum(data) & 0xFFFF


# ============================================================
# CRC-8 Variants
# ============================================================

def crc8(data: Union[bytes, bytearray],
         polynomial: int = 0x07,
         init_value: int = 0x00,
         reflect_input: bool = False,
         reflect_output: bool = False,
         xor_output: int = 0x00) -> int:
    """Compute CRC-8 checksum with configurable parameters.

    Args:
        data: Input bytes
        polynomial: CRC polynomial (default 0x07 for CRC-8/SMBUS)
        init_value: Initial CRC value (default 0x00)
        reflect_input: Reflect input bytes (LSB first)
        reflect_output: Reflect output CRC
        xor_output: XOR value applied to final CRC (default 0x00)

    Returns:
        CRC-8 checksum (0x00 - 0xFF)
    """
    def reflect(byte, width):
        result = 0
        for i in range(width):
            if byte & (1 << i):
                result |= (1 << (width - 1 - i))
        return result

    crc = init_value
    for byte in data:
        if reflect_input:
            byte = reflect(byte, 8)
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ polynomial) & 0xFF
            else:
                crc = (crc << 1) & 0xFF

    if reflect_output:
        crc = reflect(crc, 8)

    return (crc ^ xor_output) & 0xFF


def crc8_smbus(data: Union[bytes, bytearray]) -> int:
    """CRC-8/SMBUS: poly=0x07, init=0x00, no reflection, no xor_out."""
    return crc8(data, polynomial=0x07, init_value=0x00)


def crc8_maxim(data: Union[bytes, bytearray]) -> int:
    """CRC-8/MAXIM (Dallas): poly=0x31, init=0x00, reflected."""
    return crc8(data, polynomial=0x31, init_value=0x00,
                reflect_input=True, reflect_output=True)


# ============================================================
# CRC-16 Variants
# ============================================================

def crc16(data: Union[bytes, bytearray],
          polynomial: int = 0x1021,
          init_value: int = 0xFFFF,
          reflect_input: bool = False,
          reflect_output: bool = False,
          xor_output: int = 0x0000) -> int:
    """Compute CRC-16 checksum with configurable parameters.

    Args:
        data: Input bytes
        polynomial: CRC polynomial (default 0x1021 for CCITT)
        init_value: Initial CRC value (default 0xFFFF)
        reflect_input: Reflect input bytes (LSB first)
        reflect_output: Reflect output CRC
        xor_output: XOR value applied to final CRC (default 0x0000)

    Returns:
        CRC-16 checksum (0x0000 - 0xFFFF)
    """
    def reflect(value, width):
        result = 0
        for i in range(width):
            if value & (1 << i):
                result |= (1 << (width - 1 - i))
        return result

    crc = init_value
    for byte in data:
        if reflect_input:
            byte = reflect(byte, 8)
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ polynomial) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF

    if reflect_output:
        crc = reflect(crc, 16)

    return (crc ^ xor_output) & 0xFFFF


def crc16_modbus(data: Union[bytes, bytearray]) -> int:
    """CRC-16/Modbus: poly=0x8005, init=0xFFFF,
    reflected input/output, no xor_out.

    Result is stored little-endian in Modbus frames.
    """
    return crc16(data, polynomial=0x8005, init_value=0xFFFF,
                 reflect_input=True, reflect_output=True)


def crc16_ccitt(data: Union[bytes, bytearray]) -> int:
    """CRC-16/CCITT-FALSE: poly=0x1021, init=0xFFFF,
    no reflection, no xor_out.

    Result is stored big-endian in frames.
    """
    return crc16(data, polynomial=0x1021, init_value=0xFFFF)


def crc16_xmodem(data: Union[bytes, bytearray]) -> int:
    """CRC-16/XMODEM: poly=0x1021, init=0x0000,
    no reflection, no xor_out.
    """
    return crc16(data, polynomial=0x1021, init_value=0x0000)


def crc16_kermit(data: Union[bytes, bytearray]) -> int:
    """CRC-16/KERMIT: poly=0x1021, init=0x0000,
    reflected input/output, no xor_out.
    """
    return crc16(data, polynomial=0x1021, init_value=0x0000,
                 reflect_input=True, reflect_output=True)


def crc16_ibm(data: Union[bytes, bytearray]) -> int:
    """CRC-16/IBM (ARC): poly=0x8005, init=0x0000,
    reflected input/output, no xor_out.
    """
    return crc16(data, polynomial=0x8005, init_value=0x0000,
                 reflect_input=True, reflect_output=True)


# ============================================================
# CRC-32
# ============================================================

_crc32_table = None


def _build_crc32_table() -> list:
    """Build CRC-32 lookup table."""
    table = []
    for i in range(256):
        crc = i
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xEDB88320
            else:
                crc >>= 1
        table.append(crc)
    return table


def crc32(data: Union[bytes, bytearray]) -> int:
    """Compute CRC-32 checksum (IEEE 802.3, same as zlib.crc32).

    Args:
        data: Input bytes

    Returns:
        CRC-32 checksum (0x00000000 - 0xFFFFFFFF)
    """
    global _crc32_table
    if _crc32_table is None:
        _crc32_table = _build_crc32_table()

    crc = 0xFFFFFFFF
    for byte in data:
        crc = _crc32_table[(crc ^ byte) & 0xFF] ^ (crc >> 8)
    return crc ^ 0xFFFFFFFF


# ============================================================
# Convenience: Pack checksum into bytes
# ============================================================

def pack_checksum(value: int, width: int, endianness: str = "little") -> bytes:
    """Pack a checksum value into bytes.

    Args:
        value: Checksum integer value
        width: Number of bytes (1, 2, or 4)
        endianness: "little" or "big"

    Returns:
        Packed bytes
    """
    fmt = "<" if endianness == "little" else ">"
    if width == 1:
        return struct.pack(f"{fmt}B", value & 0xFF)
    elif width == 2:
        return struct.pack(f"{fmt}H", value & 0xFFFF)
    elif width == 4:
        return struct.pack(f"{fmt}I", value & 0xFFFFFFFF)
    else:
        raise ValueError(f"Invalid checksum width: {width}")


# ============================================================
# Self-Test
# ============================================================

def _self_test():
    """Run self-tests with known test vectors."""
    print("=" * 60)
    print("CRC & Checksum Self-Test")
    print("=" * 60)

    test_data = b"123456789"
    all_passed = True

    tests = [
        ("XOR", xor_checksum(test_data), 0x31),
        ("Sum8", sum8_checksum(test_data), 0xDD),
        ("CRC-8/SMBUS", crc8_smbus(test_data), 0xF4),
        ("CRC-8/MAXIM", crc8_maxim(test_data), 0xA1),
        ("CRC-16/Modbus", crc16_modbus(test_data), 0x4B37),
        ("CRC-16/CCITT-FALSE", crc16_ccitt(test_data), 0x29B1),
        ("CRC-16/XMODEM", crc16_xmodem(test_data), 0x31C3),
        ("CRC-16/KERMIT", crc16_kermit(test_data), 0x2189),
        ("CRC-32", crc32(test_data), 0xCBF43926),
    ]

    for name, computed, expected in tests:
        status = "PASS" if computed == expected else "FAIL"
        if status == "FAIL":
            all_passed = False
        print(f"  [{status}] {name}: computed=0x{computed:08X}, expected=0x{expected:08X}")

    print("=" * 60)
    print(f"RESULT: {'ALL PASSED' if all_passed else 'SOME FAILED'}")
    print("=" * 60)
    return all_passed


if __name__ == "__main__":
    _self_test()
