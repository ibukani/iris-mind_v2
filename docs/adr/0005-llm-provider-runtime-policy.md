# ADR 0005: LLM Provider Runtime Policy

## Status

Accepted

## Context

Iris は default local MVP と tests で deterministic な fake provider を使い、必要に応じて Ollama / OpenAI を選択する。LLM provider は runtime に強く影響するが、provider SDK、認証、network I/O、model-specific response 形状を cognitive layer へ漏らすと境界が崩れる。

設定は TOML、環境変数、CLI override から typed runtime config に集約される。OpenAI API key のような secret は TOML へ書かず、環境変数または将来の secret manager から adapter / config boundary で読む。

## Decision

LLM provider は `fake`、`ollama`、`openai` の typed provider value として扱う。model slot は `default_chat`、`fast_judge`、`reasoning` に分け、runtime wiring が slot ごとの `LLMClient` を constructor injection で認知ステップへ渡す。

`adapters/llm/` は typed `LLMRequest` を受け取り typed `LLMResponse` を返す技術境界とする。provider SDK、HTTP request、認証、provider-specific diagnostics は adapter または runtime observability / diagnostics wiring に閉じ込める。

`cognitive/` は provider 名、SDK、環境変数、network retry、raw response body を知らない。response generation は注入済み generator / client を使い、provider 切替は runtime config と wiring の責務にする。

Fake provider は default と tests の deterministic provider とする。実 provider tests は fake または mocked provider client を使い、通常の検証で実 network へ接続しない。

Secrets は TOML に保存しない。API key、auth token、password は環境変数または将来の secret manager から adapter / config boundary へ供給する。

## Non-decisions

- Provider SDK の完全な機能差分を Iris contracts に露出しない。
- Prompt selection、persona policy、memory extraction policy はこの ADR の対象外。
- Provider-level billing、quota management、organization policy はこの ADR の対象外。

## Consequences

Provider 追加時は typed config、config specs、adapter、diagnostics、wiring、tests を同時に更新する必要がある。cognitive layer や contracts layer には provider-specific import を追加しない。

Runtime observability は safe metadata だけを記録する。prompt、user text、memory content、API key、raw response body は logs に含めない。

## Implementation anchors

- `iris/runtime/config/llm.py`
- `iris/runtime/wiring/llm.py`
- `iris/adapters/llm/`
- `iris/runtime/observability/llm.py`
- `iris/runtime/observability/diagnostics.py`
- `docs/observability.md`
- `tests/architecture/test_config_env_ownership.py`
- `tests/architecture/test_config_spec_integrity.py`
- `tests/architecture/test_cognitive_runtime_anti_patterns.py`
- `tests/architecture/test_runtime_boundaries.py`
- `tests/architecture/test_runtime_boundary_guards.py`
- `tests/adapters/test_ollama_llm.py`
- `tests/adapters/test_openai_llm.py`
- `tests/adapters/test_ollama_diagnostics.py`
- `tests/adapters/test_openai_diagnostics.py`
