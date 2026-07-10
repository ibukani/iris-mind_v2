"""Runtime doctor の永続状態と運用キュー検査。"""

from __future__ import annotations

import contextlib
from enum import StrEnum
from pathlib import Path
import sqlite3
from typing import TYPE_CHECKING

from iris.adapters.persistence.sqlite.backup import (
    BACKUP_MANIFEST_FILENAME,
    SQLiteBackupError,
    read_backup_manifest,
)
from iris.adapters.persistence.sqlite.migrator import (
    SQLiteCorruptDatabaseError,
    SQLiteSchemaError,
    SQLiteSchemaMigrator,
    SQLiteUnsupportedSchemaVersionError,
)
from iris.contracts.delivery import DeliveryStatus
from iris.core.datetime_utils import now_utc, parse_datetime
from iris.runtime.config.state import RuntimeStateBackend
from iris.runtime.doctor_filesystem import FilePathCheckSpec, check_file_path
from iris.runtime.doctor_models import (
    OperationalStatusSummary,
    RuntimeDoctorCheck,
    SQLiteSchemaGate,
    build_check,
)
from iris.runtime.learning.jobs import BackgroundJobStatus
from iris.runtime.state.memory_candidates import MemoryCandidateReviewStatus

if TYPE_CHECKING:
    from iris.runtime.config import IrisRuntimeConfig


def state_backend_check(config: IrisRuntimeConfig) -> RuntimeDoctorCheck:
    """選択された runtime state backend を報告する。

    Returns:
        backend 名を含む doctor check。
    """
    return build_check(
        "state-backend",
        status="ok",
        summary=f"selected state backend: {config.state.backend.value}",
    )


def sqlite_state_check(config: IrisRuntimeConfig) -> RuntimeDoctorCheck:
    """SQLite path・schema・backup 状態を検査する。

    Returns:
        SQLite state の doctor check。
    """
    if config.state.backend is not RuntimeStateBackend.SQLITE:
        return build_check("sqlite-state", status="skipped", summary="state.backend is not sqlite")
    path = Path(config.state.sqlite_path)
    path_check = _sqlite_state_path_check(path)
    if path_check.status == "fail" or not path.exists():
        return path_check
    return _sqlite_schema_check(path)


def _sqlite_state_path_check(path: Path) -> RuntimeDoctorCheck:
    return check_file_path(
        path,
        spec=FilePathCheckSpec(
            name="sqlite-state",
            directory_summary="configured sqlite path is a directory: {path}",
            directory_issue="sqlite path must be a file path, not a directory",
            directory_next_action=(
                "change state.sqlite_path / IRIS_STATE_SQLITE_PATH to a file path"
            ),
            existing_ok_summary="{path}",
            existing_fail_summary="cannot access {path}",
            existing_fail_issue="sqlite path is not readable and writable",
            existing_fail_next_action="check directory permissions or set IRIS_STATE_SQLITE_PATH",
            missing_ok_summary="{path} can be created; schema will initialize on startup",
            missing_fail_summary="cannot open {path}",
            missing_fail_issue="sqlite parent directory is not writable",
            missing_fail_next_action="check directory permissions or set IRIS_STATE_SQLITE_PATH",
        ),
    )


def _sqlite_schema_check(path: Path) -> RuntimeDoctorCheck:
    try:
        status = SQLiteSchemaMigrator().inspect(path)
    except SQLiteSchemaError as exc:
        return _sqlite_schema_failure_check(path, exc)
    if status.pending_versions:
        pending = ",".join(str(version) for version in status.pending_versions)
        return build_check(
            "sqlite-state",
            status="warn",
            summary=(
                f"{path} schema_version={status.user_version} "
                f"current={status.current_version} pending={pending} "
                f"{_sqlite_backup_summary(path)}"
            ),
            next_action="start Iris normally to apply supported SQLite migrations",
        )
    latest = status.latest_migration or "none"
    return build_check(
        "sqlite-state",
        status="ok",
        summary=(
            f"{path} schema_version={status.user_version} latest_migration={latest} "
            f"quick_check={status.quick_check} {status.wal_checkpoint} "
            f"{_sqlite_backup_summary(path)}"
        ),
    )


