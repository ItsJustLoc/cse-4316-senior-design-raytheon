"""Ollama's HTTP API is the only inference dependency on the host machine."""

import json
import math
from dataclasses import dataclass
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class NLPError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class OllamaConfig:
    model: str
    base_url: str = "http://127.0.0.1:11434"
    timeout: float = 120.0

    def __post_init__(self):
        if not isinstance(self.model, str) or not self.model.strip():
            raise NLPError("invalid_config", "Set a downloaded model with --model or OLLAMA_MODEL.")
        if any(char.isspace() for char in self.model) or self.model.endswith(":cloud"):
            raise NLPError("invalid_config", "Use a local Ollama model name without whitespace.")
        if (type(self.timeout) not in (float, int)
                or not math.isfinite(self.timeout) or self.timeout <= 0):
            raise NLPError("invalid_config", "Ollama timeout must be a positive finite number.")
        try:
            url = urlsplit(self.base_url)
            valid = (
                url.scheme in ("http", "https") and url.hostname
                and url.path in ("", "/") and not url.query and not url.fragment
                and not url.username and not url.password and url.port != 0
                and not any(char.isspace() for char in self.base_url)
            )
        except (ValueError, TypeError, AttributeError):
            valid = False
        if not valid:
            raise NLPError("invalid_config", "Ollama URL must be http(s)://host[:port] without credentials or a path.")
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))


def chat(config: OllamaConfig, messages: list, schema: dict) -> str:
    payload = {
        "model": config.model,
        "messages": messages,
        "format": schema,
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_predict": 768},
    }
    request = Request(
        f"{config.base_url}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=config.timeout) as response:
            raw = response.read(65537)
    except HTTPError as error:
        error.close()
        if error.code == 404:
            raise NLPError(
                "model_unavailable",
                f"Ollama returned 404. Check the server URL and download {config.model!r} on that server.",
            ) from error
        raise NLPError("backend_unavailable", f"Ollama returned HTTP {error.code}.") from error
    except (URLError, OSError, HTTPException) as error:
        raise NLPError(
            "backend_unavailable",
            "Could not complete the Ollama request. Check the server, model, and timeout.",
        ) from error
    try:
        if len(raw) > 65536:
            raise ValueError("Response is too large.")
        envelope = json.loads(raw)
        if envelope["done"] is not True or envelope.get("done_reason", "stop") != "stop":
            raise ValueError("Generation did not finish normally.")
        content = envelope["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Missing generated text.")
        return content
    except (ValueError, KeyError, TypeError, RecursionError) as error:
        raise NLPError("invalid_model_response", "Ollama returned a malformed or incomplete response.") from error
