# Iris — Cognitive Runtime MVP _(iris-mind)_

AI コンパニオン — Cognitive Runtime Architecture v0.1 ターゲット MVP。

## Usage

```bash
uv run python -m iris.runtime.server
uv run python -m iris.runtime.server --config .iris/config/llm.toml
uv run python -m iris.runtime.server --host 127.0.0.1 --port 50051
```

**Note:** `iris-mind_v2` is a server-only runtime. User-facing CLI functionality belongs to `iris-cli_v2`. The former one-turn CLI entrypoint (`iris/runtime/cli.py`) has been intentionally removed. External clients communicate with the runtime using the gRPC `SubmitObservation` RPC. Model and provider configuration should be done through TOML or environment variables.

- `--config`: Loads one explicit runtime TOML file, usually `.iris/config/llm.toml`.
- `--host`: Overrides `server.host`.
- `--port`: Overrides `server.port`.

The fake LLM remains the default and does not require external services or API keys.

## Local Ollama

Install and start Ollama separately before using the local provider. Pull the example models:

```bash
ollama pull qwen3:8b
ollama pull qwen3:4b
ollama pull deepseek-r1:8b
```



## Runtime LLM Config

Iris ships with built-in defaults, so you only need to write the values you want to
override. The recommended local runtime config path is `.iris/config/llm.toml`.
Create it from the committed sample:

```bash
cp .iris/config/llm.example.toml .iris/config/llm.toml
```

Edit model names if needed, then run:

```bash
uv run python -m iris.runtime.server --config .iris/config/llm.toml
```

`.iris/config/llm.toml` is local developer config and should not be committed.
`.iris/config/llm.example.toml` is the committed sample. OpenAI credentials must
be supplied with the `OPENAI_API_KEY` environment variable, never in TOML.

### Configuration role split

Each configuration source has a clear role. Pick the right tool for the value you
need to change.

| Source | Role | Examples |
|---|---|---|
| Built-in defaults | Safe fallback for every value. | `provider = "fake"`, `base_url = "http://localhost:11434"` |
| TOML | Structured non-secret developer configuration. | model names, timeouts, `ollama.base_url` |
| Environment variables | Secrets, deployment overrides, and CI/container overrides. | `OPENAI_API_KEY`, `IRIS_DEFAULT_CHAT_MODEL` |
| CLI flags | Temporary experiment overrides. | `--config`, `--host`, `--port` |

Do not store API keys, auth tokens, passwords, or other credentials in TOML files.
Use environment variables (or your secret manager) for those.

Purpose-specific example configs are committed under `examples/config/`:

- `examples/config/minimal.toml` — overrides `models.default_chat` only.
- `examples/config/local-ollama.toml` — configures all model slots and the shared
  `ollama` block.
- `examples/config/openai.toml` — configures OpenAI model settings. Does not
  include `OPENAI_API_KEY`; supply it via env.

### Config precedence

Iris applies configuration from lowest to highest precedence; later steps
override earlier ones:

1. Built-in defaults
2. TOML file passed with `--config`
3. Environment variables such as `IRIS_DEFAULT_CHAT_PROVIDER`,
   `IRIS_DEFAULT_CHAT_MODEL`, `IRIS_OLLAMA_HOST`, and `IRIS_OPENAI_MODEL`
4. CLI flags: `--host`, `--port`, `--config`

`OPENAI_API_KEY` must be provided through the environment, not TOML. Iris will
read it directly from the process environment when constructing the OpenAI
client.

### Config module layout

The runtime configuration lives under `iris/runtime/config/` as a small package
so future domains (memory, affect, gRPC, scheduler) can grow without bloating a
single file. The public import path is unchanged:

```python
from iris.runtime.config import (
    ConfigError,
    IrisRuntimeConfig,
    LLMProvider,
    ModelSlotName,
    RuntimeConfigOverrides,
    RuntimeModelConfig,
    RuntimeModelsConfig,
    RuntimeOllamaConfig,
    RuntimeOpenAIConfig,
    RuntimeServerConfig,
    default_runtime_config,
    load_runtime_config,
    parse_llm_provider,
)
```

The submodules `iris.runtime.config.errors`, `iris.runtime.config.parsing`,
`iris.runtime.config.llm`, `iris.runtime.config.sources`, and
`iris.runtime.config.root` are private implementation details. Callers should
import only from `iris.runtime.config` (or the public submodules only when
extending the package itself). Direct `os.environ` reads outside
`iris.runtime.config` are forbidden by an architecture guard test; the only
current exception is `iris.adapters.llm.openai`, which still reads
`OPENAI_API_KEY` until the adapter is migrated to the typed config.

## Target Architecture

```text
iris.runtime.server / main.py
→ IrisApp
→ CognitiveCycle (perception → memory → affect → policy → response)
→ target LLM adapter (FakeLLMClient, OpenAI adapter, or Ollama adapter)
→ Presenter / Safety gates
→ PresentedOutput (returned to gRPC client)
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
└── runtime/            App composition, Server entrypoint, wiring
    ├── server.py       gRPC Server entrypoint
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
└── main.py             Redirects to iris.runtime.server
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
