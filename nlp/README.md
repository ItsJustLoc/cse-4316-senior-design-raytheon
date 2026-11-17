# Leader's Intent NLP

## Run locally or on a Jetson

Use Python 3.10+ and a local Ollama installation with a downloaded, text-capable model that supports structured output.
Ollama owns CPU/GPU acceleration; this package only speaks HTTP.
Install Ollama using its [platform instructions](https://docs.ollama.com/download), then download a model on the machine running Ollama.
For example, the [Qwen3 4B model](https://ollama.com/library/qwen3:4b-instruct) can be downloaded with `ollama pull qwen3:4b-instruct`.
Model suitability, memory use alongside perception, and latency must be checked on the actual Jetson.

From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
ollama pull qwen3:4b-instruct
python -m nlp serve --model qwen3:4b-instruct
```

Ollama must already be running; start `ollama serve` in another terminal if its service is not running.
Open [the local input screen](http://127.0.0.1:8080).
Enter an instruction, review the result, and select **Use this mission as context** before a follow-up such as “the yellow one instead.”
Context is held only in that browser tab and is cleared by a page reload or the **Clear** button.
This does not accept or execute a mission.

On a Jetson, use the same commands after installing an Ollama build compatible with its JetPack/OS.
No model is bundled or automatically downloaded by the application.
For an operator laptop, keep the app bound to loopback and forward its port: `ssh -L 8080:127.0.0.1:8080 user@jetson`.
Alternatively, `--bind <Jetson-LAN-IPv4-address>` exposes the UI on that specific interface; this unauthenticated local tool is only intended for a trusted network.
The browser connects to the Python app, and the Python app connects to Ollama.
There are no CDN assets or cloud inference fallbacks.

## Configuration

| Flag | Environment variable | Default |
| --- | --- | --- |
| `--model` | `OLLAMA_MODEL` | Required; choose an installed local model |
| `--url` | `OLLAMA_URL` | `http://127.0.0.1:11434` |
| `--timeout` | `OLLAMA_TIMEOUT` | `120` seconds of socket inactivity |
| `serve --bind` | — | `127.0.0.1` |
| `serve --port` | — | `8080` |

Flags override the environment.
`OLLAMA_URL` is the application client setting; Ollama's separate `OLLAMA_HOST` setting controls where its daemon listens.
The URL must include `http://` or `https://`, a host, and optionally a port, without credentials or an API path.
The application does not automatically load `.env` files.
The timeout and 768-token output limit bound ordinary inference failures; the socket timeout is not a hard mission deadline.
There are no automatic retries or repair attempts that could turn a failure into a different command.

## Command line and Python API

```sh
python -m nlp parse --model qwen3:4b-instruct "Read the NFC message from the green cube without collecting it."
printf '%s' 'Retrieve the blue box.' | python -m nlp parse --model qwen3:4b-instruct
python -m nlp parse --model qwen3:4b-instruct --context current-mission.json "The yellow one instead."
```

`--context` takes a file containing just a `Mission` object, for example `{"action":"retrieve","target":{"color":"blue","object_type":"box"}}`.
It does not take the full result envelope.
Exit code `0` means a ready proposal, `1` means clarification or rejection, and `2` means an input/configuration/backend error.
Interpretations are printed as JSON on stdout; errors are JSON on stderr.

```python
from nlp.client import NLPError, OllamaConfig
from nlp.parser import IntentParser

parser = IntentParser(OllamaConfig(model="qwen3:4b-instruct"))
try:
    result = parser.parse("Retrieve the blue box.")
    print(result.model_dump_json(indent=2))
    if result.interpretation.status == "ready":
        proposal = result.interpretation.mission
        # Resolve against the map and validate with the mission controller here.
        update = parser.parse("The yellow one instead.", current_mission=proposal)
except NLPError as error:
    print(error.code, str(error))
```

Each call is independent unless the caller explicitly supplies `current_mission`.
The parser never mutates that context.

## Contract and integration boundary

```json
{
  "schema_version": 1,
  "original_text": "Retrieve the blue box.",
  "interpretation": {
    "status": "ready",
    "mission": {
      "action": "retrieve",
      "target": {"color": "blue", "object_type": "box"}
    },
    "message": "Retrieve the blue box and deliver it to the starting zone."
  }
}
```

`status` is `ready`, `clarification_required`, or `rejected`.
Only `ready` may contain a mission; the other states require `mission: null` and an explanation/question.
All object shapes reject extra fields, and the output is validated again after inference.
The model cannot add speed settings, motor commands, coordinates, or code to the contract.
Literal stop/cancel commands and bare supported target designations are parsed deterministically, so these simple requests do not depend on model availability.
Known spatial-qualifier phrases are rejected before inference because this version cannot represent them; this conservative check can also reject a negated qualifier.
Other natural-language instructions go through Ollama.
The parser also rejects target colors/types that are absent from the text and supplied context, with `grey` normalized to `gray` and generic `object` allowed.

| Action | Meaning | Target |
| --- | --- | --- |
| `retrieve` | Find target, read/relay NFC, collect it, deliver it to start | Required |
| `read_nfc` | Find target and read/relay NFC without collecting it | Required |
| `return_to_start` | Return the vehicle to the starting zone | Must be null |
| `stop` | Propose stopping/canceling mission work | Must be null |

The initial vocabulary is colors `red`, `orange`, `yellow`, `green`, `blue`, `purple`, `pink`, `brown`, `black`, `white`, and `gray`; object types are `cube`, `box`, `ball`, and generic `object`.
This is an implementation vocabulary, not a claim that the competition's final target inventory is fixed.
The prompt requests clarification for missing/ambiguous targets and rejects unsupported spatial qualifiers, routes, speeds, timing conditions, or rule overrides.
Shape validation and target grounding do not prove semantic correctness or resistance to every prompt injection.
Model behavior must be evaluated separately; always show the proposal and have the downstream controller independently enforce arena bounds, obstacle avoidance, target uniqueness, and other mission rules.

The repository does not yet contain that controller.
Before execution it must resolve the target against the current map, accept and version the new mission, record the original text plus accepted mission, cancel superseded tasks, and dispatch recognized actions.
Keep emergency overrides independent of the NLP process and its latency.
Do not feed `message` to an actuator or treat it as execution acknowledgment.

## HTTP interface

`POST /api/interpret` accepts `application/json` with `{"text":"Retrieve the blue box.","current_mission":null}` and returns the same result envelope.
An omitted `current_mission` means no context.
Ready, clarification, and rejection are all HTTP `200`; callers must inspect `interpretation.status`.
Errors use `{"error":{"code":"...","message":"..."}}`.
Input errors return `400`, a bad origin/host `403`, excessive bodies `413`, incorrect content types `415`, invalid model output `502`, and an unavailable/busy backend `503`.
Input text is limited to 4000 characters and the HTTP body to 64 KiB.
Only one inference request is admitted at a time; additional requests get `busy` instead of queuing stale work.
The UI uses same-origin requests, has no cross-origin access, and renders model text as text rather than HTML.
This standard-library HTTP server is a local operator/development tool, not an authenticated internet-facing deployment.

## Verification

```sh
python -m unittest discover -s tests -v
pre-commit run --all-files
python scripts/evaluate_nlp.py --model qwen3:4b-instruct
```

The deterministic suite uses a local HTTP stand-in for Ollama and needs no GPU, internet connection, or model.
It covers schemas, target grounding, context isolation, transport failures, CLI process behavior, and browser API validation.
The separate evaluator runs `tests/nlp_cases.json` through the full parser with a real model, including its deterministic paths, and compares status and full mission with expected values.
It exits nonzero when any case fails; rerun it after changing models or prompts and on the Jetson before integration.
These examples are regression cases, not a statistical accuracy estimate.

Validated on November 16, 2026 with Ollama 0.40.16 on an Apple Silicon development machine: all 22 corpus cases matched status and mission using `qwen3:4b-instruct` (model digest prefix `0edcdef34593`).
Three of those cases use deterministic parsing; the remaining 19 use the live model.
The automated suite has 33 tests, and the browser was checked for real inference, target changes, clarification, service errors, and layouts from 320 to 1440 pixels wide.
Jetson runtime performance and vehicle/controller integration have not been verified.

## Design rationale

Translate typed Mission Bird Dog instructions into a proposed, validated mission using an independently running local Ollama server.
The same Python code must run on a development computer and a Jetson without importing CUDA, GPIO, camera, or vehicle drivers.
The model name, server URL, and request timeout are deployment settings.
Model downloads and Ollama installation are explicit operator steps.

The initial contract supports retrieving one colored object, reading its NFC message, returning to the starting zone, and stopping the mission.
An explicit current mission allows target changes such as “the blue one instead” without global conversation state.
Ambiguous instructions require clarification; unsupported actions or constraints are rejected rather than silently discarded.
Ready results are proposals, not vehicle commands or proof that a target exists.
The mission controller owns acceptance, map resolution, mission versions, cancellation of superseded work, and execution.
Emergency overrides must remain independent of model inference.

## Implementation boundaries

Source lives in `nlp/`; deterministic tests live in `tests/test_nlp*.py` and run with `python -m unittest discover -s tests -v`.
`models.py` owns the shared schema, `client.py` the Ollama transport, `parser.py` the interpretation policy, and `server.py`/`web/` the operator interface.
The JSON schema and validation use the same Pydantic models to avoid two drifting contracts.
The request follows Ollama's [chat API](https://docs.ollama.com/api/chat) and [structured-output contract](https://docs.ollama.com/capabilities/structured-outputs).
No camera, CAD, navigation, or vehicle-controller code is required to run this module.
