# CAN Protocol Rules Reference

## CAN Frame Structure

### Standard CAN Frame (2.0A)
- **Frame ID**: 11 bits (0x000 - 0x7FF)
- **RTR**: 1 bit (Remote Transmission Request)
- **IDE**: 1 bit (Identifier Extension, 0 for standard)
- **DLC**: 4 bits (Data Length Code, 0-8)
- **Data Field**: 0-8 bytes
- **CRC**: 15 bits + 1 delimiter
- **ACK**: 2 bits

### Extended CAN Frame (2.0B)
- **Frame ID**: 29 bits (0x00000000 - 0x1FFFFFFF)
- **SRR**: 1 bit (Substitute Remote Request)
- **IDE**: 1 bit (1 for extended)
- **RTR**: 1 bit
- **DLC**: 4 bits (0-8)
- **Data Field**: 0-8 bytes

### Common Data Length Code (DLC) Mapping
| DLC | Data Bytes |
|-----|-----------|
| 0   | 0         |
| 1   | 1         |
| ... | ...       |
| 8   | 8         |
| 9-15| Reserved (still 8 bytes in classic CAN) |

## CAN Signal Extraction (DBC-Style)

### Signal Definition Fields
- **Start Bit**: Bit position where signal begins (0-indexed)
- **Bit Length**: Number of bits in the signal
- **Byte Order**:
  - **Intel (Little Endian)**: LSB first, bit numbering goes 0→7 in byte 0, then 8→15 in byte 1, etc.
  - **Motorola (Big Endian)**: MSB first, bit numbering goes 7→0 in byte 0, then 15→8 in byte 1, etc.
- **Value Type**: Signed or Unsigned
- **Factor (Scaling)**: Multiplier to convert raw value to physical value
- **Offset**: Added to raw value after scaling
- **Minimum/Maximum**: Physical value range
- **Unit**: Engineering unit string

### Physical Value Calculation
```
physical_value = (raw_value * factor) + offset
raw_value = (physical_value - offset) / factor
```

### Intel (Little Endian) Bit Extraction
```
Given: start_bit=20, bit_length=12, data=[b0, b1, b2, b3, b4, b5, b6, b7]

Byte index of start bit: 20 // 8 = 2 (byte 2)
Bit index within byte: 20 % 8 = 4

Concatenate bytes starting from byte 2:
  combined = (b2 >> 4) | (b3 << 4) | (b4 << 12) | ...
  raw_value = combined & ((1 << 12) - 1)
```

### Motorola (Big Endian) Bit Extraction
```
Given: start_bit=20, bit_length=12, data=[b0, b1, b2, b3, b4, b5, b6, b7]

Byte index of start bit: 20 // 8 = 2 (byte 2)
Bit index within byte (MSB=7): 20 % 8 = 4

Bit positions (Motorola numbering, MSB first):
  Byte 2: bits 7,6,5,4,3,2,1,0
  start at bit 4 of byte 2, go upward to bit 7, then wrap to byte 3 bit 7 downward

  For start_bit=20 (byte 2, bit 4), length 12:
  Read bits: b2[7:4], b3[7:0] → 4+8=12 bits
  raw_value = ((b2 & 0x0F) << 8) | b3
```

### Motorola Bit Numbering Convention
```
Byte 0:  7  6  5  4  3  2  1  0
Byte 1: 15 14 13 12 11 10  9  8
Byte 2: 23 22 21 20 19 18 17 16
Byte 3: 31 30 29 28 27 26 25 24
...
```
Start bit in Motorola refers to the MSB position of the signal.

## Signed Value Handling
For signed signals (two's complement):
```python
if raw_value >= (1 << (bit_length - 1)):
    raw_value -= (1 << bit_length)
```

## Common CAN Checksum Rules

### CAN Frame CRC (Hardware Level)
- CRC-15 with polynomial 0x4599 (handled by CAN controller, usually not in application layer)

### Application Layer Checksums
- **XOR Checksum**: XOR all data bytes
- **Sum Checksum**: Sum all bytes modulo 256
- **Rolling Counter**: A counter field (typically 4 bits) that increments per frame for sequence validation

## Auto-Filled Defaults (when user does not specify)
- Byte order: Intel (Little Endian) — most common in automotive CAN
- Value type: Unsigned
- Factor: 1.0
- Offset: 0
- DLC: derived from data length
- Frame type: Standard (11-bit ID) unless extended is specified

## Common Pitfalls in CAN Parsing
1. **Bit numbering confusion**: Intel vs Motorola numbering is different and easy to mix up
2. **Cross-byte signals**: Signals spanning multiple bytes need careful byte concatenation
3. **Signed signals**: Two's complement conversion must be applied before scaling
4. **Factor/Offset order**: Physical = raw * factor + offset (NOT raw + offset * factor)
5. **Reserved bits**: Some signals may be reserved and should be ignored, not parsed as data
