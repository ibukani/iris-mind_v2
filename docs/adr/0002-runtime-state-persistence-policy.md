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
- delivery outbox records
- scheduler targets
- safety audit records
- runtime learning background jobs
- implicit memory candidate review records

SQLite backend でも次は process-local のままにする。

- activity projections
- presence
- space occupancy
- ephemeral space bindings

Delivery outbox と Scheduler target store は `state.backend = "sqlite"` の場合、SQLite バックエンドを利用して永続化される（再起動時の送信漏れやスケジュール喪失を防ぐため）。

Runtime learning background jobs と implicit memory candidate review records も `state.backend = "sqlite"` の場合、SQLite バックエンドを利用して永続化される。これにより、implicit candidate extraction job、retry / lease state、pending review、approved / rejected / discarded lifecycle、promotion metadata は再起動後も失われない。`state.backend = "memory"` では従来通り process-local であり、test / local ephemeral runtime 用途に限定する。

Activity journal は `state.backend = "sqlite"` で durable になる。investigation、debugging、provider event deduplication、future replay、future projection rebuild のための append-only audit log であり、normal runtime processing の hot query path ではない。runtime context は journal scan ではなく projection と current-state store から組み立てる。

Safety audit records は `state.backend = "sqlite"` で durable になる。output safety block / delivery safety block / repeated block 判定用 metadata を restart 越しに保持する。ただし raw user text、prompt、generated output body は保存しない。MVP retention policy は `retention_until` metadata に 90 日後の削除境界を保存するが、自動削除 job は後続 phase とする。

## Non-decisions

- Activity journal から memory / relationship / affect を暗黙復元する仕様は決めない。
- Space binding を durable owner にしない。

## Consequences

`state.backend = "sqlite"` は「すべての runtime store が SQLite」という意味ではない。durable companion state と audit history は SQLite を使い、volatile runtime state は in-memory のままにする。

Actor identity が long-term memory と relationship semantics を所有する。Space は context scope であり、memory の primary owner ではない。Presence と occupancy は current-state signal であり、process restart を越えて残さない。

## Schema management

SQLite backend の schema ownership、migration、backup、restore、corrupt DB recovery は ADR 0012 に従う。`state.backend = "sqlite"` の durable store は store-local `CREATE TABLE` ではなく `SQLiteSchemaMigrator` が管理する known schema を開く。

Activity journal replay は projection rebuild と diagnostics の補助には使えるが、account / relationship / affect / delivery / scheduler state の完全復元元とはみなさない。

## Implementation anchors

- `iris/runtime/config/state.py`
- `iris/runtime/wiring/state.py`
- `iris/runtime/wiring/state_policy.py`
- `iris/adapters/persistence/sqlite/engine.py`
- `iris/adapters/persistence/sqlite/schema/`
- `iris/adapters/persistence/sqlite/stores/account.py`
- `iris/adapters/persistence/sqlite/stores/memory.py`
- `iris/adapters/persistence/sqlite/stores/relationship.py`
- `iris/adapters/persistence/sqlite/stores/affect.py`
- `iris/adapters/persistence/sqlite/stores/activity_journal.py`
- `iris/adapters/persistence/sqlite/stores/delivery_outbox.py`
- `iris/adapters/persistence/sqlite/stores/scheduler_targets.py`
- `iris/adapters/persistence/sqlite/stores/safety_audit.py`
- `iris/adapters/persistence/sqlite/stores/background_jobs.py`
- `iris/adapters/persistence/sqlite/stores/memory_candidate_reviews.py`
