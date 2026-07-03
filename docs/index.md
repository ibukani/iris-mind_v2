# Iris Runtime Foundation Docs

Iris runtime foundation の主要ドキュメント入口。

## Character

- [`character.md`](character.md): Iris のキャラクター個性・人格・設定。PersonaPatch / SystemPrompt の参照元。

## Architecture

- [`architecture.md`](architecture.md): 現在の層構造、runtime flow、scheduler、delivery、state、observability の実装状態。
- [`runtime-api.md`](runtime-api.md): 外部 gRPC 契約、`SubmitObservation`、`PollAppActions`、`ReportActionResult`。
- [`learning-candidate-review.md`](learning-candidate-review.md): 学習候補の list / read / approve / reject / discard service boundary。
- [`observability.md`](observability.md): runtime trace context、lifecycle logs、LLM request observability、startup diagnostics、runtime doctor。
- [`archive/legacy-v0.md`](archive/legacy-v0.md): 現在のコードベースへ適用しない旧アーキテクチャ情報。

## ADR

- [`adr/README.md`](adr/README.md): ADR 一覧と現在の決定。
- [`adr/0001-ephemeral-deterministic-space.md`](adr/0001-ephemeral-deterministic-space.md): Space 解決は deterministic だが ephemeral。
- [`adr/0002-runtime-state-persistence-policy.md`](adr/0002-runtime-state-persistence-policy.md): `state.backend` が永続化する runtime state の範囲。
- [`adr/0003-identity-owned-memory.md`](adr/0003-identity-owned-memory.md): Memory の主 owner は `ActorId`。
- [`adr/0004-relationship-and-affect-state.md`](adr/0004-relationship-and-affect-state.md): relationship / affect は専用 store の current state。
- [`adr/0005-llm-provider-runtime-policy.md`](adr/0005-llm-provider-runtime-policy.md): LLM provider は adapter 境界と typed config で扱う。
- [`adr/0006-proactive-scheduler-delivery-safety.md`](adr/0006-proactive-scheduler-delivery-safety.md): proactive scheduler と delivery outbox の安全境界。
- [`adr/0007-runtime-boundary-guard.md`](adr/0007-runtime-boundary-guard.md): runtime boundary guard の方針。
- [`adr/0008-runtime-observability-and-diagnostics.md`](adr/0008-runtime-observability-and-diagnostics.md): runtime observability と diagnostics。
- [`adr/0013-local-llm-lifecycle-readiness-warmup.md`](adr/0013-local-llm-lifecycle-readiness-warmup.md): Local LLM lifecycle / readiness / warmup。

## Source Of Truth

- 実装境界: `iris/` 配下の layer と `tests/architecture/`。
- agent 作業ルール: [`../AGENTS.md`](../AGENTS.md) と [`../.agents/README.md`](../.agents/README.md)。
- 検証コマンド: `make check`。agent の反復診断は `make ai-quick` / `make ai-check`。
