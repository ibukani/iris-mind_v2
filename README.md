# Iris — Cognitive Runtime MVP _(iris-mind)_

AI コンパニオン — Cognitive Runtime Architecture v0.1 ターゲット MVP。

## Usage

```bash
uv run python -m iris.runtime.server init-config
uv run python -m iris.runtime.server
uv run python -m iris.runtime.server --config ./configs/dev.toml
uv run python -m iris.runtime.server --host 127.0.0.1 --port 50051
```

通常起動は**単一TOML source policy**を採用する。次の順序で最初に存在する
configだけをロードする。

1. `./.iris/config/runtime.toml`
2. `$IRIS_MIND_CONFIG`
3. `$XDG_CONFIG_HOME/iris-mind/runtime.toml`
4. `~/.config/iris-mind/runtime.toml`

config が見つからない場合はエラーにしない。組み込み defaults、環境変数、CLI overrides だけで起動する。`--config PATH` は default discovery を無効化して指定 TOML を直接使う。`--config PATH` が存在しない場合、または `$IRIS_MIND_CONFIG` が存在しない path を指す場合は `ConfigError`。

**Note:** `iris-mind` はサーバ専用ランタイムである。ユーザ向け CLI 機能 は `iris-cli` 側に属する。以前のワンターン CLI エントリポイント (`iris/runtime/cli.py`) は意図的に削除済み。外部クライアントは gRPC Runtime API を利用する。CLI 向けの `SubmitObservation` 契約は [`docs/runtime-api.md`](docs/runtime-api.md) を参照。モデルとプロバイダの設定は TOML または環境変数で行う。

- `--config`: default discovery を無効化し、指定 TOML を直接読み込む。
- `--host`: `server.host` を上書きする。
- `--port`: `server.port` を上書きする。

Fake LLM がデフォルトであり、外部サービスや API キーは不要。

## Docs

- [`docs/index.md`](docs/index.md): runtime foundation docs の入口。
- [`docs/architecture.md`](docs/architecture.md): 層構造、runtime flow、現在の実装スコープ。
- [`docs/runtime-api.md`](docs/runtime-api.md): gRPC Runtime API と pull-based delivery API。
- [`docs/observability.md`](docs/observability.md): runtime logs、LLM request observability、doctor。
- [`docs/adr/README.md`](docs/adr/README.md): ADR 一覧と形式。

## ローカル Ollama

ローカルプロバイダを使う前に、Ollama を別途インストール・起動する。サンプルモデルを取得する:

```bash
ollama pull qwen3:8b
ollama pull qwen3:4b
ollama pull deepseek-r1:8b
```



## ランタイム設定

Iris は設定ファイルなしでも起動し、組み込みデフォルトを使う。
ランタイム設定をカスタマイズしたい場合だけ、ローカル設定ファイルを明示的に作成する。
推奨パスは `.iris/config/runtime.toml`。

```bash
uv run python -m iris.runtime.server init-config
```

必要に応じてモデル名を編集し、次を実行する:

```bash
uv run python -m iris.runtime.server
```

`.iris/config/runtime.toml` はローカル開発者用設定であり、コミットしない。
`init-config` はPython package内の短いv2 templateを使う。通常設定にはprofile選択と
変更したい値だけを書き、完全なeffective configは組み込みpolicyからruntimeが構築する。
OpenAIの認証情報などの秘密情報はTOMLには書かず、
`OPENAI_API_KEY`などの環境変数で渡す。

設定ファイル形式は`[config] version = 2`。v1、未知version、未知section、未知key、
未知model slotは`ConfigError`になる。

LLM プロバイダの起動時診断モード (`off` / `warn` / `strict`)、warmup 設定、
リクエスト可観測性、gRPC エラーマッピングの詳細については
[docs/observability.md](docs/observability.md) を参照。

read-only runtime diagnostics は次で実行できる:

```bash
uv run python -m iris.runtime.doctor
uv run python -m iris.runtime.doctor --json
make runtime-doctor
make runtime-doctor-json
```

