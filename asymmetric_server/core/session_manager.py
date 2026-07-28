"""
TrafficIdentifierServer (TIS) - Server Session & Target Proxy Manager.

Tracks session states for active client proxy connections (session_id 1-65535).
Handles SOCKS5 negotiation, connects outbound to remote destination internet servers,
relays client request payloads, and streams target response data back to MTCMS.
"""

import asyncio
import socket
import struct
import logging
from typing import Dict, Optional, Tuple, Any
from asymmetric_server.core.tcp_sender import MultiTCPConnectionManagerServer
from asymmetric_server import config

logger = logging.getLogger("asymmetric_server.session_manager")


class ServerSession:
    """Represents an active proxied target session on the Remote Server."""

    def __init__(self, session_id: int, client_ip: str) -> None:
        self.session_id = session_id
        self.client_ip = client_ip
        self.state = "INIT"  # States: INIT, SOCKS_GREETING, CONNECTING, CONNECTED, CLOSED
        self.target_reader: Optional[asyncio.StreamReader] = None
        self.target_writer: Optional[asyncio.StreamWriter] = None
        self.read_task: Optional[asyncio.Task] = None
        self.pending_payloads: List[bytes] = []
        self.lock = asyncio.Lock()


class TrafficIdentifierServer:
    """
    TrafficIdentifierServer (TIS)

    Manages active session mappings and target outbound TCP connections.
    """

    def __init__(self, tcp_sender: MultiTCPConnectionManagerServer) -> None:
        """
        Initializes TIS.

        Args:
            tcp_sender (MultiTCPConnectionManagerServer): MTCMS instance to send return frames.
        """
        self.tcp_sender = tcp_sender
        self.sessions: Dict[int, ServerSession] = {}
        self._lock = asyncio.Lock()

    async def handle_client_payload(self, session_id: int, payload: bytes, client_ip: str) -> None:
        """
        Processes an incoming UDP payload from the Client Proxy.

        Args:
            session_id (int): 16-bit Session ID.
            payload (bytes): Incoming client data payload.
            client_ip (str): IP address of the Client Proxy.
        """
        # Debug option: If simple_obfuscation_test is enabled in server config, reply with constant HTTP 302 Found
        if config.SIMPLE_OBFUSCATION_TEST or config.load_server_config_file().get("simple_obfuscation_test", False):
            logger.info(f"[TIS] Debug simple_obfuscation_test enabled: replying with constant HTTP 302 Found to Session ID {session_id}")
            await self.tcp_sender.send_response_frame(session_id, config.DEBUG_302_RESPONSE_DATA, client_ip)
            return

        async with self._lock:
            session = self.sessions.get(session_id)
            if not session:
                session = ServerSession(session_id, client_ip)
                self.sessions[session_id] = session
                logger.info(f"[TIS] Session {session_id}: Created new server session for Client Proxy IP {client_ip}")

        # Per-session locking to prevent race conditions during state transitions & open_connection
        async with session.lock:
            if session.state == "CLOSED":
                return

            if session.state == "INIT":
                if session.pending_payloads:
                    payload = b"".join(session.pending_payloads) + payload
                    session.pending_payloads.clear()
                await self._process_initial_payload(session, payload)
            elif session.state == "SOCKS_GREETING":
                if session.pending_payloads:
                    payload = b"".join(session.pending_payloads) + payload
                    session.pending_payloads.clear()
                await self._process_socks_connect_request(session, payload)
            elif session.state == "CONNECTING":
                logger.debug(f"[TIS] Session {session_id}: Buffering {len(payload)} bytes while connecting to target.")
                session.pending_payloads.append(payload)
            elif session.state == "CONNECTED":
                await self._forward_to_target(session, payload)
            else:
                logger.warning(f"[TIS] Session {session_id}: Payload received in invalid state '{session.state}'. Dropping.")

    async def _process_initial_payload(self, session: ServerSession, payload: bytes) -> None:
        """
        Inspects initial payload to handle SOCKS5 handshake or raw request.
        """
        # SOCKS5 Handshake check (Starts with version 0x05)
        if len(payload) >= 2 and payload[0] == 0x05:
            logger.debug(f"[TIS] Session {session.session_id}: SOCKS5 greeting received. Replying with No-Auth (0x05 0x00).")
            session.state = "SOCKS_GREETING"
            # Response: SOCKS Version 5, Method 0x00 (NO AUTH REQUIRED)
            response = b"\x05\x00"
            await self.tcp_sender.send_response_frame(session.session_id, response, session.client_ip)
        elif payload.upper().startswith(b"CONNECT "):
            logger.debug(f"[TIS] Session {session.session_id}: HTTP CONNECT request received ({len(payload)} bytes). Handling HTTP proxy tunnel...")
            await self._process_http_connect_request(session, payload)
        else:
            # Fallback: Raw target / HTTP transparent proxy parsing
            logger.debug(f"[TIS] Session {session.session_id}: Non-SOCKS5 payload received ({len(payload)} bytes). Attempting direct target connection...")
            await self._process_direct_target_connection(session, payload)

    async def _process_http_connect_request(self, session: ServerSession, payload: bytes) -> None:
        """
        Parses HTTP CONNECT request (used for HTTPS tunneling) and establishes target connection.
        """
        lines = payload.split(b"\r\n")
        first_line = lines[0].decode("utf-8", errors="ignore").strip()
        parts = first_line.split()

        target_host = ""
        target_port = 443

        if len(parts) >= 2:
            host_port = parts[1]
            if "://" in host_port:
                host_port = host_port.split("://", 1)[1]
            if ":" in host_port:
                hp_parts = host_port.rsplit(":", 1)
                target_host = hp_parts[0]
                try:
                    target_port = int(hp_parts[1])
                except ValueError:
                    target_port = 443
            else:
                target_host = host_port

        if not target_host:
            for line in lines[1:]:
                if line.lower().startswith(b"host:"):
                    hp = line.split(b":", 1)[1].strip().decode("utf-8", errors="ignore")
                    if ":" in hp:
                        hp_parts = hp.rsplit(":", 1)
                        target_host = hp_parts[0]
                        try:
                            target_port = int(hp_parts[1])
                        except ValueError:
                            target_port = 443
                    else:
                        target_host = hp
                    break

        if not target_host:
            logger.error(f"[TIS] Session {session.session_id}: Unable to parse target host from HTTP CONNECT request.")
            response = b"HTTP/1.1 400 Bad Request\r\n\r\n"
            await self.tcp_sender.send_response_frame(session.session_id, response, session.client_ip)
            await self.close_session(session.session_id)
            return

        session.state = "CONNECTING"
        try:
            logger.info(f"[TIS] Session {session.session_id}: HTTP CONNECT tunnel to target {target_host}:{target_port}")
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target_host, target_port),
                timeout=config.SOCKET_TIMEOUT
            )
            session.target_reader = reader
            session.target_writer = writer
            session.state = "CONNECTED"

            sock = writer.get_extra_info("socket")
            if sock:
                try:
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except Exception:
                    pass

            # Send HTTP 200 Connection Established back to client proxy
            response = b"HTTP/1.1 200 Connection Established\r\n\r\n"
            await self.tcp_sender.send_response_frame(session.session_id, response, session.client_ip)

            # Spawn target reader loop task
            session.read_task = asyncio.create_task(self._target_reader_loop(session))

            # Flush buffered payloads
            if session.pending_payloads:
                logger.debug(f"[TIS] Session {session.session_id}: Flushing {len(session.pending_payloads)} buffered payloads to target.")
                for pending in session.pending_payloads:
                    await self._forward_to_target(session, pending)
                session.pending_payloads.clear()

        except Exception as err:
            logger.error(f"[TIS] Session {session.session_id}: Failed to establish HTTP CONNECT to {target_host}:{target_port}: {err}")
            response = b"HTTP/1.1 502 Bad Gateway\r\n\r\n"
            await self.tcp_sender.send_response_frame(session.session_id, response, session.client_ip)
            await self.close_session(session.session_id)

    async def _process_socks_connect_request(self, session: ServerSession, payload: bytes) -> None:
        """
        Parses SOCKS5 CONNECT request and establishes outbound target socket connection.
        """
        if len(payload) < 6 or payload[0] != 0x05 or payload[1] != 0x01:
            logger.error(f"[TIS] Session {session.session_id}: Invalid SOCKS5 command packet. Closing session.")
            await self.close_session(session.session_id)
            return

        cmd = payload[1]  # 0x01 = CONNECT
        address_type = payload[3]  # 0x01=IPv4, 0x03=Domain, 0x04=IPv6

        target_host = ""
        target_port = 0

        try:
            if address_type == 0x01:  # IPv4
                target_host = socket.inet_ntoa(payload[4:8])
                target_port = struct.unpack("!H", payload[8:10])[0]
            elif address_type == 0x03:  # Domain Name
                domain_len = payload[4]
                target_host = payload[5 : 5 + domain_len].decode("utf-8", errors="ignore")
                target_port = struct.unpack("!H", payload[5 + domain_len : 7 + domain_len])[0]
            elif address_type == 0x04:  # IPv6
                target_host = socket.inet_ntop(socket.AF_INET6, payload[4:20])
                target_port = struct.unpack("!H", payload[20:22])[0]
            else:
                logger.error(f"[TIS] Session {session.session_id}: Unsupported address type {address_type}")
                await self.close_session(session.session_id)
                return

            logger.info(f"[TIS] Session {session.session_id}: SOCKS5 CONNECT request to target {target_host}:{target_port}")

            session.state = "CONNECTING"
            # Connect to target destination
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target_host, target_port),
                timeout=config.SOCKET_TIMEOUT
            )

            session.target_reader = reader
            session.target_writer = writer
            session.state = "CONNECTED"

            # Apply socket options
            sock = writer.get_extra_info("socket")
            if sock:
                try:
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except Exception:
                    pass

            # Send SOCKS5 Success Response back to Client Proxy
            # BND.ADDR=0.0.0.0, BND.PORT=0
            socks_success = b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00"
            await self.tcp_sender.send_response_frame(session.session_id, socks_success, session.client_ip)

            # Spawn target reader loop task
            session.read_task = asyncio.create_task(self._target_reader_loop(session))

            # Flush buffered payloads
            if session.pending_payloads:
                logger.debug(f"[TIS] Session {session.session_id}: Flushing {len(session.pending_payloads)} buffered payloads to target.")
                for pending in session.pending_payloads:
                    await self._forward_to_target(session, pending)
                session.pending_payloads.clear()

        except Exception as err:
            logger.error(f"[TIS] Session {session.session_id}: Failed to connect to target {target_host}:{target_port}: {err}")
            # Reply SOCKS5 failure (0x01 General SOCKS server failure)
            socks_fail = b"\x05\x01\x00\x01\x00\x00\x00\x00\x00\x00"
            await self.tcp_sender.send_response_frame(session.session_id, socks_fail, session.client_ip)
            await self.close_session(session.session_id)

    async def _process_direct_target_connection(self, session: ServerSession, payload: bytes) -> None:
        """
        Fallback for direct connection if target host/port can be derived or default local proxy.
        """
        lines = payload.split(b"\r\n")
        first_line = lines[0].decode("utf-8", errors="ignore").strip()
        parts = first_line.split()

        target_host = ""
        target_port = 80

        # 1. Try to extract target host/port from request line (e.g. GET http://domain.com/path HTTP/1.1)
        if len(parts) >= 2:
            raw_url = parts[1]
            if "://" in raw_url:
                scheme, rest = raw_url.split("://", 1)
                host_port = rest.split("/", 1)[0]
                if ":" in host_port:
                    hp_parts = host_port.rsplit(":", 1)
                    target_host = hp_parts[0]
                    try:
                        target_port = int(hp_parts[1])
                    except ValueError:
                        target_port = 443 if scheme.lower() == "https" else 80
                else:
                    target_host = host_port
                    target_port = 443 if scheme.lower() == "https" else 80
            elif ":" in raw_url and not raw_url.startswith("/"):
                host_port = raw_url.split("/", 1)[0]
                if ":" in host_port:
                    hp_parts = host_port.rsplit(":", 1)
                    target_host = hp_parts[0]
                    try:
                        target_port = int(hp_parts[1])
                    except ValueError:
                        target_port = 80

        # 2. If target_host not in request line, parse 'Host:' header
        if not target_host:
            for line in lines:
                if line.lower().startswith(b"host:"):
                    hp = line.split(b":", 1)[1].strip().decode("utf-8", errors="ignore")
                    if ":" in hp:
                        hp_parts = hp.rsplit(":", 1)
                        target_host = hp_parts[0]
                        try:
                            target_port = int(hp_parts[1])
                        except ValueError:
                            target_port = 80
                    else:
                        target_host = hp
                    break

        # 3. If target_host still not found and HTTP header delimiter is missing, buffer payload
        if not target_host:
            if b"\r\n\r\n" not in payload and len(payload) < 8192:
                logger.debug(f"[TIS] Session {session.session_id}: Incomplete headers ({len(payload)} bytes). Buffering initial payload...")
                session.state = "INIT"
                session.pending_payloads.append(payload)
                return
            else:
                logger.warning(f"[TIS] Session {session.session_id}: Target host unspecified in HTTP payload. Defaulting to 127.0.0.1:80")
                target_host = "127.0.0.1"
                target_port = 80

        session.state = "CONNECTING"
        try:
            logger.info(f"[TIS] Session {session.session_id}: Direct target connect to {target_host}:{target_port}")
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target_host, target_port),
                timeout=config.SOCKET_TIMEOUT
            )
            session.target_reader = reader
            session.target_writer = writer
            session.state = "CONNECTED"

            sock = writer.get_extra_info("socket")
            if sock:
                try:
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except Exception:
                    pass

            session.read_task = asyncio.create_task(self._target_reader_loop(session))
            await self._forward_to_target(session, payload)

            if session.pending_payloads:
                logger.debug(f"[TIS] Session {session.session_id}: Flushing {len(session.pending_payloads)} buffered payloads to target.")
                for pending in session.pending_payloads:
                    await self._forward_to_target(session, pending)
                session.pending_payloads.clear()

        except Exception as err:
            logger.error(f"[TIS] Session {session.session_id}: Direct connect failed: {err}")
            await self.close_session(session.session_id)

    async def _forward_to_target(self, session: ServerSession, payload: bytes) -> None:
        """Forwards client data payload to active target StreamWriter."""
        if session.target_writer and not session.target_writer.is_closing():
            try:
                session.target_writer.write(payload)
                await session.target_writer.drain()
                logger.debug(f"[TIS] Session {session.session_id}: Forwarded {len(payload)} bytes to target server.")
            except Exception as err:
                logger.error(f"[TIS] Session {session.session_id}: Error sending to target: {err}")
                await self.close_session(session.session_id)

    async def _target_reader_loop(self, session: ServerSession) -> None:
        """
        Reads returning data from target remote server and transmits back via MTCMS.
        """
        session_id = session.session_id
        try:
            while session.state == "CONNECTED" and session.target_reader:
                chunk = await session.target_reader.read(config.CHUNK_READ_SIZE)
                if not chunk:
                    logger.info(f"[TIS] Session {session_id}: Target remote server closed connection (EOF).")
                    await self.tcp_sender.send_response_frame(session_id, b"", session.client_ip)
                    break

                logger.debug(f"[TIS] Session {session_id}: Received {len(chunk)} bytes from target. Relaying via MTCMS...")
                sent = await self.tcp_sender.send_response_frame(session_id, chunk, session.client_ip)
                if not sent:
                    logger.warning(f"[TIS] Session {session_id}: Failed to deliver response frame over TCP. Closing session.")
                    break

        except asyncio.CancelledError:
            logger.debug(f"[TIS] Session {session_id}: Target reader loop cancelled.")
        except Exception as err:
            logger.error(f"[TIS] Session {session_id}: Target reader loop error: {err}")
        finally:
            await self.close_session(session_id)

    async def close_session(self, session_id: int) -> None:
        """Cleanly closes and removes a target session."""
        async with self._lock:
            session = self.sessions.pop(session_id, None)

        if session:
            async with session.lock:
                session.state = "CLOSED"
                session.pending_payloads.clear()
                if session.read_task and not session.read_task.done():
                    session.read_task.cancel()

                if session.target_writer:
                    try:
                        if not session.target_writer.is_closing():
                            session.target_writer.close()
                            await session.target_writer.wait_closed()
                    except Exception:
                        pass

            logger.info(f"[TIS] Session {session_id}: Cleanly closed & removed from TIS session table.")

    async def close_all(self) -> None:
        """Closes all active server sessions."""
        async with self._lock:
            session_ids = list(self.sessions.keys())

        for sid in session_ids:
            await self.close_session(sid)

    @property
    def active_session_count(self) -> int:
        """Returns total active server sessions count."""
        return len(self.sessions)
