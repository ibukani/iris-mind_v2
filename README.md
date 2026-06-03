# Iris — Cognitive Runtime MVP _(iris-mind)_

AI コンパニオン — Cognitive Runtime Architecture v0.1 ターゲット MVP。

## Usage

```bash
uv run python main.py --text "hello"
uv run python main.py --text "hello" --llm fake
uv run python -m iris.runtime.cli --text "hello"
```

- `--llm fake` (default): Deterministic response, no API key needed.
- `--llm openai`: Uses `OPENAI_API_KEY` from environment. Configure model with `--model`.

## Target Architecture

```
main.py / iris.runtime.cli
→ IrisApp
→ CognitiveCycle (PerceptionStep → ActionSelectionStep)
→ target LLM adapter (FakeLLMClient or OpenAI adapter)
→ Presenter / Safety gates
→ stdout
```

## Project Structure

```
iris-mind/
├── iris/
│   ├── core/            # Foundation types (IDs, etc.)
│   ├── contracts/       # Domain contracts (actions, observations, memory)
│   ├── cognitive/       # Cognitive cycle, pipeline, workspace
│   ├── presentation/    # Output formatting / presentation
│   ├── safety/          # Safety gates (action gate, output filter)
│   ├── features/        # Feature definitions and wiring
│   ├── adapters/        # LLM/memory adapters (FakeLLM, OpenAI, etc.)
│   └── runtime/         # App composition, CLI entrypoint, wiring
├── tests/
│   ├── architecture/    # Architecture boundary tests
│   ├── adapters/        # Adapter unit tests
│   ├── cognitive/       # Cognitive cycle tests
│   ├── contracts/       # Contract type tests
│   ├── features/        # Feature tests
│   ├── runtime/         # End-to-end runtime tests
│   └── test_oneturn_flow.py
└── main.py              # Target runtime entrypoint
```

## Development

```bash
uv run ruff check .                   # lint
uv run ruff format --check .          # format check
uv run pytest tests/                  # run all tests
```

## License

MIT
