# ADR 0004: Relationship And Affect State

## Status

Accepted

## Context

Iris は actor ごとの現在の関係性と、Iris 自身の affect baseline/current state を扱う。これらは検索対象の memory content ではなく、現在 state として更新される durable contract である。

## Decision

- Relationship は `ActorId` を主キーにした current per-actor state とする。
- Relationship の durable record は `RelationshipSnapshotRecord` とする。
- Affect は Iris の baseline/current affect state として `AffectBaselineRecord` に保存する。
- Global affect baseline は `scope="global"` かつ `actor_id=None` とする。
- Actor-scoped affect は `scope="actor"` かつ `actor_id` 必須とする。
- SQLite backend は relationship store と affect store を durable にする。
- Memory、relationship、affect は同じ runtime SQLite DB path を共有してよいが、table と contract は分ける。
- Space は relationship / affect の durable owner ではない。
- Companion UX 向けの global mood、actor relationship、actor affect trace、space atmosphere、recent interaction tone の分離は ADR 0016 に従う。

## Non-decisions

- LLM による memory extraction はこの ADR の対象外。
- Relationship / affect を raw activity journal に混ぜない。
- Activity projection、presence、space occupancy を durable state にしない。
- Relationship / affect update policy はこの ADR の対象外。ここでは state ownership と persistence だけを決める。
- Space atmosphere や recent interaction tone を durable relationship / affect owner に昇格する仕様は決めない。

## Consequences

SQLite backend は以下を durable にする。

- account store
- memory store
- relationship store
- affect store
- activity journal

以下は ephemeral または derived のままにする。

- activity projection
- presence
- space occupancy
- space atmosphere
- recent interaction tone

Activity journal は audit/debug/replay support のために durable にできる。ただし activity projection、presence、space occupancy、space atmosphere、recent interaction tone の正本ではない。

## Implementation anchors

- `iris/contracts/relationship.py`
- `iris/contracts/affect.py`
- `iris/contracts/companion_affect.py`
- `iris/adapters/persistence/sqlite/stores/relationship.py`
- `iris/adapters/persistence/sqlite/stores/affect.py`
- `iris/runtime/wiring/state.py`
