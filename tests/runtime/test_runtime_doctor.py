"""Runtime doctor command tests."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import replace
import json
import sqlite3
from typing import TYPE_CHECKING

import pytest

from iris.adapters.llm.diagnostics import (
    ProviderCapability,
    ProviderDiagnosticIssue,
    ProviderReadinessResult,
    ReadinessStatus,
)
from iris.adapters.llm.lifecycle import ModelLoadState
from iris.adapters.persistence.sqlite.backup import SQLiteBackupService
from iris.adapters.persistence.sqlite.migrator import SQLiteSchemaMigrator
from iris.runtime import doctor
from iris.runtime.config import IrisRuntimeConfig, RuntimeSafetyConfig, default_runtime_config
from iris.runtime.config.llm import LLMProvider, ModelSlotName
from iris.runtime.config.state import RuntimeStateBackend
from iris.runtime.doctor import main, run_runtime_doctor
from iris.runtime.observability.diagnostics import DiagnosticsCheckOutcome, StartupDiagnosticsReport
from iris.runtime.wiring.runtime import RuntimeOperationalWiringDiagnostics

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


@pytest.mark.anyio
async def test_runtime_doctor_default_config_reports_ok(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Default fake-provider config passes runtime doctor."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("IRIS_MIND_CONFIG", raising=False)

    report = await run_runtime_doctor()

    assert report.ok
    names = {check.name for check in report.checks}
    assert "config-discovery" in names
    assert "config-parse" in names
    assert "state-backend" in names
    assert "provider-readiness" in names
    assert "delivery" in names
    assert "delivery-outbox" in names
    assert "background-jobs" in names
    assert "scheduler" in names
    assert "scheduler-runtime" in names
    assert "proactive-safety" in names


@pytest.mark.anyio
async def test_runtime_doctor_default_memory_backend_reports_operational_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Memory backend の doctor は scheduler/delivery/proactive 状態を表示する。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("IRIS_MIND_CONFIG", raising=False)
    monkeypatch.setattr(doctor, "run_startup_diagnostics", _disabled_startup_diagnostics)

    report = await run_runtime_doctor()

    delivery_check = next(item for item in report.checks if item.name == "delivery-outbox")
    assert delivery_check.status == "ok"
    assert "enabled=enabled backend=memory broker=wired" in delivery_check.summary
    assert "pending=0 leased=0" in delivery_check.summary
    background_check = next(item for item in report.checks if item.name == "background-jobs")
    assert background_check.status == "ok"
    assert "loop=enabled backend=memory" in background_check.summary
    scheduler_check = next(item for item in report.checks if item.name == "scheduler-runtime")
    assert scheduler_check.status == "ok"
    assert "enabled=disabled loop=disabled runner_wired=wired" in scheduler_check.summary
    assert "availability_provider=wired" in scheduler_check.summary
    proactive_check = next(item for item in report.checks if item.name == "proactive-safety")
    assert proactive_check.status == "ok"
    assert "proactive_talk=disabled" in proactive_check.summary
    assert "generation_mode=not_configured" in proactive_check.summary
    assert "threshold=not_configured" in proactive_check.summary
    assert "quiet_hours=disabled 22:00-08:00 Asia/Tokyo" in proactive_check.summary
    assert "output_safety=allow_all" in proactive_check.summary
    assert "safety_audit_journal=wired" in proactive_check.summary


@pytest.mark.anyio
async def test_runtime_doctor_missing_explicit_config_reports_failure(tmp_path: Path) -> None:
    """Missing explicit config path is reported as a config discovery failure."""
    missing = tmp_path / "missing.toml"

    report = await run_runtime_doctor(str(missing))

    assert not report.ok
    failure = next(check for check in report.checks if check.status == "fail")
    assert failure.name in {"config-discovery", "config-parse"}
    assert failure.next_action in {
        "check --config path or IRIS_MIND_CONFIG",
        "fix runtime TOML or environment override",
    }


def test_runtime_doctor_json_cli_outputs_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """--json CLI emits a JSON report."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("IRIS_MIND_CONFIG", raising=False)
    monkeypatch.setattr("sys.argv", ["iris.runtime.doctor", "--json"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["checks"][0]["name"] == "config-discovery"


@pytest.mark.anyio
async def test_runtime_doctor_forces_startup_diagnostics_warmup_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime doctor は startup diagnostics に warmup_models=False を渡す。"""

    async def fake_run_startup_diagnostics(
        config: IrisRuntimeConfig,
    ) -> StartupDiagnosticsReport:
        await asyncio.sleep(0)
        assert not config.diagnostics.warmup_models
        return StartupDiagnosticsReport(outcomes=(), enabled=True)

    config = default_runtime_config()
    warmup_config = replace(
        config,
        diagnostics=replace(config.diagnostics, warmup_models=True),
    )
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(warmup_config))
    monkeypatch.setattr(doctor, "run_startup_diagnostics", fake_run_startup_diagnostics)

    report = await run_runtime_doctor()

    assert report.checks[-1] == doctor.RuntimeDoctorCheck(
        name="provider-readiness",
        status="skipped",
        summary="all model slots use fake provider",
    )


@pytest.mark.anyio
async def test_runtime_doctor_provider_readiness_reports_model_load_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider readiness check summary includes the model load state."""
    check = await _provider_check(
        monkeypatch,
        _outcome(
            readiness=_result(ReadinessStatus.OK, model_load_state=ModelLoadState.WARM),
            warmup=None,
        ),
    )

    assert "model_load_state=warm" in check.summary


@pytest.mark.anyio
async def test_runtime_doctor_warmup_fail_overrides_readiness_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Readiness OK でも warmup FAIL なら doctor check は fail。"""
    check = await _provider_check(
        monkeypatch,
        _outcome(
            readiness=_result(ReadinessStatus.OK),
            warmup=_result(
                ReadinessStatus.FAIL,
                issue_code="model_still_not_loaded",
                remediation="restart ollama",
            ),
        ),
    )

    assert check.status == "fail"
    assert check.issue == "warmup:model_still_not_loaded"
    assert check.next_action == "restart ollama"


@pytest.mark.anyio
async def test_runtime_doctor_warmup_warn_overrides_readiness_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Readiness OK でも warmup WARN なら doctor check は warn。"""
    check = await _provider_check(
        monkeypatch,
        _outcome(
            readiness=_result(ReadinessStatus.OK),
            warmup=_result(ReadinessStatus.WARN, issue_code="model_not_loaded"),
        ),
    )

    assert check.status == "warn"
    assert check.issue == "warmup:model_not_loaded"


@pytest.mark.anyio
async def test_runtime_doctor_readiness_fail_wins_without_warmup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Readiness FAIL かつ warmup 無しなら doctor check は fail。"""
    check = await _provider_check(
        monkeypatch,
        _outcome(
            readiness=_result(ReadinessStatus.FAIL, issue_code="model_missing"),
            warmup=None,
        ),
    )

    assert check.status == "fail"
    assert check.issue == "readiness:model_missing"


@pytest.mark.anyio
async def test_runtime_doctor_reports_most_severe_diagnostics_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Readiness と warmup の両方に issue がある場合は最重度を反映する。"""
    check = await _provider_check(
        monkeypatch,
        _outcome(
            readiness=_result(ReadinessStatus.WARN, issue_code="tags_unavailable"),
            warmup=_result(
                ReadinessStatus.FAIL,
                issue_code="warmup_timeout",
                remediation="raise timeout",
            ),
        ),
    )

    assert check.status == "fail"
    assert check.issue == "warmup:warmup_timeout"
    assert check.next_action == "raise timeout"


async def _provider_check(
    monkeypatch: pytest.MonkeyPatch,
    outcome: DiagnosticsCheckOutcome,
) -> doctor.RuntimeDoctorCheck:
    async def fake_run_startup_diagnostics(
        config: IrisRuntimeConfig,
    ) -> StartupDiagnosticsReport:
        await asyncio.sleep(0)
        del config
        return StartupDiagnosticsReport(outcomes=(outcome,), enabled=True)

    config = default_runtime_config()
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(config))
    monkeypatch.setattr(doctor, "run_startup_diagnostics", fake_run_startup_diagnostics)

    report = await run_runtime_doctor()

    return next(check for check in report.checks if check.name == "provider-readiness")


def _loaded_config(config: IrisRuntimeConfig) -> Callable[[str | None], IrisRuntimeConfig]:
    def fake_load_config(config_path: str | None = None) -> IrisRuntimeConfig:
        del config_path
        return config

    return fake_load_config


def _outcome(
    *,
    readiness: ProviderReadinessResult,
    warmup: ProviderReadinessResult | None,
) -> DiagnosticsCheckOutcome:
    return DiagnosticsCheckOutcome(
        slot=ModelSlotName.DEFAULT_CHAT,
        provider=LLMProvider.OLLAMA,
        model="qwen3:8b",
        readiness=readiness,
        warmup=warmup,
    )


def _result(
    status: ReadinessStatus,
    *,
    issue_code: str | None = None,
    remediation: str | None = None,
    model_load_state: ModelLoadState = ModelLoadState.UNKNOWN,
) -> ProviderReadinessResult:
    issues: tuple[ProviderDiagnosticIssue, ...] = ()
    if issue_code is not None:
        issues = (
            ProviderDiagnosticIssue(
                code=issue_code,
                message=issue_code,
                severity=status,
                remediation=remediation,
            ),
        )
    return ProviderReadinessResult(
        provider=LLMProvider.OLLAMA.value,
        model="qwen3:8b",
        status=status,
        capabilities=ProviderCapability(warmup=True),
        issues=issues,
        model_load_state=model_load_state,
    )


# ---------------------------------------------------------------------------
# Task 1 regression tests: path false-positive fixes
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_sqlite_path_is_directory_reports_fail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """sqlite_path が directory なら sqlite-state check は fail。"""
    sqlite_dir = tmp_path / "iris_state_dir"
    sqlite_dir.mkdir()

    config = default_runtime_config()
    sqlite_config = replace(
        config,
        state=replace(
            config.state,
            backend=RuntimeStateBackend.SQLITE,
            sqlite_path=str(sqlite_dir),
        ),
    )
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(sqlite_config))

    report = await run_runtime_doctor()

    sqlite_check = next(c for c in report.checks if c.name == "sqlite-state")
    assert sqlite_check.status == "fail"
    assert "directory" in sqlite_check.summary
    assert sqlite_check.issue is not None
    assert "file path" in sqlite_check.issue
    assert sqlite_check.next_action is not None
    assert "IRIS_STATE_SQLITE_PATH" in sqlite_check.next_action


