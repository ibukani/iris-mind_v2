# ADR 0022: Runtime ordering and conflict policy

## Status

Accepted

## Context

Issue #74 は、複数 adapter / client から同時に届く observation、transcript、interaction activity、state candidate、delivery result を、global order や distributed consensus なしで deterministic に扱うための boundary を定義する。

同じ runtime-owned scope の duplicate / stale event が後着順で state を上書きすると、activity projection の再活性化、candidate の二重登録、delivery の二重実行が起きる。異なる scope は独立して処理できるため、全入力を一つの global lock や total order に集約しない。

## Decision

`iris.contracts.ordering` に次の typed contract を置く。

- `RuntimeOrderingKey` は ordering の owner と scope を表す。
- `OrderingDecision` は `accept`、`ignore_duplicate`、`ignore_stale`、`reject_conflict`、`defer` を表す。
- non-accept decision は `OrderingConflict` を持ち、`reason`、`expected_version`、`observed_version` を返す。
- ordering key は `adapter_id`、provider、account、actor、space、session、channel の組み合わせで scope を明示する。

ordering は runtime-owned key ごとに行う。初期 key の owner は次のとおりである。

| Owner | Scope key |
|---|---|
| observation | provider + external account + space + session / runtime stream |
| transcript | actor + space + session |
| interaction activity | adapter + provider + actor + account + space + channel |
| state candidate | owner + candidate kind |
| delivery result | action_id + lease / attempt |

Interaction activity projection は次の順序比較を使う。

- provider sequence が双方にある場合は `provider_sequence`、`observed_at`、`received_at` の順で比較する。
- provider sequence がない場合は `observed_at`、`received_at` の順で比較する。
- 同一 snapshot は mutation せず `ignore_duplicate` を返す。
- 古い snapshot は mutation せず `ignore_stale` を返す。
- 同じ ordering version で内容が異なる snapshot は到着順で選ばず、`version_conflict` として `reject_conflict` を返す。
- 異なる ordering key は共有の global order を要求せず、独立して処理する。

Durable deduplication の正本は各 owner の store とする。activity journal は provider event / activity ID、delivery outbox は action ID / attempt を durable に dedupe する。ordering contract はこれらの durable port を置き換えず、projection や将来の candidate / transcript / observation store が同じ conflict vocabulary を共有するために使う。

## Non-decisions

この ADR は distributed total order、cross-account consensus、adapter 間の global sequence、eventual conflict の自動 merge を導入しない。

Interaction activity projection の process-local state を durable truth にはしない。restart 後の重複排除は activity journal / delivery outbox など owner の durable store が担い、候補・transcript・observation の durable ordering は各 feature slice の実装で追加する。

## Consequences

同じ scope の out-of-order activity は新しい状態を復活させず、duplicate と version conflict は理由付きで観測できる。caller は `OrderingDecision` を使って後続 projection、retry、review、defer を分岐できる。

scope が ordering key に含まれるため、異なる actor、space、channel、adapter の入力が互いの state を上書きしない。global lock を置かないため、並列性を維持したまま同一 key の deterministic policy を共有できる。

## Implementation anchors

- `iris/contracts/ordering.py`
- `iris/runtime/state/interaction_activity.py`
- `iris/adapters/persistence/sqlite/stores/activity_journal.py`
- `iris/adapters/persistence/sqlite/stores/delivery_outbox.py`
- `tests/runtime/state/test_interaction_activity.py`
- `tests/runtime/state/test_activity_integrator.py`
