#!/usr/bin/env python3
"""
Test Framework for Protocol Pack/Unpack Verification
=====================================================
Provides utilities for bidirectional test automation:
- Forward test: raw hex -> unpack -> compare with expected dict
- Reverse test: expected dict -> pack -> compare with original hex
- Diff report generation

Usage:
    from test_framework import run_test, compare_dicts, generate_diff_report
    success = run_test(unpack_func, pack_func, raw_hex, expected_dict)
"""

import struct
from typing import Dict, Any, Callable, Tuple, List


# ============================================================
# Dictionary Comparison
# ============================================================

def compare_dicts(actual: dict, expected: dict,
                  float_tolerance: float = 1e-6) -> Tuple[bool, List[str]]:
    """Compare two dictionaries and return differences.

    Args:
        actual: Actual parsed dictionary
        expected: Expected dictionary
        float_tolerance: Tolerance for floating-point comparisons

    Returns:
        Tuple of (all_match, list_of_differences)
    """
    all_match = True
    differences = []

    # Check all expected keys
    for key, expected_val in expected.items():
        if key not in actual:
            differences.append(f"MISSING: field '{key}' not in actual result")
            all_match = False
            continue

        actual_val = actual[key]

        # Float comparison
        if isinstance(expected_val, float) or isinstance(actual_val, float):
            if abs(float(actual_val) - float(expected_val)) > float_tolerance:
                differences.append(
                    f"VALUE_MISMATCH: '{key}': expected {expected_val}, got {actual_val}"
                )
                all_match = False
        # Exact comparison
        elif actual_val != expected_val:
            differences.append(
                f"VALUE_MISMATCH: '{key}': expected {expected_val}, got {actual_val}"
            )
            all_match = False

    # Check for unexpected extra keys (informational, not a failure)
    for key in actual:
        if key not in expected and not key.startswith("_"):
            differences.append(f"INFO: extra field '{key}' = {actual[key]} in actual (not in expected)")

    return all_match, differences


# ============================================================
# Hex Comparison
# ============================================================

def compare_hex(actual: str, expected: str) -> Tuple[bool, List[str]]:
    """Compare two hex strings byte-by-byte.

    Args:
        actual: Actual hex string
        expected: Expected hex string

    Returns:
        Tuple of (all_match, list_of_differences)
    """
    # Normalize hex strings
    actual_clean = actual.replace(" ", "").replace("0x", "").replace("0X", "").upper()
    expected_clean = expected.replace(" ", "").replace("0x", "").replace("0X", "").upper()

    all_match = True
    differences = []

    if len(actual_clean) != len(expected_clean):
        differences.append(
            f"LENGTH_MISMATCH: actual={len(actual_clean)//2} bytes "
            f"({actual_clean}), expected={len(expected_clean)//2} bytes ({expected_clean})"
        )
        all_match = False
    else:
        for i in range(0, len(actual_clean), 2):
            byte_idx = i // 2
            actual_byte = actual_clean[i:i+2]
            expected_byte = expected_clean[i:i+2]
            if actual_byte != expected_byte:
                differences.append(
                    f"BYTE_MISMATCH at offset {byte_idx}: "
                    f"got 0x{actual_byte}, expected 0x{expected_byte}"
                )
                all_match = False

    return all_match, differences


# ============================================================
# Diff Report Generation
# ============================================================

def generate_diff_report(differences: List[str], context: str = "") -> str:
    """Generate a formatted diff report.

    Args:
        differences: List of difference strings
        context: Optional context label

    Returns:
        Formatted report string
    """
    lines = []
    lines.append("=" * 60)
    if context:
        lines.append(f"Diff Report: {context}")
        lines.append("-" * 60)
    if not differences:
        lines.append("No differences found. All fields match.")
    else:
        lines.append(f"Found {len(differences)} difference(s):")
        for diff in differences:
            # Categorize
            if diff.startswith("MISSING"):
                lines.append(f"  [MISSING] {diff}")
            elif diff.startswith("VALUE_MISMATCH"):
                lines.append(f"  [VALUE]   {diff}")
            elif diff.startswith("LENGTH_MISMATCH"):
                lines.append(f"  [LENGTH]  {diff}")
            elif diff.startswith("BYTE_MISMATCH"):
                lines.append(f"  [BYTE]    {diff}")
            elif diff.startswith("INFO"):
                lines.append(f"  [INFO]    {diff}")
            else:
                lines.append(f"  [?]       {diff}")
    lines.append("=" * 60)
    return "\n".join(lines)


# ============================================================
# Full Bidirectional Test Runner
# ============================================================

