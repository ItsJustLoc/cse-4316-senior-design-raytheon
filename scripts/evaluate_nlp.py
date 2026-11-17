"""Explicit live-model evaluation; excluded from the deterministic CI suite."""

import argparse
import json
import sys
import time
from pathlib import Path

from nlp.client import NLPError, OllamaConfig
from nlp.models import Mission
from nlp.parser import IntentParser


def main():
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument("--model", required=True)
    arguments.add_argument("--url", default="http://127.0.0.1:11434")
    arguments.add_argument("--timeout", type=float, default=120)
    args = arguments.parse_args()
    parser = IntentParser(OllamaConfig(args.model, args.url, args.timeout))
    cases = json.loads((Path(__file__).resolve().parents[1] / "tests/nlp_cases.json").read_text())
    passed = 0
    for index, case in enumerate(cases, 1):
        current = Mission.model_validate(case["current_mission"]) if "current_mission" in case else None
        started = time.monotonic()
        try:
            result = parser.parse(case["text"], current_mission=current).interpretation.model_dump()
            success = result["status"] == case["status"] and result["mission"] == case["mission"]
        except NLPError as error:
            success = False
            result = {"error": error.code, "message": str(error)}
        passed += success
        print(json.dumps({"case": index, "passed": success, "text": case["text"],
                          "seconds": round(time.monotonic() - started, 2), "result": result}), flush=True)
    print(json.dumps({"model": args.model, "passed": passed, "total": len(cases)}))
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
