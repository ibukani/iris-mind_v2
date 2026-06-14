# LLM プロバイダ診断と可観測性

Iris ランタイムは LLM プロバイダの診断 (startup diagnostics) と
リクエスト単位の可観測性 (request observability) を提供する。
このドキュメントでは、運用者が両機能を使ってプロバイダの状態を
把握し、問題を切り分ける方法を説明する。

## 起動時診断 (Startup Diagnostics)

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
| `enabled` | bool | `true` | 診断の有効 / 無効 |
| `timeout_seconds` | float | `5.0` | 各 probe のタイムアウト |
| `fail_fast` | bool | `false` | 1 件失敗で起動を中断するか |
| `warmup_models` | bool | `false` | プローブ成功後に warmup を実行するか |
| `log_issues_as_warnings` | bool | `true` | 失敗を WARNING ログに出力するか |

例:

```toml
[diagnostics]
enabled = true
timeout_seconds = 5.0
fail_fast = false
warmup_models = false
log_issues_as_warnings = true
```

### 環境変数オーバーライド

`IRIS_DIAGNOSTICS_*` で個別フィールドを上書きできる。

| 環境変数 | 効果 |
|----------|------|
| `IRIS_DIAGNOSTICS_ENABLED` | `enabled` を上書き |
| `IRIS_DIAGNOSTICS_TIMEOUT_SECONDS` | `timeout_seconds` を上書き |
| `IRIS_DIAGNOSTICS_FAIL_FAST` | `fail_fast` を上書き |
| `IRIS_DIAGNOSTICS_WARMUP_MODELS` | `warmup_models` を上書き |
| `IRIS_DIAGNOSTICS_LOG_ISSUES_AS_WARNINGS` | `log_issues_as_warnings` を上書き |

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

- `fail_fast = false` (既定) - 失敗を記録しつつ起動は継続
- `fail_fast = true` - 失敗した時点で起動中断

`fail_fast = true` は致命的: 未設定のプロバイダ認証情報、
未インストールのモデル、ネットワーク到達不能などが起動を
阻止する。

## リクエスト可観測性 (Request Observability)

`LLMClientFactory` が構築する LLM クライアントは、生成呼び出し
ごとに以下を loguru レコードとして出力する:

| イベント | レベル | 説明 |
|----------|--------|------|
| `llm.request.start` | DEBUG | 呼び出し直前に発火 |
| `llm.request.success` | INFO | 成功時に発火、latency_ms を含む |
| `llm.request.error` | WARNING | 失敗時に発火、error_type / error_message を含む |

`ObservableLLMClient` ラッパが各呼び出しに以下の追加属性を
bind する:

- `model` - 呼び出し対象モデル名
- `latency_ms` - 経過時間 (ミリ秒、`time.perf_counter` 計測)
- `finish_reason` - プロバイダの finish reason (成功時)
- `error_type` - 例外クラス名 (失敗時)
- `error_message` - 例外メッセージ (失敗時)

## プロバイダ別の capability

`LLMProviderDiagnostics.capabilities` フラグで各 provider が
対応する診断項目を宣言する。

| プロバイダ | health_check | model_availability_check | model_loaded_check | warmup |
|------------|--------------|------------------------|--------------------|--------|
| ollama     | true         | true                   | true               | true   |
| openai     | true         | true                   | false              | false  |

OpenAI は warmup の概念がない (モデルが API 側で提供される) ため
`warmup = false`。`LLMRequestObserver.warmup()` は SKIPPED を返す。

## gRPC ステータスマッピング

`gRPC` 入口層は `LLMProviderError` サブクラスを以下の
gRPC ステータスコードに翻訳する。

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
再起動する。

### OpenAI 認証エラー

`OpenAIDiagnostics.check_readiness()` が `authentication_failed`
issue を報告する。`OPENAI_API_KEY` 環境変数が正しく設定されて
いるか確認する。

### リクエストタイムアウト

`OllamaLLMClient.generate()` が `OllamaAdapterError` を送出し、
gRPC 層が `DEADLINE_EXCEEDED` を返す。`[ollama].timeout_seconds`
を増加させるか、モデルサイズを小さくする。

### リクエストレート制限

`OpenAILLMClient.generate()` が `LLMProviderRateLimitError` を
送出し、gRPC 層が `RESOURCE_EXHAUSTED` を返す。リクエスト頻度を
下げるか、プランをアップグレードする。
