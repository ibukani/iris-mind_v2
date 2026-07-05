# ADR 0021: Relationship update policy v2

## Status

Accepted

## Context

Issue #102 では、companion semantics の relationship update を raw VAD / sentiment score から直接更新しない policy として固定する。#100 は `AppraisalSignal` を user emotion、Iris への態度、topic sentiment、care intent、dependency-risk hint に分離した。#104 は durable / derived / ephemeral state boundary として `ActorRelationshipState`、`ActorAffectTrace`、`SpaceAtmosphereState`、`RecentInteractionTone` を分離した。

Relationship update policy v2 は、この2つの contract を接続する。ただし #72 の worker 実装や durable store への promotion はこの ADR の対象外である。

## Decision

`iris.contracts.relationship_update` を追加し、#72 worker が参照できる policy result / candidate contract を定義する。

Primary update target は `ActorRelationshipState` だけにする。`IrisGlobalMood` は durable target だが、この policy の direct target にはしない。`ActorAffectTrace`、`SpaceAtmosphereState`、`RecentInteractionTone` は relationship state と混ぜない。

Policy result は次の decision を持つ。

- `automatic_bounded`: cap 内の非ゼロ delta を automatic candidate として扱える。
- `review_required`: low-confidence または high-magnitude のため durable promotion 前に review が必要。
- `suppressed`: relationship update source ではない、または safety boundary に属するため zero-delta にする。

各 `RelationshipUpdateCandidate` は次を保持する。

- `target_state_kind`
- `decision_kind`
- `delta`
- `bounds`
- `reason_kind`
- `reason`
- `confidence`
- `source_refs`
- `source_observation_ids`
- `source_event_ids`
- `review_required`
- immutable metadata

`RelationshipUpdateSourceRef` は typed appraisal signal provenance を表す。free-form metadata ではなく、`signal_kind`、`source_reason`、`source_confidence`、optional `source_observation_id`、`source_event_ids` を持つ。

Automatic relationship delta の source にできる signal は `attitude_toward_iris` のみである。

| Signal kind | Relationship policy v2 の扱い |
|---|---|
| `user_emotion` | `suppressed`; user sadness / anxiety だけで trust / affinity を下げない |
| `attitude_toward_iris` | bounded candidate; confidence / magnitude / zero-delta により automatic / review-required / suppressed |
| `topic_sentiment` | `suppressed`; relationship update source にしない |
| `care_intent` | `suppressed`; relationship / dependency-risk と混ぜない |
| `dependency_risk_hint` | `suppressed`; safety boundary に留め、好意や信頼として扱わない |

Initial constants は Runtime Config v2 まで contract / docs / tests で固定する。

```text
min_automatic_confidence = 0.75
high_magnitude_review_threshold = 0.025
direct_message.max_abs_affinity_delta = 0.03
direct_message.max_abs_trust_delta = 0.01
group_space.max_abs_affinity_delta = 0.015
group_space.max_abs_trust_delta = 0.005
```

Group-space は誤帰属リスクがあるため、DM 以下の cap を使う。Custom config でも group-space cap が DM cap を超える設定は拒否する。High-magnitude review threshold は少なくとも DM の最大 cap 範囲内で到達可能にし、threshold が全 cap より大きくなって無効化される config は拒否する。Review-required decision は non-zero delta に限定する。Group-space atmosphere と recent interaction tone は durable relationship update の直接 source にしない。

`compute_relationship_update_policy` は pure function として `AppraisalSignal` 群、`CompanionInteractionScope`、optional source event IDs、decay multiplier、policy config を受け取り、`RelationshipUpdatePolicyResult` を返す。Raw VAD / `AffectSnapshot` は入力にしない。

## Non-decisions

#72 の background worker execution、queue/backpressure、store への durable promotion は定義しない。

Runtime Config v2 前に update caps / decay / thresholds / review cutoffs を user-editable config として公開しない。

High-risk safety response policy 本体は定義しない。`dependency_risk_hint` は relationship update ではなく safety boundary の signal として残す。

Control Plane UI は導入しない。

## Consequences

Relationship update は raw score ではなく typed appraisal signal を参照する。これにより、「今日は悲しい」は actor affect trace / recent tone として扱われ、Iris への trust / affinity 低下には直結しない。

`attitude_toward_iris` だけが relationship candidate source になり、automatic update と review-required update は decision kind で分離される。Candidate は reason、confidence、source observation IDs、source event IDs、bounds を持つため、#72 worker と review boundary が説明可能な update candidate として扱える。

Runtime integration は将来、Runtime Config v2 で materialize された typed effective config をこの policy に渡す。現時点では built-in constants を使用し、deployment / Control Plane 設定へ露出しない。

## Implementation anchors

- `iris/contracts/relationship_update.py`
- `iris/cognitive/affect/relationship_update_policy.py`
- `tests/contracts/test_relationship_update_contracts.py`: 新規 contract tests。
- `tests/cognitive/test_relationship_update_policy.py`: 新規 policy behavior tests。
- `tests/cognitive/test_relationship_step.py`: この PR では変更しない既存 regression anchor。semantic mode が raw VAD から `affinity` / `trust` を直接更新しないことを確認する。
