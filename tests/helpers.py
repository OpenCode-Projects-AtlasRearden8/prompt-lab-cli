"""Shared test helpers: temp libraries and a fake OpenAI-compatible endpoint
running on localhost (no network access, no API keys, fully offline)."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROMPT_TEXT = "Explain {{input}} in one friendly sentence."

T = threading.Lock()


def make_library(tmp_root):
    """Create an initialized empty library; return its Path."""
    root = tmp_root / "lib"
    (root / "prompts").mkdir(parents=True)
    return root


class FakeChatHandler(BaseHTTPRequestHandler):
    """http://localhost chat/completions + /models, echoing the prompt back."""

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            body = {"data": [{"id": "fake-small"}, {"id": "fake-large"}]}
            self._send_json(body)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path.rstrip("/").endswith("/chat/completions"):
            with T:
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length))
                received = dict(self.headers)
                requests_pool.append((received, payload))
                user = payload["messages"][-1]["content"]
                self._send_json(
                    {"choices": [{"message": {"role": "assistant", "content": f"echo: {user}"}}]}
                )
        else:
            self.send_error(404)

    def _send_json(self, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class BrokenHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        self.send_response(500)
        body = b'{"error": {"message": "boom"}}'
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


requests_pool = []


class EndpointMixin(unittest.TestCase):
    """Starts a local fake endpoint for tests that exercise real sockets."""

    handler = FakeChatHandler

    @classmethod
    def setUpClass(cls):
        with T:
            requests_pool.clear()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), cls.handler)
        cls.port = cls.server.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}/v1"
        thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def last_request_payload(self):
        with T:
            return requests_pool[-1][1]

    def last_request_headers(self):
        with T:
            return requests_pool[-1][0]

    def clear_requests(self):
        with T:
            requests_pool.clear()
