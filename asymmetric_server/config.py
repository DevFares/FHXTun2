"""
Configuration Settings for Asymmetric Python Proxy Server.

Centralizes configuration for the server proxy system, loading settings from server_config.json
if available, falling back to environment variables and default parameters.
"""

import os
import json
import logging
from typing import Sequence, Dict, Any

logger = logging.getLogger("asymmetric_server.config")

SERVER_CONFIG_FILE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "server_config.json")
)

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

# Default configuration dictionary for Server Proxy
DEFAULT_SERVER_CONFIG: Dict[str, Any] = {
    "bind_udp_host": "0.0.0.0",
    "bind_udp_port": 9090,
    "bind_tcp_host": "0.0.0.0",
    "bind_tcp_port_start": 2525,
    "bind_tcp_port_end": 2530,
    "max_active_sessions": 65535,
    "socket_timeout": 30,
    "socket_buffer_size": 1048576,
    "chunk_read_size": 65536,
    "http_obfuscation_enabled": False,
    "simple_obfuscation_test": False,
    "http_spoof_header_template": DEFAULT_304_HEADER_TEMPLATE,
    "log_level": "DEBUG",
}

DEBUG_302_RESPONSE_DATA: bytes = (
    b"HTTP/1.1 302 Found\r\n"
    b"Content-Type: text/html; charset=UTF-8\r\n"
    b"Content-Length: 173\r\n"
    b"Location: http://espaceclient.eddenyalive.com/primary\r\n"
    b"Cache-Control: no-cache\r\n"
    b"Connection: Close\r\n\r\n"
    b"<html><head><title>302 Found</title></head><body><h1>302 Found</h1><p>The document has moved <a href=\"http://espaceclient.eddenyalive.com/primary\">here</a></p></body></html>"
)


def load_server_config_file() -> Dict[str, Any]:
    """Loads settings from server_config.json, returning defaults if missing or invalid."""
    config = DEFAULT_SERVER_CONFIG.copy()
    if os.path.exists(SERVER_CONFIG_FILE_PATH):
        try:
            with open(SERVER_CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                config.update(data)
                logger.info(f"[SERVER CONFIG] Loaded settings from {SERVER_CONFIG_FILE_PATH}")
        except Exception as err:
            logger.warning(f"[SERVER CONFIG] Failed to parse {SERVER_CONFIG_FILE_PATH}, using defaults: {err}")
    return config


def save_server_config_file(new_config: Dict[str, Any]) -> bool:
    """Saves updated configuration dictionary to server_config.json."""
    try:
        current = load_server_config_file()
        current.update(new_config)
        with open(SERVER_CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
        logger.info(f"[SERVER CONFIG] Saved updated settings to {SERVER_CONFIG_FILE_PATH}")
        return True
    except Exception as err:
        logger.error(f"[SERVER CONFIG] Error saving config file: {err}")
        return False


# Initial Config Load
_cfg = load_server_config_file()

BIND_UDP_HOST: str = os.getenv("BIND_UDP_HOST", _cfg.get("bind_udp_host", "0.0.0.0"))
BIND_UDP_PORT: int = int(os.getenv("BIND_UDP_PORT", str(_cfg.get("bind_udp_port", 9090))))

BIND_TCP_HOST: str = os.getenv("BIND_TCP_HOST", _cfg.get("bind_tcp_host", "0.0.0.0"))
BIND_TCP_PORT_START: int = int(_cfg.get("bind_tcp_port_start", _cfg.get("client_tcp_port_start", 2525)))
BIND_TCP_PORT_END: int = int(_cfg.get("bind_tcp_port_end", _cfg.get("client_tcp_port_end", 2530)))
BIND_TCP_PORTS: Sequence[int] = range(BIND_TCP_PORT_START, BIND_TCP_PORT_END + 1)

MAX_ACTIVE_SESSIONS: int = int(_cfg.get("max_active_sessions", 65535))
SOCKET_TIMEOUT: int = int(_cfg.get("socket_timeout", 30))

HEADER_SIZE: int = 4  # [2 Bytes Session ID][2 Bytes Payload Length]
MAX_PAYLOAD_SIZE: int = 65535  # Max uint16 size

SOCKET_BUFFER_SIZE: int = int(_cfg.get("socket_buffer_size", 1024 * 1024))
CHUNK_READ_SIZE: int = int(_cfg.get("chunk_read_size", 65536))

HTTP_OBFUSCATION_ENABLED: bool = bool(_cfg.get("http_obfuscation_enabled", False))
SIMPLE_OBFUSCATION_TEST: bool = bool(_cfg.get("simple_obfuscation_test", False))
HTTP_SPOOF_HEADER_TEMPLATE: str = str(_cfg.get("http_spoof_header_template", DEFAULT_304_HEADER_TEMPLATE))

LOG_LEVEL: str = os.getenv("LOG_LEVEL", _cfg.get("log_level", "DEBUG"))
LOG_FORMAT: str = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
