# Serial Protocol Rules Reference

## Common Serial Frame Structure

### Typical Frame Layout
```
| Header | Length | Command/Type | Payload | Checksum | Footer |
|--------|--------|-------------|---------|----------|--------|
| 1-2B   | 1-2B   | 1B          | N B     | 1-2B     | 0-1B   |
```

### Field Definitions

#### Frame Header (帧头)
- Fixed magic bytes (e.g., `0x55 0xAA`, `0xEB 0x90`)
- Length: typically 1 or 2 bytes
- Purpose: frame synchronization and detection

#### Length Field (长度域)
- Position: immediately after header
- Width: 1 byte (max 255) or 2 bytes (max 65535)
- Content varies by protocol:
  - Total frame length (including header and checksum)
  - Payload length only (excluding header and checksum)
  - Length of everything after length field (payload + checksum + footer)
- **Critical**: Determine whether length includes header/checksum or not

#### Command/Type Field (命令字)
- Width: typically 1 byte
- Purpose: identifies the message type for dispatch

#### Payload (数据域)
- Variable length
- Contains the actual business data
- May have sub-structure (fields with offsets, types, endianness)

#### Checksum (校验域)
- Position: typically after payload, before footer (if any)
- Common algorithms:
  - **XOR**: XOR all bytes in the checksum range
  - **Sum8/Sum16**: Sum all bytes modulo 256 or 65536
  - **CRC8**: Polynomial 0x07 or 0x31 (common variants)
  - **CRC16-Modbus**: Polynomial 0xA001 (reflected 0x8005)
  - **CRC16-CCITT**: Polynomial 0x1021 (initial 0xFFFF or 0x0000)
  - **CRC32**: Polynomial 0x04C11DB7

#### Frame Footer (帧尾)
- Fixed magic bytes (e.g., `0x0D 0x0A`, `0xFA`)
- Optional: some protocols have no footer

## Checksum Computation Details

### XOR Checksum
```python
def xor_checksum(data: bytes, start: int, end: int) -> int:
    result = 0
    for i in range(start, end):
        result ^= data[i]
    return result
```

### CRC16-Modbus
```python
def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc  # Little-endian in frame: low byte first
```

### CRC16-CCITT (0x1021, init 0xFFFF)
```python
def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc  # Big-endian in frame: high byte first
```

### Checksum Range
- **Critical**: Identify which bytes are included in the checksum
  - Common: from header to end of payload (excluding checksum itself and footer)
  - Some protocols: from length field to end of payload
  - Some protocols: entire frame excluding checksum

## Endianness in Serial Protocols

### Little Endian (common in embedded ARM)
- Multi-byte values stored LSB first
- `struct.pack('<H', 0x1234)` → `b'\x34\x12'`

### Big Endian (common in network protocols)
- Multi-byte values stored MSB first
- `struct.pack('>H', 0x1234)` → `b'\x12\x34'`

## Sticky Packet (粘包) and Fragmentation (分包) Handling

### Problem
- TCP/serial streams may deliver multiple frames in one read, or split one frame across reads
- UART serial is character-based; frames can be split at any byte boundary

### Solutions
1. **Timeout-based framing**: Collect bytes until a quiet period, then parse
2. **Header + Length framing**: Scan for header, read length field, then read remaining bytes
3. **Footer-based framing**: Scan for header and footer delimiters
4. **Fixed-length framing**: Every frame is the same size

### Frame Extraction Algorithm (Header + Length)
```python
def extract_frames(buffer: bytes, header: bytes, length_offset: int,
                   length_width: int, length_includes_header: bool,
                   length_includes_checksum: bool, checksum_width: int) -> list:
    frames = []
    pos = 0
    while pos < len(buffer):
        # Find next header
        idx = buffer.find(header, pos)
        if idx == -1:
            break
        # Read length field
        len_start = idx + len(header) + length_offset
        if len_start + length_width > len(buffer):
            break  # Incomplete frame
        if length_width == 1:
            frame_len = buffer[len_start]
        else:
            frame_len = struct.unpack('<H', buffer[len_start:len_start+2])[0]
        # Calculate total frame length
        total_len = frame_len
        if not length_includes_header:
            total_len += len(header) + length_offset + length_width
        if not length_includes_checksum:
            total_len += checksum_width
        # Check if complete frame is available
        if idx + total_len > len(buffer):
            break  # Incomplete frame
        frames.append(buffer[idx:idx + total_len])
        pos = idx + total_len
    return frames
```

## Auto-Filled Defaults (when user does not specify)
- Endianness: Little Endian (common in MCU/embedded systems)
- Checksum: None (if not specified, but warn user)
- Length field meaning: Payload length only
- Header: No default — must be specified by user
- Footer: None (no footer if not specified)

## Common Pitfalls in Serial Parsing
1. **Length field interpretation**: Always clarify if length includes header/checksum
2. **Checksum byte order**: CRC16 in Modbus is little-endian, CRC16-CCITT is big-endian
3. **Checksum range**: Some protocols exclude the length field, others include it
4. **BCD encoding**: Some serial protocols use BCD for numeric fields (e.g., `0x12 0x34` = 1234, not 0x1234)
5. **Variable-length payload**: Payload length may depend on command type
6. **Escape characters**: Some protocols use byte-stuffing (e.g., `0x7D` followed by `0x5D` means literal `0x7D`)
