"""LLM プロバイダ診断の起動時ランナー。

Server 起動時に各モデルスロット (default_chat / fast_judge / reasoning)
に対して :func:`run_startup_diagnostics` を呼び、non-fake プロバイダの
スロットに対して :meth:`LLMProviderDiagnostics.check_readiness` を実行する。
``diagnostics.warmup_models`` 設定と provider の :class:`ProviderCapability`
が ``warmup=True`` の場合のみ :meth:`LLMProviderDiagnostics.warmup` も実行する。

ファクトリ :func:`iris.runtime.wiring.llm.build_provider_diagnostics` は
``RuntimeModelConfig`` の ``provider`` フィールド (``LLMProvider`` Literal)
で分岐する closed discriminated factory。 ``provider == "fake"`` の場合は
``None`` を返し、診断対象外であることを示す。 adapter 構築失敗は
``ConfigError`` に翻訳されるため、 runner は ``ConfigError`` のみ catch
すればよい。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from iris.adapters.llm.diagnostics import (
    ProviderCapability,
    ProviderDiagnosticIssue,
    ProviderReadinessResult,
    ReadinessStatus,
)
from iris.runtime.config.errors import ConfigError
from iris.runtime.wiring.llm import build_provider_diagnostics

if TYPE_CHECKING:
    from iris.runtime.config.llm import (
        LLMProvider,
        ModelSlotName,
        RuntimeModelConfig,
        RuntimeModelsConfig,
    )
    from iris.runtime.config.root import IrisRuntimeConfig

_DIAGNOSTICS_MODEL_SLOTS: tuple[ModelSlotName, ...] = (
    "default_chat",
    "fast_judge",
    "reasoning",
)


@dataclass(frozen=True)
class DiagnosticsCheckOutcome:
    """1 つのモデルスロットの起動時診断結果。

    Attributes:
        slot: 対象モデルスロット。
        provider: スロットに設定された LLM プロバイダ。
        model: スロットに設定されたモデル名。
        readiness: ``check_readiness`` の結果。
        warmup: ``warmup`` の結果。 warmup を実行しなかった場合は ``None``。
    """

    slot: ModelSlotName
    provider: LLMProvider
    model: str
    readiness: ProviderReadinessResult
    warmup: ProviderReadinessResult | None = None


@dataclass(frozen=True)
class StartupDiagnosticsReport:
    """全モデルスロットの起動時診断の集計結果。

    Attributes:
        outcomes: 起動時に検査したスロットの結果タプル。
        enabled: diagnostics が有効だったか。 False の場合 ``outcomes`` は空。
    """

    outcomes: tuple[DiagnosticsCheckOutcome, ...] = ()
    enabled: bool = True

    @property
    def has_failures(self) -> bool:
        """いずれかの outcome が FAIL を含む場合に True。"""
        return any(_outcome_has_failure(outcome) for outcome in self.outcomes)

    @property
    def all_ok(self) -> bool:
        """Enabled かつ 1 件以上の outcome がすべて OK の場合に True。"""
        return bool(self.outcomes) and self.enabled and not self.has_failures

    @property
    def checked_count(self) -> int:
        """検査したスロット数。"""
        return len(self.outcomes)


async def run_startup_diagnostics(
    runtime_config: IrisRuntimeConfig,
) -> StartupDiagnosticsReport:
    """全モデルスロットの起動時診断を実行する。

    ``diagnostics.enabled == False`` の場合は空のレポートを返す。 fake プロバイダ
    のスロットはスキップされる。 プロービング時の ``ConfigError`` (adapter
    構築失敗を含む) は失敗 outcome としてキャプチャされ、 runner は他の
    スロットのチェックを続行する。

    ``fail_fast=True`` の場合、いずれかの outcome が FAIL だった時点で
    ``RuntimeError`` を送出して起動を中断する。 ``fail_fast=False`` の
    場合は失敗を記録しつつレポートを返す。

    ``log_issues_as_warnings=True`` の場合、検出された各 issue を
    ``startup.diagnostics.issue`` として WARNING ログに出力する。 False の
    場合は per-issue の警告ログを抑止する。

    Args:
        runtime_config: ランタイム設定。

    Returns:
        集計された診断レポート。

    Raises:
        RuntimeError: ``fail_fast=True`` で 1 件以上の outcome が FAIL の場合。
    """
    diagnostics_config = runtime_config.diagnostics
    if not diagnostics_config.enabled:
        logger.info("startup.diagnostics.skipped reason=disabled")
        return StartupDiagnosticsReport(outcomes=(), enabled=False)

    logger.bind(
        mode="strict" if diagnostics_config.fail_fast else "warn",
        warmup_models=diagnostics_config.warmup_models,
        log_issues_as_warnings=diagnostics_config.log_issues_as_warnings,
    ).info("startup.diagnostics.start")

    outcomes = await _probe_all_slots(
        runtime_config,
        warmup_models=diagnostics_config.warmup_models,
        log_issues_as_warnings=diagnostics_config.log_issues_as_warnings,
    )
    report = StartupDiagnosticsReport(outcomes=tuple(outcomes), enabled=True)
    failure_count = sum(1 for outcome in report.outcomes if _outcome_has_failure(outcome))
    logger.bind(
        checked_count=report.checked_count,
        failure_count=failure_count,
    ).info("startup.diagnostics.complete")
    if report.has_failures and diagnostics_config.fail_fast:
        logger.bind(failure_count=failure_count).error(
            "startup.diagnostics.fail_fast"
        )
        message = _build_fail_fast_message(report)
        raise RuntimeError(message)
    return report


async def _probe_all_slots(
    runtime_config: IrisRuntimeConfig,
    *,
    warmup_models: bool,
    log_issues_as_warnings: bool,
) -> list[DiagnosticsCheckOutcome]:
    """Probe every configured model slot and collect outcomes.

    Args:
        runtime_config: The runtime configuration to probe.
        warmup_models: Whether warmup should run when the provider
            capability allows it.
        log_issues_as_warnings: Whether to log each issue as a warning.

    Returns:
        List of outcomes, one per probed slot (skipped fake slots are omitted).
    """
    outcomes: list[DiagnosticsCheckOutcome] = []
    for slot in _DIAGNOSTICS_MODEL_SLOTS:
        outcome = await _probe_slot(
            runtime_config,
            slot,
            warmup_models=warmup_models,
            log_issues_as_warnings=log_issues_as_warnings,
        )
        if outcome is not None:
            outcomes.append(outcome)
    return outcomes


async def _probe_slot(
    runtime_config: IrisRuntimeConfig,
    slot: ModelSlotName,
    *,
    warmup_models: bool,
    log_issues_as_warnings: bool,
) -> DiagnosticsCheckOutcome | None:
    """Probe a single slot and return the outcome (or None for fake slots).

    Args:
        runtime_config: The runtime configuration to probe.
        slot: Slot name to probe.
        warmup_models: Whether warmup should run when the provider
            capability allows it.
        log_issues_as_warnings: Whether to log each issue as a warning.

    Returns:
        The outcome for the slot, or ``None`` when the slot is skipped
        (e.g. the provider is ``fake``).
    """
    logger.bind(slot=slot).info("startup.diagnostics.check")
    model_config = _slot_config(runtime_config.models, slot)
    try:
        provider_diag = build_provider_diagnostics(model_config, runtime_config)
    except ConfigError as exc:
        failure = _build_construction_failure(slot, model_config, exc)
        _log_outcome_issues(
            failure,
            model_config,
            log_issues_as_warnings=log_issues_as_warnings,
        )
        return failure
    if provider_diag is None:
        return None
    readiness = await provider_diag.check_readiness(model_config.model)
    logger.bind(
        slot=slot,
        provider=model_config.provider,
        model=model_config.model,
        status=readiness.status.value,
        latency_ms=round(readiness.latency_ms or 0.0, 2),
    ).info("startup.diagnostics.readiness")
    if log_issues_as_warnings:
        _log_issues(readiness, slot, model_config)
    warmup: ProviderReadinessResult | None = None
    if warmup_models and provider_diag.capabilities.warmup:
        warmup = await provider_diag.warmup(model_config.model)
        logger.bind(
            slot=slot,
            provider=model_config.provider,
            model=model_config.model,
            status=warmup.status.value,
            latency_ms=round(warmup.latency_ms or 0.0, 2),
        ).info("startup.diagnostics.warmup")
        if log_issues_as_warnings:
            _log_issues(warmup, slot, model_config)
    return DiagnosticsCheckOutcome(
        slot=slot,
        provider=model_config.provider,
        model=model_config.model,
        readiness=readiness,
        warmup=warmup,
    )


def _log_issues(
    result: ProviderReadinessResult,
    slot: ModelSlotName,
    model_config: RuntimeModelConfig,
) -> None:
    """Emit one WARNING log per issue with safe metadata only.

    Args:
        result: The readiness / warmup result containing the issues.
        slot: Slot name being summarized.
        model_config: Model config for the slot.
    """
    for issue in result.issues:
        logger.bind(
            slot=slot,
            provider=model_config.provider,
            model=model_config.model,
            issue_code=issue.code,
            severity=issue.severity.value,
        ).warning("startup.diagnostics.issue")


def _log_outcome_issues(
    outcome: DiagnosticsCheckOutcome,
    model_config: RuntimeModelConfig,
    *,
    log_issues_as_warnings: bool,
) -> None:
    """Log a synthetic readiness result for construction failures.

    Args:
        outcome: The failed outcome whose readiness result carries the
            construction failure issues.
        model_config: The model config that was used to build diagnostics.
        log_issues_as_warnings: Whether to emit per-issue warnings.
    """
    logger.bind(
        slot=outcome.slot,
        provider=outcome.provider,
        model=outcome.model,
        status=outcome.readiness.status.value,
    ).info("startup.diagnostics.readiness")
    if log_issues_as_warnings:
        _log_issues(outcome.readiness, outcome.slot, model_config)


def _build_fail_fast_message(report: StartupDiagnosticsReport) -> str:
    """Build a fail-fast abort message summarizing failed outcomes.

    Args:
        report: Aggregated startup diagnostics report.

    Returns:
        A human-readable abort message listing failed slots and issues.
    """
    lines = ["startup diagnostics failed (fail_fast=true)"]
    for outcome in report.outcomes:
        if not _outcome_has_failure(outcome):
            continue
        failed_results: list[tuple[str, ProviderReadinessResult]] = []
        if outcome.readiness.status is ReadinessStatus.FAIL:
            failed_results.append(("readiness", outcome.readiness))
        if outcome.warmup and outcome.warmup.status is ReadinessStatus.FAIL:
            failed_results.append(("warmup", outcome.warmup))
        for stage, result in failed_results:
            codes = ", ".join(issue.code for issue in result.issues) or "unknown"
            lines.append(
                f"  - slot={outcome.slot} provider={outcome.provider} "
                f"model={outcome.model} stage={stage} "
                f"status={result.status.value} codes=[{codes}]"
            )
    return "\n".join(lines)


def _slot_config(
    models: RuntimeModelsConfig,
    slot: ModelSlotName,
) -> RuntimeModelConfig:
    """指定モデルスロットの現在の config を返す。

    Args:
        models: ランタイム models config。
        slot: 対象スロット名。

    Returns:
        指定スロットに格納された ``RuntimeModelConfig``。
    """
    if slot == "default_chat":
        return models.default_chat
    if slot == "fast_judge":
        return models.fast_judge
    return models.reasoning


def _outcome_has_failure(outcome: DiagnosticsCheckOutcome) -> bool:
    """Outcome に FAIL ステータスがあれば True を返す。

    Args:
        outcome: 検査対象 outcome。

    Returns:
        readiness または warmup のいずれかが FAIL なら True。
    """
    if outcome.readiness.status is ReadinessStatus.FAIL:
        return True
    return bool(outcome.warmup and outcome.warmup.status is ReadinessStatus.FAIL)


def _build_construction_failure(
    slot: ModelSlotName,
    model_config: RuntimeModelConfig,
    exc: BaseException,
) -> DiagnosticsCheckOutcome:
    """診断の組み立て失敗を FAIL outcome として記録する。

    Args:
        slot: 失敗したスロット名。
        model_config: 失敗したスロットの model config。
        exc: 元の例外。

    Returns:
        失敗を表す FAIL outcome。
    """
    issue = ProviderDiagnosticIssue(
        code="diagnostics_build_failed",
        message=str(exc),
        severity=ReadinessStatus.FAIL,
    )
    readiness = ProviderReadinessResult(
        provider=model_config.provider,
        model=model_config.model,
        status=ReadinessStatus.FAIL,
        capabilities=ProviderCapability(),
        issues=(issue,),
    )
    return DiagnosticsCheckOutcome(
        slot=slot,
        provider=model_config.provider,
        model=model_config.model,
        readiness=readiness,
        warmup=None,
    )
