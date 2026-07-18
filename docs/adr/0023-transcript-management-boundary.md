# ADR 0023: Transcript management boundary

## Status

Accepted

## Context

Issue #73 は、raw conversation transcript を canonical memory と分離したまま、owner scope 内で query / export / cleanup する management boundary を求める。

Read-only query / export は `TranscriptReadService`、stable cursor、bounded page / export、`transcript.read` scope で実装済みである。Cleanup mutation は retry、process restart、複数 management client を考慮し、dry-run と execution を区別する必要がある。

## Decision

`TranscriptCleanupRequest` は次を必須にする。

- `operation_id`
- actor / account / space を一つ以上含む `TranscriptAccessScope`
- `cutoff`
- `dry_run`
- `TranscriptDeletionPolicy`

`TranscriptCleanupResult` は target、eligible、deleted、excluded の件数、除外理由、operation reuse、`OrderingDecision` を返す。

SQLite cleanup は `BEGIN IMMEDIATE` transaction 内で scope と cutoff を再評価し、transcript record の削除と `transcript_cleanup_operations` への operation result 保存を同一 transaction で行う。同じ `operation_id` と同じ request fingerprint の再実行は保存済み result を返す。同じ `operation_id` に異なる request fingerprint が届いた場合は mutation せず `version_conflict` を返す。

`legal_hold_until` が cleanup cutoff より後の record は `legal_hold` 理由で除外する。Retention prune も有効な legal hold を削除しない。

Cleanup は transcript store だけを変更する。次の owner へ削除を伝搬しない。

- canonical memory
- memory / interaction policy review candidate
- background job
- delivery outbox / delivery history
- relationship / affect state

Cross-store deletion を要求する `TranscriptDeletionPolicy` は transcript cleanup の対象にせず、`policy_disabled` として除外する。Distributed transaction や暗黙 cascade は導入しない。

Authorization は `admin` principal と `transcript.cleanup` scope を要求する。`admin.runtime` は既存の admin scope delegation policy に従う。External client と trusted adapter は cleanup を実行できない。

`TranscriptCleanupService` は default-disabled とする。#74 の observation / transcript / state mutation ordering と production-like multi-client gate が完了するまで、標準 runtime wiring は cleanup mutation を有効化しない。無効時は mutation せず `defer` decision を返す。

## Non-decisions

Control Plane UI、public gRPC management RPC、canonical memory cleanup、review candidate cleanup、background job cleanup、delivery outbox cleanupはこの ADR で実装しない。

Cluster-wide total order、distributed lock、distributed transaction は導入しない。

## Consequences

管理 client は実削除前に同一 scope / cutoff の対象件数と legal hold 除外件数を確認できる。Execution retry と process restart 後の retry は同じ operation result に収束し、operation identity の誤再利用は silent last-write-wins にならない。

Transcript cleanup は他の durable owner を変更しないため、memory、review、job、delivery の lifecycle は各 store の policy に留まる。

## Implementation anchors

- `iris/contracts/transcript.py`
- `iris/runtime/transcript/service.py`
- `iris/runtime/state/transcript.py`
- `iris/adapters/persistence/sqlite/stores/transcript.py`
- `iris/adapters/persistence/sqlite/migrations/v0008_transcript_cleanup.py`
- `tests/adapters/persistence/sqlite/test_transcript_store.py`
- `tests/runtime/auth/test_authorization_policy.py`
