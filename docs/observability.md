# LLM プロバイダ診断と可観測性

Iris ランタイムは LLM プロバイダの診断 (startup diagnostics)、
runtime request lifecycle logs、LLM request observability、read-only runtime doctor
を提供する。
このドキュメントでは、運用者が両機能を使ってプロバイダの状態を
把握し、問題を切り分ける方法を説明する。

## Runtime Trace Context

runtime request は `RuntimeTraceContext` を `contextvars` で束縛する。主キーは `correlation_id`。`ObservationEnvelope.correlation_id` がない場合は `observation_id` を fallback として使う。

trace context の field:

- `correlation_id`
- `observation_id`
- `observation_kind`
- `ingress_kind`
- `adapter_id`
- `provider`
- `actor_id`
- `space_id`

optional field は値がない場合、log extra から省略される。

## Runtime Lifecycle Logs

`IrisRuntimeService.handle_observation()` は observation lifecycle を safe metadata のみで記録する。通常配線では `LoggingRuntimeObservationObserver` が `RuntimeLogger` に送る。

event names:

- `runtime.observation.start`
- `runtime.observation.integrate.start`
- `runtime.observation.integrate.success`
- `runtime.context.assemble.start`
- `runtime.context.assemble.success`
- `runtime.observation.route`
- `runtime.observation.no_send`
- `runtime.activity_reaction.start`
- `runtime.activity_reaction.success`
- `runtime.cognitive.start`
- `runtime.cognitive.success`
- `runtime.observation.success`
- `runtime.observation.error`

safe fields:

- `correlation_id`
- `observation_kind`
- `route`
- `ingress_kind`
- `adapter_id`
- `provider`
- `actor_id`
- `space_id`
- `latency_ms`
- `output_present`
- `error_type`

runtime lifecycle logs は観測するだけで、routing、retry、safety、delivery、memory の判断を行わない。

## Runtime Response Latency Budget

Runtime response path は段階別 latency sample を `runtime.latency.stage` として記録する。
各 sample は `correlation_id`、`observation_kind`、`ingress_kind`、任意の
`actor_id` / `space_id`、`stage`、`latency_ms`、`budget_ms`、
`budget_exceeded`、`model_call_count`、`classifier_call_count`、
`embedding_call_count`、`reranker_call_count`、`avoided_large_llm_call_count`、`model_load_state` を含む。budget を超えた場合、
`slow_warning_enabled = true` なら同じ metadata で `runtime.latency.slow` も記録する。

観測する stage:

| stage | 既定 budget | 説明 |
|-------|-------------|------|
| `handle_observation` | 3000 ms | runtime request 全体 |
| `observation_integration` | 50 ms | observation claim の state 統合 |
| `workspace_context_assembly` | 100 ms | workspace / presence / availability context 組み立て |
| `conversation_context_load` | 100 ms | 短期会話 window の読み込み |
| `cognitive_processing` | 2500 ms | IrisApp / cognitive pipeline 全体 |
| `llm_generate` | 2200 ms | LLM generation request |
| `conversation_record` | 100 ms | 成功 response の短期会話履歴記録 |
| `transcript_append` | 100 ms | confirmed transcript 追記 |
| `runtime_learning_hook` | 200 ms | runtime outcome learning hook |
| `background_enqueue` | 100 ms | background job enqueue |
| `classifier_call` | 50 ms | 後続Issueで分類器 observer を接続する予約 stage |
| `embedding_call` | 150 ms | 後続Issueで embedding observer を接続する予約 stage |
| `reranker_call` | 100 ms | 後続Issueで reranker observer を接続する予約 stage |

`classifier_call` / `embedding_call` / `reranker_call` は #89 で小型モデル port wrapper に接続済み。
`ObservableTextClassifier` / `ObservableEmbeddingClient` / `ObservableReranker` は、adapter の実行前に
request-local counter を進め、成功・失敗どちらでも同じ stage 名で latency sample を記録する。
user text、query text、candidate text、embedding vector、raw provider response は latency event に含めない。

