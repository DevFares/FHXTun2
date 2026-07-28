"""
Unit and Integration Tests for Asymmetric Python Proxy Client.
"""

import asyncio
import unittest
import struct
from asymmetric_proxy.utils.protocol import pack_frame, unpack_header, unpack_frame
from asymmetric_proxy.core.session_manager import TrafficIdentifierFunction


class TestProtocol(unittest.TestCase):
    def test_pack_and_unpack_frame(self):
        session_id = 42
        payload = b"Hello Asymmetric 5G World!"
        frame = pack_frame(session_id, payload)

        self.assertEqual(len(frame), 4 + len(payload))
        
        unpacked_id, length = unpack_header(frame[:4])
        self.assertEqual(unpacked_id, session_id)
        self.assertEqual(length, len(payload))

        result = unpack_frame(frame)
        self.assertIsNotNone(result)
        res_id, res_payload = result
        self.assertEqual(res_id, session_id)
        self.assertEqual(res_payload, payload)


class TestSessionManager(unittest.IsolatedAsyncioTestCase):
    async def test_session_lifecycle(self):
        tif = TrafficIdentifierFunction()
        
        # Mock StreamWriter class
        class MockWriter:
            def __init__(self):
                self.closed = False
            def get_extra_info(self, key, default=None):
                return ("127.0.0.1", 12345)
            def is_closing(self):
                return self.closed
            def close(self):
                self.closed = True
            async def wait_closed(self):
                pass

        writer = MockWriter()
        session_id = await tif.create_session(writer) # type: ignore
        self.assertGreaterEqual(session_id, 1)
        self.assertLessEqual(session_id, 65535)

        retrieved_writer = await tif.get_session_writer(session_id)
        self.assertEqual(retrieved_writer, writer)

        await tif.close_session(session_id)
        retrieved_after_close = await tif.get_session_writer(session_id)
        self.assertIsNone(retrieved_after_close)


if __name__ == "__main__":
    unittest.main()
