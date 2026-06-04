# Iris — Cognitive Runtime MVP _(iris-mind)_

AI コンパニオン — Cognitive Runtime Architecture v0.1 ターゲット MVP。

## Usage

```bash
uv run python main.py --text "hello"
uv run python main.py --text "hello" --llm ollama --model qwen3:8b
uv run python main.py --config .iris/config/llm.toml --text "こんにちは"
uv run python main.py --config .iris/config/llm.toml --text "hello" --model qwen3:14b
uv run python -m iris.runtime.cli --text "hello"
```

- `--llm`: Overrides `models.default_chat.provider` with `fake`, `openai`, or `ollama`.
- `--model`: Overrides `models.default_chat.model`.
- `--ollama-host`: Overrides `ollama.base_url`.
- `--config`: Loads one explicit runtime TOML file, usually `.iris/config/llm.toml`.

The fake LLM remains the default and does not require external services or API keys.

## Local Ollama

Install and start Ollama separately before using the local provider. Pull the example models:

```bash
ollama pull qwen3:8b
ollama pull qwen3:4b
ollama pull deepseek-r1:8b
```

Run Iris against the default local Ollama host:

```bash
uv run python main.py --text "hello" --llm ollama --model qwen3:8b
```

Use `--ollama-host` when Ollama is listening somewhere else:

```bash
uv run python main.py --text "hello" --llm ollama --model qwen3:8b --ollama-host http://localhost:11434
```

## Runtime LLM Config

The recommended local runtime config path is `.iris/config/llm.toml`. Create it from the
committed sample:

```bash
cp .iris/config/llm.example.toml .iris/config/llm.toml
```

Edit model names if needed, then run:

```bash
uv run python main.py --config .iris/config/llm.toml --text "こんにちは"
```

`.iris/config/llm.toml` is local developer config and should not be committed.
`.iris/config/llm.example.toml` is the committed sample. OpenAI API keys must be supplied
with `OPENAI_API_KEY`, not TOML.

Iris supports named model slots:

- `default_chat`: currently used by one-turn response generation.
- `fast_judge`: parsed and validated for future lightweight judgment/appraisal.
- `reasoning`: parsed and validated for future heavy reasoning.

```toml
[models.default_chat]
provider = "ollama"
model = "qwen3:8b"
temperature = 0.7
max_output_tokens = 512

[models.fast_judge]
provider = "ollama"
model = "qwen3:4b"
temperature = 0.0
max_output_tokens = 128

[models.reasoning]
provider = "ollama"
model = "deepseek-r1:8b"
temperature = 0.0
max_output_tokens = 1024

[ollama]
base_url = "http://localhost:11434"
timeout_seconds = 120.0
keep_alive = "5m"

[openai]
model = "gpt-5-mini"
timeout_seconds = 60.0
max_output_tokens = 512
```

Config precedence is:

1. CLI flags: `--llm`, `--model`, `--ollama-host`
2. Environment variables such as `IRIS_DEFAULT_CHAT_PROVIDER`, `IRIS_DEFAULT_CHAT_MODEL`,
   `IRIS_OLLAMA_HOST`, and `IRIS_OPENAI_MODEL`
3. TOML file passed with `--config`
4. Built-in defaults

## Target Architecture

```text
main.py / iris.runtime.cli
→ IrisApp
→ CognitiveCycle (perception → memory → affect → policy → response)
→ target LLM adapter (FakeLLMClient, OpenAI adapter, or Ollama adapter)
→ Presenter / Safety gates
→ stdout
```

Available pipeline configurations:

| Wiring function | Steps |
|---|---|
| `wire_text_response_cognitive_cycle` | perception → response |
| `wire_memory_aware_text_response_cognitive_cycle` | perception → memory → response |
| `wire_affect_memory_aware_text_response_cognitive_cycle` | perception → (memory) → appraisal → relationship → response |
| `wire_policy_affect_memory_aware_text_response_cognitive_cycle` | perception → (memory) → appraisal → relationship → policy → response |

## Project Structure

```text
iris/
├── core/               IDs, base types
├── contracts/          Domain contracts (actions, observations, memory, identity, policy, spaces)
├── cognitive/          Cognitive cycle, pipeline, workspace
│   ├── action/         Response generation
│   ├── affect/         Appraisal, mood, relationship
│   ├── cycle/          CognitiveCycle coordinator, pipeline protocol, frame builder
│   ├── memory/         Memory retrieval step
│   ├── perception/     Observation parsing
│   ├── policy/         Inhibition / behavioral constraints
│   └── workspace/      WorkspaceFrame (typed one-turn snapshot)
├── presentation/       ActionPlan → PresentedOutput conversion
├── safety/             Action gate, output filter
├── features/           Feature extension (proactive_talk)
│   └── proactive_talk/ Salience scoring, goal proposal, proactive policy
├── adapters/           External integrations
│   ├── app_gateway/    External app protocol boundary
│   ├── llm/            FakeLLM, OpenAI, Ollama clients
│   └── memory/         Fake, vector, LangChain memory stores
└── runtime/            App composition, CLI entrypoint, wiring
    └── wiring/         Constructor-injection wiring (app, cognitive, features, llm, memory, presentation)
├── tests/
│   ├── architecture/   Guard tests (18+ files)
│   ├── adapters/
│   ├── cognitive/
│   ├── contracts/
│   ├── features/
│   ├── helpers/
│   └── runtime/
├── scripts/
│   ├── verify.py       Repository verification entry point
│   ├── ai_context.py   AI harness context dump
│   └── ai_report.py    Completion report skeleton
└── main.py             CLI entrypoint
```

## Development

Use the canonical verification entry point before reporting work complete:

```bash
make check
```

`make verify` is an alias for `make check`. The full verification path runs:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy iris tests scripts main.py
uv run pyright .
uv run pytest tests/architecture -q
uv run pytest tests/ --cov=iris --cov-branch --cov-report=term-missing:skip-covered --cov-report=html --cov-fail-under=90
```

Useful targeted commands:

```bash
make quick        # lint, format, mypy, pyright, architecture tests (no coverage)
make lint         # ruff check
make lint-fix     # ruff check --fix
make format       # ruff format --check
make format-write # ruff format
make type         # mypy strict across iris/tests/scripts/main.py
make pyright      # pyright strict
make arch         # architecture tests
make test         # all tests without coverage
make coverage     # full coverage gate (90% threshold + HTML report)
```

## AI Harness

AI coding agents should start from `AGENTS.md`. Claude Code should start from `CLAUDE.md`,
which delegates shared rules to `AGENTS.md` and `.agents/`.

Agent-oriented commands:

```bash
make ai-context           # show active harness paths
make ai-quick             # fast strict loop (keep going after failures)
make ai-check             # full strict loop (keep going after failures)
make ai-arch              # architecture guard tests
make ai-test-target TARGET=tests/path.py::test_name  # focused test
make ai-report            # Japanese completion report skeleton
```

The required final verification for agent work is:

```bash
make check
```

If the environment cannot run it, the agent must report the exact command, failure reason,
narrower checks that were possible, and remaining risk.

## License

MIT
