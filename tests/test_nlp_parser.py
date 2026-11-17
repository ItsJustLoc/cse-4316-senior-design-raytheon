"""Exercise the parser over real local HTTP without downloading a model."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import URLError

from nlp.client import NLPError, OllamaConfig
from nlp.models import Mission, Target
from nlp.parser import IntentParser

READY = {
    "status": "ready",
    "mission": {"action": "retrieve", "target": {"color": "blue", "object_type": "box"}},
    "message": "Retrieve the blue box and return it to the starting zone.",
}


class OllamaStub:
    def __enter__(self):
        self.requests = []
        self.status = 200
        self.response = self.chat_response(READY)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.requests.append((self.path, body))
                self.send_response(owner.status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(owner.response)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    @staticmethod
    def chat_response(interpretation):
        return json.dumps({
            "message": {"role": "assistant", "content": json.dumps(interpretation)},
            "done": True, "done_reason": "stop",
        }).encode()


class ParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stub = OllamaStub().__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.stub.__exit__()

    def setUp(self):
        self.stub.requests.clear()
        self.stub.status = 200
        self.stub.response = self.stub.chat_response(READY)
        self.parser = IntentParser(OllamaConfig(model="test-model", base_url=self.stub.url))

    def test_text_to_validated_mission_over_http(self):
        text = "Retrieve the blue box and bring it to the start."
        result = self.parser.parse(text)
        self.assertEqual(result.original_text, text)
        self.assertEqual(result.schema_version, 1)
        self.assertEqual(result.interpretation.mission.target.color, "blue")
        path, request = self.stub.requests[0]
        self.assertEqual(path, "/api/chat")
        self.assertEqual(request["model"], "test-model")
        self.assertIs(request["stream"], False)
        self.assertEqual(len(request["format"]["anyOf"]), 2)
        self.assertEqual(request["options"]["temperature"], 0)
        self.assertEqual(request["messages"][-1]["role"], "user")
        self.assertEqual(json.loads(request["messages"][-1]["content"])["text"], text)

    def test_target_change_receives_explicit_context_without_mutating_it(self):
        current = Mission(action="retrieve", target=Target(color="red", object_type="box"))
        result = self.parser.parse("The blue one instead.", current_mission=current)
        self.assertEqual(result.interpretation.mission.target.color, "blue")
        self.assertEqual(current.target.color, "red")
        payload = json.loads(self.stub.requests[0][1]["messages"][-1]["content"])
        self.assertEqual(payload["current_mission"], current.model_dump())
        self.parser.parse("Retrieve the blue box.")
        payload = json.loads(self.stub.requests[1][1]["messages"][-1]["content"])
        self.assertIsNone(payload["current_mission"])

    def test_clarification_and_rejection_never_include_a_mission(self):
        for status in ("clarification_required", "rejected"):
            with self.subTest(status=status):
                self.stub.response = self.stub.chat_response({
                    "status": status, "mission": None, "message": "Specify one target color.",
                })
                result = self.parser.parse("Retrieve something.")
                self.assertEqual(result.interpretation.status, status)
                self.assertIsNone(result.interpretation.mission)

    def test_model_cannot_invent_a_target_color_or_shape(self):
        for text in ("Retrieve the teal box.", "Retrieve the blue object."):
            with self.subTest(text=text):
                result = self.parser.parse(text)
                self.assertEqual(result.interpretation.status, "rejected")
                self.assertIsNone(result.interpretation.mission)

    def test_gray_alias_and_generic_object_are_grounded(self):
        for text, target in (
            ("Retrieve the grey box.", {"color": "gray", "object_type": "box"}),
            ("Retrieve blue.", {"color": "blue", "object_type": "object"}),
        ):
            with self.subTest(text=text):
                self.stub.response = self.stub.chat_response({
                    **READY, "mission": {"action": "retrieve", "target": target},
                })
                self.assertEqual(self.parser.parse(text).interpretation.status, "ready")

    def test_empty_invalid_and_oversize_inputs_do_not_call_the_model(self):
        for value in ("", "  \n", "x" * 4001, None, 42):
            with self.subTest(value=repr(value)[:30]), self.assertRaises(NLPError) as error:
                self.parser.parse(value)
            self.assertEqual(error.exception.code, "invalid_input")
        self.assertEqual(self.stub.requests, [])

    def test_malformed_or_incomplete_responses_fail_closed(self):
        for response in (
            b"not json", b"[]", b"{}", b"null", b"x" * 65537,
            json.dumps({"message": {"content": "{}"}, "done": True}).encode(),
            json.dumps({"message": {"content": json.dumps(READY)}, "done": False}).encode(),
            json.dumps({"message": {"content": json.dumps(READY)}, "done": True,
                        "done_reason": "length"}).encode(),
            json.dumps({"message": {"content": READY}, "done": True}).encode(),
            self.stub.chat_response({**READY, "mission": {"action": "drive", "target": None}}),
            self.stub.chat_response({**READY, "mission": None}),
        ):
            with self.subTest(response=response[:120]):
                self.stub.response = response
                with self.assertRaises(NLPError) as error:
                    self.parser.parse("Retrieve the blue box.")
                self.assertEqual(error.exception.code, "invalid_model_response")

    def test_http_errors_are_actionable_and_not_retried(self):
        for status, expected in ((404, "model_unavailable"), (500, "backend_unavailable")):
            with self.subTest(status=status):
                self.stub.status = status
                self.stub.response = b'{"error":"backend details"}'
                with self.assertRaises(NLPError) as error:
                    self.parser.parse("Retrieve the blue box.")
                self.assertEqual(error.exception.code, expected)
        self.assertEqual(len(self.stub.requests), 2)

    def test_connection_failure_and_timeout_are_errors(self):
        for exception in (URLError("connection refused"), TimeoutError("timed out")):
            with self.subTest(exception=exception):
                with patch("nlp.client.urlopen", side_effect=exception), self.assertRaises(NLPError) as error:
                    self.parser.parse("Retrieve the blue box.")
                self.assertEqual(error.exception.code, "backend_unavailable")


class ConfigTests(unittest.TestCase):
    def test_host_and_model_are_independent_of_hardware(self):
        config = OllamaConfig(model="local-model:3b", base_url="http://jetson.local:11434/")
        self.assertEqual(config.base_url, "http://jetson.local:11434")
        self.assertEqual(config.model, "local-model:3b")

    def test_invalid_settings_are_rejected(self):
        for kwargs in (
            {"model": ""}, {"model": "  "}, {"model": "some-model:cloud"},
            {"model": "model", "timeout": 0}, {"model": "model", "timeout": float("nan")},
            {"model": "model", "timeout": float("inf")},
            {"model": "model", "base_url": "file:///etc/passwd"},
            {"model": "model", "base_url": "http://host/api/chat"},
            {"model": "model", "base_url": "http://user:pass@host"},
            {"model": "model", "base_url": "http://host:bad"},
            {"model": "model", "base_url": "http://host?query=true"},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(NLPError):
                OllamaConfig(**kwargs)


if __name__ == "__main__":
    unittest.main()
