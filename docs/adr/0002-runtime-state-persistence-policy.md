# ADR 0002: Runtime State Persistence Policy

## Status

Accepted

## Context

Iris Runtime は二つの state backend を持つ。

- memory
- sqlite

backend は durable companion state と audit history の範囲を決める。全 runtime cache を SQLite 化する設定ではない。

## Decision

`state.backend = "memory"` では全 runtime state が process-local。

`state.backend = "sqlite"` では次を永続化する。

- account bindings
- actor identity links
- long-term memory records
- relationship state
- affect baseline state
- activity journal records

SQLite backend でも次は process-local のままにする。

- activity projections
- presence
- space occupancy
- ephemeral space bindings

Delivery outbox と Scheduler target store は `state.backend = "sqlite"` の場合、SQLite バックエンドを利用して永続化される（再起動時の送信漏れやスケジュール喪失を防ぐため）。

Activity journal は `state.backend = "sqlite"` で durable になる。investigation、debugging、provider event deduplication、future replay、future projection rebuild のための append-only audit log であり、normal runtime processing の hot query path ではない。runtime context は journal scan ではなく projection と current-state store から組み立てる。

## Non-decisions

- Activity journal から memory / relationship / affect を暗黙復元する仕様は決めない。
- Space binding を durable owner にしない。

## Consequences

`state.backend = "sqlite"` は「すべての runtime store が SQLite」という意味ではない。durable companion state と audit history は SQLite を使い、volatile runtime state は in-memory のままにする。

Actor identity が long-term memory と relationship semantics を所有する。Space は context scope であり、memory の primary owner ではない。Presence と occupancy は current-state signal であり、process restart を越えて残さない。

## Implementation anchors

- `iris/runtime/config/state.py`
- `iris/runtime/wiring/state.py`
- `iris/adapters/accounts/sqlite.py`
- `iris/adapters/memory/sqlite.py`
- `iris/adapters/relationship/sqlite.py`
- `iris/adapters/affect/sqlite.py`
- `iris/adapters/activity/sqlite_journal.py`
- `iris/runtime/state/`
