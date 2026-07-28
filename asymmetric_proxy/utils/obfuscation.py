"""
HTTP De-obfuscation & Unwrapping Utilities for Asymmetric Proxy Client.

Parses incoming HTTP response packets, extracts the hex-encoded payload body,
and converts it back to binary proxy frames.
"""

import email.utils
import random
import secrets
import logging
from typing import Tuple, Optional, List
from asymmetric_proxy.utils.protocol import unpack_header, HEADER_SIZE

logger = logging.getLogger("asymmetric_proxy.obfuscation")

_headernb = 0

BACKUP_304_HEADER_TEMPLATE = (
    "HTTP/1.1 304 Not Modified\r\n"
    "Date: {date}\r\n"
    "Connection: Keep-Alive\r\n"
    "Keep-Alive: timeout=360000, max=360000\r\n"
    "ETag: {etag}\r\n"
    "Cache-Control: public, max-age=0\r\n"
    "Vary: Origin\r\n"
    "Nb: {headernb}\r\n"
    "Content-Type: image/png\r\n"
    "\r\n"
)

DEFAULT_304_HEADER_TEMPLATE = (
    "HTTP/1.1 304 Not Modified\r\n"
    "Connection: Keep-Alive\r\n"
    "Keep-Alive: timeout=360000, max=360000\r\n"
    "ETag: {etag}\r\n"
    "Cache-Control: public, max-age=0\r\n"
    "Vary: Origin\r\n"
    "Content-Type: image/png\r\n"
    "\r\n"
)


def generate_304_header(template: str = None) -> bytes:
    """Generates a spoofing HTTP response header with dynamic fields."""
    global _headernb
    _headernb += 1
    date_str = email.utils.formatdate(usegmt=True)
    random_len = random.randint(1000, 9999)
    random_hash = secrets.token_hex(6)
    etag = f'W/"{random_len:x}-{random_hash}"'

    tpl = template if (template and template.strip()) else DEFAULT_304_HEADER_TEMPLATE

    if not tpl.endswith("\r\n\r\n"):
        if tpl.endswith("\r\n"):
            tpl += "\r\n"
        else:
            tpl += "\r\n\r\n"

    try:
        header_str = tpl.format(
            date=date_str,
            etag=etag,
            headernb=_headernb
        )
    except Exception:
        header_str = DEFAULT_304_HEADER_TEMPLATE.format(
            date=date_str,
            etag=etag,
            headernb=_headernb
        )

    return header_str.encode("utf-8")


def obfuscate_frame(frame: bytes, template: str = None) -> bytes:
    """Encapsulates binary frame into a spoofed HTTP response with hex-encoded body."""
    header_bytes = generate_304_header(template)
    hex_body = frame.hex().encode("ascii")
    return header_bytes + hex_body + b"\r\n"


def deobfuscate_stream(buffer: bytearray) -> List[Tuple[int, bytes]]:
    """
    Parses buffer containing HTTP-obfuscated return packets.
    Extracts complete binary frames (session_id, payload) and removes consumed bytes from buffer.

    Format expected per packet:
        HTTP/1.1 ... \\r\\n\\r\\n<hex_string_of_frame>\\r\\n

    Returns:
        List[Tuple[int, bytes]]: List of extracted (session_id, payload) frames.
    """
    extracted_frames = []

    while True:
        # 1. Locate end of HTTP header
        header_end = buffer.find(b"\r\n\r\n")
        if header_end == -1:
            break

        payload_start = header_end + 4

        # 2. Check if we have at least 8 hex chars (4 binary header bytes) to determine frame size
        if len(buffer) < payload_start + 8:
            break

        # Read first 8 hex characters (4 bytes binary header)
        try:
            hex_header = buffer[payload_start : payload_start + 8]
            header_bytes = bytes.fromhex(hex_header.decode("ascii"))
            session_id, payload_len = unpack_header(header_bytes)
        except Exception as err:
            logger.warning(f"[DEOBFUSCATE] Error decoding header hex string ({err}). Advancing past corrupt header end.")
            del buffer[:payload_start]
            continue

        # 3. Calculate required hex string length
        total_frame_binary_len = HEADER_SIZE + payload_len
        total_hex_len = total_frame_binary_len * 2

        if len(buffer) < payload_start + total_hex_len:
            break

        # 4. Extract and decode hex payload
        try:
            hex_body = buffer[payload_start : payload_start + total_hex_len]
            frame_bytes = bytes.fromhex(hex_body.decode("ascii"))
            payload = frame_bytes[HEADER_SIZE:]
            extracted_frames.append((session_id, payload))
        except Exception as err:
            logger.error(f"[DEOBFUSCATE] Error converting hex body to bytes for Session {session_id}: {err}")
            del buffer[: payload_start + total_hex_len]
            continue

        # 5. Consume processed bytes from buffer, including trailing CRLF if present
        consumed_len = payload_start + total_hex_len
        if len(buffer) >= consumed_len + 2 and buffer[consumed_len : consumed_len + 2] == b"\r\n":
            consumed_len += 2
        elif len(buffer) >= consumed_len + 1 and buffer[consumed_len : consumed_len + 1] in (b"\r", b"\n"):
            consumed_len += 1

        del buffer[:consumed_len]

    return extracted_frames
