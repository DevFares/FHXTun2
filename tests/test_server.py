"""
Unit and Integration Tests for Asymmetric Python Proxy Server.
"""

import asyncio
import unittest
import struct
from asymmetric_server.utils.protocol import pack_frame, unpack_header, unpack_frame
from asymmetric_server.core.tcp_sender import MultiTCPConnectionManagerServer
from asymmetric_server.core.session_manager import TrafficIdentifierServer, ServerSession


class TestServerProtocol(unittest.TestCase):
    def test_pack_and_unpack_server_frame(self):
        session_id = 101
        payload = b"Server response traffic payload"
        frame = pack_frame(session_id, payload)

        self.assertEqual(len(frame), 4 + len(payload))
        unpacked_id, length = unpack_header(frame[:4])
        self.assertEqual(unpacked_id, session_id)
        self.assertEqual(length, len(payload))

        unpacked = unpack_frame(frame)
        self.assertIsNotNone(unpacked)
        if unpacked:
            sid, p = unpacked
            self.assertEqual(sid, session_id)
            self.assertEqual(p, payload)


class TestServerSessionManager(unittest.IsolatedAsyncioTestCase):
    async def test_tis_socks5_greeting_flow(self):
        class MockTCPSender:
            def __init__(self):
                self.sent_frames = []

            async def send_response_frame(self, session_id, payload, client_host=None):
                self.sent_frames.append((session_id, payload, client_host))
                return True

        sender = MockTCPSender()
        tis = TrafficIdentifierServer(tcp_sender=sender)  # type: ignore

        # 1. Send SOCKS5 greeting (0x05 0x01 0x00)
        session_id = 88
        greeting_payload = b"\x05\x01\x00"
        await tis.handle_client_payload(session_id, greeting_payload, "127.0.0.1")

        self.assertIn(session_id, tis.sessions)
        self.assertEqual(tis.sessions[session_id].state, "SOCKS_GREETING")
        self.assertEqual(len(sender.sent_frames), 1)

        # Expect reply 0x05 0x00 (SOCKS5 No Auth)
        reply_sid, reply_payload, reply_ip = sender.sent_frames[0]
        self.assertEqual(reply_sid, session_id)
        self.assertEqual(reply_payload, b"\x05\x00")

        # Clean up
        await tis.close_session(session_id)
        self.assertNotIn(session_id, tis.sessions)


class TestMTCMS(unittest.IsolatedAsyncioTestCase):
    async def test_mtcms_listening_and_accepted_socket_transmission(self):
        # 1. Start MTCMS on port 2528
        mtcms = MultiTCPConnectionManagerServer(bind_host="127.0.0.1", ports=[2528])
        await mtcms.start()

        try:
            # 2. Client connects to server MTCMS listener
            reader, writer = await asyncio.open_connection("127.0.0.1", 2528)
            await asyncio.sleep(0.05)  # Allow server to process connection acceptance

            self.assertEqual(len(mtcms._active_connections), 1)

            # 3. MTCMS sends response frame over accepted connection
            session_id = 99
            payload = b"MTCMS return payload data"
            sent = await mtcms.send_response_frame(session_id, payload)
            self.assertTrue(sent)

            # 4. Verify client received frame
            received_frame = await asyncio.wait_for(reader.read(1024), timeout=2.0)
            self.assertGreater(len(received_frame), 4)

            sid, p = unpack_frame(received_frame)
            self.assertEqual(sid, session_id)
            self.assertEqual(p, payload)

            writer.close()
            await writer.wait_closed()
        finally:
            await mtcms.close()


if __name__ == "__main__":
    unittest.main()
