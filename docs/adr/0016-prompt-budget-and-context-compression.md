# ADR 0016: Prompt budget and context compression policy

## Status

Accepted.

## Context

Local LLM では、prompt size が generation latency、VRAM/CPU 使用量、cold start 影響範囲に直結する。

Iris は今後、global persona、safety constraints、短期会話、user memory、project memory、relationship signal、internal state、interaction policy、task context、retrieval / reranking result を user-facing prompt に組み込む。これらを境界なしに連結すると、prompt が肥大化し、#88 の user-facing hot path model-call budget と #90 の latency observability があっても応答時間が不安定になる。

## Decision

Runtime prompt assembly は `prompt_budget` config と `runtime/prompting` の deterministic policy を通す。

Prompt は section 単位で扱い、各 section は次を持つ。

- `kind`
- `trust_boundary`
- `max_chars`
- `max_items`
- `priority`
- `overflow_behavior`

対応する profile は次の4種類。

- `local_low`
- `local_balanced`
- `local_quality`
- `proactive_short`

`proactive_short` は通常 chat profile より短く保つ。#78 の proactive text generation はこの profile を参照できる。

### Trust boundary

Trusted sections と外部由来 context は混ぜない。

| trust boundary | 例 | 扱い |
|---|---|---|
| `trusted` | system instruction、runtime safety guardrails、将来の persona section | `SYSTEM` role message に置く |
| `internal_derived` | affect / relationship summary、policy constraints、goals、conversation summary | `SYSTEM` には入れず、internal context message として分離する |
| `external_context` | memory / project context / retrieval result | `SYSTEM` には入れず、untrusted external context message として分離する |
| `user_input` | recent conversation、latest user input | role message として扱い、trusted instruction と混ぜない |

### Overflow behavior

Overflow は LLM summarization を呼ばず、決定論的に処理する。

- `required`: required section。現実装では deterministic truncate で request を成立させる。
- `truncate`: section 文字数で切り詰める。
- `truncate_items`: item 数を先に絞り、その後文字数で切り詰める。
- `omit`: section ごと落とす。
- `use_existing_summary_then_truncate`: 既存 summary が別 section で supplied され得る section 用の deterministic truncate policy。新規 LLM 要約は行わず、現実装では追加の生成をせずに対象 section 自体を `truncate_items` / `truncate` と同じ決定論的手順で切り詰める。

短期会話は古い item から落とし、memory / policy / task context は入力順を保って先頭から保持する。

### Observability

Prompt budget observability は本文を出さない。記録するのは次の safe metadata のみ。

- profile name
- total chars / max chars
- section kind
- trust boundary
- input/output chars
- input/output items
- omitted / truncated counts
- overflow behavior

prompt text、user text、memory content、system instruction、raw provider response は log に出さない。

### Retrieval / classifier integration

#94 の retrieval top-k は `memory_top_k_for_profile()` / `project_context_top_k_for_profile()` で prompt budget を参照する。

#89 の classifier / embedding / reranking output を user-facing prompt に入れる場合は、section kind、trust boundary、budget accounting を明示する。port / fake / rule implementation は #91 と並列可能だが、heavy prompt integration はこの policy を通す。

## Non-decisions

この ADR では次を決めない。

- LLM による本格要約 worker。
- memory retrieval pipeline 本体。
- response quality evaluation。
- persona source of truth。
- small-model / embedding / reranker の具体 adapter。

## Consequences

- prompt size は config-gated な profile / section budget で制御される。
- trusted instruction と external context の混在を避けられる。
- #94 / #98 / #78 は prompt section boundary と budget accounting を前提に進められる。
- prompt overflow 時に追加 LLM call を発生させないため、#88 の user-facing hot path large LLM budget を破らない。

## Implementation anchors

- `iris/contracts/prompting.py`
- `iris/runtime/config/prompt_budget.py`
- `iris/runtime/prompting/budget.py`
- `iris/runtime/prompting/assembler.py`
- `iris/runtime/prompting/observability.py`
- `iris/runtime/wiring/llm.py`
- `iris/runtime/config/templates/runtime.example.toml`
- `.iris/control-plane/runtime-config.schema.json`
- `tests/runtime/prompting/`
- `tests/runtime/observability/test_prompt_budget_observability.py`
