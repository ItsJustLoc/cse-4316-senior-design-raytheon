"""Verify the actual CLI process, JSON output, and environment configuration."""

import json
import os
import subprocess
import sys
import unittest

from test_nlp_parser import OllamaStub


class CLITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stub = OllamaStub().__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.stub.__exit__()

    def run_cli(self, *args, input=None, **env):
        environment = {key: value for key, value in os.environ.items()
                       if key not in ("OLLAMA_MODEL", "OLLAMA_URL", "OLLAMA_TIMEOUT")}
        environment.update(env)
        return subprocess.run(
            [sys.executable, "-m", "nlp", *args], input=input,
            capture_output=True, text=True, env=environment, timeout=10, check=False,
        )

    def test_parse_uses_environment_and_prints_only_json(self):
        result = self.run_cli("parse", "Retrieve the blue box.",
                              OLLAMA_MODEL="test", OLLAMA_URL=self.stub.url)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["interpretation"]["status"], "ready")
        self.assertEqual(result.stderr, "")

    def test_stdin_and_flags_override_environment(self):
        result = self.run_cli("parse", "--model", "test", "--url", self.stub.url,
                              input="Retrieve the blue box.",
                              OLLAMA_MODEL="", OLLAMA_URL="invalid")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["original_text"], "Retrieve the blue box.")

    def test_missing_model_and_invalid_timeout_are_structured_errors(self):
        for env in ({}, {"OLLAMA_MODEL": "test", "OLLAMA_TIMEOUT": "not-a-number"}):
            with self.subTest(env=env):
                result = self.run_cli("parse", "Retrieve the blue box.", **env)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertEqual(json.loads(result.stderr)["error"]["code"], "invalid_config")

    def test_clarification_has_nonzero_exit_and_json_result(self):
        self.stub.response = self.stub.chat_response({
            "status": "clarification_required", "mission": None, "message": "Which color?",
        })
        try:
            result = self.run_cli("parse", "Retrieve it.", "--model", "test", "--url", self.stub.url)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIsNone(json.loads(result.stdout)["interpretation"]["mission"])
        finally:
            self.stub.response = self.stub.chat_response({
                "status": "ready", "mission": {"action": "retrieve", "target": {
                    "color": "blue", "object_type": "box"}}, "message": "Retrieve the blue box.",
            })


if __name__ == "__main__":
    unittest.main()
