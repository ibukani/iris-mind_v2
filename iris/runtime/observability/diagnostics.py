"""LLM プロバイダ診断の起動時ランナー。

Server 起動時に各モデルスロット (default_chat / fast_judge / reasoning)
に対して :func:`run_startup_diagnostics` を呼び、non-fake プロバイダの
スロットに対して :meth:`LLMProviderDiagnostics.check_readiness` を実行する。
``diagnostics.mode`` が ``off`` 以外で、 ``diagnostics.warmup_models`` が
true かつ provider の :class:`ProviderCapability` が ``warmup=True`` の
場合のみ :meth:`LLMProviderDiagnostics.warmup` も実行する。

ファクトリ :func:`iris.runtime.wiring.llm.build_provider_diagnostics` は
``RuntimeModelConfig`` の ``provider`` フィールド (``LLMProvider`` Literal)
で分岐する closed discriminated factory。 ``provider == "fake"`` の場合は
``None`` を返し、診断対象外であることを示す。 adapter 構築失敗は
``ConfigError`` に翻訳されるため、 runner は ``ConfigError`` のみ catch
すればよい。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Awaitable

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

    ``diagnostics.mode == "off"`` の場合は空のレポートを返す。 fake
    プロバイダのスロットはスキップされる。 プロービング時の
    ``ConfigError`` (adapter 構築失敗を含む) は失敗 outcome として
    キャプチャされ、 runner は他のスロットのチェックを続行する。

    ``mode == "strict"`` の場合、いずれかの outcome が FAIL だった時点で
    ``ConfigError`` を送出して起動を中断する。 ``mode == "warn"`` の
    場合は失敗を警告ログに出力しつつレポートを返す。 ``mode == "off"``
    の場合は provider diagnostics を作成せず、空のレポートを返す。

    Args:
        runtime_config: ランタイム設定。

    Returns:
        集計された診断レポート。

    Raises:
        ConfigError: ``mode == "strict"`` で 1 件以上の outcome が FAIL の場合。
    """
    diagnostics_config = runtime_config.diagnostics
    if diagnostics_config.mode == "off":
        logger.info("startup.diagnostics.skipped reason=mode_off")
        return StartupDiagnosticsReport(outcomes=(), enabled=False)

    logger.bind(
        mode=diagnostics_config.mode,
        warmup_models=diagnostics_config.warmup_models,
    ).info("startup.diagnostics.start")

    outcomes = await _probe_all_slots(
        runtime_config,
        warmup_models=diagnostics_config.warmup_models,
        timeout_seconds=diagnostics_config.timeout_seconds,
    )
    report = StartupDiagnosticsReport(outcomes=tuple(outcomes), enabled=True)
    failure_count = sum(1 for outcome in report.outcomes if _outcome_has_failure(outcome))
    logger.bind(
        checked_count=report.checked_count,
        failure_count=failure_count,
        mode=diagnostics_config.mode,
    ).info("startup.diagnostics.complete")
    if report.has_failures and diagnostics_config.mode == "strict":
        logger.bind(failure_count=failure_count).error("startup.diagnostics.strict_fail")
        raise ConfigError(_build_strict_fail_message(report))
    return report


async def _probe_all_slots(
    runtime_config: IrisRuntimeConfig,
    *,
    warmup_models: bool,
    timeout_seconds: float,
) -> list[DiagnosticsCheckOutcome]:
    """Probe every configured model slot and collect outcomes.

    Args:
        runtime_config: The runtime configuration to probe.
        warmup_models: Whether warmup should run when the provider
            capability allows it.
        timeout_seconds: Per-probe timeout in seconds.

    Returns:
        List of outcomes, one per probed slot (skipped fake slots are omitted).
    """
    outcomes: list[DiagnosticsCheckOutcome] = []
    for slot in _DIAGNOSTICS_MODEL_SLOTS:
        outcome = await _probe_slot(
            runtime_config,
            slot,
            warmup_models=warmup_models,
            timeout_seconds=timeout_seconds,
        )
        if outcome is not None:
            outcomes.append(outcome)
    return outcomes


