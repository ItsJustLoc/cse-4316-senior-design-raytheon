"""Exercise the browser API through HTTP and the actual Ollama adapter."""

import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from test_nlp_parser import OllamaStub

from nlp.client import OllamaConfig
from nlp.parser import IntentParser
from nlp.server import create_server


class BrowserAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ollama = OllamaStub().__enter__()
        parser = IntentParser(OllamaConfig(model="test", base_url=cls.ollama.url))
        cls.server = create_server(parser, "127.0.0.1", 0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.ollama.__exit__()

    def post(self, payload, **headers):
        request = Request(self.url + "/api/interpret", data=json.dumps(payload).encode(),
                          headers={"Content-Type": "application/json", "Origin": self.url, **headers})
        try:
            response = urlopen(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_assets_are_served_with_safe_headers(self):
        for path, content_type in (("/", "text/html"), ("/app.js", "text/javascript"),
                                   ("/style.css", "text/css")):
            with self.subTest(path=path), urlopen(self.url + path) as response:
                self.assertEqual(response.status, 200)
                self.assertTrue(response.headers["Content-Type"].startswith(content_type))
                self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
                self.assertGreater(len(response.read()), 0)

    def test_browser_input_reaches_ollama_and_returns_proposal(self):
        status, result = self.post({"text": "Retrieve the blue box.", "current_mission": None})
        self.assertEqual(status, 200)
        self.assertEqual(result["interpretation"]["mission"]["target"]["color"], "blue")

    def test_rejects_invalid_body_context_origin_and_content_type(self):
        for payload, headers, expected in (
            ({"text": " "}, {}, 400),
            ({"text": 42}, {}, 400),
            ({"text": "x", "execute": True}, {}, 400),
            ({"text": "x", "current_mission": {"action": "drive"}}, {}, 400),
            ({"text": "x"}, {"Origin": "https://untrusted.invalid"}, 403),
            ({"text": "x"}, {"Content-Type": "text/plain"}, 415),
            ({"text": "x" * 65537}, {}, 413),
            (["not", "an", "object"], {}, 400),
        ):
            with self.subTest(expected=expected, headers=headers):
                status, result = self.post(payload, **headers)
                self.assertEqual(status, expected)
                self.assertIn("error", result)

    def test_unrecognized_host_is_rejected(self):
        status, result = self.post({"text": "x"}, Host="untrusted.invalid")
        self.assertEqual(status, 403)
        self.assertIn("error", result)

    def test_busy_server_rejects_instead_of_queuing_inference(self):
        with self.server.inference_lock:
            status, result = self.post({"text": "Retrieve the blue box."})
        self.assertEqual(status, 503)
        self.assertEqual(result["error"]["code"], "busy")

    def test_model_unavailable_is_an_error_not_a_mission(self):
        self.ollama.status = 404
        try:
            status, result = self.post({"text": "Retrieve the blue box."})
            self.assertEqual(status, 503)
            self.assertEqual(result["error"]["code"], "model_unavailable")
        finally:
            self.ollama.status = 200


if __name__ == "__main__":
    unittest.main()