`avoided_large_llm_call_count` は `ModelCallBudgetGate` が large LLM call を実行前に止めた回数。
user-facing hot path では large LLM 2 回目以降を実 client に到達させず、
`runtime.model_call.cascade_result` に `decision`、`reason`、`confidence`、`fallback_behavior`、
`model_slot`、`model` を safe metadata として記録する。prompt、user text、raw response は記録しない。

P50 / P95 / P99 は metrics backend を持たせず、`runtime.latency.stage` event を
外部 log/metrics pipeline で集計する。distributed tracing や dashboard はこの実装の範囲外。

ローカル LLM の cold start は latency だけでは断定しない。`llm_generate` event は
`model_load_state = "unknown"` を含め、Ollama など provider-specific diagnostics が
model loaded state を提供できるようになった時点で `cold_start` / `warm` のような
値へ拡張する。

### 設定

`[observability.latency_budget]` セクションで段階別 budget と warning を制御する。

```toml
[observability.latency_budget]
enabled = true
slow_warning_enabled = true
handle_observation_ms = 3000.0
observation_integration_ms = 50.0
workspace_context_assembly_ms = 100.0
conversation_context_load_ms = 100.0
cognitive_processing_ms = 2500.0
llm_generate_ms = 2200.0
conversation_record_ms = 100.0
transcript_append_ms = 100.0
runtime_learning_hook_ms = 200.0
background_enqueue_ms = 100.0
classifier_call_ms = 50.0
embedding_call_ms = 150.0
reranker_call_ms = 100.0
```

すべての `*_ms` 値は正の数でなければならない。`enabled = false` の場合、
latency stage event と slow warning は出力しない。`slow_warning_enabled = false` の場合、
latency sample は出すが `runtime.latency.slow` は出力しない。


## Small Model Port Boundary

小型分類器・embedding・reranker は provider-neutral contract として `iris/contracts/` に置く。
実モデル adapter の選定は #89 の範囲外であり、現在は fake / rule implementation だけを提供する。

| port | contract | fake / rule adapter | runtime wrapper |
|------|----------|---------------------|-----------------|
| `TextClassifier` | `iris/contracts/classification.py` | `iris/adapters/classifiers/` | `iris/runtime/local_ai/` |
| `EmbeddingClient` | `iris/contracts/embeddings.py` | `iris/adapters/embeddings/fake.py` | `iris/runtime/local_ai/` |
| `Reranker` | `iris/contracts/retrieval.py` | `iris/adapters/rerankers/` | `iris/runtime/local_ai/` |

Runtime wrapper は2層に分ける。

- `Budgeted*` wrapper: #88 の `ModelCallBudgetGate` を呼び出し前に通す。拒否時は adapter を呼ばず、typed fallback result を返す。
- `Observable*` wrapper: #90 の trace counter と latency stage に接続する。prompt / user text / memory content は記録しない。

`ClassificationResult`、`EmbeddingResult`、`RerankResult` は `ModelInvocationMetadata` と `latency_ms` を持つ。
`ClassificationResult` は `label`、`confidence`、`reason`、`fallback_applied`、`original_label` を持ち、
`ClassificationFallbackPolicy` により low-confidence result を deterministic に `unknown` へ正規化できる。

#94 の memory retrieval / reranking pipeline は `EmbeddingClient` と `Reranker` を再利用する。
#82 high-risk context detection と #100 appraisal semantics は `TextClassifier` を再利用する。
#91 の prompt budget が未適用の段階では、classifier / reranker result を user-facing prompt context に直接混ぜない。

## Sensitive Data Policy

ログに出してはいけないもの:

- user text
- prompt text
- memory content
- raw provider response
- system instruction
- API key
- token
- secret

safe ID と safe metadata はログに出してよい。`RuntimeLogger` は exact key
(`text`, `prompt_text`, `user_text`, `raw_response_body`, `api_key`, `token`,
`secret`, `password` など) と sensitive suffix (`_text`, `_prompt`, `_token`,
`_secret`, `_password`, `_response_body` など) だけを drop する。`memory_result_count`,
`context_assembled`, `content_type`, `output_present`, `route` のような safe diagnostic
field は保持する。

## 起動時診断 (Startup Diagnostics)

