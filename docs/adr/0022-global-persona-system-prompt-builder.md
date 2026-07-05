# ADR 0022: Global persona and SystemPromptBuilder

## Status

Accepted

## Context

Iris の companion UX では、応答ごとの人格・口調のぶれを抑える必要がある。一方、従来の `docs/character.md` は自由記述、TODO、補足説明を含むため、runtime hot path の source of truth として直接 parse するには不安定だった。

#91 の prompt budget / context compression policy により、prompt section kind、trust boundary、budget accounting の境界は既に存在する。global persona はこの境界に接続する必要がある。

## Decision

repo root の `persona.toml` を runtime-readable global persona の正本にする。

`PersonaProfile` contract が `persona.toml` を validation し、`PersonaProfileLoader` が missing / invalid TOML に対して deterministic fallback を返す。

`SystemPromptBuilder` は `PersonaProfile` を `PromptSectionKind.PERSONA` かつ `PromptTrustBoundary.TRUSTED` の section に変換する。chat prompt assembly はこの builder boundary から persona section を受け取り、既存の prompt budget / section metadata / observability report に通す。

hot path での persona 有効化は `companion_semantics.global_persona_enabled` で config-gated にする。`global_persona_enabled = false` の既定では既存 chat prompt を変えない。

## Non-decisions

- user-specific response preference learning は扱わない。
- account-specific / space-specific interaction policy は `persona.toml` に混ぜない。
- memory / relationship update / user feedback から global persona を自動変更しない。
- production safety mode は扱わない。
- proactive text generation vertical slice はここでは実装しない。ただし同じ `SystemPromptBuilder` boundary を再利用できる形にする。

## Consequences

- `docs/character.md` は runtime source ではなく、`persona.toml` の編集ガイドと人格設計意図の文書になる。
- persona section は trusted system content として扱われるが、safety constraints と runtime policy が常に優先される。
- missing / invalid `persona.toml` は user-facing response failure に直結せず、deterministic fallback と safe diagnostics で扱う。
- prompt budget report は persona section size、truncation、omission を本文なしで観測できる。

## Implementation anchors

- `persona.toml`
- `iris/contracts/persona.py`
- `iris/runtime/persona/loader.py`
- `iris/runtime/prompting/system_prompt.py`
- `iris/runtime/prompting/assembler.py`
- `iris/runtime/config/companion_semantics.py`
- `tests/contracts/test_persona_contracts.py`
- `tests/runtime/persona/test_persona_loader.py`
- `tests/runtime/prompting/test_system_prompt_builder.py`
