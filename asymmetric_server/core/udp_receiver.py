"""
UDPConnectionManagerServer (UCMS) - Server UDP Inbound Listener.

Listens on UDP port 9090 to receive incoming outbound proxy frames from the Client Proxy.
Unpacks binary headers, extracts Session IDs & client payload, and dispatches them to TIS.
"""

import asyncio
import socket
import logging
from typing import Optional
from asymmetric_server.core.session_manager import TrafficIdentifierServer
from asymmetric_server.utils.protocol import unpack_frame, HEADER_SIZE
from asymmetric_server import config

logger = logging.getLogger("asymmetric_server.udp_receiver")


class UDPReceiverProtocol(asyncio.DatagramProtocol):
    """Asyncio Datagram Protocol for receiving UDP proxy frames from Client Proxy."""

    def __init__(self, session_manager: TrafficIdentifierServer) -> None:
        self.session_manager = session_manager
        self.transport: Optional[asyncio.DatagramTransport] = None
        self.bytes_received = 0
        self.packets_received = 0

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport
        sock = transport.get_extra_info("socket")
        if sock:
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, config.SOCKET_BUFFER_SIZE)
            except Exception as err:
                logger.warning(f"[UCMS] Failed to set SO_RCVBUF on UDP socket: {err}")
        
        bind_addr = transport.get_extra_info("sockname", "0.0.0.0:9090")
        logger.info(f"[UCMS] Listening for incoming client UDP datagrams on {bind_addr}")

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        client_ip = addr[0]
        self.bytes_received += len(data)
        self.packets_received += 1

        if len(data) < HEADER_SIZE:
            logger.warning(f"[UCMS] Received truncated datagram ({len(data)} bytes) from {addr}. Dropping.")
            return

        result = unpack_frame(data)
        if result is None:
            logger.warning(f"[UCMS] Failed to unpack frame from {addr}. Dropping packet.")
            return

        session_id, payload = result
        logger.debug(
            f"[UCMS] Received UDP frame from Client Proxy {client_ip}:{addr[1]} | "
            f"Session ID: {session_id}, Payload Size: {len(payload)} bytes"
        )

        # Dispatch frame handling asynchronously without blocking datagram loop
        asyncio.create_task(
            self.session_manager.handle_client_payload(session_id, payload, client_ip)
        )

    def error_received(self, exc: Exception) -> None:
        logger.error(f"[UCMS] UDP Protocol error: {exc}")


class UDPConnectionManagerServer:
    """
    UDPConnectionManagerServer (UCMS)

    Wrapper around asyncio datagram endpoint for server UDP listener lifecycle.
    """

    def __init__(self, host: str, port: int, session_manager: TrafficIdentifierServer) -> None:
        self.host = host
        self.port = port
        self.session_manager = session_manager
        self.transport: Optional[asyncio.DatagramTransport] = None
        self.protocol: Optional[UDPReceiverProtocol] = None

    async def start(self) -> None:
        """Binds socket and starts listening for UDP datagrams from Client Proxy."""
        loop = asyncio.get_running_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: UDPReceiverProtocol(self.session_manager),
            local_addr=(self.host, self.port)
        )
        self.transport = transport
        self.protocol = protocol
        logger.info(f"[UCMS] Server UDP receiver running on {self.host}:{self.port}")

    def stop(self) -> None:
        """Stops the UDP receiver transport."""
        if self.transport:
            self.transport.close()
            logger.info("[UCMS] Stopped server UDP listener.")

    @property
    def metrics(self) -> dict:
        """Returns reception statistics."""
        return {
            "packets_received": self.protocol.packets_received if self.protocol else 0,
            "bytes_received": self.protocol.bytes_received if self.protocol else 0,
            "listen_endpoint": f"{self.host}:{self.port}",
        }