@pytest.mark.anyio
async def test_sqlite_existing_file_reports_ok(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """既存の readable/writable sqlite file は OK になる。"""
    sqlite_file = tmp_path / "iris.db"
    SQLiteSchemaMigrator().ensure_current(sqlite_file)

    config = default_runtime_config()
    sqlite_config = replace(
        config,
        state=replace(
            config.state,
            backend=RuntimeStateBackend.SQLITE,
            sqlite_path=str(sqlite_file),
        ),
    )
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(sqlite_config))

    report = await run_runtime_doctor()

    sqlite_check = next(c for c in report.checks if c.name == "sqlite-state")
    assert sqlite_check.status == "ok"


@pytest.mark.anyio
async def test_sqlite_missing_path_with_writable_parent_reports_ok(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """sqlite_path が存在しないが親 directory が writable なら OK。"""
    sqlite_file = tmp_path / "iris.db"  # does not exist yet

    config = default_runtime_config()
    sqlite_config = replace(
        config,
        state=replace(
            config.state,
            backend=RuntimeStateBackend.SQLITE,
            sqlite_path=str(sqlite_file),
        ),
    )
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(sqlite_config))

    report = await run_runtime_doctor()

    sqlite_check = next(c for c in report.checks if c.name == "sqlite-state")
    assert sqlite_check.status == "ok"
    assert "can be created" in sqlite_check.summary


