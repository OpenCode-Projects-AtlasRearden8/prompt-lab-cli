import unittest
from unittest import mock

import promptlab.runner as runner

from helpers import EndpointMixin


class RenderTests(unittest.TestCase):
    def test_placeholder_filling(self):
        rendered, used = runner.render("Explain {{input}} simply.", "chess openings")
        self.assertEqual(rendered, "Explain chess openings simply.")
        self.assertTrue(used)

    def test_missing_placeholder_flagged(self):
        rendered, used = runner.render("Say hello warmly.", "whatever")
        self.assertEqual(rendered, "Say hello warmly.")
        self.assertFalse(used)

    def test_repeat_placeholder(self):
        rendered, _ = runner.render("{{input}} — yes, {{input}}.", "cats")
        self.assertEqual(rendered, "cats — yes, cats.")


class ChatMockedTests(unittest.TestCase):
    """Patches the socket layer so no network happens at all."""

    def test_chat_happy_path(self):
        response = '{"choices": [{"message": {"content": "hello back"}}]}'
        with mock.patch.object(runner, "send_json", return_value=(200, response)):
            result = runner.chat(
                "http://localhost:11434/v1", "fake-model", "hi there", timeout=5
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["content"], "hello back")
        self.assertGreaterEqual(result["latency"], 0.0)

    def test_chat_sends_expected_payload(self):
        captured = {}

        def fake_send_json(url, payload=None, method="POST", timeout=60.0):
            captured["url"] = url
            captured["payload"] = payload
            return 200, '{"choices": [{"message": {"content": "ok"}}]}'

        with mock.patch.object(runner, "send_json", side_effect=fake_send_json):
            runner.chat(
                "http://localhost:11434/v1",
                "fake-model",
                "user text",
                system="be nice",
                temperature=0.5,
                max_tokens=32,
                timeout=7,
            )
        self.assertEqual(captured["url"], "http://localhost:11434/v1/chat/completions")
        payload = captured["payload"]
        self.assertEqual(payload["model"], "fake-model")
        self.assertEqual(payload["temperature"], 0.5)
        self.assertEqual(payload["max_tokens"], 32)
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(payload["messages"][1]["role"], "user")
        self.assertEqual(payload["messages"][1]["content"], "user text")

    def test_chat_http_error_is_friendly(self):
        import urllib.error

        err = urllib.error.HTTPError(
            "url", 500, "oops", None, None
        )

        def fake_send_json(*args, **kwargs):
            raise err

        with mock.patch.object(runner, "send_json", side_effect=fake_send_json):
            result = runner.chat("http://localhost:11434/v1", "m", "x")
        self.assertFalse(result["ok"])
        self.assertIn("500", result["error"])

    def test_chat_connection_error_is_friendly(self):
        import urllib.error

        with mock.patch.object(
            runner, "send_json", side_effect=urllib.error.URLError("connection refused")
        ):
            result = runner.chat("http://localhost:9999/v1", "m", "x")
        self.assertFalse(result["ok"])
        self.assertIn("Could not reach", result["error"])
        self.assertIn("Is the server running", result["error"])

    def test_chat_garbage_response_is_friendly(self):
        with mock.patch.object(runner, "send_json", return_value=(200, "not json at all")):
            result = runner.chat("http://localhost:11434/v1", "m", "x")
        self.assertFalse(result["ok"])
        self.assertIn("parse", result["error"])

    def test_chat_schemaless_response_is_friendly(self):
        with mock.patch.object(runner, "send_json", return_value=(200, '{"wrong": ["shape"]}')):
            result = runner.chat("http://localhost:11434/v1", "m", "x")
        self.assertFalse(result["ok"])


class ChatRealServerTests(EndpointMixin):
    """Full socket round-trip against a localhost fake endpoint. No network."""

    def test_chat_posts_and_parses(self):
        self.clear_requests()
        result = runner.chat(self.base_url, "fake-small", "tell me about chess", timeout=5)
        self.assertTrue(result["ok"])
        self.assertEqual(result["content"], "echo: tell me about chess")
        payload = self.last_request_payload()
        self.assertEqual(payload["model"], "fake-small")
        self.assertEqual(payload["messages"][0]["role"], "user")
        headers = self.last_request_headers()
        self.assertNotIn("Authorization", headers)
        self.assertNotIn("Api-Key", headers)

    def test_list_models(self):
        models = runner.list_models(self.base_url)
        self.assertEqual(models, ["fake-large", "fake-small"])

    def test_broken_endpoint_reports_error(self):
        import urllib.error

        with mock.patch.object(runner, "send_json", side_effect=urllib.error.HTTPError(
            self.base_url, 500, "oops", None, None
        )):
            result = runner.chat(self.base_url, "m", "x")
        self.assertFalse(result["ok"])

    def test_no_server_listening_reports_error(self):
        result = runner.chat("http://127.0.0.1:1/v1", "m", "x", timeout=2)
        self.assertFalse(result["ok"])
        self.assertIn("Could not reach", result["error"])


if __name__ == "__main__":
    unittest.main()
