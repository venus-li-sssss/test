# MQTT Protocol Rules Reference

## MQTT Fixed Header

### Structure
```
| Byte 1              | Byte 2+                    |
|---------------------|----------------------------|
| Type (4 bits) | Flags (4 bits) | Remaining Length (1-4 bytes) |
```

### Packet Type (upper 4 bits of byte 1)
| Type Code | Name          | Direction        | Flags |
|-----------|---------------|------------------|-------|
| 1         | CONNECT       | Client → Server  | 0000  |
| 2         | CONNACK       | Server → Client  | 0000  |
| 3         | PUBLISH       | Either           | DUP QoS RETAIN |
| 4         | PUBACK        | Either           | 0000  |
| 5         | PUBREC        | Either           | 0000  |
| 6         | PUBREL        | Either           | 0010  |
| 7         | PUBCOMP       | Either           | 0000  |
| 8         | SUBSCRIBE     | Client → Server  | 0010  |
| 9         | SUBACK        | Server → Client  | 0000  |
| 10        | UNSUBSCRIBE   | Client → Server  | 0010  |
| 11        | UNSUBACK      | Server → Client  | 0000  |
| 12        | PINGREQ       | Client → Server  | 0000  |
| 13        | PINGRESP      | Server → Client  | 0000  |
| 14        | DISCONNECT    | Either           | 0000  |
| 15        | AUTH (MQTT 5) | Either           | 0000  |

### PUBLISH Flags (lower 4 bits of byte 1)
| Bit 3 | Bit 2-1 | Bit 0 |
|-------|---------|-------|
| DUP   | QoS     | RETAIN|

- **DUP**: 0 = first send, 1 = retransmission
- **QoS**: 0 = at most once, 1 = at least once, 2 = exactly once
- **RETAIN**: 1 = server should retain this message

## Remaining Length Encoding/Decoding

### Variable-Length Integer (VBI) Encoding
MQTT uses a variable-length encoding for the "Remaining Length" field:

```python
def encode_remaining_length(length: int) -> bytes:
    """Encode MQTT remaining length (variable byte integer)."""
    if length < 0 or length > 268435455:
        raise ValueError(f"Invalid remaining length: {length}")
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

def decode_remaining_length(data: bytes, offset: int = 1) -> tuple:
    """Decode MQTT remaining length.
    Returns (remaining_length, bytes_consumed).
    """
    multiplier = 1
    value = 0
    pos = offset
    while True:
        if pos >= len(data):
            raise ValueError("Incomplete remaining length field")
        encoded_byte = data[pos]
        value += (encoded_byte & 0x7F) * multiplier
        if multiplier > 128 * 128 * 128:
            raise ValueError("Malformed remaining length")
        pos += 1
        if (encoded_byte & 0x80) == 0:
            break
        multiplier *= 128
    return value, pos - offset
```

### Remaining Length Value Ranges
| Bytes | Range                  |
|-------|------------------------|
| 1     | 0 - 127                |
| 2     | 128 - 16383            |
| 3     | 16384 - 2097151        |
| 4     | 2097152 - 268435455    |

Maximum: 256 MB. No 5th byte allowed.

## MQTT 3.1.1 Packet Structures

### CONNECT (Type 1)
```
Variable Header:
  Protocol Name:   0x00 0x04 "MQTT" (4 bytes length-prefixed string)
  Protocol Level:  0x04 (MQTT 3.1.1)
  Connect Flags:   1 byte
    bit 7: Username Flag
    bit 6: Password Flag
    bit 5: Will Retain
    bit 4-3: Will QoS
    bit 2: Will Flag
    bit 1: Clean Session
    bit 0: Reserved (must be 0)
  Keep Alive:      2 bytes (big endian, seconds)

Payload (in order):
  Client Identifier: length-prefixed string
  Will Topic:        (if Will Flag set) length-prefixed string
  Will Message:      (if Will Flag set) length-prefixed bytes
  Username:          (if Username Flag set) length-prefixed string
  Password:          (if Password Flag set) length-prefixed bytes
```

