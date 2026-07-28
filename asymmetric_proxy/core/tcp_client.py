"""
TCPConnectionManagerClient (TCMC) - Local Application Proxy Ingress Server.

Listens on LOCAL_HOST:LOCAL_PORT (e.g., 127.0.0.1:1080) for incoming TCP connections 
from local applications, browsers, or client software. Registers each connection with 
the TrafficIdentifierFunction (TIF), reads client data in chunks, and dispatches 
it to the UDPConnectionManagerClient (UCMC) for outbound asymmetric transmission.
"""

import asyncio
import socket
import logging
from asymmetric_proxy.core.session_manager import TrafficIdentifierFunction
from asymmetric_proxy.core.udp_sender import UDPConnectionManagerClient
from asymmetric_proxy.config import SOCKET_BUFFER_SIZE, CHUNK_READ_SIZE

logger = logging.getLogger("asymmetric_proxy.tcp_client")


class TCPConnectionManagerClient:
    """
    TCPConnectionManagerClient (TCMC)
    
    Serves as the local TCP entry point for applications directing traffic through the proxy.
    """

    def __init__(
        self,
        local_host: str,
        local_port: int,
        session_manager: TrafficIdentifierFunction,
        udp_sender: UDPConnectionManagerClient,
    ) -> None:
        """
        Initializes the Local TCP Proxy Ingress Server.

        Args:
            local_host (str): Local host IP to bind (e.g. "127.0.0.1").
            local_port (int): Local port to listen on (e.g. 1080).
            session_manager (TrafficIdentifierFunction): Shared session manager instance (TIF).
            udp_sender (UDPConnectionManagerClient): Shared UDP sender instance (UCMC).
        """
        self.local_host = local_host
        self.local_port = local_port
        self.session_manager = session_manager
        self.udp_sender = udp_sender
        self.server: asyncio.Server | None = None
        self._total_connections_handled = 0

    async def start(self) -> None:
        """
        Binds and starts the Local TCP Proxy Server listener with 5G socket optimizations.
        """
        try:
            # Custom socket creation to apply socket options before bind
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # Enable TCP_NODELAY (Disable Nagle's algorithm)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

            # Increase socket receive/send buffers for high 5G throughput
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, SOCKET_BUFFER_SIZE)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, SOCKET_BUFFER_SIZE)
            except Exception as err:
                logger.warning(f"[TCMC] Failed to set buffer sizes on socket: {err}")

            sock.bind((self.local_host, self.local_port))
            sock.listen(128)
            sock.setblocking(False)

            self.server = await asyncio.start_server(
                self._handle_client_connection,
                sock=sock
            )
            logger.info(
                f"[TCMC] Local TCP Ingress Proxy Server listening on "
                f"tcp://{self.local_host}:{self.local_port} (Ready for local apps)"
            )
        except Exception as exc:
            logger.critical(
                f"[TCMC] Critical Failure starting Local TCP Ingress Proxy Server on "
                f"{self.local_host}:{self.local_port}: {exc}",
                exc_info=True
            )
            raise

    async def _handle_client_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """
        Handles a newly accepted local application TCP connection.

        Args:
            reader (asyncio.StreamReader): Local client StreamReader.
            writer (asyncio.StreamWriter): Local client StreamWriter.
        """
        self._total_connections_handled += 1
        peername = writer.get_extra_info("peername", ("127.0.0.1", 0))

        # Enable TCP_NODELAY on connection socket
        sock = writer.get_extra_info("socket")
        if sock:
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except Exception:
                pass

        session_id = 0
        read_error = False
        try:
            # Register session with TIF
            session_id = await self.session_manager.create_session(writer)
            logger.info(f"[TCMC] Session {session_id}: Registered local connection from {peername}")

            # Continuously read incoming local application data and dispatch via UDP
            while True:
                data = await reader.read(CHUNK_READ_SIZE)
                if not data:
                    logger.info(
                        f"[TCMC] Session {session_id}: Local application sent EOF (half-closed upload). "
                        f"Request read loop finished."
                    )
                    break

                data_len = len(data)
                logger.debug(
                    f"[TCMC] Session {session_id}: Received {data_len} bytes from Local App {peername}. "
                    f"Forwarding to UCMC..."
                )

                # Send packet via UCMC UDP sender
                await self.udp_sender.send_packet(session_id, data)

        except asyncio.CancelledError:
            read_error = True
            logger.debug(f"[TCMC] Session {session_id}: Task cancelled.")
        except ConnectionResetError:
            read_error = True
            logger.warning(f"[TCMC] Session {session_id}: Local client connection reset by peer.")
        except Exception as exc:
            read_error = True
            logger.error(f"[TCMC] Session {session_id}: Error reading from local client {peername}: {exc}", exc_info=True)
        finally:
            if session_id > 0:
                if read_error or writer.is_closing():
                    await self.session_manager.close_session(session_id)
                else:
                    logger.debug(
                        f"[TCMC] Session {session_id}: Request upload finished. "
                        f"Session remains active for downloading response data."
                    )

    async def stop(self) -> None:
        """Stops the Local TCP Proxy Server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
            logger.info("[TCMC] Local TCP Ingress Proxy Server stopped.")

    @property
    def total_connections(self) -> int:
        """Total connections accepted since startup."""
        return self._total_connections_handled