### Local LLM lifecycle / readiness / warmup

Local provider は `LLMProviderDiagnostics` と request-time lifecycle probe の 2 層で扱う。

- startup diagnostics: 起動時または `runtime doctor` で provider / model readiness を確認する。
- warmup: `diagnostics.warmup_models = true` のときだけ provider 固有の load-oriented request を実行する。
- request-time lifecycle probe: user-facing generation 直前に lightweight な loaded / installed state を確認する。

`runtime doctor` は read-only コマンドであるため warmup を実行しない。doctor の
`provider-readiness` check は `model_load_state` を出力し、operator が `warm` /
`unloaded` / `unavailable` を確認できるようにする。

Ollama lifecycle policy:

| 状態 | 条件 | 挙動 |
|------|------|------|
| `warm` | `/api/ps` に model が存在する | 通常 generation |
| `unloaded` | `/api/tags` に model があり `/api/ps` に無い | generation 成功時に `cold_start` として観測 |
| `unavailable` | daemon 到達不能、probe timeout、model 未導入 | `LLMProviderModelUnavailableError` で fail-fast |
| `unknown` | probe response が不完全 | 通常 generation に進み provider timeout に委ねる |

keep-alive / idle unload は runtime が独自 timer や unload command を持たない。Ollama では
`ollama.keep_alive` を generation / warmup request に渡し、実際の idle unload は provider に委ねる。
provider が model を unload した場合、次の request-time probe は `unloaded` を返し、生成成功時に
`cold_start` として観測する。

この境界は #88 の model call budget / cascade policy や #93 の local inference scheduler の
入力になるが、#87 では scheduling / GPU arbitration は実装しない。

ランタイム起動時に、各モデルスロット (default_chat / fast_judge /
reasoning) に対して以下を実行する:

1. **readiness probe** - プロバイダのエンドポイント疎通と
   モデル存在確認
2. **warmup** (設定有効時のみ) - モデルをメモリにロードさせる
   ための生成リクエスト

`fake` プロバイダのスロットは対象外。`ollama` / `openai` スロット
のみが診断される。

### 設定

`[diagnostics]` セクションで挙動を制御する。

| フィールド | 型 | 既定値 | 説明 |
|------------|----|--------|------|
| `mode` | enum (`off` / `warn` / `strict`) | `warn` | 診断の動作モード |
| `timeout_seconds` | float | `5.0` | 各 probe のタイムアウト (秒) |
| `warmup_models` | bool | `false` | プローブ成功後に warmup を実行するか |

`mode` の値による挙動:

- `off` - 起動時診断を完全にスキップする
- `warn` - 診断を実施し、失敗を警告ログに残して起動を続行する
- `strict` - 診断を実施し、いずれかの readiness/warmup 結果が `FAIL`
  だった場合は `ConfigError` を送出して起動を中断する

例:

```toml
[diagnostics]
mode = "warn"
timeout_seconds = 5.0
warmup_models = true
```

### 環境変数オーバーライド

`IRIS_DIAGNOSTICS_*` で個別フィールドを上書きできる。

| 環境変数 | 効果 |
|----------|------|
| `IRIS_DIAGNOSTICS_MODE` | `mode` を上書き (`off` / `warn` / `strict`) |
| `IRIS_DIAGNOSTICS_TIMEOUT_SECONDS` | `timeout_seconds` を上書き |
| `IRIS_DIAGNOSTICS_WARMUP_MODELS` | `warmup_models` を上書き |

```bash
export IRIS_DIAGNOSTICS_MODE=warn
export IRIS_DIAGNOSTICS_TIMEOUT_SECONDS=5
export IRIS_DIAGNOSTICS_WARMUP_MODELS=true
```

不正な `mode` 値は `ConfigError` (`Invalid diagnostics.mode: ...`)
を発生させ、起動時に拒否される。

### レポート

診断結果は `StartupDiagnosticsReport` にまとめられる。各スロット
ごとに `DiagnosticsCheckOutcome` が生成され、`status` /
`provider` / `model` / `readiness` / `warmup` のフィールドを持つ。

`status` は以下のいずれか:

