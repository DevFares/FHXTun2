"""
Main Entry Point for Asymmetric Python Proxy Server.

Stitches together:
- UDPConnectionManagerServer (UCMS) on UDP 9090
- MultiTCPConnectionManagerServer (MTCMS) connecting back to TCP ports 2525-2530
- TrafficIdentifierServer (TIS) managing target connections & SOCKS5 parsing
"""

import asyncio
import logging
import signal
import sys
from asymmetric_server import config
from asymmetric_server.core.tcp_sender import MultiTCPConnectionManagerServer
from asymmetric_server.core.session_manager import TrafficIdentifierServer
from asymmetric_server.core.udp_receiver import UDPConnectionManagerServer

# Setup logging
logging.basicConfig(level=getattr(logging, config.LOG_LEVEL, logging.INFO), format=config.LOG_FORMAT)
logger = logging.getLogger("asymmetric_server.main")


async def async_main() -> None:
    """Asynchronous main loop for running the Remote Proxy Server."""
    print("==================================================================")
    print("      Starting Asymmetric Python Proxy Server (Remote Server)     ")
    print("==================================================================")
    print(f"  [UDP Inbound Listener]  : {config.BIND_UDP_HOST}:{config.BIND_UDP_PORT}")
    print(f"  [TCP Return Listener]   : {config.BIND_TCP_HOST}:{list(config.BIND_TCP_PORTS)}")
    print(f"  [Max Active Sessions]   : {config.MAX_ACTIVE_SESSIONS}")
    print(f"  [Socket Buffer Size]    : {config.SOCKET_BUFFER_SIZE} Bytes")
    print(f"  [Log Verbosity Level]   : {config.LOG_LEVEL}")
    print("==================================================================\n")

    # 1. Initialize MTCMS (TCP Multi-Port Inbound Return Listener)
    tcp_sender = MultiTCPConnectionManagerServer(
        bind_host=config.BIND_TCP_HOST,
        ports=config.BIND_TCP_PORTS
    )
    await tcp_sender.start()

    # 2. Initialize TIS (Session & Target Outbound Proxy Manager)
    session_manager = TrafficIdentifierServer(tcp_sender=tcp_sender)

    # 3. Initialize UCMS (UDP Inbound Receiver)
    udp_receiver = UDPConnectionManagerServer(
        host=config.BIND_UDP_HOST,
        port=config.BIND_UDP_PORT,
        session_manager=session_manager
    )

    # Start UDP receiver
    await udp_receiver.start()

    # Event to handle shutdown signal
    stop_event = asyncio.Event()

    def _shutdown_signal_handler():
        logger.info("[SERVER] Shutdown signal received. Stopping server components...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _shutdown_signal_handler)
            except NotImplementedError:
                pass

    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        logger.info("[SERVER] KeyboardInterrupt caught. Shutting down...")
    finally:
        udp_receiver.stop()
        await session_manager.close_all()
        await tcp_sender.close()
        logger.info("[SERVER] Asymmetric Proxy Server stopped cleanly.")


def main() -> None:
    """Synchronous launcher entry point."""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\n[SERVER] Server process terminated by user.")


if __name__ == "__main__":
    main()
