"""
Binary Protocol Encoders and Decoders for Asymmetric Proxy Frames.

Frame Binary Layout:
+-----------------------+--------------------------+------------------------+
| Session ID (2 Bytes)  | Payload Length (2 Bytes) | Payload Data (N Bytes) |
| Big-Endian uint16 (!H)| Big-Endian uint16 (!H)   | raw bytes              |
+-----------------------+--------------------------+------------------------+
Total Header Size: 4 Bytes.
"""

import struct
import logging
from typing import Tuple, Optional

logger = logging.getLogger("asymmetric_proxy.protocol")

HEADER_FORMAT = "!HH"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 4 bytes


def pack_frame(session_id: int, payload: bytes) -> bytes:
    """
    Packs a session ID and payload bytes into a custom binary frame.

    Args:
        session_id (int): 16-bit integer session identifier (1-65535).
        payload (bytes): Raw binary payload data to encapsulate.

    Returns:
        bytes: The compiled binary frame ready for transmission over UDP/TCP.

    Raises:
        ValueError: If session_id is out of bounds or payload exceeds 65,535 bytes.
    """
    if not (1 <= session_id <= 65535):
        raise ValueError(f"Invalid Session ID {session_id}. Must be between 1 and 65535.")
    
    length = len(payload)
    if length > 65535:
        raise ValueError(f"Payload length {length} exceeds maximum frame limit of 65535 bytes.")

    # Pack 2-byte Session ID and 2-byte Length followed by payload bytes
    # Uses struct.pack with Big-Endian Network Byte Order '!HH'
    header = struct.pack(HEADER_FORMAT, session_id, length)
    
    # Trace log for frame creation
    logger.debug(f"[PROTOCOL] Packed frame for Session {session_id}: Header=4 bytes, Payload={length} bytes")
    return header + payload


def unpack_header(buffer: bytes) -> Tuple[int, int]:
    """
    Unpacks the 4-byte header into (session_id, payload_length).

    Args:
        buffer (bytes or memoryview): Buffer containing at least 4 bytes of header data.

    Returns:
        Tuple[int, int]: Tuple of (session_id, payload_length).

    Raises:
        ValueError: If buffer length is less than HEADER_SIZE (4 bytes).
    """
    if len(buffer) < HEADER_SIZE:
        raise ValueError(f"Buffer size ({len(buffer)} bytes) insufficient to unpack header of size {HEADER_SIZE}")

    # Unpack big-endian unsigned short integers
    session_id, payload_length = struct.unpack(HEADER_FORMAT, buffer[:HEADER_SIZE])
    return session_id, payload_length


def unpack_frame(data: bytes) -> Optional[Tuple[int, bytes]]:
    """
    Attempts to unpack a complete frame from raw binary input data.

    Args:
        data (bytes): Input data chunk containing frame header + body.

    Returns:
        Optional[Tuple[int, bytes]]: (session_id, payload) if valid and complete frame, else None.
    """
    if len(data) < HEADER_SIZE:
        logger.debug(f"[PROTOCOL] Data shorter than header size ({len(data)} < {HEADER_SIZE})")
        return None

    session_id, payload_length = unpack_header(data)
    total_expected = HEADER_SIZE + payload_length

    if len(data) < total_expected:
        logger.debug(f"[PROTOCOL] Frame incomplete for Session {session_id}: have {len(data)} bytes, need {total_expected}")
        return None

    # Zero-copy slicing with memoryview for high efficiency
    payload = data[HEADER_SIZE:total_expected]
    logger.debug(f"[PROTOCOL] Unpacked complete frame for Session {session_id}: {payload_length} bytes payload")
    return session_id, payload
