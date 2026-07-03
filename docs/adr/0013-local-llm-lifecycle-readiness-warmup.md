# ADR 0013: Local LLM lifecycle, readiness, and warmup

## Status

Accepted

## Context

Iris は Qwen3.5-9B 級のローカル LLM を主経路にする。Ollama / llama.cpp / future local backend では、API provider よりも model load、cold start、keep-alive、daemon readiness が user-facing latency を大きく左右する。

#90 で runtime latency stage、slow warning、model call count、`model_load_state` の観測枠は追加済みだった。しかし `model_load_state` は `unknown` 固定で、cold start と warm generation を分離できなかった。

## Decision

Local model lifecycle を provider-neutral な `ModelLoadState` として扱う。

値:

- `unknown`
- `unloaded`
- `warming`
- `warm`
- `cold_start`
- `unavailable`

Startup diagnostics は `ProviderReadinessResult.model_load_state` を返す。`runtime doctor` は read-only のまま readiness を確認し、warmup は実行しない。Ollama warmup は `ollama.warmup_prompt` が未設定なら load-only request、設定済みならその prompt を使う。

Request-time generation は任意の `ModelLifecycleProbe` を受け取る。Ollama provider では `/api/ps` と `/api/tags` を短い readiness timeout で確認し、生成直前の local model state を観測する。

Ollama で `unavailable` が確定した場合、user-facing generation は `LLMProviderModelUnavailableError` で fail-fast する。probe が不確実な場合は `unknown` として通常 generation に進み、既存の provider timeout と gRPC status mapping に委ねる。

keep-alive / idle unload policy は provider-owned とする。Runtime は独自の idle unload timer や unload command を持たず、Ollama では `ollama.keep_alive` を generation / warmup payload に渡す。Provider が idle unload した model は次回 probe で `unloaded` として観測し、生成成功時に `cold_start` として記録する。

Ollama response の `load_duration` と `eval_duration` は `LLMResponse.load_latency_ms` / `generation_latency_ms` に正規化する。`runtime.latency.stage` は `cold_start_latency_ms` と `generation_latency_ms` を safe metadata として出力する。

## Non-decisions

- 本格的な GPU scheduler は #93 に残す。
- model call budget / cascade policy は #88 に残す。
- classifier / embedding / reranker adapter boundary は #89 に残す。
- Control Plane UI は実装しない。
- 特定 local model の最終採用は決めない。

## Consequences

- Operator は startup diagnostics / runtime doctor / request latency logs で `warm` / `cold_start` / `unavailable` を区別できる。
- Local model unavailable により user-facing generation が provider timeout より長く無限待ちする経路を避けられる。
- `model_load_state` は #88 / #93 の budget / scheduler policy の入力として再利用できる。
- Request-time lifecycle probe 自体が軽量である必要があるため、prompt や raw response を扱わない。

## Implementation anchors

- `iris/adapters/llm/lifecycle.py`
- `iris/adapters/llm/ollama_lifecycle.py`
- `iris/adapters/llm/diagnostics.py`
- `iris/adapters/llm/ollama_diagnostics.py`
- `iris/adapters/llm/observability.py`
- `iris/runtime/observability/llm.py`
- `iris/runtime/wiring/llm.py`
- `iris/runtime/doctor.py`
