"""Runtime doctor command tests."""

from __future__ import annotations

import asyncio
from dataclasses import replace
import json
from typing import TYPE_CHECKING

import pytest

from iris.adapters.llm.diagnostics import (
    ProviderCapability,
    ProviderDiagnosticIssue,
    ProviderReadinessResult,
    ReadinessStatus,
)
from iris.runtime import doctor
from iris.runtime.config import IrisRuntimeConfig, default_runtime_config
from iris.runtime.config.llm import LLMProvider, ModelSlotName
from iris.runtime.doctor import main, run_runtime_doctor
from iris.runtime.observability.diagnostics import DiagnosticsCheckOutcome, StartupDiagnosticsReport

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


@pytest.mark.anyio
async def test_runtime_doctor_default_config_reports_ok() -> None:
    """Default fake-provider config passes runtime doctor."""
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
) -> None:
    """--json CLI emits a JSON report."""
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