@pytest.mark.anyio
async def test_logging_file_path_is_directory_reports_fail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """logging.file_path が directory なら logging-file check は fail。"""
    log_dir = tmp_path / "iris_log_dir"
    log_dir.mkdir()

    config = default_runtime_config()
    logging_config = replace(
        config,
        logging=replace(config.logging, file_path=str(log_dir)),
    )
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(logging_config))

    report = await run_runtime_doctor()

    logging_check = next(c for c in report.checks if c.name == "logging-file")
    assert logging_check.status == "fail"
    assert "directory" in logging_check.summary
    assert logging_check.issue is not None
    assert "file path" in logging_check.issue
    assert logging_check.next_action is not None
    assert "directory" in logging_check.next_action


@pytest.mark.anyio
async def test_logging_existing_file_reports_ok(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """既存の writable logging file は OK になる。"""
    log_file = tmp_path / "iris.log"
    log_file.write_bytes(b"")

    config = default_runtime_config()
    logging_config = replace(
        config,
        logging=replace(config.logging, file_path=str(log_file)),
    )
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(logging_config))

    report = await run_runtime_doctor()

    logging_check = next(c for c in report.checks if c.name == "logging-file")
    assert logging_check.status == "ok"


@pytest.mark.anyio
async def test_runtime_doctor_reports_sqlite_schema_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Current SQLite DB は schema version と latest migration を表示する。"""
    db_path = tmp_path / "state.sqlite3"
    SQLiteSchemaMigrator().ensure_current(db_path)
    config = _sqlite_config(db_path)
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(config))
    monkeypatch.setattr(doctor, "run_startup_diagnostics", _disabled_startup_diagnostics)

    report = await run_runtime_doctor()

    check = next(item for item in report.checks if item.name == "sqlite-state")
    assert check.status == "ok"
    assert "schema_version=6" in check.summary
    assert "latest_migration=background_job_pressure" in check.summary


@pytest.mark.anyio
async def test_runtime_doctor_warns_on_pending_sqlite_migration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Unversioned SQLite DB は read-only doctor で pending migration として表示する。"""
    db_path = tmp_path / "legacy.sqlite3"
    db_path.write_bytes(b"")
    config = _sqlite_config(db_path)
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(config))
    monkeypatch.setattr(doctor, "run_startup_diagnostics", _disabled_startup_diagnostics)

    report = await run_runtime_doctor()

    check = next(item for item in report.checks if item.name == "sqlite-state")
    assert check.status == "warn"
    assert "pending=1,2,3,4,5,6" in check.summary