### CONNACK (Type 2)
```
Variable Header:
  Session Present Flag: 1 byte (bit 0 = session present, bits 1-7 = 0)
  Return Code:          1 byte
    0x00: Connection Accepted
    0x01: Unacceptable protocol version
    0x02: Identifier rejected
    0x03: Server unavailable
    0x04: Bad username or password
    0x05: Not authorized
Payload: none
```

### PUBLISH (Type 3)
```
Variable Header:
  Topic Name:   length-prefixed UTF-8 string (2 bytes length + string)
  Packet ID:    2 bytes (only for QoS 1 and QoS 2)

Payload:
  Application message (binary data)
```

### PUBACK / PUBREC / PUBREL / PUBCOMP (Types 4-7)
```
Variable Header:
  Packet ID: 2 bytes (big endian)
Payload: none
```

### SUBSCRIBE (Type 8)
```
Variable Header:
  Packet ID: 2 bytes (big endian)

Payload:
  For each topic filter:
    Topic Filter: length-prefixed UTF-8 string
    QoS:          1 byte (0, 1, or 2)
```

### SUBACK (Type 9)
```
Variable Header:
  Packet ID: 2 bytes (big endian)

Payload:
  Return Codes: 1 byte per topic filter
    0x00: Maximum QoS 0
    0x01: Maximum QoS 1
    0x02: Maximum QoS 2
    0x80: Failure
```

## Length-Prefixed String/Bytes Format
MQTT strings and binary data are prefixed with a 2-byte big-endian length:
```python
def encode_mqtt_string(s: str) -> bytes:
    """Encode a UTF-8 string with 2-byte length prefix."""
    encoded = s.encode('utf-8')
    return struct.pack('>H', len(encoded)) + encoded

def decode_mqtt_string(data: bytes, offset: int) -> tuple:
    """Decode a length-prefixed UTF-8 string.
    Returns (string, new_offset).
    """
    if offset + 2 > len(data):
        raise ValueError("Incomplete string length field")
    length = struct.unpack('>H', data[offset:offset+2])[0]
    offset += 2
    if offset + length > len(data):
        raise ValueError("Incomplete string data")
    s = data[offset:offset+length].decode('utf-8')
    return s, offset + length
```

## Custom Payload Sub-Protocol

MQTT PUBLISH payloads are often custom binary protocols. Common patterns:

### JSON Payload
- UTF-8 encoded JSON string
- Parse with `json.loads()` after extracting payload bytes

### Binary TLV (Type-Length-Value)
```
| Type (1B) | Length (1B) | Value (N B) |
```
Each field has a type tag, length, and value bytes.

### Binary Fixed-Layout
- Similar to serial protocol frame layout
- Use `struct.unpack()` with a format string
- May have its own checksum

## Auto-Filled Defaults (when user does not specify)
- MQTT version: 3.1.1 (protocol level 4)
- String encoding: UTF-8
- Byte order: Big Endian (MQTT standard)
- QoS: 0 (at most once)
- Keep Alive: 60 seconds
- Clean Session: True

## Common Pitfalls in MQTT Parsing
1. **Remaining length**: Variable byte encoding is easy to get wrong — always use the iterative decode
2. **String length prefix**: MQTT uses 2-byte big-endian length prefix for strings, not null-terminated
3. **Topic name encoding**: Topic is a UTF-8 string, but may contain special characters
4. **Packet ID presence**: Only present for QoS 1 and QoS 2 PUBLISH, never for QoS 0
5. **Payload boundaries**: Payload is everything after the variable header, up to remaining length
6. **MQTT 5 vs 3.1.1**: MQTT 5 adds property length field and reason codes — clarify which version
7. **Will message**: Stored as binary bytes, not a string — length-prefixed but may not be UTF-8
