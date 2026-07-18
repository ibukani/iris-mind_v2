"""SQLite schema ownership metadata。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SQLiteSchemaClassification(StrEnum):
    """SQLite table の永続化上の分類。"""

    SOURCE_OF_TRUTH = "source_of_truth"
    DERIVED_INDEX = "derived_rebuildable_index"
    APPEND_ONLY_AUDIT_LOG = "append_only_audit_log"
    PROCESS_LOCAL = "process_local_not_persisted"


@dataclass(frozen=True)
class SQLiteTableOwnership:
    """SQLite table の所有権と復元方針。"""

    table_name: str
    owner: str
    classification: SQLiteSchemaClassification
    notes: str


SQLITE_SCHEMA_OWNERSHIP: tuple[SQLiteTableOwnership, ...] = (
    SQLiteTableOwnership(
        table_name="schema_migrations",
        owner="sqlite migrator",
        classification=SQLiteSchemaClassification.APPEND_ONLY_AUDIT_LOG,
        notes="migration history。PRAGMA user_version と合わせて互換性確認に使う。",
    ),
    SQLiteTableOwnership(
        table_name="accounts",
        owner="SQLiteAccountStore",
        classification=SQLiteSchemaClassification.SOURCE_OF_TRUTH,
        notes="外部 provider subject と内部 account / actor link の正本。",
    ),
    SQLiteTableOwnership(
        table_name="memories",
        owner="SQLiteMemoryStore",
        classification=SQLiteSchemaClassification.SOURCE_OF_TRUTH,
        notes="長期記憶 record の正本。",
    ),
    SQLiteTableOwnership(
        table_name="memories_fts5",
        owner="SQLiteMemoryStore",
        classification=SQLiteSchemaClassification.DERIVED_INDEX,
        notes="memories から rebuild できる全文検索 index。",
    ),
    SQLiteTableOwnership(
        table_name="relationship_snapshots",
        owner="SQLiteRelationshipStore",
        classification=SQLiteSchemaClassification.SOURCE_OF_TRUTH,
        notes="actor identity を主軸にした relationship state。",
    ),
    SQLiteTableOwnership(
        table_name="affect_baselines",
        owner="SQLiteAffectStore",
        classification=SQLiteSchemaClassification.SOURCE_OF_TRUTH,
        notes="affect baseline state の正本。",
    ),
    SQLiteTableOwnership(
        table_name="activity_events",
        owner="SQLiteActivityJournal",
        classification=SQLiteSchemaClassification.APPEND_ONLY_AUDIT_LOG,
        notes="diagnostics / dedupe / future projection rebuild 用 append-only log。",
    ),
    SQLiteTableOwnership(
        table_name="delivery_outbox",
        owner="SQLiteDeliveryOutbox",
        classification=SQLiteSchemaClassification.SOURCE_OF_TRUTH,
        notes="未送信/送信中/失敗 delivery state の正本。",
    ),
    SQLiteTableOwnership(
        table_name="delivery_report_fingerprints",
        owner="SQLiteDeliveryOutbox",
        classification=SQLiteSchemaClassification.SOURCE_OF_TRUTH,
        notes="delivery report idempotency metadata。",
    ),
    SQLiteTableOwnership(
        table_name="scheduler_targets",
        owner="SQLiteSchedulerTargetStore",
        classification=SQLiteSchemaClassification.SOURCE_OF_TRUTH,
        notes="proactive scheduler target の永続 state。",
    ),
    SQLiteTableOwnership(
        table_name="safety_audit_records",
        owner="SQLiteSafetyAuditJournal",
        classification=SQLiteSchemaClassification.APPEND_ONLY_AUDIT_LOG,
        notes="raw user text / generated output body を保存しない safety decision metadata。",
    ),
    SQLiteTableOwnership(
        table_name="background_jobs",
        owner="SQLiteBackgroundJobQueue",
        classification=SQLiteSchemaClassification.SOURCE_OF_TRUTH,
        notes="runtime learning job の lease / retry / failure state の正本。",
    ),
    SQLiteTableOwnership(
        table_name="memory_candidate_reviews",
        owner="SQLiteMemoryCandidateReviewStore",
        classification=SQLiteSchemaClassification.SOURCE_OF_TRUTH,
        notes="implicit learning candidate review lifecycle の正本。",
    ),
    SQLiteTableOwnership(
        table_name="conversation_transcripts",
        owner="SQLiteTranscriptStore",
        classification=SQLiteSchemaClassification.SOURCE_OF_TRUTH,
        notes="opt-in confirmed transcript と retention / legal hold metadata の正本。",
    ),
    SQLiteTableOwnership(
        table_name="transcript_cleanup_operations",
        owner="SQLiteTranscriptStore",
        classification=SQLiteSchemaClassification.SOURCE_OF_TRUTH,
        notes="cleanup request fingerprint と idempotent result の正本。",
    ),
    SQLiteTableOwnership(
        table_name="memory_embeddings",
        owner="future vector index backend",
        classification=SQLiteSchemaClassification.DERIVED_INDEX,
        notes="future external vector index metadata。memory 正本ではない。",
    ),
)

PROCESS_LOCAL_RUNTIME_STORES: tuple[str, ...] = (
    "activity_projection_store",
    "presence_store",
    "space_occupancy_store",
    "conversation_history_store",
    "learning_dispatch_store",
)
