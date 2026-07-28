"""
Unit tests for Asymmetric Proxy Server Web Configuration Interface & REST API.
"""

import unittest
import json
import os
from asymmetric_server.config import (
    load_server_config_file,
    save_server_config_file,
    SERVER_CONFIG_FILE_PATH,
)
import asymmetric_server.web_config.web_config_server as server_web
HAS_FLASK = server_web.HAS_FLASK
app = getattr(server_web, "app", None)


class TestServerWebConfig(unittest.TestCase):
    def test_load_and_save_server_config(self):
        original = load_server_config_file()
        test_patch = {"log_level": "INFO"}
        
        saved = save_server_config_file(test_patch)
        self.assertTrue(saved)
        
        reloaded = load_server_config_file()
        self.assertEqual(reloaded.get("log_level"), "INFO")
        
        # Restore original
        save_server_config_file(original)

    def test_flask_api_routes(self):
        if not HAS_FLASK or app is None:
            self.skipTest("Flask is not installed in this environment.")
            
        client = app.test_client()
        
        # Test GET /
        resp_index = client.get("/")
        self.assertEqual(resp_index.status_code, 200)
        self.assertIn(b"Asymmetric Proxy Server Configuration Editor", resp_index.data)
        
        # Test GET /api/config
        resp_get = client.get("/api/config")
        self.assertEqual(resp_get.status_code, 200)
        data = json.loads(resp_get.data)
        self.assertIn("bind_udp_port", data)
        
        # Test POST /api/config
        original = data.copy()
        post_data = {"socket_timeout": 45}
        resp_post = client.post("/api/config", json=post_data)
        self.assertEqual(resp_post.status_code, 200)
        post_res = json.loads(resp_post.data)
        self.assertTrue(post_res.get("success"))
        
        # Verify update
        resp_get_updated = client.get("/api/config")
        updated_data = json.loads(resp_get_updated.data)
        self.assertEqual(updated_data.get("socket_timeout"), 45)
        
        # Restore original
        client.post("/api/config", json=original)


if __name__ == "__main__":
    unittest.main()
