"""
HTTP Obfuscation & Packet Spoofing Utilities for Asymmetric Proxy Server.

Encapsulates return TCP response payload frames inside a realistic HTTP/1.1 response
(HTTP 200 OK) with hex-encoded frame data in the body.
This tricks Deep Packet Inspection (DPI) and firewalls into treating the proxy return stream as standard web traffic.
"""

import email.utils
import random
import secrets
import logging

logger = logging.getLogger("asymmetric_server.obfuscation")

headernb = 0
_headernb = 0

DEFAULT_200_HEADER_TEMPLATE = (
    "HTTP/1.1 200 OK\r\n"
    "accept-ranges: bytes\r\n"
    "connection: Keep-Alive\r\n"
    "content-length: {content_length}\r\n"
    "content-type: text/html; charset=UTF-8\r\n"
    "date: {date}\r\n"
    'etag: "2ce-625e02018439f"\r\n'
    "keep-alive: timeout=5, max=100\r\n"
    "last-modified: Fri, 01 Nov 2024 20:53:21 GMT\r\n"
    "strict-transport-security: max-age=0\r\n"
    "\r\n"
)


def generate_200_response(body_bytes: bytes = None, template: str = None) -> bytes:
    """
    Generates a spoofing HTTP/1.1 200 OK response with dynamic Date, Content-Length, and payload bytes.

    Args:
        body_bytes (bytes, optional): Payload bytes (e.g. hex-encoded proxy frame). If None, generates random 700 bytes.
        template (str, optional): Custom HTTP response header string template.

    Returns:
        bytes: Encoded HTTP 200 OK response bytes including headers and body payload.
    """
    global headernb, _headernb
    headernb += 1
    _headernb = headernb

    if body_bytes is None:
        payload_str = "".join(str(random.randint(0, 9)) for _ in range(700))
        payload_bytes = payload_str.encode("utf-8")
    else:
        payload_bytes = body_bytes

    content_length = len(payload_bytes)
    date_str = email.utils.formatdate(usegmt=True)

    header_str = (
        f"HTTP/1.1 200 OK\r\n"
        f"accept-ranges: bytes\r\n"
        f"connection: Keep-Alive\r\n"
        f"content-length: {content_length}\r\n"
        f"content-type: text/html; charset=UTF-8\r\n"
        f"date: {date_str}\r\n"
        f'etag: "2ce-625e02018439f"\r\n'
        f"keep-alive: timeout=5, max=100\r\n"
        f"last-modified: Fri, 01 Nov 2024 20:53:21 GMT\r\n"
        f"strict-transport-security: max-age=0\r\n"
        f"\r\n"
    )

    full_response = header_str.encode("utf-8") + payload_bytes
    return full_response


# Backwards compatibility alias
generate_304_header = generate_200_response


def obfuscate_frame(frame: bytes, template: str = None) -> bytes:
    """
    Encapsulates binary frame into a spoofed HTTP 200 OK response with hex-encoded body.

    Format:
        [HTTP 200 OK Headers]\r\n\r\n[hex_string_of_frame]\r\n

    Args:
        frame (bytes): Binary proxy frame (4-byte header + binary payload).
        template (str, optional): Custom HTTP response header template.

    Returns:
        bytes: Obfuscated HTTP response payload packet ready for TCP transmission.
    """
    hex_body = frame.hex().encode("ascii")
    return generate_200_response(body_bytes=hex_body, template=template) + b"\r\n"
