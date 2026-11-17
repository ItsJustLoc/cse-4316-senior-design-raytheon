"""Command-line and browser entry points for the same intent parser."""

import argparse
import json
import os
import sys
from pathlib import Path

from pydantic import ValidationError

from nlp.client import NLPError, OllamaConfig
from nlp.models import Mission
from nlp.parser import IntentParser


def main():
    parser = argparse.ArgumentParser(description="Interpret Mission Bird Dog Leader's Intent.")
    commands = parser.add_subparsers(dest="command", required=True)
    options = argparse.ArgumentParser(add_help=False)
    options.add_argument("--model", default=os.getenv("OLLAMA_MODEL", ""))
    options.add_argument("--url", default=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"))
    options.add_argument("--timeout", default=os.getenv("OLLAMA_TIMEOUT", "120"))
    parse = commands.add_parser("parse", parents=[options], help="Print a JSON interpretation.")
    parse.add_argument("text", nargs="?", help="Intent text; omit to read stdin.")
    parse.add_argument("--context", type=Path, help="JSON file containing a previous Mission object.")
    serve = commands.add_parser("serve", parents=[options], help="Open a local browser input server.")
    serve.add_argument("--bind", default="127.0.0.1", help="Interface IPv4 address.")
    serve.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    try:
        try:
            timeout = float(args.timeout)
        except ValueError as error:
            raise NLPError("invalid_config", "Ollama timeout must be a number of seconds.") from error
        interpreter = IntentParser(OllamaConfig(args.model, args.url, timeout))
        if args.command == "serve":
            from nlp.server import run_server
            run_server(interpreter, args.bind, args.port)
            return 0
        current = None
        if args.context:
            try:
                with args.context.open(encoding="utf-8") as source:
                    current = Mission.model_validate_json(source.read(65537))
            except (OSError, UnicodeError, ValidationError) as error:
                raise NLPError("invalid_input", "Context must be a readable JSON Mission object.") from error
        text = args.text if args.text is not None else sys.stdin.read(4001)
        result = interpreter.parse(text, current_mission=current)
        print(result.model_dump_json(indent=2))
        return 0 if result.interpretation.status == "ready" else 1
    except NLPError as error:
        print(json.dumps({"error": {"code": error.code, "message": str(error)}}), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