@pytest.mark.anyio
async def test_runtime_doctor_reports_sqlite_backup_age_when_manifest_is_known(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """標準 backup manifest がある場合は sqlite-state に backup age を出す。"""
    db_path = tmp_path / "state.sqlite3"
    SQLiteSchemaMigrator().ensure_current(db_path)
    SQLiteBackupService().create_backup(db_path, tmp_path / "backup")
    config = _sqlite_config(db_path)
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(config))
    monkeypatch.setattr(doctor, "run_startup_diagnostics", _disabled_startup_diagnostics)

    report = await run_runtime_doctor()

    check = next(item for item in report.checks if item.name == "sqlite-state")
    assert check.status == "ok"
    assert "backup_age_seconds=" in check.summary


@pytest.mark.anyio
async def test_runtime_doctor_reports_runtime_learning_state_counts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """SQLite runtime learning state counts は read-only doctor に表示される。"""
    db_path = tmp_path / "state.sqlite3"
    SQLiteSchemaMigrator().ensure_current(db_path)
    _insert_runtime_learning_state_rows(db_path)
    config = _sqlite_config(db_path)
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(config))
    monkeypatch.setattr(doctor, "run_startup_diagnostics", _disabled_startup_diagnostics)

    report = await run_runtime_doctor()

    check = next(item for item in report.checks if item.name == "runtime-learning-state")
    assert check.status == "ok"
    assert "background_jobs pending=1 leased=1 succeeded=0 failed_retryable=1" in check.summary
    assert "failed_permanent=0 cancelled=0" in check.summary
    assert (
        "memory_candidate_reviews pending_review=1 approved=1 rejected=0 discarded=0"
        in check.summary
    )


@pytest.mark.anyio
async def test_runtime_doctor_reports_sqlite_delivery_outbox_counts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """SQLite delivery_outbox status counts は本文なしで doctor に表示される。"""
    db_path = tmp_path / "state.sqlite3"
    SQLiteSchemaMigrator().ensure_current(db_path)
    _insert_delivery_outbox_rows(db_path)
    config = _sqlite_config(db_path)
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(config))
    monkeypatch.setattr(doctor, "run_startup_diagnostics", _disabled_startup_diagnostics)

    report = await run_runtime_doctor()

    check = next(item for item in report.checks if item.name == "delivery-outbox")
    assert check.status == "ok"
    assert "backend=sqlite" in check.summary
    assert (
        "pending=1 leased=1 succeeded=0 failed_permanent=1 cancelled=0 blocked=1" in check.summary
    )
    assert "SECRET_USER_MESSAGE" not in check.summary


@pytest.mark.anyio
async def test_runtime_doctor_reports_background_jobs_as_dedicated_check(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Background job queue counts は dedicated check として表示される。"""
    db_path = tmp_path / "state.sqlite3"
    SQLiteSchemaMigrator().ensure_current(db_path)
    _insert_runtime_learning_state_rows(db_path)
    config = _sqlite_config(db_path)
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(config))
    monkeypatch.setattr(doctor, "run_startup_diagnostics", _disabled_startup_diagnostics)

    report = await run_runtime_doctor()

    check = next(item for item in report.checks if item.name == "background-jobs")
    assert check.status == "ok"
    assert "loop=enabled backend=sqlite" in check.summary
    assert "pending=1 leased=1 succeeded=0 failed_retryable=1" in check.summary
    assert "failed_permanent=0 cancelled=0" in check.summary


@pytest.mark.anyio
async def test_runtime_doctor_warns_on_delivery_disabled_with_pending_outbox(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Delivery disabled で pending outbox があれば warn になる。"""
    db_path = tmp_path / "state.sqlite3"
    SQLiteSchemaMigrator().ensure_current(db_path)
    _insert_delivery_outbox_rows(db_path)
    config = _sqlite_config(db_path)
    config = replace(config, delivery=replace(config.delivery, enabled=False))
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(config))
    monkeypatch.setattr(doctor, "run_startup_diagnostics", _disabled_startup_diagnostics)

    report = await run_runtime_doctor()

    check = next(item for item in report.checks if item.name == "delivery-outbox")
    assert check.status == "warn"
    assert check.issue == "delivery outbox has pending items but delivery broker is disabled"
    assert "enabled=disabled backend=sqlite broker=not_wired" in check.summary