def _sqlite_schema_failure_check(path: Path, exc: SQLiteSchemaError) -> RuntimeDoctorCheck:
    if isinstance(exc, SQLiteUnsupportedSchemaVersionError):
        return build_check(
            "sqlite-state",
            status="fail",
            summary=f"unsupported sqlite schema at {path}",
            issue=str(exc),
            next_action="upgrade Iris before opening this database",
        )
    if isinstance(exc, SQLiteCorruptDatabaseError):
        return build_check(
            "sqlite-state",
            status="fail",
            summary=f"sqlite integrity check failed: {path}",
            issue=str(exc),
            next_action="restore from a verified SQLite backup; do not delete the DB silently",
        )
    return build_check(
        "sqlite-state",
        status="fail",
        summary=f"sqlite schema check failed: {path}",
        issue=str(exc),
        next_action=("inspect schema_migrations and restore from backup if history is not trusted"),
    )


def _sqlite_backup_summary(path: Path) -> str:
    manifest_path = path.parent / "backup" / BACKUP_MANIFEST_FILENAME
    backup_summary = "backup_age=unknown"
    if manifest_path.exists():
        try:
            manifest = read_backup_manifest(manifest_path)
        except SQLiteBackupError:
            return backup_summary
        created_at = parse_datetime(manifest.created_at)
        if Path(manifest.source_db_path) == path and created_at is not None:
            age_seconds = max(0, int((now_utc() - created_at).total_seconds()))
            backup_summary = f"backup_age_seconds={age_seconds}"
    return backup_summary


def runtime_learning_state_check(config: IrisRuntimeConfig) -> RuntimeDoctorCheck:
    """Runtime learning 永続テーブルの schema と件数を検査する。

    Returns:
        runtime learning state の doctor check。
    """
    if config.state.backend is not RuntimeStateBackend.SQLITE:
        return _runtime_learning_state_skipped("state.backend is not sqlite")
    path = Path(config.state.sqlite_path)
    if not path.exists() or path.is_dir():
        return _runtime_learning_state_skipped("sqlite state DB is not available")
    schema_check = _runtime_learning_schema_check(path)
    if schema_check is not None:
        return schema_check
    return _sqlite_runtime_learning_counts_check(path)


def _runtime_learning_state_skipped(summary: str) -> RuntimeDoctorCheck:
    return build_check("runtime-learning-state", status="skipped", summary=summary)


def _runtime_learning_schema_check(path: Path) -> RuntimeDoctorCheck | None:
    try:
        schema = SQLiteSchemaMigrator().inspect(path)
    except SQLiteSchemaError as exc:
        return build_check(
            "runtime-learning-state",
            status="fail",
            summary="runtime learning state is not readable",
            issue=str(exc),
            next_action="fix sqlite-state check before inspecting learning state",
        )
    if schema.pending_versions:
        return build_check(
            "runtime-learning-state",
            status="warn",
            summary="sqlite schema migration is pending",
            next_action="start Iris normally to migrate runtime learning tables",
        )
    return None


def _sqlite_runtime_learning_counts_check(path: Path) -> RuntimeDoctorCheck:
    try:
        summary = _runtime_learning_counts_summary(path)
    except sqlite3.DatabaseError as exc:
        return build_check(
            "runtime-learning-state",
            status="fail",
            summary="runtime learning state query failed",
            issue=str(exc),
            next_action="inspect SQLite runtime learning tables or restore from backup",
        )
    return build_check("runtime-learning-state", status="ok", summary=summary)


