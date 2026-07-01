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
from iris.adapters.persistence.sqlite.backup import SQLiteBackupService
from iris.adapters.persistence.sqlite.migrator import SQLiteSchemaMigrator
from iris.runtime import doctor
from iris.runtime.config import IrisRuntimeConfig, default_runtime_config
from iris.runtime.config.llm import LLMProvider, ModelSlotName
from iris.runtime.config.state import RuntimeStateBackend
from iris.runtime.doctor import main, run_runtime_doctor
from iris.runtime.observability.diagnostics import DiagnosticsCheckOutcome, StartupDiagnosticsReport

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
    assert "scheduler" in names


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
    assert "schema_version=1" in check.summary
    assert "latest_migration=baseline_runtime_state" in check.summary


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
    assert "pending=1" in check.summary


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
