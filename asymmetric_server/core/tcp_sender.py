"""
MultiTCPConnectionManagerServer (MTCMS) - Inbound Multi-Port Return TCP Server.

Listens on configured TCP ports (e.g. 2525-2530) for incoming TCP connection demands
initiated from Client Proxies. Maintains accepted socket connections and uses them to stream
response payloads back to the Client Proxy asynchronously.
"""

import asyncio
import socket
import logging
from typing import Sequence, List, Dict, Optional, Any
from asymmetric_server.utils.protocol import pack_frame
from asymmetric_server import config

logger = logging.getLogger("asymmetric_server.tcp_sender")


class MultiTCPConnectionManagerServer:
    """
    MultiTCPConnectionManagerServer (MTCMS)

    Listens on TCP return ports and maintains accepted client connections.
    Distributes response payload frames over active accepted client socket connections.
    """

    def __init__(self, bind_host: str = "0.0.0.0", ports: Sequence[int] = range(2525, 2531), client_host: Optional[str] = None) -> None:
        """
        Initializes MTCMS.

        Args:
            bind_host (str): IP address to bind server TCP return listeners.
            ports (Sequence[int]): Sequence or range of return ports to listen on.
            client_host (Optional[str]): Deprecated legacy parameter kept for fallback compatibility.
        """
        self.bind_host = bind_host
        self.ports = list(ports)
        self.servers: List[asyncio.Server] = []
        self._active_connections: List[Dict[str, Any]] = []
        self._round_robin_idx = 0
        self._lock = asyncio.Lock()
        self._bytes_sent = 0
        self._packets_sent = 0

    async def start(self) -> None:
        """
        Binds and starts TCP server listeners across configured return ports.
        """
        for port in self.ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, config.SOCKET_BUFFER_SIZE)
                except Exception as sock_err:
                    logger.warning(f"[MTCMS] Socket option SO_SNDBUF failed on port {port}: {sock_err}")

                sock.bind((self.bind_host, port))
                sock.listen(128)
                sock.setblocking(False)

                server = await asyncio.start_server(
                    self._handle_client_connection,
                    sock=sock
                )
                self.servers.append(server)
                logger.info(f"[MTCMS] Listening for client return TCP connection demands on {self.bind_host}:{port}")

            except Exception as exc:
                logger.error(f"[MTCMS] Failed to bind TCP return listener on port {port}: {exc}")

    async def _handle_client_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """
        Processes and registers an accepted incoming TCP connection from a Client Proxy.
        """
        peer = writer.get_extra_info("peername", ("0.0.0.0", 0))
        peer_ip = peer[0] if isinstance(peer, (tuple, list)) and len(peer) > 0 else "0.0.0.0"
        peer_port = peer[1] if isinstance(peer, (tuple, list)) and len(peer) > 1 else 0

        # Enable high-speed socket options
        sock = writer.get_extra_info("socket")
        if sock:
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, config.SOCKET_BUFFER_SIZE)
            except Exception as sock_err:
                logger.warning(f"[MTCMS] Socket option error for client {peer_ip}:{peer_port}: {sock_err}")

        conn_entry = {
            "reader": reader,
            "writer": writer,
            "ip": peer_ip,
            "port": peer_port,
        }

        async with self._lock:
            self._active_connections.append(conn_entry)
            logger.info(
                f"[MTCMS] Accepted TCP connection demand from Client Proxy {peer_ip}:{peer_port}. "
                f"Active return sockets count: {len(self._active_connections)}"
            )

        # Monitor client connection lifecycle
        asyncio.create_task(self._monitor_client_connection(reader, writer, conn_entry))

    async def _monitor_client_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, conn_entry: Dict[str, Any]
    ) -> None:
        """
        Monitors an accepted connection for disconnects and performs immediate cleanup.
        """
        peer_ip = conn_entry["ip"]
        peer_port = conn_entry["port"]
        try:
            while True:
                data = await reader.read(1024)
                if not data:
                    logger.debug(f"[MTCMS] Client {peer_ip}:{peer_port} closed connection (EOF).")
                    break
        except Exception:
            pass
        finally:
            async with self._lock:
                if conn_entry in self._active_connections:
                    self._active_connections.remove(conn_entry)

            try:
                if not writer.is_closing():
                    writer.close()
                    await writer.wait_closed()
            except Exception:
                pass

            logger.info(
                f"[MTCMS] Removed closed connection from {peer_ip}:{peer_port}. "
                f"Remaining active sockets: {len(self._active_connections)}"
            )

    async def send_response_frame(self, session_id: int, payload: bytes, client_host: Optional[str] = None) -> bool:
        """
        Packs payload into binary frame and transmits it over an accepted client socket connection.

        Args:
            session_id (int): 16-bit Session ID.
            payload (bytes): Response payload data.
            client_host (Optional[str]): Optional client IP filter to target specific client socket.

        Returns:
            bool: True if sent successfully, False otherwise.
        """
        frame = pack_frame(session_id, payload)

        async with self._lock:
            if not self._active_connections:
                logger.warning(
                    f"[MTCMS] Session {session_id}: No active accepted client TCP connections available to send return payload!"
                )
                return False

            # Filter candidates if client_host is specified and matching sockets exist
            candidates = self._active_connections
            if client_host:
                matching = [c for c in self._active_connections if c["ip"] == client_host]
                if matching:
                    candidates = matching

            num_candidates = len(candidates)
            start_idx = self._round_robin_idx
            self._round_robin_idx = (self._round_robin_idx + 1) % max(1, num_candidates)

            # Try round-robin send across candidate accepted connections
            for i in range(num_candidates):
                conn = candidates[(start_idx + i) % num_candidates]
                writer: asyncio.StreamWriter = conn["writer"]
                if writer.is_closing():
                    continue

                try:
                    writer.write(frame)
                    await writer.drain()

                    self._bytes_sent += len(payload)
                    self._packets_sent += 1

                    logger.debug(
                        f"[MTCMS] Session {session_id}: Transmitted TCP response frame "
                        f"({len(payload)} bytes) over accepted connection to {conn['ip']}:{conn['port']}"
                    )
                    return True
                except (ConnectionResetError, BrokenPipeError, OSError) as err:
                    logger.warning(f"[MTCMS] Connection write error to {conn['ip']}:{conn['port']}: {err}")

            logger.error(
                f"[MTCMS] Session {session_id}: Failed to deliver TCP return frame across all active client sockets."
            )
            return False

    async def close(self) -> None:
        """
        Stops all listening TCP servers and closes all accepted client connection sockets cleanly.
        """
        for server in self.servers:
            server.close()
            await server.wait_closed()
        self.servers.clear()

        async with self._lock:
            for conn in list(self._active_connections):
                writer: asyncio.StreamWriter = conn["writer"]
                try:
                    if not writer.is_closing():
                        writer.close()
                        await writer.wait_closed()
                except Exception:
                    pass
            self._active_connections.clear()

        logger.info("[MTCMS] Closed all TCP listeners and accepted client return connections.")

    @property
    def metrics(self) -> dict:
        """Returns runtime MTCMS statistics."""
        return {
            "packets_sent": self._packets_sent,
            "bytes_sent": self._bytes_sent,
            "active_connections": len(self._active_connections),
            "listening_ports": self.ports,
        }