def _runtime_learning_counts_summary(path: Path) -> str:
    with contextlib.closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        job_counts = _background_job_status_counts(conn)
        review_counts = _candidate_review_status_counts(conn)
    job_summary = _ordered_counts(job_counts, BackgroundJobStatus)
    review_summary = _ordered_counts(review_counts, MemoryCandidateReviewStatus)
    return f"background_jobs {job_summary}; memory_candidate_reviews {review_summary}"


def _background_job_status_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows: list[sqlite3.Row] = conn.execute(
        "SELECT status, COUNT(*) AS count FROM background_jobs GROUP BY status"
    ).fetchall()
    return dict(_status_count_pair(row) for row in rows)


def _delivery_outbox_status_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows: list[sqlite3.Row] = conn.execute(
        "SELECT status, COUNT(*) AS count FROM delivery_outbox GROUP BY status"
    ).fetchall()
    return dict(_status_count_pair(row) for row in rows)


def _candidate_review_status_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows: list[sqlite3.Row] = conn.execute(
        "SELECT status, COUNT(*) AS count FROM memory_candidate_reviews GROUP BY status"
    ).fetchall()
    return dict(_status_count_pair(row) for row in rows)


def _status_count_pair(row: sqlite3.Row) -> tuple[str, int]:
    status_value: object = row["status"]
    count_value: object = row["count"]
    return str(status_value), _sqlite_int(count_value)


def _sqlite_int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    message = f"unexpected SQLite count value: {value!r}"
    raise TypeError(message)


def _ordered_counts[EnumT: StrEnum](counts: dict[str, int], enum_type: type[EnumT]) -> str:
    parts = [f"{status.value}={counts.get(status.value, 0)}" for status in enum_type]
    return " ".join(parts)


def logging_path_check(config: IrisRuntimeConfig) -> RuntimeDoctorCheck:
    """Logging file path の作成・読み書き可否を検査する。

    Returns:
        logging path の doctor check。
    """
    file_path = config.logging.file_path
    if file_path is None:
        return build_check(
            "logging-file",
            status="skipped",
            summary="logging.file_path is not set",
        )
    return check_file_path(
        Path(file_path),
        spec=FilePathCheckSpec(
            name="logging-file",
            directory_summary="configured logging file path is a directory: {path}",
            directory_issue="logging file path must be a file path, not a directory",
            directory_next_action="change logging.file_path or delete/replace the directory",
            existing_ok_summary="{path}",
            existing_fail_summary="logging parent is not writable: {parent}",
            existing_fail_issue="log file parent cannot be written",
            existing_fail_next_action="create directory or change logging.file_path",
            missing_ok_summary="{path} can be created",
            missing_fail_summary="logging parent is not writable: {parent}",
            missing_fail_issue="log file parent cannot be written",
            missing_fail_next_action="create directory or change logging.file_path",
        ),
    )


def delivery_outbox_status_summary(config: IrisRuntimeConfig) -> OperationalStatusSummary:
    """Delivery outbox の status 件数を read-only で集計する。

    Returns:
        outbox status summary。
    """
    if config.state.backend is not RuntimeStateBackend.SQLITE:
        return OperationalStatusSummary(
            summary=_ordered_zero_counts(DeliveryStatus),
        )
    return _sqlite_delivery_outbox_status_summary(Path(config.state.sqlite_path))


def _sqlite_delivery_outbox_status_summary(path: Path) -> OperationalStatusSummary:
    if not path.exists() or path.is_dir():
        return OperationalStatusSummary(
            summary="sqlite state DB is not available",
            status="skipped",
        )
    gate = _sqlite_counts_schema_gate(path, "delivery-outbox")
    if gate.check is not None:
        return _summary_from_gate_check(gate.check)
    return _querydelivery_outbox_status_summary(path)


