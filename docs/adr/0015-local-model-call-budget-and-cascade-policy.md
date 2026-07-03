# ADR 0014: Local model call budget and cascade policy

## Status

Accepted.

## Context

ローカル LLM 前提では、1つの user-facing turn に入る model call 数がそのまま体感速度、GPU/CPU 使用量、cold start の影響範囲になる。

今後、safety classification、memory admission、proactive salience、implicit memory extraction、reflection、relationship / affect update、interaction policy candidate generation が増えると、同じ hot path に複数の large LLM call が混入しやすい。

## Decision

Iris runtime は feature / call site ごとに `model_call_budget` を持ち、`ModelCallBudgetGate` で呼び出し前に `CascadeResult` を返す。

`CascadeResult` は次の safe metadata だけを持つ。

- `decision`
- `reason`
- `confidence`
- `fallback_behavior`
- `model_metadata`

prompt、user text、raw response、memory raw text は cascade result と log に入れない。

### Default budget table

| call site | large LLM | small classifier | embedding | reranker | background LLM | fallback |
|---|---:|---:|---:|---:|---:|---|
| `user_response_hot_path` | 1 | 1 | 1 | 1 | 0 | `deterministic_baseline` |
| `proactive` | 1 | 1 | 1 | 0 | 1 | `defer` |
| `memory_extraction` | 0 | 1 | 1 | 0 | 1 | `enqueue_background` |
| `reflection` | 0 | 0 | 1 | 0 | 1 | `defer` |
| `relationship_update` | 0 | 1 | 1 | 0 | 1 | `no_op` |
| `interaction_policy_candidate` | 0 | 1 | 1 | 1 | 1 | `reject` |
| `runtime_learning_hook` | 0 | 0 | 0 | 0 | 1 | `enqueue_background` |

`user_response_hot_path.large_llm_max_calls` は 1 以下でなければならない。`runtime_learning_hook` は `enqueue-only` であり、direct LLM call を行わない。runtime learning hook で重い処理が必要な場合は background job に enqueue し、worker 側で別の budget を使う。

### Cascade policy

- budget 内かつ confidence が閾値以上なら `accept`。
- budget 超過時は model call を実行せず `fallback`。
- low-confidence かつ `high_risk` / `uncertain` で policy が許可する場合だけ `escalate`。
- low-confidence で escalation できない場合は feature ごとの fallback behavior を使う。
- `runtime_learning_hook` の direct large LLM call は `deny`。

### Runtime fallback execution

`BudgetedResponseGenerator` は現段階で user-facing large LLM hot path の gate である。
small classifier / embedding / reranker の budget は config / policy contract として定義済みだが、
実呼び出し箇所への enforcement はこの ADR の実装範囲外である。後続 #69 / #70 / #71 / #72 / #78 で
各 feature の classifier / embedding / reranker / background worker を追加するとき、同じ
`ModelCallBudgetGate` contract に接続する。

このため、現時点で runtime が強制する blocking boundary は次の2つに限定する。

1. user-facing response hot path の large LLM は request scope あたり最大1回。
2. `runtime_learning_hook` は enqueue-only であり、direct large LLM call を行わない。

user-facing 経路では `CascadeFallbackBehavior` を次の実行時挙動へ写像する。

| fallback behavior | runtime behavior |
|---|---|
| `deterministic_baseline` | LLM を再呼び出しせず、固定文面の deterministic fallback response を候補応答にする |
| `defer` | actor-visible text を生成せず `defer` として skip する |
| `enqueue_background` | hot path では actor-visible text を生成せず `defer` として skip する。background enqueue は worker 側の責務 |
| `reject` | actor-visible text を生成せず `deny` として skip する |
| `no_op` | actor-visible text を生成せず skip する |

`escalate` は上位モデル配線が明示されるまでは暗黙に二度目の LLM call を行わず、
user-facing generator では `defer` に正規化する。

### Observability

Runtime trace counter は次を出す。

- `model_call_count`
- `classifier_call_count`
- `embedding_call_count`
- `reranker_call_count`
- `avoided_large_llm_call_count`

`BudgetedResponseGenerator` は `runtime.model_call.cascade_result` を safe metadata だけで記録する。`avoided_large_llm_call_count` は budget gate が large LLM call を止めた回数を表す。

## 関連 Issue

この policy は #69 / #70 / #71 / #72 / #78 の前提として参照できる。
#90 の runtime observability と #87 の local LLM lifecycle / readiness を前提に、
#89 / #91 / #92 / #93 / #96 以降の companion work が user-facing hot path に
追加の large LLM call を混入させないための境界として扱う。

## Non-decisions

この ADR では次を決めない。

- classifier / embedding / reranker の具体モデル選定。
- local inference scheduler の本格実装。
- cloud billing optimization。
- proactive delivery queue の公平性制御。

## Consequences

- user-facing hot path は large LLM 1回を基準に設計される。
- runtime learning hook は enqueue-only になり、応答完了後の学習処理が hot path を重くしない。
- 後続の memory extraction / reflection / relationship update / interaction policy candidate は同じ `model_call_budget` contract を参照できる。
- budget を超えた呼び出しは実際の LLM client に到達しないため、回避された large LLM call を trace で確認できる。

## Implementation anchors

- `iris/contracts/model_policy.py`
- `iris/runtime/config/model_call_budget.py`
- `iris/runtime/model_call_budget.py`
- `iris/runtime/wiring/llm.py`
- `iris/runtime/observability/context.py`
- `.iris/config/runtime.example.toml`
- `.iris/control-plane/runtime-config.schema.json`
- `tests/runtime/test_model_call_budget.py`
- `tests/architecture/test_runtime_learning_hook_model_budget.py`
