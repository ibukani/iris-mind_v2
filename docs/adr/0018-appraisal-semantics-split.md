# ADR 0018: Appraisal semantics split

## Status

Accepted

## Context

Issue #100 では、companion behavior 向けの appraisal 結果を raw VAD valence に潰さず、後続が意味種別を区別して参照できる typed contract に分離する。

既存の affect 経路は引き続き `AffectSnapshot` を生成して mood / VAD 互換性を保つ。ただし、relationship、worker、safety が raw score を直接読み直すと、「今日は悲しい」という user emotion を Iris への trust 低下として誤解する。同様に、映画・バグ・topic への否定的感情、Iris への態度、care intent、dependency-risk hint は別の意味を持つ。

ADR 0017 は companion affect state vocabulary として global mood、actor relationship、actor affect trace、space atmosphere、recent interaction tone を定義している。この ADR は、その state vocabulary と矛盾しない appraisal 出力形を固定する。

## Decision

`iris.contracts.appraisal` を追加し、typed appraisal semantics contract とする。

Signal kind は次の5種類に固定する。

- `user_emotion`: actor の見かけの感情。
- `attitude_toward_iris`: Iris に向けられた actor の態度。
- `topic_sentiment`: 話題・対象物への sentiment。
- `care_intent`: Iris または参加者への care / concern / supportive intent。
- `dependency_risk_hint`: dependency-risk 表現を示す非最終の safety hint。

各 `AppraisalSignal` は immutable で、次の情報を持つ。

- `kind`
- `label`
- `polarity`
- `confidence`
- `reason`
- `source_span`
- `state_boundary`
- optional `safety_hint`
- optional `source_observation_id`
- immutable metadata

根拠断片は free-form metadata ではなく `AppraisalSourceSpan` で表す。`dependency_risk_hint` だけが初期の `dependency_risk` safety hint を持てる。

State boundary mapping は次の通り。

| Signal kind | State boundary |
|---|---|
| `user_emotion` | `actor_affect_trace` |
| `attitude_toward_iris` | `actor_relationship` |
| `topic_sentiment` | `recent_interaction_tone` |
| `care_intent` | `recent_interaction_tone` |
| `dependency_risk_hint` | none; safety hint boundary only |

`AppraisalStep` は既存の VAD / mood 用 `AffectSnapshot` を維持し、config で有効な場合だけ typed appraisal signals を追加で出す。初期実装は deterministic / rule-based であり、user-facing hot path に追加の large LLM call を導入しない。

`WorkspaceFrame` は `AppraisalSemanticsSnapshot` を持つ。後続 step は appraisal step に戻らず、frame 上の typed semantics を読む。

`RelationshipStep` は #100 で typed appraisal signals を durable relationship update policy として扱わない。semantic appraisal mode が有効な場合、raw VAD から affinity/trust を推定する経路を止め、interaction continuity として familiarity だけを更新する。`attitude_toward_iris` を relationship delta に変換する bounded policy は #102 の責務として残す。

Runtime config gate は `[companion_semantics]` に置く。

- `appraisal_signals_enabled`
- `dependency_risk_hint_enabled`

Runtime config から組み立てる場合も direct cognitive wiring も、typed appraisal signal 生成は既定 off とする。テストでは明示的に有効化し、初期 deployment で #100 挙動が無断有効化されないことを固定する。

## Non-decisions

Relationship update policy v2 の詳細は定義しない。これは #102 の責務。

Final high-risk classifier / response safety policy は定義しない。`dependency_risk_hint` は safety code が後続で参照できる typed hint に留める。

Model-backed appraisal classifier は導入しない。初期 classifier は deterministic baseline とする。

Control Plane UI は導入しない。

## Consequences

Semantic appraisal mode が有効な場合、relationship state は全ての negative valence を Iris への trust 低下として解釈しない。VAD mood 情報を保持しながら、downstream policy には typed semantic input を渡せる。

Worker prompt assembly は raw sentiment score ではなく `AppraisalSignal` を参照できる。これにより、後続で worker が curated state/context を受け取り、mutable cognitive internals を直接読まない境界を作れる。

Safety は `dependency_risk_hint` を拾えるが、それを好意・信頼・relationship signal として扱わない。

Config-built deployment は周辺 policy / safety work が揃うまで typed semantics を無効のまま保てる。テストは contract と regression boundary を固定する。

## Implementation anchors

- `iris/contracts/appraisal.py`
- `iris/cognitive/affect/appraisal.py`
- `iris/cognitive/affect/relationship.py`
- `iris/cognitive/workspace/frame.py`
- `iris/cognitive/cycle/frame_builder.py`
- `iris/runtime/config/companion_semantics.py`
- `iris/runtime/wiring/cognitive.py`
