"""
UDPConnectionManagerClient (UCMC) - Outbound UDP Packet Dispatcher.

Responsible ONLY for encapsulating client payload with custom protocol headers 
and transmitting packets over standard non-blocking UDP socket to the Remote Proxy.
Optimized with high-capacity socket send buffers (SO_SNDBUF) for 5G speed bursts.
"""

import socket
import asyncio
import logging
from asymmetric_proxy.utils.protocol import pack_frame
from asymmetric_proxy.config import SOCKET_BUFFER_SIZE, MAX_UDP_PAYLOAD_SIZE

logger = logging.getLogger("asymmetric_proxy.udp_sender")


class UDPConnectionManagerClient:
    """
    UDPConnectionManagerClient (UCMC)
    
    Handles outbound transmit pipeline via UDP to REMOTE_PROXY_HOST:REMOTE_UDP_PORT.
    """

    def __init__(self, remote_host: str, remote_port: int) -> None:
        """
        Initializes UCMC with remote target destination endpoint.

        Args:
            remote_host (str): IP address or hostname of Remote Proxy Server.
            remote_port (int): UDP port number of Remote Proxy Server.
        """
        self.remote_host = remote_host
        self.remote_port = remote_port
        self.remote_addr = (remote_host, remote_port)
        self.transport: asyncio.DatagramTransport | None = None
        self._raw_socket: socket.socket | None = None
        self._bytes_sent = 0
        self._packets_sent = 0

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        """
        Creates and configures the non-blocking UDP socket with optimized 5G send buffers.

        Args:
            loop (asyncio.AbstractEventLoop): The active asyncio event loop.
        """
        # Create non-blocking UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)

        # Tune Socket Send Buffer (SO_SNDBUF) for high-bandwidth 5G bursts
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, SOCKET_BUFFER_SIZE)
            actual_buf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
            logger.info(f"[UCMC] Configured UDP SO_SNDBUF buffer size to {actual_buf} bytes.")
        except Exception as err:
            logger.warning(f"[UCMC] Could not tune SO_SNDBUF buffer: {err}")

        self._raw_socket = sock
        logger.info(f"[UCMC] Initialized UDP Sender socket targeting {self.remote_host}:{self.remote_port}")

    async def send_packet(self, session_id: int, payload: bytes) -> None:
        """
        Encapsulates payload into custom protocol frame and sends via UDP.

        Args:
            session_id (int): Session identifier for tracking.
            payload (bytes): Raw client payload data.
        """
        if not self._raw_socket:
            logger.error("[UCMC] Error: Socket not initialized. Call start() before sending.")
            return

        try:
            loop = asyncio.get_running_loop()
            total_len = len(payload)
            max_chunk = MAX_UDP_PAYLOAD_SIZE if MAX_UDP_PAYLOAD_SIZE > 0 else 1350

            # Chunk payload to avoid exceeding network MTU over UDP
            for offset in range(0, total_len, max_chunk):
                chunk = payload[offset : offset + max_chunk]
                frame = pack_frame(session_id, chunk)
                frame_length = len(frame)

                await loop.sock_sendto(self._raw_socket, frame, self.remote_addr)

                self._bytes_sent += frame_length
                self._packets_sent += 1

                logger.debug(
                    f"[UCMC] Session {session_id}: Wrapped & sent {len(chunk)} bytes payload "
                    f"({frame_length} total frame) via UDP to {self.remote_host}:{self.remote_port}"
                )
        except Exception as exc:
            logger.error(f"[UCMC] Session {session_id}: Error sending UDP packet: {exc}", exc_info=True)

    def close(self) -> None:
        """Closes the underlying UDP socket."""
        if self._raw_socket:
            logger.info("[UCMC] Closing UDP sender socket.")
            self._raw_socket.close()
            self._raw_socket = None

    @property
    def metrics(self) -> dict:
        """Returns runtime performance transmission metrics."""
        return {
            "packets_sent": self._packets_sent,
            "bytes_sent": self._bytes_sent,
            "target": f"{self.remote_host}:{self.remote_port}",
        }
