# ADR 0012: SQLite Schema Migration / Backup / Recovery Policy

## Status

Accepted

## Context

`state.backend = "sqlite"` は Iris runtime data の durable backend である。account、memory、relationship、affect、activity journal、delivery outbox、scheduler target は restart を越えて残る state として扱う。

過去の SQLite 初期化は bootstrap 寄りだった。

- SQLAlchemy-managed store は `Base.metadata.create_all()` で table を作成していた。
- `SQLiteMemoryStore` は `CREATE TABLE IF NOT EXISTS` と FTS5 table 作成を store constructor 内で実行していた。
- 明示的な schema version、migration history、backup / restore contract がなかった。

この状態では schema drift、partial migration、future version open、corrupt DB の診断不能、WAL を無視した危険な copy が起きやすい。

## Decision

SQLite schema は `iris/adapters/persistence/sqlite/migrator.py` が所有する。store constructor は schema を独自判断で作らず、migration 済み DB を open する。

Startup path:

```text
SQLite path
→ SQLiteSchemaMigrator.ensure_current()
→ AsyncDatabaseManager / SQLiteMemoryStore / durable stores
```

Schema version は二段構えにする。

- `PRAGMA user_version`: 高速な compatibility check。
- `schema_migrations`: migration version、name、checksum、applied_at の history。

Current schema version は `CURRENT_SQLITE_SCHEMA_VERSION = 1`。runtime は supported old DB を current へ migrate するが、unknown future version は silent open しない。

Baseline migration `v0001_baseline` は current SQLite schema の正本である。対象は以下。

| table | 分類 | owner |
|---|---|---|
| `schema_migrations` | append-only migration log | SQLite migrator |
| `accounts` | source of truth | `SQLiteAccountStore` |
| `memories` | source of truth | `SQLiteMemoryStore` |
| `memories_fts5` | derived / rebuildable index | `SQLiteMemoryStore` |
| `relationship_snapshots` | source of truth | `SQLiteRelationshipStore` |
| `affect_baselines` | source of truth | `SQLiteAffectStore` |
| `activity_events` | append-only audit log | `SQLiteActivityJournal` |
| `delivery_outbox` | source of truth | `SQLiteDeliveryOutbox` |
| `delivery_report_fingerprints` | source of truth / idempotency metadata | `SQLiteDeliveryOutbox` |
| `scheduler_targets` | source of truth | `SQLiteSchedulerTargetStore` |
| future `memory_embeddings` | derived / rebuildable index metadata | vector index backend |

Process-local state は SQLite schema の対象にしない。

- `activity_projection_store`
- `presence_store`
- `space_occupancy_store`
- `conversation_history_store`
- `background_job_queue`
- `memory_candidate_review_store`
- `learning_dispatch_store`

Migration policy:

- store 使用前に migration runner を実行する。
- migration は version 昇順で適用する。
- 各 migration は `BEGIN IMMEDIATE` で transactionally に実行する。
- migration 成功後にのみ `schema_migrations` と `PRAGMA user_version` を更新する。
- failed migration 後に best-effort continuation しない。
- existing unversioned DB は、既存 table が baseline required columns を満たす場合だけ adopt する。
- required columns を欠く unversioned table は fail closed にする。
- `memories_fts5` は derived index なので、baseline migration 時に `memories` から不足 entry を rebuild する。

Backup / restore policy:

- backup は restore 用の SQLite-level snapshot。
- export は selected durable state の portable JSON / JSONL 表現。現時点では未実装。
- backup は SQLite online backup API を使う。
- WAL / SHM を無視した `.db` 単体 copy は採用しない。
- backup artifact は `state.sqlite3` と `manifest.json` を含む。
- manifest は format version、schema version、created_at、source DB path、SQLite checksum、backup DB filename、app version field を持つ。
- restore は manifest と checksum を検証し、既存 target は `overwrite=True` なしに上書きしない。

Corrupt DB / recovery policy:

- startup / doctor は unreadable DB または `PRAGMA quick_check` failure を検出する。
- DB を silent delete / recreate しない。
- startup は fail closed する。
- original DB は保持する。
- recovery instruction と DB path を error / doctor report に出す。
- 明示的な restore path は `SQLiteBackupService.restore_backup()`。

Activity journal replay scope:

- activity journal は diagnostics、provider event dedupe、future projection rebuild に使ってよい。
- activity journal は全 durable state の canonical source ではない。
- account links、relationships、affect baselines、delivery outbox、scheduler targets は、専用 store が source of truth。
- event が明示的に journal され test されていない限り、activity journal から完全復元できると仮定しない。

Runtime doctor は read-only を維持する。SQLite backend では DB path、schema version、latest migration、pending migration、future version rejection、corrupt detection を報告する。doctor は migration を適用しない。

## Non-decisions

- downgrade migration は実装しない。
- remote database は導入しない。
- Alembic は必須にしない。
- export / import はこの ADR では実装しない。
- corrupt DB を自動修復しない。
- activity journal を全 durable state の唯一の source of truth にしない。

## Consequences

SQLite backend は upgrade 可能になり、future schema を誤って開かなくなる。store-local schema bootstrap は段階的に消える。

Migration runner が authoritative になるため、新しい durable table / column は raw SQL migration と test を伴って追加する必要がある。SQLAlchemy model を変更するだけでは schema change とみなさない。

Backup は restorable snapshot として扱えるが、portable export ではない。conflicting identity / account merge policy がない限り、JSON import は追加しない。

## Implementation anchors

- `iris/adapters/persistence/sqlite/schema/version.py`
- `iris/adapters/persistence/sqlite/schema/ownership.py`
- `iris/adapters/persistence/sqlite/migrator.py`
- `iris/adapters/persistence/sqlite/migrator_types.py`
- `iris/adapters/persistence/sqlite/migrations/v0001_baseline.py`
- `iris/adapters/persistence/sqlite/backup.py`
- `iris/adapters/persistence/sqlite/engine.py`
- `iris/adapters/persistence/sqlite/stores/memory.py`
- `iris/runtime/wiring/state.py`
- `iris/runtime/doctor.py`
- `tests/adapters/persistence/sqlite/test_migrations.py`
- `tests/adapters/persistence/sqlite/test_backup_restore.py`
- `tests/runtime/test_runtime_doctor.py`
