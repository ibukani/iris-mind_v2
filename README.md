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
→ CognitiveCycle (PerceptionStep → ActionSelectionStep)
→ target LLM adapter (FakeLLMClient, OpenAI adapter, or Ollama adapter)
→ Presenter / Safety gates
→ stdout
```

## Project Structure

```text
iris-mind/
├── iris/
│   ├── core/
│   ├── contracts/      Domain contracts (actions, observations, memory)
│   ├── cognitive/      Cognitive cycle, pipeline, workspace
│   ├── presentation/
│   ├── safety/         Safety gates (action gate, output filter)
│   ├── features/
│   ├── adapters/       LLM/memory adapters (FakeLLM, OpenAI, Ollama, vector store)
│   └── runtime/        App composition, CLI entrypoint, wiring
├── tests/
│   ├── architecture/
│   ├── adapters/
│   ├── cognitive/
│   ├── contracts/
│   ├── features/
│   └── runtime/
├── scripts/
│   └── verify.py
└── main.py
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
uv run pytest tests/
```

Useful targeted commands:

```bash
make quick   # lint, format, mypy, pyright, architecture tests
make lint    # ruff check
make format  # ruff format
make type    # mypy strict across iris/tests/scripts/main.py
make arch    # architecture tests
make pyright # pyright strict
make test    # all tests with coverage gate
```

## Agent Harness

AI coding agents should start from `AGENTS.md`. Claude Code should start from `CLAUDE.md`,
which delegates shared rules to `AGENTS.md` and `.agents/`.

The required final verification for agent work is:

```bash
make check
```

If the environment cannot run it, the agent must report the exact command, failure reason,
narrower checks that were possible, and remaining risk.

## License

MIT
