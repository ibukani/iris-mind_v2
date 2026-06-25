# ADR 0004: Relationship And Affect State

## 状態

採択

## 背景

Iris は actor ごとの現在の関係性と、Iris 自身の affect baseline/current state を扱う。
これらは検索対象の memory content ではなく、現在 state として更新される durable contract である。

## 決定

- Relationship は `ActorId` を主キーにした current per-actor state とする。
- Relationship の durable record は `RelationshipSnapshotRecord` とする。
- Affect は Iris の baseline/current affect state として `AffectBaselineRecord` に保存する。
- Global affect baseline は `scope="global"` かつ `actor_id=None` とする。
- Actor-scoped affect は `scope="actor"` かつ `actor_id` 必須とする。
- SQLite backend は relationship store と affect store を durable にする。
- Memory、relationship、affect は同じ runtime SQLite DB path を共有してよいが、table と contract は分ける。
- Space は relationship / affect の durable owner ではない。

## 非決定

- LLM による memory extraction はこの ADR の対象外。
- Relationship / affect を raw activity journal に混ぜない。
- Activity projection、presence、space occupancy を durable state にしない。

## 影響

SQLite backend は以下を durable にする。

- account store
- memory store
- relationship store
- affect store
- activity journal

以下は ephemeral のままにする。

- activity projection
- presence
- space occupancy

Activity journal は audit/debug/replay support のために durable にできる。
ただし activity projection、presence、space occupancy の正本ではない。