@pytest.mark.anyio
async def test_runtime_doctor_warns_on_background_jobs_disabled_with_work(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Background job loop disabled で未処理 job があれば warn になる。"""
    db_path = tmp_path / "state.sqlite3"
    SQLiteSchemaMigrator().ensure_current(db_path)
    _insert_runtime_learning_state_rows(db_path)
    config = _sqlite_config(db_path)
    config = replace(
        config,
        learning=replace(config.learning, background_jobs_enabled=False),
    )
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(config))
    monkeypatch.setattr(doctor, "run_startup_diagnostics", _disabled_startup_diagnostics)

    report = await run_runtime_doctor()

    check = next(item for item in report.checks if item.name == "background-jobs")
    assert check.status == "warn"
    assert (
        check.issue == "background jobs are pending or failed but background job loop is disabled"
    )
    assert "loop=disabled backend=sqlite" in check.summary


@pytest.mark.anyio
async def test_runtime_doctor_warns_on_scheduler_without_availability_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scheduler enabled で availability provider が欠落すると warn になる。"""
    config = _scheduler_enabled_config()
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(config))
    monkeypatch.setattr(doctor, "run_startup_diagnostics", _disabled_startup_diagnostics)
    monkeypatch.setattr(
        doctor,
        "_runtime_operational_wiring_snapshot",
        _static_wiring(RuntimeOperationalWiringDiagnostics(availability_provider_wired=False)),
    )

    report = await run_runtime_doctor()

    check = next(item for item in report.checks if item.name == "scheduler-runtime")
    assert check.status == "warn"
    assert check.issue == "scheduler.enabled=true but availability_provider is not wired"


@pytest.mark.anyio
async def test_runtime_doctor_warns_on_scheduler_without_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scheduler enabled で runner が欠落すると warn になる。"""
    config = _scheduler_enabled_config()
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(config))
    monkeypatch.setattr(doctor, "run_startup_diagnostics", _disabled_startup_diagnostics)
    monkeypatch.setattr(
        doctor,
        "_runtime_operational_wiring_snapshot",
        _static_wiring(RuntimeOperationalWiringDiagnostics(scheduler_runner_wired=False)),
    )

    report = await run_runtime_doctor()

    check = next(item for item in report.checks if item.name == "scheduler-runtime")
    assert check.status == "warn"
    assert check.issue == "scheduler.enabled=true but scheduler runner is not wired"


@pytest.mark.anyio
async def test_runtime_doctor_warns_on_scheduler_without_safety_audit_journal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scheduler enabled で safety audit journal が欠落すると warn になる。"""
    config = _scheduler_enabled_config()
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(config))
    monkeypatch.setattr(doctor, "run_startup_diagnostics", _disabled_startup_diagnostics)
    monkeypatch.setattr(
        doctor,
        "_runtime_operational_wiring_snapshot",
        _static_wiring(RuntimeOperationalWiringDiagnostics(safety_audit_journal_wired=False)),
    )

    report = await run_runtime_doctor()

    check = next(item for item in report.checks if item.name == "scheduler-runtime")
    assert check.status == "warn"
    assert check.issue == "scheduler.enabled=true but safety_audit_journal is not wired"


