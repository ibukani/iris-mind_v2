"""Read-only runtime diagnostics command."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys

from iris.runtime.config import (
    ConfigError,
    IrisRuntimeConfig,
    load_runtime_config,
    resolve_runtime_config_path,
)
from iris.runtime.config.state import RuntimeStateBackend
from iris.runtime.observability.diagnostics import DiagnosticsCheckOutcome, run_startup_diagnostics


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
    checks: list[RuntimeDoctorCheck] = []
    resolved_path = _resolve_config_path(config_path)
    checks.append(resolved_path.check)
    if resolved_path.check.status == "fail":
        return _report(checks)

    loaded = _load_config(config_path)
    checks.append(loaded.check)
    if loaded.config is None:
        return _report(checks)

    config = loaded.config
    checks.extend(
        (
            _state_backend_check(config),
            _sqlite_state_check(config),
            _logging_path_check(config),
            _server_check(config),
            _model_slots_check(config),
            _delivery_check(config),
            _scheduler_check(config),
        ),
    )
    checks.extend(await _startup_diagnostics_checks(config))
    return _report(checks)


@dataclass(frozen=True)
class _ResolvedConfigPath:
    check: RuntimeDoctorCheck


@dataclass(frozen=True)
class _LoadedConfig:
    check: RuntimeDoctorCheck
    config: IrisRuntimeConfig | None


def _resolve_config_path(config_path: str | None) -> _ResolvedConfigPath:
    try:
        path = resolve_runtime_config_path(config_path)
    except ConfigError as exc:
        return _ResolvedConfigPath(
            RuntimeDoctorCheck(
                name="config-discovery",
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
        RuntimeDoctorCheck(name="config-discovery", status="ok", summary=summary),
    )


def _load_config(config_path: str | None) -> _LoadedConfig:
    try:
        config = load_runtime_config(config_path)
    except ConfigError as exc:
        return _LoadedConfig(
            check=RuntimeDoctorCheck(
                name="config-parse",
                status="fail",
                summary="config parse / validation failed",
                issue=str(exc),
                next_action="fix runtime TOML or environment override",
            ),
            config=None,
        )
    return _LoadedConfig(
        check=RuntimeDoctorCheck(
            name="config-parse",
            status="ok",
            summary="config parsed and validated",
        ),
        config=config,
    )


def _state_backend_check(config: IrisRuntimeConfig) -> RuntimeDoctorCheck:
    return RuntimeDoctorCheck(
        name="state-backend",
        status="ok",
        summary=f"selected state backend: {config.state.backend.value}",
    )


def _sqlite_state_check(config: IrisRuntimeConfig) -> RuntimeDoctorCheck:
    if config.state.backend is not RuntimeStateBackend.SQLITE:
        return RuntimeDoctorCheck(
            name="sqlite-state",
            status="skipped",
            summary="state.backend is not sqlite",
        )
    path = Path(config.state.sqlite_path)
    if path.exists():
        return _existing_sqlite_check(path)
    return _missing_sqlite_check(path)


def _existing_sqlite_check(path: Path) -> RuntimeDoctorCheck:
    if os.access(path, os.R_OK) and os.access(path, os.W_OK):
        return RuntimeDoctorCheck(name="sqlite-state", status="ok", summary=str(path))
    return RuntimeDoctorCheck(
        name="sqlite-state",
        status="fail",
        summary=f"cannot access {path}",
        issue="sqlite path is not readable and writable",
        next_action="check directory permissions or set IRIS_STATE_SQLITE_PATH",
    )


def _missing_sqlite_check(path: Path) -> RuntimeDoctorCheck:
    parent = path.parent
    if parent.exists() and os.access(parent, os.W_OK | os.X_OK):
        return RuntimeDoctorCheck(
            name="sqlite-state",
            status="ok",
            summary=f"{path} can be created",
        )
    return RuntimeDoctorCheck(
        name="sqlite-state",
        status="fail",
        summary=f"cannot open {path}",
        issue="sqlite parent directory is not writable",
        next_action="check directory permissions or set IRIS_STATE_SQLITE_PATH",
    )


def _logging_path_check(config: IrisRuntimeConfig) -> RuntimeDoctorCheck:
    file_path = config.logging.file_path
    if file_path is None:
        return RuntimeDoctorCheck(
            name="logging-file",
            status="skipped",
            summary="logging.file_path is not set",
        )
    parent = Path(file_path).parent
    if parent.exists() and os.access(parent, os.W_OK | os.X_OK):
        return RuntimeDoctorCheck(name="logging-file", status="ok", summary=str(file_path))
    return RuntimeDoctorCheck(
        name="logging-file",
        status="fail",
        summary=f"logging parent is not writable: {parent}",
        issue="log file parent cannot be written",
        next_action="create directory or change logging.file_path",
    )


def _server_check(config: IrisRuntimeConfig) -> RuntimeDoctorCheck:
    local = "local-only" if config.server.local_only else "network-visible"
    return RuntimeDoctorCheck(
        name="server",
        status="ok",
        summary=f"{config.server.host}:{config.server.port} ({local})",
    )


def _model_slots_check(config: IrisRuntimeConfig) -> RuntimeDoctorCheck:
    slots = (
        f"default_chat={config.models.default_chat.provider.value}:{config.models.default_chat.model}",
        f"fast_judge={config.models.fast_judge.provider.value}:{config.models.fast_judge.model}",
        f"reasoning={config.models.reasoning.provider.value}:{config.models.reasoning.model}",
    )
    return RuntimeDoctorCheck(name="model-slots", status="ok", summary=", ".join(slots))


def _delivery_check(config: IrisRuntimeConfig) -> RuntimeDoctorCheck:
    status = "enabled" if config.delivery.enabled else "disabled"
    return RuntimeDoctorCheck(name="delivery", status="ok", summary=status)


def _scheduler_check(config: IrisRuntimeConfig) -> RuntimeDoctorCheck:
    status = "enabled" if config.scheduler.enabled else "disabled"
    return RuntimeDoctorCheck(name="scheduler", status="ok", summary=status)


async def _startup_diagnostics_checks(
    config: IrisRuntimeConfig,
) -> tuple[RuntimeDoctorCheck, ...]:
    try:
        report = await run_startup_diagnostics(config)
    except ConfigError as exc:
        return (
            RuntimeDoctorCheck(
                name="provider-readiness",
                status="fail",
                summary="startup diagnostics failed",
                issue=str(exc),
                next_action="fix provider configuration or set diagnostics.mode=warn",
            ),
        )
    if not report.enabled:
        return (
            RuntimeDoctorCheck(
                name="provider-readiness",
                status="skipped",
                summary="diagnostics.mode is off",
            ),
        )
    checks = [_diagnostics_outcome_check(outcome) for outcome in report.outcomes]
    if not checks:
        checks.append(
            RuntimeDoctorCheck(
                name="provider-readiness",
                status="skipped",
                summary="all model slots use fake provider",
            ),
        )
    return tuple(checks)


def _diagnostics_outcome_check(outcome: DiagnosticsCheckOutcome) -> RuntimeDoctorCheck:
    status = "ok"
    issue = None
    next_action = None
    readiness = outcome.readiness
    if readiness.issues:
        first_issue = readiness.issues[0]
        status = "fail" if readiness.status.value == "fail" else "warn"
        issue = first_issue.code
        next_action = first_issue.remediation
    summary = f"{outcome.slot} {outcome.provider.value} {outcome.model} {readiness.status.value}"
    return RuntimeDoctorCheck(
        name="provider-readiness",
        status=status,
        summary=summary,
        issue=issue,
        next_action=next_action,
    )


def _report(checks: list[RuntimeDoctorCheck]) -> RuntimeDoctorReport:
    ok = all(check.status != "fail" for check in checks)
    return RuntimeDoctorReport(ok=ok, checks=tuple(checks))


def _format_json(report: RuntimeDoctorReport) -> str:
    payload = {
        "ok": report.ok,
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "summary": check.summary,
                "issue": check.issue,
                "next_action": check.next_action,
            }
            for check in report.checks
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _format_text(report: RuntimeDoctorReport) -> str:
    lines = ["Runtime doctor ok:"] if report.ok else ["Runtime doctor failed:"]
    for check in report.checks:
        lines.extend(("", f"* {check.name}: {check.summary} [{check.status}]"))
        if check.issue is not None:
            lines.append(f"  issue: {check.issue}")
        if check.next_action is not None:
            lines.append(f"  next: {check.next_action}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
