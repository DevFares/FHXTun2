"""
MultiTCPConnectionManager (MTCM) - Multi-Port Outbound TCP Stream Connector.

Initiates connection demands to the Remote Proxy Server's return TCP ports (e.g. 2525-2530).
Maintains persistent outbound TCP streams to receive response payload frames,
unpacks binary headers, extracts Session IDs, and forwards data back to local application sockets via TIF.
"""

import asyncio
import socket
import logging
from typing import Sequence, List, Set, Optional
from asymmetric_proxy.core.session_manager import TrafficIdentifierFunction
from asymmetric_proxy.utils.protocol import unpack_header, HEADER_SIZE
from asymmetric_proxy.utils.obfuscation import deobfuscate_stream
from asymmetric_proxy.utils.packet_logger import packet_logger
from asymmetric_proxy import config

logger = logging.getLogger("asymmetric_proxy.tcp_receiver")


class MultiTCPConnectionManager:
    """
    MultiTCPConnectionManager (MTCM)

    Establishes and maintains TCP stream connections to the Remote Proxy Server's return ports.
    Receives incoming response frames and routes payload data back to local application sockets.
    """

    def __init__(
        self,
        ports: Sequence[int],
        session_manager: TrafficIdentifierFunction,
        remote_host: str = "127.0.0.1",
        host: Optional[str] = None
    ) -> None:
        """
        Initializes MTCM.

        Args:
            ports (Sequence[int]): Port range to connect to on Remote Proxy (e.g. range(2525, 2531)).
            session_manager (TrafficIdentifierFunction): Shared session manager instance (TIF).
            remote_host (str): Remote Proxy Server IP host address.
            host (Optional[str]): Legacy bind host parameter kept for compatibility.
        """
        self.ports = list(ports)
        self.session_manager = session_manager
        self.remote_host = remote_host or host or "127.0.0.1"
        self._connection_tasks: List[asyncio.Task] = []
        self._active_writers: Set[asyncio.StreamWriter] = set()
        self._running = False
        self._bytes_received = 0
        self._packets_received = 0

    async def start_listeners(self) -> None:
        """
        Launches connection demand loops across all configured return ports.
        (Maintained alias for system compatibility)
        """
        await self.start_connectors()

    async def start_connectors(self) -> None:
        """
        Initiates outbound TCP return stream connection demands to the Remote Proxy Server.
        """
        self._running = True
        for port in self.ports:
            task = asyncio.create_task(self._connection_loop(port))
            self._connection_tasks.append(task)
        logger.info(
            f"[MTCM] Launched TCP return stream connection demands to Remote Proxy {self.remote_host} on ports {self.ports}"
        )

    async def _connection_loop(self, port: int) -> None:
        """
        Maintains a persistent connection demand loop to Remote Proxy Server on (remote_host, port).
        """
        while self._running:
            try:
                logger.debug(f"[MTCM] Connecting return stream demand to Remote Proxy at {self.remote_host}:{port}...")
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.remote_host, port),
                    timeout=5.0
                )

                # Set 5G low-latency socket options
                sock = writer.get_extra_info("socket")
                if sock:
                    try:
                        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, config.SOCKET_BUFFER_SIZE)
                    except Exception as err:
                        logger.warning(f"[MTCM] Socket option error on port {port}: {err}")

                self._active_writers.add(writer)
                logger.info(f"[MTCM] Connected TCP return channel demand to Remote Proxy {self.remote_host}:{port}")

                await self._read_stream(reader, writer, port)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug(f"[MTCM] Connection demand to {self.remote_host}:{port} failed/disconnected: {exc}. Retrying...")

            if self._running:
                await asyncio.sleep(1.0)

    async def _read_stream(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, port: int) -> None:
        """
        Reads and unpacks response binary frames from an active return stream.
        """
        buffer = bytearray()
        try:
            while self._running:
                chunk = await reader.read(config.CHUNK_READ_SIZE)
                if not chunk:
                    logger.debug(f"[MTCM] Remote Proxy {self.remote_host}:{port} closed TCP return stream.")
                    break

                if getattr(config, "WRITE_RECEIVED_PACKETS_FULL", False):
                    packet_logger.log_full_packet(port, chunk)

                buffer.extend(chunk)

                # Frame decoding loop
                while True:
                    is_obfuscated_active = getattr(config, "HTTP_OBFUSCATION_ENABLED", False) or buffer.startswith(b"HTTP/") or b"HTTP/1." in buffer[:32]

                    if is_obfuscated_active:
                        frames = deobfuscate_stream(buffer)
                        if not frames:
                            break
                        for session_id, payload in frames:
                            if getattr(config, "WRITE_RECEIVED_PACKETS_DATA", False):
                                packet_logger.log_data_packet(session_id, payload)

                            payload_len = len(payload)
                            self._bytes_received += payload_len
                            self._packets_received += 1

                            logger.debug(
                                f"[MTCM] Session {session_id}: Received obfuscated response frame ({payload_len} bytes) from port {port}"
                            )

                            # Route to local application socket via TIF
                            client_writer = await self.session_manager.get_session_writer(session_id)
                            if client_writer and not client_writer.is_closing():
                                try:
                                    if payload_len == 0:
                                        logger.info(f"[MTCM] Session {session_id}: Target remote server EOF frame received. Closing local session.")
                                        await self.session_manager.close_session(session_id)
                                    else:
                                        client_writer.write(payload)
                                        await client_writer.drain()
                                        logger.debug(
                                            f"[MTCM] Session {session_id}: Forwarded {payload_len} bytes to Local Application socket."
                                        )
                                except (ConnectionResetError, BrokenPipeError, OSError) as conn_err:
                                    logger.warning(f"[MTCM] Session {session_id}: Local client socket reset: {conn_err}")
                                    await self.session_manager.close_session(session_id)
                            else:
                                logger.warning(f"[MTCM] Session {session_id}: Orphaned/closed session frame dropped.")
                    else:
                        if len(buffer) < HEADER_SIZE:
                            break
                        session_id, payload_len = unpack_header(buffer)
                        total_frame_len = HEADER_SIZE + payload_len

                        if len(buffer) < total_frame_len:
                            break

                        payload = bytes(buffer[HEADER_SIZE:total_frame_len])
                        del buffer[:total_frame_len]

                        self._bytes_received += payload_len
                        self._packets_received += 1

                        logger.debug(
                            f"[MTCM] Session {session_id}: Received response frame ({payload_len} bytes) from port {port}"
                        )

                        # Route to local application socket via TIF
                        client_writer = await self.session_manager.get_session_writer(session_id)
                        if client_writer and not client_writer.is_closing():
                            try:
                                if payload_len == 0:
                                    logger.info(f"[MTCM] Session {session_id}: Target remote server EOF frame received. Closing local session.")
                                    await self.session_manager.close_session(session_id)
                                else:
                                    client_writer.write(payload)
                                    await client_writer.drain()
                                    logger.debug(
                                        f"[MTCM] Session {session_id}: Forwarded {payload_len} bytes to Local Application socket."
                                    )
                            except (ConnectionResetError, BrokenPipeError, OSError) as conn_err:
                                logger.warning(f"[MTCM] Session {session_id}: Local client socket reset: {conn_err}")
                                await self.session_manager.close_session(session_id)
                        else:
                            logger.warning(f"[MTCM] Session {session_id}: Orphaned/closed session frame dropped.")

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error(f"[MTCM] Error reading return stream on port {port}: {exc}")
        finally:
            self._active_writers.discard(writer)
            try:
                if not writer.is_closing():
                    writer.close()
                    await writer.wait_closed()
            except Exception:
                pass

    async def stop(self) -> None:
        """
        Stops all active connection demand loops and closes return streams cleanly.
        """
        self._running = False
        for task in self._connection_tasks:
            if not task.done():
                task.cancel()

        for writer in list(self._active_writers):
            try:
                if not writer.is_closing():
                    writer.close()
                    await writer.wait_closed()
            except Exception:
                pass
        self._active_writers.clear()
        self._connection_tasks.clear()
        logger.info("[MTCM] All TCP return stream demand tasks and sockets stopped.")

    @property
    def metrics(self) -> dict:
        """Returns runtime performance reception metrics."""
        return {
            "packets_received": self._packets_received,
            "bytes_received": self._bytes_received,
            "target_ports": self.ports,
            "active_sockets_count": len(self._active_writers),
        }