### 設定ソースの役割分担

各設定ソースには明確な役割がある。変更したい値に応じて適切な手段を選ぶ。

| ソース | 役割 | 例 |
|---|---|---|
| 組み込みのデフォルト | 全項目の安全なフォールバック。 | `provider = "fake"`、`base_url = "http://localhost:11434"`、`state.backend = "memory"` |
| TOML | 秘密情報を含まない構造化 developer 設定。 | モデル名、タイムアウト、`ollama.base_url`、`state.sqlite_path` |
| 環境変数 | 秘密情報、デプロイ時上書き、CI / コンテナ上書き。 | `OPENAI_API_KEY`、`IRIS_STATE_BACKEND` |
| CLI フラグ | 一時的な実験的上書き。 | `--host`、`--port` |

API キー、auth トークン、パスワード、その他の認証情報を TOML ファイルに書かない。
これらは環境変数 (またはシークレットマネージャ) を使う。

Ollama/OpenAIへ切り替える場合は`models.*.provider`と`model`だけをruntime.tomlへ追加する。
`OPENAI_API_KEY`はenvで供給する。独立したexampleファイルは持たない。

### 設定の優先順位

Iris は設定を低い優先度から高い優先度まで順に適用し、後のステップが前のステップを上書きする:

1. 組み込みのデフォルト
2. default discoveryで最初に見つかった単一TOML、または`--config`で渡された単一TOML
3. `IRIS_DEFAULT_CHAT_PROVIDER`、`IRIS_DEFAULT_CHAT_MODEL`、`IRIS_OLLAMA_HOST`、`IRIS_OPENAI_MODEL` などの環境変数
4. CLI フラグ: `--host`、`--port`

`OPENAI_API_KEY` は TOML ではなく環境変数で渡す。Iris は OpenAI クライアント生成時にプロセス環境から直接読み取る。

### Control Plane manifestとdrift防止

`iris.runtime.config.runtime_config_specs()`がuser-facing config metadataの正規仕様。
Control Planeは`iris-control-plane.toml`の`[[editable_configs]]`を通じてruntime configを管理する。

- 管理対象config: `.iris/config/runtime.toml`
- Template: `iris.runtime.config_provider`経由でpackage resourceから取得
- Schema manifest (field-level editing/validation用): `.iris/control-plane/runtime-config.schema.json`
- SecretsはTOMLに書かず、環境変数またはsecret managerで供給する。

新しい設定fieldを追加する場合はtyped config、ConfigSpec、parser/env/validation、
canonical example、manifest、READMEを同時更新する。testsはdefaults、example、
manifest、env名、secret露出をConfigSpecと比較し、不一致をCI failureにする。

### 設定モジュールの構成

ランタイム設定は `iris/runtime/config/` 配下に小さなパッケージとして配置されており、将来的なドメイン (memory、affect、gRPC、scheduler など) を 1 ファイルに肥大化させずに拡張できる。公開 import パスは変更なし:

```python
from iris.runtime.config import (
    ConfigError,
    ConfigFieldSpec,
    IrisRuntimeConfig,
    LLMProvider,
    ModelSlotName,
    RuntimeConfigOverrides,
    RuntimeConfigMetadata,
    RuntimeModelConfig,
    RuntimeModelsConfig,
    RuntimeOllamaConfig,
    RuntimeOpenAIConfig,
    RuntimeServerConfig,
    default_runtime_config,
    load_runtime_config,
    parse_llm_provider,
    resolve_runtime_config_path,
    runtime_config_specs,
)
```

サブモジュール `iris.runtime.config.errors`、`iris.runtime.config.parsing`、`iris.runtime.config.llm`、`iris.runtime.config.sources`、`iris.runtime.config.root` は private 実装詳細である。呼び出し側は `iris.runtime.config` からのみ import する (パッケージ自体を拡張する場合に限り public サブモジュールから import 可)。`iris.runtime.config` の外で `os.environ` を直接読むことは architecture guard test で禁止されている。現時点で唯一の例外は `iris.adapters.llm.openai` であり、typed config への移行完了までは `OPENAI_API_KEY` を直接読む。