async def _probe_slot(
    runtime_config: IrisRuntimeConfig,
    slot: ModelSlotName,
    *,
    warmup_models: bool,
    timeout_seconds: float,
) -> DiagnosticsCheckOutcome | None:
    """Probe a single slot and return the outcome (or None for fake slots).

    Args:
        runtime_config: The runtime configuration to probe.
        slot: Slot name to probe.
        warmup_models: Whether warmup should run when the provider
            capability allows it.
        timeout_seconds: Per-probe timeout in seconds. Each of
            ``check_readiness`` and ``warmup`` is wrapped in
            :func:`asyncio.timeout`; a timeout is converted to a
            :class:`ProviderReadinessResult` with status ``FAIL`` and a
            dedicated ``readiness_timeout`` / ``warmup_timeout`` issue.

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
        _log_outcome_issues(failure, model_config)
        return failure
    if provider_diag is None:
        return None
    readiness = await _run_with_timeout(
        provider_diag.check_readiness(model_config.model),
        timeout_seconds=timeout_seconds,
        model_config=model_config,
        stage="readiness",
    )
    logger.bind(
        slot=slot,
        provider=model_config.provider,
        model=model_config.model,
        status=readiness.status.value,
        latency_ms=round(readiness.latency_ms or 0.0, 2),
    ).info("startup.diagnostics.readiness")
    _log_issues(readiness, slot, model_config)
    warmup: ProviderReadinessResult | None = None
    if warmup_models and provider_diag.capabilities.warmup:
        warmup = await _run_with_timeout(
            provider_diag.warmup(model_config.model),
            timeout_seconds=timeout_seconds,
            model_config=model_config,
            stage="warmup",
        )
        logger.bind(
            slot=slot,
            provider=model_config.provider,
            model=model_config.model,
            status=warmup.status.value,
            latency_ms=round(warmup.latency_ms or 0.0, 2),
        ).info("startup.diagnostics.warmup")
        _log_issues(warmup, slot, model_config)
    return DiagnosticsCheckOutcome(
        slot=slot,
        provider=model_config.provider,
        model=model_config.model,
        readiness=readiness,
        warmup=warmup,
    )


async def _run_with_timeout(
    awaitable: Awaitable[ProviderReadinessResult],
    *,
    timeout_seconds: float,
    model_config: RuntimeModelConfig,
    stage: str,
) -> ProviderReadinessResult:
    """Await ``awaitable`` and convert :class:`TimeoutError` into a FAIL outcome.

    Args:
        awaitable: A coroutine returned by ``provider_diag.check_readiness``
            or ``provider_diag.warmup``.
        timeout_seconds: Per-call timeout in seconds.
        model_config: The model config being probed (used for metadata
            on the synthetic FAIL result).
        stage: ``"readiness"`` or ``"warmup"`` (used for the issue code
            and remediation hint).

    Returns:
        The original :class:`ProviderReadinessResult` when the probe
        completes, or a synthetic FAIL result with a
        ``readiness_timeout`` / ``warmup_timeout`` issue when the
        probe exceeds the configured timeout.
    """
    try:
        async with asyncio.timeout(timeout_seconds):
            return await awaitable
    except TimeoutError:
        issue_code = f"{stage}_timeout"
        message = "".join(
            (
                f"{stage.capitalize()} probe exceeded diagnostics.timeout_seconds=",
                f"{timeout_seconds}s for model '{model_config.model}'",
            )
        )
        logger.bind(
            provider=model_config.provider,
            model=model_config.model,
            stage=stage,
            timeout_seconds=timeout_seconds,
        ).warning("startup.diagnostics.timeout")
        return ProviderReadinessResult(
            provider=model_config.provider,
            model=model_config.model,
            status=ReadinessStatus.FAIL,
            capabilities=ProviderCapability(),
            issues=(
                ProviderDiagnosticIssue(
                    code=issue_code,
                    message=message,
                    severity=ReadinessStatus.FAIL,
                    remediation="Raise diagnostics.timeout_seconds or fix provider endpoint",
                ),
            ),
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
        remediation = issue.remediation
        logger.bind(
            slot=slot,
            provider=model_config.provider,
            model=model_config.model,
            status=result.status.value,
            issue_code=issue.code,
            severity=issue.severity.value,
            **({"remediation": remediation} if remediation is not None else {}),
        ).warning("startup.diagnostics.issue")


def _log_outcome_issues(
    outcome: DiagnosticsCheckOutcome,
    model_config: RuntimeModelConfig,
) -> None:
    """Log a synthetic readiness result for construction failures.

    Args:
        outcome: The failed outcome whose readiness result carries the
            construction failure issues.
        model_config: The model config that was used to build diagnostics.
    """
    logger.bind(
        slot=outcome.slot,
        provider=outcome.provider,
        model=outcome.model,
        status=outcome.readiness.status.value,
    ).info("startup.diagnostics.readiness")
    _log_issues(outcome.readiness, outcome.slot, model_config)


def _build_strict_fail_message(report: StartupDiagnosticsReport) -> str:
    """Build a strict-mode abort message summarizing failed outcomes.

    Args:
        report: Aggregated startup diagnostics report.

    Returns:
        A human-readable abort message listing failed slots and issues.
    """
    lines = ["startup diagnostics failed (mode=strict)"]
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
                "".join(
                    (
                        f"  - slot={outcome.slot} provider={outcome.provider} ",
                        f"model={outcome.model} stage={stage} ",
                        f"status={result.status.value} codes=[{codes}]",
                    )
                )
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
