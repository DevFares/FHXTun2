"""
TrafficIdentifierFunction (TIF) - Thread-Safe & Async-Safe Session Manager.

Maintains active session states mapping 16-bit Session IDs (1-65535) to active 
asyncio.StreamWriter client socket handles. Handles atomic ID allocation, thread-safe 
lookups, and clean resource teardowns.
"""

import asyncio
import logging
import random
from typing import Dict, Optional, List

logger = logging.getLogger("asymmetric_proxy.session_manager")


class TrafficIdentifierFunction:
    """
    TrafficIdentifierFunction (TIF)
    
    Thread-safe / Async-safe mapping table maintaining associations between
    16-bit integer Session IDs and local client asyncio.StreamWriter connections.
    """

    def __init__(self, min_id: int = 1, max_id: int = 65535) -> None:
        """
        Initializes the TrafficIdentifierFunction.

        Args:
            min_id (int): Minimum session ID boundary (default: 1).
            max_id (int): Maximum session ID boundary (default: 65535).
        """
        self._sessions: Dict[int, asyncio.StreamWriter] = {}
        self._lock = asyncio.Lock()
        self._min_id = min_id
        self._max_id = max_id
        self._counter = min_id
        self._total_sessions_created = 0

    async def create_session(self, writer: asyncio.StreamWriter) -> int:
        """
        Generates a unique 16-bit Session ID and registers the client StreamWriter connection.

        Args:
            writer (asyncio.StreamWriter): Active StreamWriter socket object for the local client.

        Returns:
            int: The assigned unique 16-bit Session ID (1 to 65535).

        Raises:
            RuntimeError: If all 65,535 session slots are exhausted.
        """
        async with self._lock:
            # Check capacity
            if len(self._sessions) >= (self._max_id - self._min_id + 1):
                logger.error("[TIF] Critical: Session ID pool exhausted! All slots active.")
                raise RuntimeError("Session table capacity reached (65535 concurrent active sessions).")

            # Sequential allocation with collision avoidance
            attempts = 0
            max_attempts = self._max_id - self._min_id + 1
            while attempts < max_attempts:
                candidate_id = self._counter
                self._counter = self._min_id if self._counter >= self._max_id else self._counter + 1
                attempts += 1

                if candidate_id not in self._sessions:
                    self._sessions[candidate_id] = writer
                    self._total_sessions_created += 1
                    peername = writer.get_extra_info("peername")
                    logger.info(
                        f"[TIF] Session {candidate_id} CREATED for client {peername}. "
                        f"Active sessions count: {len(self._sessions)}"
                    )
                    return candidate_id

            raise RuntimeError("Failed to allocate a unique Session ID.")

    async def get_session_writer(self, session_id: int) -> Optional[asyncio.StreamWriter]:
        """
        Retrieves the asyncio.StreamWriter corresponding to the given Session ID.

        Args:
            session_id (int): The 16-bit Session ID to look up.

        Returns:
            Optional[asyncio.StreamWriter]: The matching writer instance or None if not found.
        """
        async with self._lock:
            writer = self._sessions.get(session_id)
            if writer is None:
                logger.warning(f"[TIF] Session ID {session_id} lookup failed - session not found or already closed.")
            else:
                logger.debug(f"[TIF] Session ID {session_id} lookup successful.")
            return writer

    async def close_session(self, session_id: int) -> None:
        """
        Removes session mapping and cleanly closes the underlying client connection.

        Args:
            session_id (int): The Session ID to close and dereference.
        """
        async with self._lock:
            writer = self._sessions.pop(session_id, None)

        if writer:
            peername = writer.get_extra_info("peername", "unknown")
            logger.info(f"[TIF] Session {session_id} CLOSING connection for {peername}.")
            try:
                if not writer.is_closing():
                    writer.close()
                    await writer.wait_closed()
            except Exception as exc:
                logger.debug(f"[TIF] Error during socket cleanup for Session {session_id}: {exc}")
            finally:
                logger.info(f"[TIF] Session {session_id} cleanly removed. Active remaining: {len(self._sessions)}")
        else:
            logger.debug(f"[TIF] close_session called for non-existent or already closed Session {session_id}.")

    async def get_active_count(self) -> int:
        """Returns current number of active mapped sessions."""
        async with self._lock:
            return len(self._sessions)

    async def get_active_session_ids(self) -> List[int]:
        """Returns a snapshot list of currently active session IDs."""
        async with self._lock:
            return list(self._sessions.keys())

    @property
    def total_sessions_created(self) -> int:
        """Total sessions created since startup."""
        return self._total_sessions_created