- `OK` - すべてのチェックが成功
- `WARN` - 一部チェックが警告 (例: tags 取得不可)
- `FAIL` - probe が失敗 (例: モデル未インストール、認証エラー)
- `SKIPPED` - warmup がスキップされた (OpenAI など)

### 失敗時の挙動

- `mode = "warn"` (既定) - 失敗を警告ログに出力し、起動は継続
- `mode = "strict"` - 失敗した時点で `ConfigError` を送出して起動中断
- `mode = "off"` - 診断を完全にスキップ

`mode = "strict"` は致命的: 未設定のプロバイダ認証情報、
未インストールのモデル、ネットワーク到達不能などが起動を
阻止する。

## LLM リクエスト可観測性 (Request Observability)

`LLMClientFactory` が構築する LLM クライアントは、生成呼び出しごとに
`RuntimeLLMRequestObserver` で request lifecycle を記録する。runtime trace context が
束縛されている場合、`correlation_id` が LLM log に含まれる。

adapter-level の `LoggingRequestObserver` は低レベル利用と adapter tests のために残る。
runtime wiring は correlation-aware な `RuntimeLLMRequestObserver` を使う。

| イベント | レベル | 説明 |
|----------|--------|------|
| `llm.request.start` | DEBUG | 呼び出し直前に発火 |
| `llm.request.success` | INFO | 成功時に発火、latency_ms を含む |
| `llm.request.error` | WARNING | 失敗時に発火、error_type / error_message を含む |

`ObservableLLMClient` ラッパが各呼び出しに以下の追加属性を
`extra` 経由で付与する:

- `model` - 呼び出し対象モデル名
- `latency_ms` - 経過時間 (ミリ秒、`time.perf_counter` 計測)
- `finish_reason` - プロバイダの finish reason (成功時)
- `error_type` - 例外クラス名 (失敗時)
- `error_message` - 例外メッセージ (失敗時)

プロンプト / ユーザーテキスト / システムメッセージ / メモリ内容 /
API キー / raw response body はログに含まれない。

## プロバイダ別の capability

`LLMProviderDiagnostics.capabilities` フラグで各 provider が
対応する診断項目を宣言する。

| プロバイダ | health_check | model_availability_check | model_loaded_check | warmup |
|------------|--------------|------------------------|--------------------|--------|
| ollama     | true         | true                   | true               | true   |
| openai     | true         | true                   | false              | false  |

OpenAI は warmup の概念がない (モデルが API 側で提供される) ため
`warmup = false`。`OpenAIDiagnostics.warmup()` は SKIPPED を返す。

## gRPC ステータスマッピング

`gRPC` 入口層は `LLMProviderError` サブクラスを以下の
gRPC ステータスコードに翻訳する。`asyncio.CancelledError` は
専用ハンドラで警告ログを出して再送出される (INTERNAL に翻訳
されない)。

| プロバイダ例外 | gRPC ステータス |
|----------------|----------------|
| `LLMProviderAuthenticationError` | `UNAUTHENTICATED` |
| `LLMProviderConnectionError` | `UNAVAILABLE` |
| `LLMProviderTimeoutError` | `DEADLINE_EXCEEDED` |
| `LLMProviderRateLimitError` | `RESOURCE_EXHAUSTED` |
| `LLMProviderQuotaError` | `RESOURCE_EXHAUSTED` |
| `LLMProviderModelUnavailableError` | `FAILED_PRECONDITION` |
| `LLMProviderInvalidResponseError` | `INTERNAL` |
| その他 `LLMProviderError` | `UNKNOWN` |

クライアントは安定したステータスコードでリトライ可否を判定できる。

## トラブルシューティング

### 起動時にモデル未インストールで失敗

`OllamaDiagnostics.check_readiness()` が `model_not_installed`
issue を報告する。`ollama pull <model>` でインストールし、
再起動する。コマンドラインで確認するには:

```bash
curl http://localhost:11434/api/tags
curl http://localhost:11434/api/ps
```

### OpenAI 認証エラー

`OpenAIDiagnostics.check_readiness()` が `authentication_failed`
issue を報告する。`OPENAI_API_KEY` 環境変数が正しく設定されて
いるか確認する。