@pytest.mark.anyio
async def test_runtime_doctor_reports_all_scheduler_partial_wiring_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scheduler wiring 欠落が複数ある場合はすべて issue に出す。"""
    config = _scheduler_enabled_config()
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(config))
    monkeypatch.setattr(doctor, "run_startup_diagnostics", _disabled_startup_diagnostics)
    monkeypatch.setattr(
        doctor,
        "_runtime_operational_wiring_snapshot",
        _static_wiring(
            RuntimeOperationalWiringDiagnostics(
                scheduler_runner_wired=False,
                availability_provider_wired=False,
                safety_audit_journal_wired=False,
            )
        ),
    )

    report = await run_runtime_doctor()

    check = next(item for item in report.checks if item.name == "scheduler-runtime")
    assert check.status == "warn"
    assert check.issue is not None
    assert "scheduler.enabled=true but scheduler runner is not wired" in check.issue
    assert "scheduler.enabled=true but availability_provider is not wired" in check.issue
    assert "scheduler.enabled=true but safety_audit_journal is not wired" in check.issue


@pytest.mark.anyio
async def test_runtime_doctor_warns_on_proactive_without_delivery_safety_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proactive enabled で delivery safety gate が欠落すると warn になる。"""
    config = replace(default_runtime_config(), safety=RuntimeSafetyConfig(mode="strict"))
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(config))
    monkeypatch.setattr(doctor, "run_startup_diagnostics", _disabled_startup_diagnostics)
    monkeypatch.setattr(
        doctor,
        "_runtime_operational_wiring_snapshot",
        _static_wiring(
            RuntimeOperationalWiringDiagnostics(
                proactive_talk_enabled=True,
                delivery_safety_gate_wired=False,
            ),
        ),
    )

    report = await run_runtime_doctor()

    check = next(item for item in report.checks if item.name == "proactive-safety")
    assert check.status == "warn"
    assert check.issue == "proactive_talk enabled but delivery safety gate is not configured"


@pytest.mark.anyio
async def test_runtime_doctor_warns_on_proactive_with_allow_all_output_safety(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proactive enabled で output safety が allow_all なら warn になる。"""
    config = default_runtime_config()
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(config))
    monkeypatch.setattr(doctor, "run_startup_diagnostics", _disabled_startup_diagnostics)
    monkeypatch.setattr(
        doctor,
        "_runtime_operational_wiring_snapshot",
        _static_wiring(RuntimeOperationalWiringDiagnostics(proactive_talk_enabled=True)),
    )

    report = await run_runtime_doctor()

    check = next(item for item in report.checks if item.name == "proactive-safety")
    assert check.status == "warn"
    assert check.issue == "proactive_talk enabled but output safety gate is not configured"
    assert "output_safety=allow_all" in check.summary


@pytest.mark.anyio
async def test_runtime_doctor_warns_on_proactive_without_safety_audit_journal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proactive enabled で safety audit journal が欠落すると warn になる。"""
    config = replace(default_runtime_config(), safety=RuntimeSafetyConfig(mode="strict"))
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(config))
    monkeypatch.setattr(doctor, "run_startup_diagnostics", _disabled_startup_diagnostics)
    monkeypatch.setattr(
        doctor,
        "_runtime_operational_wiring_snapshot",
        _static_wiring(
            RuntimeOperationalWiringDiagnostics(
                proactive_talk_enabled=True,
                safety_audit_journal_wired=False,
            ),
        ),
    )

    report = await run_runtime_doctor()

    check = next(item for item in report.checks if item.name == "proactive-safety")
    assert check.status == "warn"
    assert check.issue == "proactive_talk enabled but safety_audit_journal is not wired"
    assert "safety_audit_journal=not_wired" in check.summary


@pytest.mark.anyio
async def test_runtime_doctor_reports_all_proactive_partial_wiring_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proactive safety 欠落が複数ある場合はすべて issue に出す。"""
    config = default_runtime_config()
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(config))
    monkeypatch.setattr(doctor, "run_startup_diagnostics", _disabled_startup_diagnostics)
    monkeypatch.setattr(
        doctor,
        "_runtime_operational_wiring_snapshot",
        _static_wiring(
            RuntimeOperationalWiringDiagnostics(
                proactive_talk_enabled=True,
                delivery_safety_gate_wired=False,
                output_safety_gate_wired=False,
                safety_audit_journal_wired=False,
            )
        ),
    )

    report = await run_runtime_doctor()

    check = next(item for item in report.checks if item.name == "proactive-safety")
    assert check.status == "warn"
    assert check.issue is not None
    assert "proactive_talk enabled but delivery safety gate is not configured" in check.issue
    assert "proactive_talk enabled but output safety gate is not configured" in check.issue
    assert "proactive_talk enabled but safety_audit_journal is not wired" in check.issue


@pytest.mark.anyio
async def test_runtime_doctor_proactive_disabled_is_not_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proactive disabled なら development safety でも warning にしない。"""
    config = default_runtime_config()
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(config))
    monkeypatch.setattr(doctor, "run_startup_diagnostics", _disabled_startup_diagnostics)

    report = await run_runtime_doctor()

    check = next(item for item in report.checks if item.name == "proactive-safety")
    assert check.status == "ok"
    assert check.issue is None
    assert "proactive_talk=disabled" in check.summary