## ランタイムstateの永続化ポリシー

`state.backend` は **永続化する companion state と audit history** を制御する。
全runtime cacheを永続化する設定ではない。

`state.backend = "memory"` (デフォルト) では全runtime stateが process-local。

`state.backend = "sqlite"` で永続化される対象:

- account bindings / actor identity links
- long-term memory records
- relationship state
- affect baseline state
- activity journal (append-only audit log)
- delivery outbox records
- scheduler targets
- safety audit records
- runtime learning background jobs
- memory candidate review records
- confirmed transcript records (`conversation.transcript.enabled = true` の場合だけ)

`state.backend = "sqlite"` でも process-local のまま (ephemeral):

- activity projections
- presence
- space occupancy
- ephemeral space bindings
- learning dispatch
- short-term conversation history

Activity journalは investigation、debugging、provider event dedupe、future replay、
future projection rebuildのための append-only audit log である。Normal runtime
contextのhot query pathではない。relationship と affect は専用 store を持ち、
activity journal には混ぜない。Delivery outbox と scheduler targets は SQLite backend では durable だが、external app への送信は runtime が直接行わず、pull-based delivery API を通す。Transcript は privacy-sensitive state として明示opt-in時だけ保存する。

詳細は `docs/adr/0002-runtime-state-persistence-policy.md` を参照。

## ターゲットアーキテクチャ

```text
iris.runtime.server / main.py
→ IrisApp
→ CognitiveCycle (perception → memory → affect → policy → response)
→ target LLM adapter (FakeLLMClient, OpenAI adapter, or Ollama adapter)
→ Presenter / Safety gates
→ PresentedOutput (returned to gRPC client)
```

利用可能なパイプライン構成:

| 配線関数 | ステップ |
|---|---|
| `wire_text_response_cognitive_cycle` | perception → response |
| `wire_memory_aware_text_response_cognitive_cycle` | perception → memory → response |
| `wire_affect_memory_aware_text_response_cognitive_cycle` | perception → (memory) → appraisal → relationship → response |
| `wire_policy_affect_memory_aware_text_response_cognitive_cycle` | perception → (memory) → appraisal → relationship → policy → response |

## プロジェクト構成

```text
├── iris/               認知ランタイム中核
│   ├── core/           ID、基底型
│   ├── contracts/      ドメイン契約 (actions, observations, memory, identity, policy, spaces)
│   ├── cognitive/      認知サイクル、パイプライン、ワークスペース
│   ├── presentation/   ActionPlan → PresentedOutput 変換
│   ├── safety/         Action gate, output filter
│   ├── features/       Feature 拡張 (proactive_talk, event_reaction)
│   ├── adapters/       外部統合 (llm, memory, app_gateway, sqlite_journal)
│   └── runtime/        アプリ構成、サーバエントリポイント、wiring
├── proto/              gRPC プロトコル定義
├── docs/               アーキテクチャドキュメント、ADR
├── examples/           設定サンプル
├── tests/              テストスイート
│   ├── architecture/   Guard tests
│   └── ...
├── scripts/            ユーティリティスクリプト
└── main.py             iris.runtime.server へのリダイレクト
```

## 開発

作業完了報告の前に、正規の検証エントリポイントを使う:

```bash
make check
```

`make verify` は `make check` のエイリアス。フル検証パスは次の順で実行される:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy iris tests scripts main.py
uv run pyright .
uv run pytest tests/architecture -q
uv run pytest tests/ --cov=iris --cov-branch --cov-report=term-missing:skip-covered --cov-report=html --cov-fail-under=90
```

ターゲットを絞った便利コマンド:

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

For AI-assisted development, see `AGENTS.md`.

開発時の検証には `make check` や `make quick` を使用する。

## ライセンス

MIT
