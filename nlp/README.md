# Leader's Intent NLP

## Scope and acceptance criteria

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

## Implementation and verification plan

1. Define strict typed input/output models and their semantic rules; verify valid missions and invalid combinations with `unittest`.
2. Implement Ollama structured-output inference and CLI configuration; exercise real HTTP transport against a local test server, including unavailable models, timeouts, malformed output, and incomplete generation.
3. Run a representative corpus against an installed local model and document the model and results separately from deterministic tests.
4. Run repository checks, review the changes, and publish a feature branch and pull request.

Source lives in `nlp/`; deterministic tests live in `tests/test_nlp*.py` and run with `python -m unittest discover -s tests -v`.
Use the repository's Python naming and `unittest` conventions.
Keep the existing README edit, camera experiments, and CAD files out of the NLP commits.