@pytest.mark.anyio
async def test_runtime_doctor_does_not_emit_user_content_from_operational_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Doctor output は outbox / job / memory candidate の本文を出さない。"""
    db_path = tmp_path / "state.sqlite3"
    SQLiteSchemaMigrator().ensure_current(db_path)
    _insert_delivery_outbox_rows(db_path)
    _insert_runtime_learning_state_rows(db_path)
    config = _sqlite_config(db_path)
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(config))
    monkeypatch.setattr(doctor, "run_startup_diagnostics", _disabled_startup_diagnostics)

    report = await run_runtime_doctor()

    rendered = "\n".join(
        part
        for check in report.checks
        for part in (check.summary, check.issue or "", check.next_action or "")
    )
    assert "SECRET_USER_MESSAGE" not in rendered
    assert "SECRET_JOB_TEXT" not in rendered
    assert "pending text" not in rendered
    assert "approved text" not in rendered


@pytest.mark.anyio
async def test_runtime_doctor_runtime_learning_state_warns_on_pending_migration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Runtime learning tables が未 migrate の DB では doctor が warn する。"""
    db_path = tmp_path / "legacy.sqlite3"
    db_path.write_bytes(b"")
    config = _sqlite_config(db_path)
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(config))
    monkeypatch.setattr(doctor, "run_startup_diagnostics", _disabled_startup_diagnostics)

    report = await run_runtime_doctor()

    check = next(item for item in report.checks if item.name == "runtime-learning-state")
    assert check.status == "warn"
    assert check.summary == "sqlite schema migration is pending"
    assert check.next_action == "start Iris normally to migrate runtime learning tables"
    delivery_check = next(item for item in report.checks if item.name == "delivery-outbox")
    assert delivery_check.status == "warn"
    assert "sqlite schema migration is pending" in delivery_check.summary
    background_check = next(item for item in report.checks if item.name == "background-jobs")
    assert background_check.status == "warn"
    assert "sqlite schema migration is pending" in background_check.summary


