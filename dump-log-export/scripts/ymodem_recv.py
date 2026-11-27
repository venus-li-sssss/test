#!/usr/bin/env python3
"""
YMODEM Receive Script
Receives dump files via YMODEM protocol from serial port

Usage:
    python ymodem_recv.py [--com COM_PORT] [--baud BAUD_RATE] [--output SAVE_DIR]
    
Examples:
    python ymodem_recv.py --com COM53
    python ymodem_recv.py --com COM53 --output D:\dump_logs
"""

import serial
import time
import os
import sys
import argparse

# YMODEM constants
SOH = 0x01  # Start of Header (128 bytes)
STX = 0x02  # Start of Header (1024 bytes)
EOT = 0x04  # End of Transmission
ACK = 0x06  # Acknowledge
NAK = 0x15  # Negative Acknowledge
CAN = 0x18  # Cancel
CRC = 0x43  # 'C' - CRC mode

def crc16(data):
    """Calculate CRC16-CCITT"""
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc = crc << 1
            crc &= 0xFFFF
    return crc

def receive_ymodem(com_port, baud_rate, save_dir):
    """Main YMODEM receive function"""
    
    # Create save directory
    os.makedirs(save_dir, exist_ok=True)
    
    # Open serial port
    try:
        ser = serial.Serial(com_port, baud_rate, timeout=10)
        print(f"Opened {com_port} at {baud_rate}")
    except Exception as e:
        print(f"Error opening {com_port}: {e}")
        return False
    
    files_received = []
    
    try:
        # Send 'C' to start CRC mode
        print("Sending 'C' to start YMODEM CRC mode...")
        ser.write(bytes([CRC]))
        
        while True:
            # Wait for packet
            byte = ser.read(1)
            if not byte:
                print("Timeout waiting for packet")
                break
            
            if byte[0] == SOH:
                # 128-byte packet
                header = ser.read(2)  # block number + complement
                data = ser.read(128)
                crc_bytes = ser.read(2)
                
                if len(header) != 2 or len(data) != 128 or len(crc_bytes) != 2:
                    print("Incomplete packet")
                    ser.write(bytes([NAK]))
                    continue
                
                # Verify CRC
                calc_crc = crc16(data)
                recv_crc = (crc_bytes[0] << 8) | crc_bytes[1]
                
                if calc_crc != recv_crc:
                    print(f"CRC mismatch: calculated {calc_crc:#06x}, received {recv_crc:#06x}")
                    ser.write(bytes([NAK]))
                    continue
                
                # Check if this is the filename packet (block 0)
                if header[0] == 0:
                    # Filename packet
                    filename = data.split(b'\x00')[0].decode('utf-8', errors='ignore').strip()
                    if not filename:
                        # Empty filename = end of transfer
                        print("Transfer complete!")
                        ser.write(bytes([ACK]))
                        break
                    
                    print(f"Receiving file: {filename}")
                    ser.write(bytes([ACK]))
                    
                    # Now receive the actual file data
                    file_data = bytearray()
                    while True:
                        byte = ser.read(1)
                        if not byte:
                            print("Timeout waiting for data")
                            break
                        
                        if byte[0] == SOH or byte[0] == STX:
                            packet_size = 128 if byte[0] == SOH else 1024
                            header = ser.read(2)
                            data = ser.read(packet_size)
                            crc_bytes = ser.read(2)
                            
                            if len(data) != packet_size:
                                print("Incomplete data packet")
                                break
                            
                            # Verify CRC
                            calc_crc = crc16(data)
                            recv_crc = (crc_bytes[0] << 8) | crc_bytes[1]
                            
                            if calc_crc != recv_crc:
                                print(f"CRC mismatch in data")
                                ser.write(bytes([NAK]))
                                continue
                            
                            file_data.extend(data)
                            ser.write(bytes([ACK]))
                            
                        elif byte[0] == EOT:
                            ser.write(bytes([ACK]))
                            # Save file
                            filepath = os.path.join(save_dir, filename)
                            with open(filepath, 'wb') as f:
                                f.write(file_data)
                            print(f"Saved: {filepath} ({len(file_data)} bytes)")
                            files_received.append(filepath)
                            
                            # Send 'C' for next file
                            ser.write(bytes([CRC]))
                            break
                        
                        elif byte[0] == CAN:
                            print("Transfer cancelled by sender")
                            return False
                
                else:
                    # Data packet (shouldn't happen in YMODEM)
                    ser.write(bytes([ACK]))
            
            elif byte[0] == EOT:
                # End of transmission without filename
                ser.write(bytes([ACK]))
                print("Transfer complete (EOT)")
                break
            
            elif byte[0] == CAN:
                print("Transfer cancelled")
                break
    
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        ser.close()
        print(f"\nTotal files received: {len(files_received)}")
        for f in files_received:
            print(f"  - {f}")
    
    return len(files_received) > 0

def find_dump_debug_port():
    """Find COM port with 'Dump Debug Port' in registry"""
    import subprocess
    try:
        result = subprocess.run(
            ['reg', 'query', 'HKLM\\SYSTEM\\CurrentControlSet\\Enum\\USB', '/s', '/f', 'FriendlyName'],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.split('\n'):
            if 'Dump Debug Port' in line:
                # Extract COM port number
                import re
                match = re.search(r'COM(\d+)', line)
                if match:
                    return f"COM{match.group(1)}"
    except Exception as e:
        print(f"Error scanning registry: {e}")
    return None

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='YMODEM Receiver for DUMP logs')
    parser.add_argument('--com', help='COM port (e.g., COM53). Auto-detect if omitted.')
    parser.add_argument('--baud', type=int, default=115200, help='Baud rate (default: 115200)')
    parser.add_argument('--output', default=r'D:\QDM505 tool\dump_logs', help='Save directory')
    
    args = parser.parse_args()
    
    # Auto-detect COM port if not specified
    if not args.com:
        print("Auto-detecting Dump Debug Port...")
        args.com = find_dump_debug_port()
        if not args.com:
            print("Error: Could not find 'Dump Debug Port'. Please specify --com")
            sys.exit(1)
        print(f"Found: {args.com}")
    
    print("YMODEM Receiver")
    print(f"COM Port: {args.com}")
    print(f"Baud Rate: {args.baud}")
    print(f"Save Directory: {args.output}")
    print("\nWaiting for device to send files...")
    print("Make sure the device has started the dump process.\n")
    
    success = receive_ymodem(args.com, args.baud, args.output)
    
    if success:
        print("\n✓ Transfer completed successfully!")
    else:
        print("\n✗ Transfer failed or cancelled.")
    
    sys.exit(0 if success else 1)