def run_test(unpack_func: Callable[[str], dict],
             pack_func: Callable[[dict], str],
             raw_hex: str,
             expected_dict: dict,
             protocol_name: str = "Protocol") -> bool:
    """Run a complete bidirectional test.

    Forward:  raw_hex -> unpack_func() -> compare with expected_dict
    Reverse:  expected_dict -> pack_func() -> compare with raw_hex

    Args:
        unpack_func: The unpack_frame function
        pack_func: The pack_frame function
        raw_hex: Original raw hex string
        expected_dict: Expected parsing result dictionary
        protocol_name: Name for display (e.g., "CAN", "Serial", "MQTT")

    Returns:
        True if both forward and reverse tests pass, False otherwise
    """
    print("=" * 60)
    print(f"{protocol_name} Protocol Bidirectional Test")
    print("=" * 60)

    all_passed = True

    # ==================== Forward Test ====================
    print(f"\n[Forward] Raw hex -> unpack -> expected dict")
    print(f"  Input hex:  {raw_hex}")

    forward_pass = False
    try:
        result = unpack_func(raw_hex)
        # Clean internal fields for comparison
        result_clean = {k: v for k, v in result.items() if not k.startswith("_")}
        print(f"  Parsed:     {result_clean}")
        print(f"  Expected:   {expected_dict}")

        match, diffs = compare_dicts(result_clean, expected_dict)
        if match:
            print("  [PASS] All fields match!")
            forward_pass = True
        else:
            print(generate_diff_report(diffs, "Forward Test"))
    except Exception as e:
        print(f"  [ERROR] unpack_frame raised exception: {e}")
        import traceback
        traceback.print_exc()

    if not forward_pass:
        all_passed = False

    # ==================== Reverse Test ====================
    print(f"\n[Reverse] Expected dict -> pack -> raw hex")
    print(f"  Input dict: {expected_dict}")

    reverse_pass = False
    try:
        packed_hex = pack_func(expected_dict)
        print(f"  Packed hex: {packed_hex}")
        print(f"  Expected:   {raw_hex}")

        match, diffs = compare_hex(packed_hex, raw_hex)
        if match:
            print("  [PASS] Hex match!")
            reverse_pass = True
        else:
            print(generate_diff_report(diffs, "Reverse Test"))
    except Exception as e:
        print(f"  [ERROR] pack_frame raised exception: {e}")
        import traceback
        traceback.print_exc()

    if not reverse_pass:
        all_passed = False

    # ==================== Summary ====================
    print("\n" + "=" * 60)
    forward_str = "PASS" if forward_pass else "FAIL"
    reverse_str = "PASS" if reverse_pass else "FAIL"
    print(f"Forward (unpack): [{forward_str}]")
    print(f"Reverse (pack):   [{reverse_str}]")

    if all_passed:
        print("RESULT: ALL TESTS PASSED - Bidirectional verification OK")
        print("Script is ready for production engineering use.")
    else:
        print("RESULT: TESTS FAILED - See errors above for details")
    print("=" * 60)

    return all_passed


# ============================================================
# Batch Test Runner
# ============================================================

def run_batch_tests(unpack_func: Callable[[str], dict],
                    pack_func: Callable[[dict], str],
                    test_cases: List[Tuple[str, dict]],
                    protocol_name: str = "Protocol") -> bool:
    """Run multiple test cases.

    Args:
        unpack_func: The unpack_frame function
        pack_func: The pack_frame function
        test_cases: List of (raw_hex, expected_dict) tuples
        protocol_name: Name for display

    Returns:
        True if all test cases pass
    """
    all_passed = True
    for i, (raw_hex, expected) in enumerate(test_cases):
        print(f"\n{'#' * 60}")
        print(f"# Test Case {i+1}/{len(test_cases)}")
        print(f"{'#' * 60}")
        passed = run_test(unpack_func, pack_func, raw_hex, expected,
                          f"{protocol_name} #{i+1}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)
    print(f"Batch Summary: {sum(1 for _, _ in test_cases)} test cases")
    if all_passed:
        print("ALL TEST CASES PASSED")
    else:
        print("SOME TEST CASES FAILED")
    print("=" * 60)

    return all_passed


# ============================================================
# Self-Test
# ============================================================

def _self_test():
    """Run self-test of the test framework."""
    print("Running test framework self-test...")

    # Test compare_dicts
    d1 = {"a": 1, "b": 2.5, "c": "hello"}
    d2 = {"a": 1, "b": 2.5, "c": "hello"}
    match, diffs = compare_dicts(d1, d2)
    assert match, f"Identical dicts should match: {diffs}"

    d3 = {"a": 1, "b": 2.6, "d": 4}
    match, diffs = compare_dicts(d1, d3)
    assert not match, "Different dicts should not match"
    assert len(diffs) >= 2, f"Should have at least 2 diffs: {diffs}"

    # Test compare_hex
    h1 = "55AA0101"
    h2 = "55AA0101"
    match, diffs = compare_hex(h1, h2)
    assert match, f"Identical hex should match: {diffs}"

    h3 = "55AA0102"
    match, diffs = compare_hex(h1, h3)
    assert not match, "Different hex should not match"

    print("All self-tests passed!")


if __name__ == "__main__":
    _self_test()