@pytest.mark.anyio
async def test_runtime_doctor_fails_on_corrupt_sqlite_db(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Corrupt SQLite DB は doctor でも fail closed として表示する。"""
    db_path = tmp_path / "corrupt.sqlite3"
    db_path.write_bytes(b"not a sqlite database")
    config = _sqlite_config(db_path)
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(config))
    monkeypatch.setattr(doctor, "run_startup_diagnostics", _disabled_startup_diagnostics)

    report = await run_runtime_doctor()

    check = next(item for item in report.checks if item.name == "sqlite-state")
    assert not report.ok
    assert check.status == "fail"
    assert check.next_action == (
        "restore from a verified SQLite backup; do not delete the DB silently"
    )
    assert db_path.read_bytes() == b"not a sqlite database"


@pytest.mark.anyio
async def test_runtime_doctor_fails_on_future_sqlite_schema(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Future SQLite schema version は doctor でも fail closed になる。"""
    db_path = tmp_path / "future.sqlite3"
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        conn.execute("PRAGMA user_version = 99")
        conn.commit()
    config = _sqlite_config(db_path)
    monkeypatch.setattr(doctor, "load_runtime_config", _loaded_config(config))
    monkeypatch.setattr(doctor, "run_startup_diagnostics", _disabled_startup_diagnostics)

    report = await run_runtime_doctor()

    check = next(item for item in report.checks if item.name == "sqlite-state")
    assert not report.ok
    assert check.status == "fail"
    assert check.next_action == "upgrade Iris before opening this database"


def _insert_delivery_outbox_rows(db_path: Path) -> None:
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO delivery_outbox (
                delivery_id, idempotency_key, status, created_at, updated_at, not_before,
                attempts, max_attempts, lease_id, lease_expires_at, blocked_reason,
                last_error_reason, source_observation_id, target_provider,
                target_provider_subject, target_provider_space_ref, target_session_id,
                target_actor_id, target_account_id, target_space_id, action_type,
                action_id, action_session_id, action_correlation_id, action_text
            ) VALUES
                ('delivery-pending', 'delivery-pending', 'pending',
                 '2026-07-01T00:00:00+00:00', '2026-07-01T00:00:00+00:00', NULL,
                 0, 3, NULL, NULL, NULL, NULL, NULL, 'discord', 'user-1', 'space-1',
                 'session-1', 'actor-1', 'account-1', 'space-id-1', 'send_message',
                 'action-pending', 'session-1', 'correlation-pending', 'SECRET_USER_MESSAGE'),
                ('delivery-leased', 'delivery-leased', 'leased',
                 '2026-07-01T00:00:00+00:00', '2026-07-01T00:00:00+00:00', NULL,
                 1, 3, 'lease-1', '2026-07-01T00:05:00+00:00', NULL, NULL, NULL,
                 'discord', 'user-1', 'space-1', 'session-1', 'actor-1', 'account-1',
                 'space-id-1', 'send_message', 'action-leased', 'session-1',
                 'correlation-leased', 'leased body'),
                ('delivery-failed', 'delivery-failed', 'failed_permanent',
                 '2026-07-01T00:00:00+00:00', '2026-07-01T00:00:00+00:00', NULL,
                 3, 3, NULL, NULL, NULL, 'failed', NULL, 'discord', 'user-1', 'space-1',
                 'session-1', 'actor-1', 'account-1', 'space-id-1', 'send_message',
                 'action-failed', 'session-1', 'correlation-failed', 'failed body'),
                ('delivery-blocked', 'delivery-blocked', 'blocked',
                 '2026-07-01T00:00:00+00:00', '2026-07-01T00:00:00+00:00', NULL,
                 0, 3, NULL, NULL, 'quiet_hours', NULL, NULL, 'discord', 'user-1',
                 'space-1', 'session-1', 'actor-1', 'account-1', 'space-id-1',
                 'send_message', 'action-blocked', 'session-1', 'correlation-blocked',
                 'blocked body')
            """
        )
        conn.commit()


def _scheduler_enabled_config() -> IrisRuntimeConfig:
    config = default_runtime_config()
    return replace(config, scheduler=replace(config.scheduler, enabled=True))


def _static_wiring(
    wiring: RuntimeOperationalWiringDiagnostics,
) -> Callable[[IrisRuntimeConfig], RuntimeOperationalWiringDiagnostics]:
    def build_wiring(config: IrisRuntimeConfig) -> RuntimeOperationalWiringDiagnostics:
        del config
        return wiring

    return build_wiring


def _insert_runtime_learning_state_rows(db_path: Path) -> None:
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO background_jobs (
                job_id, kind, payload_type, payload_json, status, attempts, max_attempts,
                not_before, leased_until, idempotency_key, created_at, updated_at, last_error
            ) VALUES
                ('job-pending', 'reflection', 'deferred_learning',
                 '{"text":"SECRET_JOB_TEXT"}', 'pending', 0, 3,
                 '2026-07-01T00:00:00+00:00', NULL, 'job-pending',
                 '2026-07-01T00:00:00+00:00', '2026-07-01T00:00:00+00:00', NULL),
                ('job-leased', 'reflection', 'deferred_learning', '{}', 'leased', 0, 3,
                 '2026-07-01T00:00:00+00:00', '2026-07-01T00:05:00+00:00', 'job-leased',
                 '2026-07-01T00:00:00+00:00', '2026-07-01T00:00:00+00:00', NULL),
                ('job-retry', 'reflection', 'deferred_learning', '{}', 'failed_retryable', 1, 3,
                 '2026-07-01T00:00:00+00:00', NULL, 'job-retry',
                 '2026-07-01T00:00:00+00:00', '2026-07-01T00:00:00+00:00', 'retry')
            """
        )
        conn.execute(
            """
            INSERT INTO memory_candidate_reviews (
                candidate_id, idempotency_key, status, candidate_json, candidate_text,
                candidate_kind, candidate_source, candidate_confidence, candidate_salience,
                candidate_retention_policy, candidate_sensitivity, candidate_review_required,
                metadata_json, created_at, updated_at
            ) VALUES
                ('candidate-pending', 'candidate-pending', 'pending_review', '{}', 'pending text',
                 'preference', 'implicit_conversation', 0.7, 0.6, 'review_required', 'normal', 1,
                 '{}', '2026-07-01T00:00:00+00:00', '2026-07-01T00:00:00+00:00'),
                ('candidate-approved', 'candidate-approved', 'approved', '{}', 'approved text',
                 'preference', 'implicit_conversation', 0.8, 0.7, 'review_required', 'normal', 1,
                 '{}', '2026-07-01T00:00:00+00:00', '2026-07-01T00:00:00+00:00')
            """
        )
        conn.commit()


async def _disabled_startup_diagnostics(
    config: IrisRuntimeConfig,
) -> StartupDiagnosticsReport:
    del config
    await asyncio.sleep(0)
    return StartupDiagnosticsReport(outcomes=(), enabled=False)


def _sqlite_config(db_path: Path) -> IrisRuntimeConfig:
    config = default_runtime_config()
    return replace(
        config,
        state=replace(
            config.state,
            backend=RuntimeStateBackend.SQLITE,
            sqlite_path=str(db_path),
        ),
    )
