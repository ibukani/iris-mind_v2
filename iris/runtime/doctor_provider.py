"""Runtime doctor の provider diagnostics 変換。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from iris.adapters.llm.diagnostics import ReadinessStatus
from iris.runtime.doctor_models import build_check

if TYPE_CHECKING:
    from iris.adapters.llm.diagnostics import ProviderReadinessResult
    from iris.runtime.config import IrisRuntimeConfig
    from iris.runtime.doctor_models import RuntimeDoctorCheck
    from iris.runtime.observability.diagnostics import DiagnosticsCheckOutcome


def read_only_diagnostics_config(config: IrisRuntimeConfig) -> IrisRuntimeConfig:
    """Provider warmup を無効化した runtime doctor 用 config を返す。

    Returns:
        diagnostics.warmup_models が False の runtime config。
    """
    return replace(
        config,
        diagnostics=replace(config.diagnostics, warmup_models=False),
    )


def diagnostics_outcome_check(outcome: DiagnosticsCheckOutcome) -> RuntimeDoctorCheck:
    """Provider diagnostics outcome を doctor check へ変換する。

    Returns:
        readiness と warmup の厳しい方を反映した check。
    """
    stage = _worst_diagnostics_stage(outcome.readiness, outcome.warmup)
    status = stage.status.value
    issue = stage.issue_code
    next_action = stage.next_action
    summary = _diagnostics_summary(outcome, stage)
    return build_check(
        "provider-readiness",
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
        f"model_load_state={outcome.readiness.model_load_state.value} "
        f"readiness={readiness} warmup={warmup} selected={stage.stage}:{stage.status.value}"
    )