def _querydelivery_outbox_status_summary(path: Path) -> OperationalStatusSummary:
    try:
        with contextlib.closing(sqlite3.connect(path)) as conn:
            conn.row_factory = sqlite3.Row
            counts = _delivery_outbox_status_counts(conn)
    except sqlite3.DatabaseError as exc:
        return _sqlite_operational_query_failure("delivery_outbox", exc)
    summary = _ordered_counts(counts, DeliveryStatus)
    return OperationalStatusSummary(
        summary=summary,
        pending_count=counts.get(DeliveryStatus.PENDING.value, 0),
        leased_count=counts.get(DeliveryStatus.LEASED.value, 0),
        failed_count=counts.get(DeliveryStatus.FAILED_PERMANENT.value, 0),
    )


def background_job_status_summary(config: IrisRuntimeConfig) -> OperationalStatusSummary:
    """Background job の status 件数を read-only で集計する。

    Returns:
        background job status summary。
    """
    if config.state.backend is not RuntimeStateBackend.SQLITE:
        return OperationalStatusSummary(summary=_ordered_zero_counts(BackgroundJobStatus))
    return _sqlite_background_job_status_summary(Path(config.state.sqlite_path))


def _sqlite_background_job_status_summary(path: Path) -> OperationalStatusSummary:
    if not path.exists() or path.is_dir():
        return OperationalStatusSummary(
            summary="sqlite state DB is not available",
            status="skipped",
        )
    gate = _sqlite_counts_schema_gate(path, "background-jobs")
    if gate.check is not None:
        return _summary_from_gate_check(gate.check)
    return _querybackground_job_status_summary(path)


def _querybackground_job_status_summary(path: Path) -> OperationalStatusSummary:
    try:
        with contextlib.closing(sqlite3.connect(path)) as conn:
            conn.row_factory = sqlite3.Row
            counts = _background_job_status_counts(conn)
    except sqlite3.DatabaseError as exc:
        return _sqlite_operational_query_failure("background_jobs", exc)
    summary = _ordered_counts(counts, BackgroundJobStatus)
    return OperationalStatusSummary(
        summary=summary,
        pending_count=counts.get(BackgroundJobStatus.PENDING.value, 0),
        leased_count=counts.get(BackgroundJobStatus.LEASED.value, 0),
        failed_count=(
            counts.get(BackgroundJobStatus.FAILED_RETRYABLE.value, 0)
            + counts.get(BackgroundJobStatus.FAILED_PERMANENT.value, 0)
        ),
    )


def has_background_job_work(counts: OperationalStatusSummary) -> bool:
    """処理待ち・lease中・失敗 job が存在するか判定する。

    Returns:
        運用対応が必要な件数があれば True。
    """
    return counts.pending_count > 0 or counts.leased_count > 0 or counts.failed_count > 0


def _summary_from_gate_check(check: RuntimeDoctorCheck) -> OperationalStatusSummary:
    return OperationalStatusSummary(
        summary=check.summary,
        status=check.status,
        issue=check.issue,
        next_action=check.next_action,
    )


def _sqlite_operational_query_failure(
    table_name: str,
    exc: sqlite3.DatabaseError,
) -> OperationalStatusSummary:
    return OperationalStatusSummary(
        summary=f"{table_name} count query failed",
        status="fail",
        issue=str(exc),
        next_action="inspect SQLite operational tables or restore from backup",
    )


def _sqlite_counts_schema_gate(path: Path, check_name: str) -> SQLiteSchemaGate:
    try:
        schema = SQLiteSchemaMigrator().inspect(path)
    except SQLiteSchemaError as exc:
        return SQLiteSchemaGate(
            available=False,
            check=build_check(
                check_name,
                status="fail",
                summary="sqlite operational state is not readable",
                issue=str(exc),
                next_action="fix sqlite-state check before inspecting operational state",
            ),
        )
    if schema.pending_versions:
        return SQLiteSchemaGate(
            available=False,
            check=build_check(
                check_name,
                status="warn",
                summary="sqlite schema migration is pending",
                next_action="start Iris normally to migrate operational tables",
            ),
        )
    return SQLiteSchemaGate(available=True)


def _ordered_zero_counts[EnumT: StrEnum](enum_type: type[EnumT]) -> str:
    return _ordered_counts({}, enum_type)