### リクエストタイムアウト

`OllamaLLMClient.generate()` が `LLMProviderTimeoutError` を
送出し、gRPC 層が `DEADLINE_EXCEEDED` を返す。`[ollama].timeout_seconds`
を増加させるか、モデルサイズを小さくする。

### リクエストレート制限

`OpenAILLMClient.generate()` が `LLMProviderRateLimitError` を
送出し、gRPC 層が `RESOURCE_EXHAUSTED` を返す。リクエスト頻度を
下げるか、プランをアップグレードする。

## 環境変数チューニング

WSL / Docker / 別ホスト境界で Ollama を動かしている場合は、
`IRIS_OLLAMA_HOST` でエンドポイントを切り替えるか、
`IRIS_OLLAMA_TIMEOUT_SECONDS` で probe タイムアウトを調整する。
Diagnostics 自体も環境変数で制御可能。

```bash
# Ollama endpoint
export IRIS_OLLAMA_HOST=http://localhost:11434
export IRIS_OLLAMA_TIMEOUT_SECONDS=300

# Startup diagnostics
export IRIS_DIAGNOSTICS_MODE=warn
export IRIS_DIAGNOSTICS_TIMEOUT_SECONDS=5
export IRIS_DIAGNOSTICS_WARMUP_MODELS=true
```

`IRIS_OLLAMA_HOST` を変更したら Iris-Mind を再起動し、
起動ログに `startup.diagnostics.readiness` イベントが流れることを
確認する。`mode = "strict"` の起動に失敗した場合は同じ
`startup.diagnostics.readiness` イベントで `status = "fail"` が
ログに残る。

## Runtime Doctor

runtime doctor は read-only / non-mutating な診断コマンドである。
`diagnostics.warmup_models = true` の設定でも、runtime doctor は provider warmup を
実行しない。startup diagnostics は readiness check のみを使う。

```bash
uv run python -m iris.runtime.doctor
uv run python -m iris.runtime.doctor --json
make runtime-doctor
make runtime-doctor-json
```

check 項目:

- config discovery
- config parse / validation
- selected state backend
- SQLite path permission (`state.backend = "sqlite"` の場合)
- SQLite schema version / latest migration / pending migration
- SQLite future schema rejection / corrupt DB detection
- logging file path parent permission (`logging.file_path` 設定時)
- server host / port summary
- model slot summary
- startup diagnostics readiness check
- delivery enabled / disabled
- scheduler enabled / disabled

失敗時は failure class、issue、recommended next action を出す。SQLite DB が future schema または corrupt と判定された場合、doctor は fail し、DB を silent delete / recreate しない。migration pending は warn として表示し、通常起動時に `SQLiteSchemaMigrator` が適用する。

## Ollama diagnostics の内部動作

- `OllamaDiagnostics.check_readiness()` は次の軽量 probe を実行する:
  1. `GET /` で daemon 疎通を確認
  2. `GET /api/tags` でモデルがインストール済みか確認
  3. `POST /api/show` でモデルメタデータが読めるか確認
  4. `GET /api/ps` でモデルがメモリにロード済みか確認
- ロード済み判定は `model_loaded_check` capability に基づき、
  結果は `result.metadata["model_loaded"]` として露出する。
- インストール済みだが未ロードの場合は `WARN` を返し、
  warmup がモデルロードの引き継ぎを担う。

## Warmup の動作

- `OllamaDiagnostics.warmup()` は `messages=[]` の `POST /api/chat`
  を送信し、続けて `GET /api/ps` でロード状態を確認する。
- モデルがメモリにロードされれば `OK` を返す。
- `messages=[]` を使うのは Ollama 側を load 動作として扱うためで、
  prompt を生成しない。
- `/api/chat` が 2xx を返したが `/api/ps` でモデルが見つからない
  場合は `WARN` (`model_still_not_loaded`)。
- モデルがインストールされていない場合は `SKIPPED`
  (`warmup_skipped_model_missing`)。
- OpenAI プロバイダは warmup を行わず `SKIPPED` を返す
  (`warmup_not_supported`)。
