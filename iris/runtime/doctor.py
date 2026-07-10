"""Read-only runtime diagnostics command."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import sys

from iris.runtime.config import (
    ConfigError,
    IrisRuntimeConfig,
    load_runtime_config,
    resolve_runtime_config_path,
)
from iris.runtime.doctor_formatting import format_json, format_text
from iris.runtime.doctor_models import (
    RuntimeDoctorCheck,
    RuntimeDoctorReport,
    build_check,
    build_report,
)
from iris.runtime.doctor_operations import runtime_doctor_base_checks
from iris.runtime.doctor_provider import (
    diagnostics_outcome_check,
    read_only_diagnostics_config,
)
from iris.runtime.observability.diagnostics import run_startup_diagnostics
from iris.runtime.wiring.runtime import (
    RuntimeOperationalWiringDiagnostics,
    describe_runtime_operational_wiring,
)

__all__ = [
    "RuntimeDoctorCheck",
    "RuntimeDoctorReport",
    "main",
    "run_runtime_doctor",
]


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
        sys.stdout.write(format_json(report))
    else:
        sys.stdout.write(format_text(report))
    raise SystemExit(0 if report.ok else 1)


async def run_runtime_doctor(config_path: str | None = None) -> RuntimeDoctorReport:
    """Runtime doctor checks を read-only で実行する。

    Returns:
        runtime doctor report。
    """
    resolved_path = _resolve_config_path(config_path)
    if resolved_path.check.status == "fail":
        return build_report((resolved_path.check,))

    loaded = _load_config(config_path)
    if loaded.config is None:
        return build_report((resolved_path.check, loaded.check))

    checks = _runtime_doctor_base_checks(loaded.config)
    checks.extend(await _startup_diagnostics_checks(loaded.config))
    return build_report((resolved_path.check, loaded.check, *checks))


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
            build_check(
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
        build_check("config-discovery", status="ok", summary=summary),
    )


def _load_config(config_path: str | None) -> _LoadedConfig:
    try:
        config = load_runtime_config(config_path)
    except ConfigError as exc:
        return _LoadedConfig(
            check=build_check(
                "config-parse",
                status="fail",
                summary="config parse / validation failed",
                issue=str(exc),
                next_action="fix runtime TOML or environment override",
            ),
            config=None,
        )
    return _LoadedConfig(
        check=build_check("config-parse", status="ok", summary="config parsed and validated"),
        config=config,
    )


def _runtime_operational_wiring_snapshot(
    config: IrisRuntimeConfig,
) -> RuntimeOperationalWiringDiagnostics:
    return describe_runtime_operational_wiring(config)


def _runtime_doctor_base_checks(config: IrisRuntimeConfig) -> list[RuntimeDoctorCheck]:
    wiring = _runtime_operational_wiring_snapshot(config)
    return runtime_doctor_base_checks(config, wiring)


async def _startup_diagnostics_checks(
    config: IrisRuntimeConfig,
) -> tuple[RuntimeDoctorCheck, ...]:
    try:
        report = await run_startup_diagnostics(read_only_diagnostics_config(config))
    except ConfigError as exc:
        return (
            build_check(
                "provider-readiness",
                status="fail",
                summary="startup diagnostics failed",
                issue=str(exc),
                next_action="fix provider configuration or set diagnostics.mode=warn",
            ),
        )
    if not report.enabled:
        return (
            build_check(
                "provider-readiness",
                status="skipped",
                summary="diagnostics.mode is off",
            ),
        )
    checks = [diagnostics_outcome_check(outcome) for outcome in report.outcomes]
    if not checks:
        checks.append(
            build_check(
                "provider-readiness",
                status="skipped",
                summary="all model slots use fake provider",
            ),
        )
    return tuple(checks)


if __name__ == "__main__":
    main()
