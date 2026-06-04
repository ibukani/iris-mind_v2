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
├── scripts/
│   └── verify.py        # Canonical repository verification runner
└── main.py              # Target runtime entrypoint
```

## Development

Use the canonical verification entry point before reporting work complete:

```bash
make check
```

`make verify` is an alias for `make check`.

The full verification path runs:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy iris tests scripts main.py
uv run pyright .
uv run pytest tests/architecture -q
uv run pytest tests/
```

Useful targeted commands:

```bash
make quick    # lint, format, mypy, pyright, architecture tests
make lint     # ruff check
make format   # ruff format --check
make type     # mypy strict across iris/tests/scripts/main.py
make arch     # architecture tests
make pyright  # pyright strict
make test     # all tests with coverage gate
```

## Agent Harness

AI coding agents should start from `AGENTS.md`. Claude Code should start from `CLAUDE.md`, which delegates shared rules to `AGENTS.md` and `.agents/`.

The required final verification for agent work is:

```bash
make check
```

If the environment cannot run it, the agent must report the exact command, failure reason, narrower checks that were possible, and remaining risk.

## License

MIT
