"""
Main Entry Point for Asymmetric Python Proxy Client.

Instantiates and orchestrates all proxy system components:
- TrafficIdentifierFunction (TIF): Session mapping manager
- UDPConnectionManagerClient (UCMC): Outbound UDP transmitter
- MultiTCPConnectionManager (MTCM): Inbound multi-port TCP receiver
- TCPConnectionManagerClient (TCMC): Local application TCP ingress proxy server

Supports optional built-in test loopback remote proxy simulation or direct production operation.
"""

import sys
import os
import asyncio
import logging
import signal

# Ensure current working directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from asymmetric_proxy.config import (
    LOCAL_HOST,
    LOCAL_PORT,
    REMOTE_PROXY_HOST,
    REMOTE_UDP_PORT,
    MTCM_PORTS,
    LOG_LEVEL,
    LOG_FORMAT,
)
from asymmetric_proxy.core.session_manager import TrafficIdentifierFunction
from asymmetric_proxy.core.udp_sender import UDPConnectionManagerClient
from asymmetric_proxy.core.tcp_receiver import MultiTCPConnectionManager
from asymmetric_proxy.core.tcp_client import TCPConnectionManagerClient

# Configure logging
logging.basicConfig(level=getattr(logging, LOG_LEVEL.upper(), logging.DEBUG), format=LOG_FORMAT)
logger = logging.getLogger("asymmetric_proxy.main")


async def main() -> None:
    """
    Main asynchronous startup procedure.
    Initializes components, configures signal handlers, and launches concurrent tasks.
    """
    logger.info("===============================================================")
    logger.info("   Starting Asymmetric Python Proxy Client (5G Optimized)      ")
    logger.info("===============================================================")
    logger.info(f"Local Ingress Proxy:    tcp://{LOCAL_HOST}:{LOCAL_PORT}")
    logger.info(f"Remote Outbound Target: udp://{REMOTE_PROXY_HOST}:{REMOTE_UDP_PORT}")
    logger.info(f"Remote Inbound Ports:   tcp://{LOCAL_HOST}:[{min(MTCM_PORTS)}-{max(MTCM_PORTS)}]")
    logger.info("===============================================================")

    # 1. Instantiate Session Manager (TIF)
    session_manager = TrafficIdentifierFunction()

    # 2. Instantiate UDP Sender (UCMC)
    udp_sender = UDPConnectionManagerClient(
        remote_host=REMOTE_PROXY_HOST,
        remote_port=REMOTE_UDP_PORT
    )
    loop = asyncio.get_running_loop()
    udp_sender.start(loop)

    # 3. Instantiate Multi-TCP Receiver (MTCM)
    tcp_receiver = MultiTCPConnectionManager(
        ports=MTCM_PORTS,
        session_manager=session_manager,
        remote_host=REMOTE_PROXY_HOST
    )

    # 4. Instantiate Local TCP Ingress Proxy (TCMC)
    tcp_client = TCPConnectionManagerClient(
        local_host=LOCAL_HOST,
        local_port=LOCAL_PORT,
        session_manager=session_manager,
        udp_sender=udp_sender
    )

    # Set up graceful shutdown event
    stop_event = asyncio.Event()

    def signal_handler():
        logger.info("\n[MAIN] Shutdown signal received. Stopping Asymmetric Proxy...")
        stop_event.set()

    # Register OS signals if supported on current platform
    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, signal_handler)
            except NotImplementedError:
                pass

    try:
        # Start MTCM multi-port listeners
        await tcp_receiver.start_listeners()

        # Start TCMC local ingress server
        await tcp_client.start()

        logger.info("[MAIN] Asymmetric Proxy System is FULLY ACTIVE and ready for traffic.")
        
        # Keep running until signal received or exception thrown
        await stop_event.wait()

    except Exception as err:
        logger.critical(f"[MAIN] Fatal error in proxy main loop: {err}", exc_info=True)
    finally:
        logger.info("[MAIN] Initiating graceful system teardown...")
        await tcp_client.stop()
        await tcp_receiver.stop()
        udp_sender.close()
        logger.info("[MAIN] Teardown complete. Exiting.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[MAIN] Interrupted by user.")
