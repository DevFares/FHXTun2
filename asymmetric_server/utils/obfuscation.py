"""
HTTP Obfuscation & Packet Spoofing Utilities for Asymmetric Proxy Server.

Encapsulates return TCP response payload frames inside a realistic HTTP/1.1 response
(e.g., 304 Not Modified / 200 OK image response) with hex-encoded frame data in the body.
This tricks Deep Packet Inspection (DPI) and firewalls into treating the proxy return stream as standard web traffic.
"""

import email.utils
import random
import secrets
import logging

logger = logging.getLogger("asymmetric_server.obfuscation")

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
    """
    Generates a spoofing HTTP response header with dynamic fields (Date, ETag, Nb).

    Args:
        template (str, optional): Custom HTTP response header string template.

    Returns:
        bytes: Encoded HTTP response header bytes terminating with \\r\\n\\r\\n.
    """
    global _headernb
    _headernb += 1
    date_str = email.utils.formatdate(usegmt=True)
    random_len = random.randint(1000, 9999)
    random_hash = secrets.token_hex(6)
    etag = f'W/"{random_len:x}-{random_hash}"'

    tpl = template if (template and template.strip()) else DEFAULT_304_HEADER_TEMPLATE

    # Ensure header ends with double CRLF
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
    except Exception as err:
        logger.warning(f"[OBFUSCATION] Formatting custom HTTP template failed ({err}). Falling back to default.")
        header_str = DEFAULT_304_HEADER_TEMPLATE.format(
            date=date_str,
            etag=etag,
            headernb=_headernb
        )

    return header_str.encode("utf-8")


def obfuscate_frame(frame: bytes, template: str = None) -> bytes:
    """
    Encapsulates binary frame into a spoofed HTTP response with hex-encoded body.

    Format:
        [HTTP Response Headers]\\r\\n\\r\\n[hex_string_of_frame]\\r\\n

    Args:
        frame (bytes): Binary proxy frame (4-byte header + binary payload).
        template (str, optional): Custom HTTP response header template.

    Returns:
        bytes: Obfuscated HTTP response payload packet ready for TCP transmission.
    """
    header_bytes = generate_304_header(template)
    hex_body = frame.hex().encode("ascii")
    return header_bytes + hex_body + b"\r\n"
