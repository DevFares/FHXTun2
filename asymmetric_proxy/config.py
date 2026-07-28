"""
Configuration Settings for Asymmetric Python Proxy Client.

This module centralizes all configurable parameters, loading from config.json if available
or falling back to environment variables and default parameters.
"""

import os
import json
import logging
from typing import Sequence, Dict, Any

logger = logging.getLogger("asymmetric_proxy.config")

CONFIG_FILE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config.json"))

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

# Default configuration values
DEFAULT_CONFIG: Dict[str, Any] = {
    "local_host": "127.0.0.1",
    "local_port": 1080,
    "remote_proxy_host": "127.0.0.1",
    "remote_udp_port": 30,
    "mtcm_port_start": 25,
    "mtcm_port_end": 29,
    "max_mtcm_connections": 100,
    "socket_timeout": 30,
    "socket_buffer_size": 1048576,
    "chunk_read_size": 65536,
    "http_obfuscation_enabled": True,
    "http_spoof_header_template": DEFAULT_304_HEADER_TEMPLATE,
    "write_received_packets_full": True,
    "write_received_packets_data": True,
    "log_level": "DEBUG",
}


def load_config_file() -> Dict[str, Any]:
    """Loads settings from config.json, returning defaults if missing or invalid."""
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE_PATH):
        try:
            with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                config.update(data)
                logger.info(f"[CONFIG] Loaded settings from {CONFIG_FILE_PATH}")
        except Exception as err:
            logger.warning(f"[CONFIG] Failed to parse {CONFIG_FILE_PATH}, using defaults: {err}")
    return config


def save_config_file(new_config: Dict[str, Any]) -> bool:
    """Saves new configuration dictionary to config.json."""
    try:
        current = load_config_file()
        current.update(new_config)
        with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
        logger.info(f"[CONFIG] Successfully saved updated settings to {CONFIG_FILE_PATH}")
        return True
    except Exception as err:
        logger.error(f"[CONFIG] Error saving config file: {err}")
        return False


# Initial Config Load
_cfg = load_config_file()

LOCAL_HOST: str = os.getenv("LOCAL_HOST", _cfg.get("local_host", "127.0.0.1"))
LOCAL_PORT: int = int(os.getenv("LOCAL_PORT", str(_cfg.get("local_port", 1080))))

REMOTE_PROXY_HOST: str = os.getenv("REMOTE_PROXY_HOST", _cfg.get("remote_proxy_host", "127.0.0.1"))
REMOTE_UDP_PORT: int = int(os.getenv("REMOTE_UDP_PORT", str(_cfg.get("remote_udp_port", 9090))))

MTCM_PORT_START: int = int(_cfg.get("mtcm_port_start", 2525))
MTCM_PORT_END: int = int(_cfg.get("mtcm_port_end", 2530))
MTCM_PORTS: Sequence[int] = range(MTCM_PORT_START, MTCM_PORT_END + 1)

MAX_MTCM_CONNECTIONS: int = int(_cfg.get("max_mtcm_connections", 100))
SOCKET_TIMEOUT: int = int(_cfg.get("socket_timeout", 30))

HEADER_SIZE: int = 4  # [2 Bytes Session ID][2 Bytes Payload Length]
MAX_PAYLOAD_SIZE: int = 65535  # Max uint16 size
SESSION_ID_MIN: int = 1
SESSION_ID_MAX: int = 65535

SOCKET_BUFFER_SIZE: int = int(_cfg.get("socket_buffer_size", 1024 * 1024))
CHUNK_READ_SIZE: int = int(_cfg.get("chunk_read_size", 65536))
MAX_UDP_PAYLOAD_SIZE: int = int(_cfg.get("max_udp_payload_size", 1350))

HTTP_OBFUSCATION_ENABLED: bool = bool(_cfg.get("http_obfuscation_enabled", False))
HTTP_SPOOF_HEADER_TEMPLATE: str = str(_cfg.get("http_spoof_header_template", DEFAULT_304_HEADER_TEMPLATE))

WRITE_RECEIVED_PACKETS_FULL: bool = bool(_cfg.get("write_received_packets_full", False))
WRITE_RECEIVED_PACKETS_DATA: bool = bool(_cfg.get("write_received_packets_data", False))

LOG_LEVEL: str = os.getenv("LOG_LEVEL", _cfg.get("log_level", "DEBUG"))
LOG_FORMAT: str = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
