"""Read-only runtime diagnostics command."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
from dataclasses import dataclass, replace
from enum import StrEnum
import json
import os
from pathlib import Path
import sqlite3
import sys

from iris.adapters.llm.diagnostics import ProviderReadinessResult, ReadinessStatus
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
from iris.runtime.config import (
    ConfigError,
    IrisRuntimeConfig,
    load_runtime_config,
    resolve_runtime_config_path,
)
from iris.runtime.config.state import RuntimeStateBackend
from iris.runtime.learning.jobs import BackgroundJobStatus
from iris.runtime.observability.diagnostics import DiagnosticsCheckOutcome, run_startup_diagnostics
from iris.runtime.state.memory_candidates import MemoryCandidateReviewStatus
from iris.runtime.wiring.features import wire_runtime_features


@dataclass(frozen=True)
class RuntimeDoctorCheck:
    """runtime doctor の単一 check 結果。"""

    name: str
    status: str
    summary: str
    issue: str | None = None
    next_action: str | None = None


@dataclass(frozen=True)
class RuntimeDoctorReport:
    """runtime doctor の全体結果。"""

    ok: bool
    checks: tuple[RuntimeDoctorCheck, ...]


class _DoctorCliArgs(argparse.Namespace):
    """Typed argparse namespace for runtime doctor."""

    config: str | None
    json: bool


def main() -> None:
    """Runtime doctor CLI entrypoint。

    Raises:
        SystemExit: doctor 結果に対応する process exit code。
    """
    parser = argparse.ArgumentParser(description="Iris runtime doctor")
    parser.add_argument("--config", type=str, help="Use TOML configuration file")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = _DoctorCliArgs(config=None, json=False)
    parser.parse_args(namespace=args)

    with asyncio.Runner() as runner:
        report = runner.run(run_runtime_doctor(config_path=args.config))
    if args.json:
        sys.stdout.write(_format_json(report))
    else:
        sys.stdout.write(_format_text(report))
    raise SystemExit(0 if report.ok else 1)


async def run_runtime_doctor(config_path: str | None = None) -> RuntimeDoctorReport:
    """Runtime doctor checks を read-only で実行する。

    Returns:
        runtime doctor report。
    """
    resolved_path = _resolve_config_path(config_path)
    if resolved_path.check.status == "fail":
        return _report((resolved_path.check,))

    loaded = _load_config(config_path)
    if loaded.config is None:
        return _report((resolved_path.check, loaded.check))

    checks = _runtime_doctor_base_checks(loaded.config)
    checks.extend(await _startup_diagnostics_checks(loaded.config))
    return _report((resolved_path.check, loaded.check, *checks))


@dataclass(frozen=True)
class _ResolvedConfigPath:
    check: RuntimeDoctorCheck


@dataclass(frozen=True)
class _LoadedConfig:
    check: RuntimeDoctorCheck
    config: IrisRuntimeConfig | None


@dataclass(frozen=True)
class _FilePathCheckSpec:
    name: str
    directory_summary: str
    directory_issue: str
    directory_next_action: str
    existing_ok_summary: str
    existing_fail_summary: str
    existing_fail_issue: str
    existing_fail_next_action: str
    missing_ok_summary: str
    missing_fail_summary: str
    missing_fail_issue: str
    missing_fail_next_action: str


@dataclass(frozen=True)
class RuntimeOperationalWiringDiagnostics:
    """Runtime doctor が runtime 起動なしで検査する標準 wiring snapshot。"""

    scheduler_runner_wired: bool = True
    availability_provider_wired: bool = True
    safety_audit_journal_wired: bool = True
    delivery_broker_wired: bool = True
    delivery_safety_gate_wired: bool = True
    output_safety_gate_wired: bool = True
    proactive_talk_enabled: bool = False
    proactive_generation_mode: str = "not_configured"
    proactive_threshold: str = "not_configured"


@dataclass(frozen=True)
class _OperationalStatusSummary:
    """Operational count query の結果状態と危険件数を保持する。"""

    summary: str
    status: str = "ok"
    pending_count: int = 0
    leased_count: int = 0
    failed_count: int = 0
    issue: str | None = None
    next_action: str | None = None


@dataclass(frozen=True)
class _SQLiteSchemaGate:
    """read-only SQLite count query の前提状態。"""

    available: bool
    check: RuntimeDoctorCheck | None = None


def _resolve_config_path(config_path: str | None) -> _ResolvedConfigPath:
    try:
        path = resolve_runtime_config_path(config_path)
    except ConfigError as exc:
        return _ResolvedConfigPath(
            _build_check(
                "config-discovery",
                status="fail",
                summary="config path resolution failed",
                issue=str(exc),
                next_action="check --config path or IRIS_MIND_CONFIG",
            ),
        )
    summary = "built-in defaults"
    if path is not None:
        summary = str(path)
    return _ResolvedConfigPath(
        _build_check("config-discovery", status="ok", summary=summary),
    )


def _load_config(config_path: str | None) -> _LoadedConfig:
    try:
        config = load_runtime_config(config_path)
    except ConfigError as exc:
        return _LoadedConfig(
            check=_build_check(
                "config-parse",
                status="fail",
                summary="config parse / validation failed",
                issue=str(exc),
                next_action="fix runtime TOML or environment override",
            ),
            config=None,
        )
    return _LoadedConfig(
        check=_build_check("config-parse", status="ok", summary="config parsed and validated"),
        config=config,
    )


def _state_backend_check(config: IrisRuntimeConfig) -> RuntimeDoctorCheck:
    return _build_check(
        "state-backend",
        status="ok",
        summary=f"selected state backend: {config.state.backend.value}",
    )


def _sqlite_state_check(config: IrisRuntimeConfig) -> RuntimeDoctorCheck:
    if config.state.backend is not RuntimeStateBackend.SQLITE:
        return _build_check("sqlite-state", status="skipped", summary="state.backend is not sqlite")
    path = Path(config.state.sqlite_path)
    path_check = _sqlite_state_path_check(path)
    if path_check.status == "fail" or not path.exists():
        return path_check
    return _sqlite_schema_check(path)


def _sqlite_state_path_check(path: Path) -> RuntimeDoctorCheck:
    return _check_file_path(
        path,
        spec=_FilePathCheckSpec(
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
        return _build_check(
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
    return _build_check(
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
        return _build_check(
            "sqlite-state",
            status="fail",
            summary=f"unsupported sqlite schema at {path}",
            issue=str(exc),
            next_action="upgrade Iris before opening this database",
        )
    if isinstance(exc, SQLiteCorruptDatabaseError):
        return _build_check(
            "sqlite-state",
            status="fail",
            summary=f"sqlite integrity check failed: {path}",
            issue=str(exc),
            next_action="restore from a verified SQLite backup; do not delete the DB silently",
        )
    return _build_check(
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


def _runtime_learning_state_check(config: IrisRuntimeConfig) -> RuntimeDoctorCheck:
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
    return _build_check("runtime-learning-state", status="skipped", summary=summary)


def _runtime_learning_schema_check(path: Path) -> RuntimeDoctorCheck | None:
    try:
        schema = SQLiteSchemaMigrator().inspect(path)
    except SQLiteSchemaError as exc:
        return _build_check(
            "runtime-learning-state",
            status="fail",
            summary="runtime learning state is not readable",
            issue=str(exc),
            next_action="fix sqlite-state check before inspecting learning state",
        )
    if schema.pending_versions:
        return _build_check(
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
        return _build_check(
            "runtime-learning-state",
            status="fail",
            summary="runtime learning state query failed",
            issue=str(exc),
            next_action="inspect SQLite runtime learning tables or restore from backup",
        )
    return _build_check("runtime-learning-state", status="ok", summary=summary)


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


def _logging_path_check(config: IrisRuntimeConfig) -> RuntimeDoctorCheck:
    file_path = config.logging.file_path
    if file_path is None:
        return _build_check(
            "logging-file",
            status="skipped",
            summary="logging.file_path is not set",
        )
    return _check_file_path(
        Path(file_path),
        spec=_FilePathCheckSpec(
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


def _server_check(config: IrisRuntimeConfig) -> RuntimeDoctorCheck:
    local = "local-only" if config.server.local_only else "network-visible"
    return _build_check(
        "server",
        status="ok",
        summary=f"{config.server.host}:{config.server.port} ({local})",
    )


def _model_slots_check(config: IrisRuntimeConfig) -> RuntimeDoctorCheck:
    slots = (
        f"default_chat={config.models.default_chat.provider.value}:{config.models.default_chat.model}",
        f"fast_judge={config.models.fast_judge.provider.value}:{config.models.fast_judge.model}",
        f"reasoning={config.models.reasoning.provider.value}:{config.models.reasoning.model}",
    )
    return _build_check("model-slots", status="ok", summary=", ".join(slots))


def _delivery_check(config: IrisRuntimeConfig) -> RuntimeDoctorCheck:
    status = "enabled" if config.delivery.enabled else "disabled"
    return _build_check("delivery", status="ok", summary=status)


def _scheduler_check(config: IrisRuntimeConfig) -> RuntimeDoctorCheck:
    status = "enabled" if config.scheduler.enabled else "disabled"
    return _build_check("scheduler", status="ok", summary=status)


def _scheduler_runtime_check(
    config: IrisRuntimeConfig,
    wiring: RuntimeOperationalWiringDiagnostics,
) -> RuntimeDoctorCheck:
    enabled = "enabled" if config.scheduler.enabled else "disabled"
    loop = "enabled" if config.scheduler.enabled else "disabled"
    target_store = config.state.backend.value
    summary = (
        f"enabled={enabled} loop={loop} "
        f"runner_wired={_wired_status(wired=wiring.scheduler_runner_wired)} "
        f"target_store={target_store} "
        f"availability_provider={_wired_status(wired=wiring.availability_provider_wired)} "
        f"safety_audit_journal={_wired_status(wired=wiring.safety_audit_journal_wired)}"
    )
    issues = _scheduler_runtime_warning_issues(config, wiring)
    if not issues:
        return _build_check("scheduler-runtime", status="ok", summary=summary)
    return _build_check(
        "scheduler-runtime",
        status="warn",
        summary=summary,
        issue=_issue_summary(issues),
        next_action="complete scheduler runtime wiring before enabling scheduler",
    )


def _scheduler_runtime_warning_issues(
    config: IrisRuntimeConfig,
    wiring: RuntimeOperationalWiringDiagnostics,
) -> tuple[str, ...]:
    if not config.scheduler.enabled:
        return ()
    warning_checks = (
        (
            not wiring.scheduler_runner_wired,
            "scheduler.enabled=true but scheduler runner is not wired",
        ),
        (
            not wiring.availability_provider_wired,
            "scheduler.enabled=true but availability_provider is not wired",
        ),
        (
            not wiring.safety_audit_journal_wired,
            "scheduler.enabled=true but safety_audit_journal is not wired",
        ),
    )
    return tuple(issue for has_warning, issue in warning_checks if has_warning)


def _delivery_outbox_check(
    config: IrisRuntimeConfig,
    wiring: RuntimeOperationalWiringDiagnostics,
) -> RuntimeDoctorCheck:
    counts = _delivery_outbox_status_summary(config)
    backend = config.state.backend.value
    delivery = "enabled" if config.delivery.enabled else "disabled"
    broker = _wired_status(wired=wiring.delivery_broker_wired and config.delivery.enabled)
    summary = f"enabled={delivery} backend={backend} broker={broker}; {counts.summary}"
    if counts.status != "ok":
        return _build_check(
            "delivery-outbox",
            status=counts.status,
            summary=summary,
            issue=counts.issue,
            next_action=counts.next_action,
        )
    if not config.delivery.enabled and counts.pending_count > 0:
        return _build_check(
            "delivery-outbox",
            status="warn",
            summary=summary,
            issue="delivery outbox has pending items but delivery broker is disabled",
            next_action="enable delivery worker/broker or drain pending outbox items",
        )
    return _build_check("delivery-outbox", status="ok", summary=summary)


def _delivery_outbox_status_summary(config: IrisRuntimeConfig) -> _OperationalStatusSummary:
    if config.state.backend is not RuntimeStateBackend.SQLITE:
        return _OperationalStatusSummary(
            summary=_ordered_zero_counts(DeliveryStatus),
        )
    return _sqlite_delivery_outbox_status_summary(Path(config.state.sqlite_path))


def _sqlite_delivery_outbox_status_summary(path: Path) -> _OperationalStatusSummary:
    if not path.exists() or path.is_dir():
        return _OperationalStatusSummary(
            summary="sqlite state DB is not available",
            status="skipped",
        )
    gate = _sqlite_counts_schema_gate(path, "delivery-outbox")
    if gate.check is not None:
        return _summary_from_gate_check(gate.check)
    return _query_delivery_outbox_status_summary(path)


def _query_delivery_outbox_status_summary(path: Path) -> _OperationalStatusSummary:
    try:
        with contextlib.closing(sqlite3.connect(path)) as conn:
            conn.row_factory = sqlite3.Row
            counts = _delivery_outbox_status_counts(conn)
    except sqlite3.DatabaseError as exc:
        return _sqlite_operational_query_failure("delivery_outbox", exc)
    summary = _ordered_counts(counts, DeliveryStatus)
    return _OperationalStatusSummary(
        summary=summary,
        pending_count=counts.get(DeliveryStatus.PENDING.value, 0),
        leased_count=counts.get(DeliveryStatus.LEASED.value, 0),
        failed_count=counts.get(DeliveryStatus.FAILED_PERMANENT.value, 0),
    )


def _background_jobs_check(config: IrisRuntimeConfig) -> RuntimeDoctorCheck:
    counts = _background_job_status_summary(config)
    backend = config.state.backend.value
    loop = "enabled" if config.learning.background_jobs_enabled else "disabled"
    summary = f"loop={loop} backend={backend}; {counts.summary}"
    if counts.status != "ok":
        return _build_check(
            "background-jobs",
            status=counts.status,
            summary=summary,
            issue=counts.issue,
            next_action=counts.next_action,
        )
    if not config.learning.background_jobs_enabled and _has_background_job_work(counts):
        return _build_check(
            "background-jobs",
            status="warn",
            summary=summary,
            issue="background jobs are pending or failed but background job loop is disabled",
            next_action="enable learning.background_jobs_enabled or drain background jobs",
        )
    return _build_check("background-jobs", status="ok", summary=summary)


def _background_job_status_summary(config: IrisRuntimeConfig) -> _OperationalStatusSummary:
    if config.state.backend is not RuntimeStateBackend.SQLITE:
        return _OperationalStatusSummary(summary=_ordered_zero_counts(BackgroundJobStatus))
    return _sqlite_background_job_status_summary(Path(config.state.sqlite_path))


def _sqlite_background_job_status_summary(path: Path) -> _OperationalStatusSummary:
    if not path.exists() or path.is_dir():
        return _OperationalStatusSummary(
            summary="sqlite state DB is not available",
            status="skipped",
        )
    gate = _sqlite_counts_schema_gate(path, "background-jobs")
    if gate.check is not None:
        return _summary_from_gate_check(gate.check)
    return _query_background_job_status_summary(path)


def _query_background_job_status_summary(path: Path) -> _OperationalStatusSummary:
    try:
        with contextlib.closing(sqlite3.connect(path)) as conn:
            conn.row_factory = sqlite3.Row
            counts = _background_job_status_counts(conn)
    except sqlite3.DatabaseError as exc:
        return _sqlite_operational_query_failure("background_jobs", exc)
    summary = _ordered_counts(counts, BackgroundJobStatus)
    return _OperationalStatusSummary(
        summary=summary,
        pending_count=counts.get(BackgroundJobStatus.PENDING.value, 0),
        leased_count=counts.get(BackgroundJobStatus.LEASED.value, 0),
        failed_count=(
            counts.get(BackgroundJobStatus.FAILED_RETRYABLE.value, 0)
            + counts.get(BackgroundJobStatus.FAILED_PERMANENT.value, 0)
        ),
    )


def _has_background_job_work(counts: _OperationalStatusSummary) -> bool:
    return counts.pending_count > 0 or counts.leased_count > 0 or counts.failed_count > 0


def _proactive_safety_check(
    config: IrisRuntimeConfig,
    wiring: RuntimeOperationalWiringDiagnostics,
) -> RuntimeDoctorCheck:
    proactive = "enabled" if wiring.proactive_talk_enabled else "disabled"
    delivery_safety = _delivery_safety_mode(config, wiring)
    quiet_hours = _quiet_hours_summary(config)
    output_safety = _output_safety_mode(config, wiring)
    audit_journal = _wired_status(wired=wiring.safety_audit_journal_wired)
    summary = (
        f"proactive_talk={proactive} "
        f"generation_mode={wiring.proactive_generation_mode} "
        f"threshold={wiring.proactive_threshold} "
        f"delivery_safety={delivery_safety} "
        f"quiet_hours={quiet_hours} "
        f"output_safety={output_safety} "
        f"safety_audit_journal={audit_journal}"
    )
    issues = _proactive_safety_warning_issues(config, wiring)
    if not issues:
        return _build_check("proactive-safety", status="ok", summary=summary)
    return _build_check(
        "proactive-safety",
        status="warn",
        summary=summary,
        issue=_issue_summary(issues),
        next_action="complete proactive safety wiring before enabling proactive delivery",
    )


def _proactive_safety_warning_issues(
    config: IrisRuntimeConfig,
    wiring: RuntimeOperationalWiringDiagnostics,
) -> tuple[str, ...]:
    if not wiring.proactive_talk_enabled:
        return ()
    warning_checks = (
        (
            not wiring.delivery_safety_gate_wired,
            "proactive_talk enabled but delivery safety gate is not configured",
        ),
        (
            not wiring.output_safety_gate_wired or config.safety.mode == "development",
            "proactive_talk enabled but output safety gate is not configured",
        ),
        (
            not wiring.safety_audit_journal_wired,
            "proactive_talk enabled but safety_audit_journal is not wired",
        ),
    )
    return tuple(issue for has_warning, issue in warning_checks if has_warning)


def _issue_summary(issues: tuple[str, ...]) -> str:
    return "; ".join(issues)


def _delivery_safety_mode(
    config: IrisRuntimeConfig,
    wiring: RuntimeOperationalWiringDiagnostics,
) -> str:
    if not wiring.delivery_safety_gate_wired:
        return "not_configured"
    if config.safety.mode == "strict":
        return "strict"
    return "basic"


def _output_safety_mode(
    config: IrisRuntimeConfig,
    wiring: RuntimeOperationalWiringDiagnostics,
) -> str:
    if not wiring.output_safety_gate_wired:
        return "not_configured"
    if config.safety.mode in {"basic", "strict"}:
        return "basic_output_filter"
    return "allow_all"


def _quiet_hours_summary(config: IrisRuntimeConfig) -> str:
    quiet_hours = config.delivery.quiet_hours
    status = "enabled" if quiet_hours.enabled else "disabled"
    return f"{status} {quiet_hours.start}-{quiet_hours.end} {quiet_hours.timezone}"


def _wired_status(*, wired: bool) -> str:
    return "wired" if wired else "not_wired"


def _standard_operational_wiring(config: IrisRuntimeConfig) -> RuntimeOperationalWiringDiagnostics:
    feature_catalog = wire_runtime_features()
    proactive_talk_enabled = any(
        feature.name == "proactive_talk" for feature in feature_catalog.features
    )
    return RuntimeOperationalWiringDiagnostics(
        delivery_broker_wired=config.delivery.enabled,
        proactive_talk_enabled=proactive_talk_enabled,
    )


def _summary_from_gate_check(check: RuntimeDoctorCheck) -> _OperationalStatusSummary:
    return _OperationalStatusSummary(
        summary=check.summary,
        status=check.status,
        issue=check.issue,
        next_action=check.next_action,
    )


def _sqlite_operational_query_failure(
    table_name: str,
    exc: sqlite3.DatabaseError,
) -> _OperationalStatusSummary:
    return _OperationalStatusSummary(
        summary=f"{table_name} count query failed",
        status="fail",
        issue=str(exc),
        next_action="inspect SQLite operational tables or restore from backup",
    )


def _sqlite_counts_schema_gate(path: Path, check_name: str) -> _SQLiteSchemaGate:
    try:
        schema = SQLiteSchemaMigrator().inspect(path)
    except SQLiteSchemaError as exc:
        return _SQLiteSchemaGate(
            available=False,
            check=_build_check(
                check_name,
                status="fail",
                summary="sqlite operational state is not readable",
                issue=str(exc),
                next_action="fix sqlite-state check before inspecting operational state",
            ),
        )
    if schema.pending_versions:
        return _SQLiteSchemaGate(
            available=False,
            check=_build_check(
                check_name,
                status="warn",
                summary="sqlite schema migration is pending",
                next_action="start Iris normally to migrate operational tables",
            ),
        )
    return _SQLiteSchemaGate(available=True)


def _ordered_zero_counts[EnumT: StrEnum](enum_type: type[EnumT]) -> str:
    return _ordered_counts({}, enum_type)


def _runtime_doctor_base_checks(config: IrisRuntimeConfig) -> list[RuntimeDoctorCheck]:
    """Runtime doctor の固定チェック群を順序付きで組み立てる。

    Returns:
        順序を保った RuntimeDoctorCheck の list。
    """
    wiring = _standard_operational_wiring(config)
    return [
        _state_backend_check(config),
        _sqlite_state_check(config),
        _logging_path_check(config),
        _runtime_learning_state_check(config),
        _background_jobs_check(config),
        _server_check(config),
        _model_slots_check(config),
        _delivery_check(config),
        _delivery_outbox_check(config, wiring),
        _scheduler_check(config),
        _scheduler_runtime_check(config, wiring),
        _proactive_safety_check(config, wiring),
    ]


async def _startup_diagnostics_checks(
    config: IrisRuntimeConfig,
) -> tuple[RuntimeDoctorCheck, ...]:
    try:
        report = await run_startup_diagnostics(_read_only_diagnostics_config(config))
    except ConfigError as exc:
        return (
            _build_check(
                "provider-readiness",
                status="fail",
                summary="startup diagnostics failed",
                issue=str(exc),
                next_action="fix provider configuration or set diagnostics.mode=warn",
            ),
        )
    if not report.enabled:
        return (
            _build_check(
                "provider-readiness",
                status="skipped",
                summary="diagnostics.mode is off",
            ),
        )
    checks = [_diagnostics_outcome_check(outcome) for outcome in report.outcomes]
    if not checks:
        checks.append(
            _build_check(
                "provider-readiness",
                status="skipped",
                summary="all model slots use fake provider",
            ),
        )
    return tuple(checks)


def _read_only_diagnostics_config(config: IrisRuntimeConfig) -> IrisRuntimeConfig:
    """Provider warmup を無効化した runtime doctor 用 config を返す。

    Returns:
        diagnostics.warmup_models が False の runtime config。
    """
    return replace(
        config,
        diagnostics=replace(config.diagnostics, warmup_models=False),
    )


def _check_file_path(path: Path, *, spec: _FilePathCheckSpec) -> RuntimeDoctorCheck:
    if path.is_dir():
        return _directory_file_path_check(path, spec=spec)
    if path.exists():
        return _existing_file_path_check(path, spec=spec)
    return _missing_file_path_check(path, spec=spec)


def _directory_file_path_check(path: Path, *, spec: _FilePathCheckSpec) -> RuntimeDoctorCheck:
    return _build_file_path_check(
        spec,
        status="fail",
        summary=spec.directory_summary.format(path=path),
        issue=spec.directory_issue,
        next_action=spec.directory_next_action,
    )


def _existing_file_path_check(path: Path, *, spec: _FilePathCheckSpec) -> RuntimeDoctorCheck:
    if os.access(path, os.R_OK) and os.access(path, os.W_OK):
        return _build_file_path_check(
            spec,
            status="ok",
            summary=spec.existing_ok_summary.format(path=path, parent=path.parent),
        )
    return _build_file_path_check(
        spec,
        status="fail",
        summary=spec.existing_fail_summary.format(path=path, parent=path.parent),
        issue=spec.existing_fail_issue,
        next_action=spec.existing_fail_next_action,
    )


def _missing_file_path_check(path: Path, *, spec: _FilePathCheckSpec) -> RuntimeDoctorCheck:
    parent = path.parent
    if parent.exists() and os.access(parent, os.W_OK | os.X_OK):
        return _build_file_path_check(
            spec,
            status="ok",
            summary=spec.missing_ok_summary.format(path=path, parent=parent),
        )
    return _build_file_path_check(
        spec,
        status="fail",
        summary=spec.missing_fail_summary.format(path=path, parent=parent),
        issue=spec.missing_fail_issue,
        next_action=spec.missing_fail_next_action,
    )


def _build_file_path_check(
    spec: _FilePathCheckSpec,
    *,
    status: str,
    summary: str,
    issue: str | None = None,
    next_action: str | None = None,
) -> RuntimeDoctorCheck:
    return _build_check(
        spec.name,
        status=status,
        summary=summary,
        issue=issue,
        next_action=next_action,
    )


def _diagnostics_outcome_check(outcome: DiagnosticsCheckOutcome) -> RuntimeDoctorCheck:
    stage = _worst_diagnostics_stage(outcome.readiness, outcome.warmup)
    status = stage.status.value
    issue = stage.issue_code
    next_action = stage.next_action
    summary = _diagnostics_summary(outcome, stage)
    return _build_check(
        "provider-readiness",
        status=status,
        summary=summary,
        issue=issue,
        next_action=next_action,
    )


def _build_check(
    name: str,
    *,
    status: str,
    summary: str,
    issue: str | None = None,
    next_action: str | None = None,
) -> RuntimeDoctorCheck:
    return RuntimeDoctorCheck(
        name=name,
        status=status,
        summary=summary,
        issue=issue,
        next_action=next_action,
    )


@dataclass(frozen=True)
class _DiagnosticsStage:
    stage: str
    status: ReadinessStatus
    issue_code: str | None
    next_action: str | None


def _worst_diagnostics_stage(
    readiness: ProviderReadinessResult,
    warmup: ProviderReadinessResult | None,
) -> _DiagnosticsStage:
    stages: list[_DiagnosticsStage] = [_diagnostics_stage("readiness", readiness)]
    if warmup is not None:
        stages.append(_diagnostics_stage("warmup", warmup))
    return max(stages, key=_diagnostics_stage_rank)


def _diagnostics_stage_rank(stage: _DiagnosticsStage) -> int:
    return _status_rank(stage.status)


def _diagnostics_stage(stage: str, result: ProviderReadinessResult) -> _DiagnosticsStage:
    issue = result.issues[0] if result.issues else None
    issue_code = None if issue is None else f"{stage}:{issue.code}"
    next_action = None if issue is None else issue.remediation
    return _DiagnosticsStage(
        stage=stage,
        status=result.status,
        issue_code=issue_code,
        next_action=next_action,
    )


def _status_rank(status: ReadinessStatus) -> int:
    if status is ReadinessStatus.FAIL:
        return 3
    if status is ReadinessStatus.WARN:
        return 2
    if status is ReadinessStatus.OK:
        return 1
    return 0


def _diagnostics_summary(
    outcome: DiagnosticsCheckOutcome,
    stage: _DiagnosticsStage,
) -> str:
    readiness = outcome.readiness.status.value
    warmup = "none" if outcome.warmup is None else outcome.warmup.status.value
    return (
        f"{outcome.slot} {outcome.provider.value} {outcome.model} "
        f"readiness={readiness} warmup={warmup} selected={stage.stage}:{stage.status.value}"
    )


def _report(
    checks: tuple[RuntimeDoctorCheck, ...] | list[RuntimeDoctorCheck],
) -> RuntimeDoctorReport:
    ok = all(check.status != "fail" for check in checks)
    return RuntimeDoctorReport(ok=ok, checks=tuple(checks))


def _format_json(report: RuntimeDoctorReport) -> str:
    payload = {"ok": report.ok, "checks": [_check_payload(check) for check in report.checks]}
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _format_text(report: RuntimeDoctorReport) -> str:
    lines = ["Runtime doctor ok:"] if report.ok else ["Runtime doctor failed:"]
    for check in report.checks:
        lines.extend(_format_check_block(check))
    return "\n".join(lines) + "\n"


def _check_payload(check: RuntimeDoctorCheck) -> dict[str, str | None]:
    return {
        "name": check.name,
        "status": check.status,
        "summary": check.summary,
        "issue": check.issue,
        "next_action": check.next_action,
    }


def _format_check_block(check: RuntimeDoctorCheck) -> list[str]:
    lines = ("", f"* {check.name}: {check.summary} [{check.status}]")
    block = [*lines]
    if check.issue is not None:
        block.append(f"  issue: {check.issue}")
    if check.next_action is not None:
        block.append(f"  next: {check.next_action}")
    return block


if __name__ == "__main__":
    main()
