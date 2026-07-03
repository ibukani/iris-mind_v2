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
from dataclasses import dataclass, replace
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
from iris.adapters.llm.lifecycle import ModelLoadState
from iris.runtime.config.errors import ConfigError
from iris.runtime.config.llm import (
    ModelSlotName,
    model_slot_names,
    runtime_model_config_for_slot,
)
from iris.runtime.wiring.llm import build_provider_diagnostics, resolve_provider_model

if TYPE_CHECKING:
    from iris.runtime.config.llm import (
        LLMProvider,
        RuntimeModelConfig,
    )
    from iris.runtime.config.root import IrisRuntimeConfig


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

    """
    diagnostics_config = runtime_config.diagnostics
    if diagnostics_config.mode == "off":
        _log_diagnostics_skipped()
        return StartupDiagnosticsReport(outcomes=(), enabled=False)

    _log_diagnostics_start(
        diagnostics_config.mode,
        warmup_models=diagnostics_config.warmup_models,
    )
    report = await _run_diagnostics(
        runtime_config,
        warmup_models=diagnostics_config.warmup_models,
        readiness_timeout_seconds=diagnostics_config.readiness_timeout_seconds,
        warmup_timeout_seconds=diagnostics_config.warmup_timeout_seconds,
    )
    _log_diagnostics_complete(report, diagnostics_config.mode)
    _raise_if_strict_failure(report, diagnostics_config.mode)
    return report


async def _probe_all_slots(
    runtime_config: IrisRuntimeConfig,
    *,
    warmup_models: bool,
    readiness_timeout_seconds: float,
    warmup_timeout_seconds: float,
) -> list[DiagnosticsCheckOutcome]:
    """Probe every configured model slot and collect outcomes.

    Args:
        runtime_config: The runtime configuration to probe.
        warmup_models: Whether warmup should run when the provider
            capability allows it.
        readiness_timeout_seconds: Timeout for readiness checks.
        warmup_timeout_seconds: Timeout for warmup checks.

    Returns:
        List of outcomes, one per probed slot (skipped fake slots are omitted).
    """
    outcomes: list[DiagnosticsCheckOutcome] = []
    for slot in model_slot_names():
        outcome = await _probe_slot(
            runtime_config,
            slot,
            warmup_models=warmup_models,
            readiness_timeout_seconds=readiness_timeout_seconds,
            warmup_timeout_seconds=warmup_timeout_seconds,
        )
        if outcome is not None:
            outcomes.append(outcome)
    return outcomes


def _log_diagnostics_skipped() -> None:
    logger.info("startup.diagnostics.skipped reason=mode_off")


def _log_diagnostics_start(mode: str, *, warmup_models: bool) -> None:
    logger.bind(mode=mode, warmup_models=warmup_models).info("startup.diagnostics.start")


async def _run_diagnostics(
    runtime_config: IrisRuntimeConfig,
    *,
    warmup_models: bool,
    readiness_timeout_seconds: float,
    warmup_timeout_seconds: float,
) -> StartupDiagnosticsReport:
    outcomes = await _probe_all_slots(
        runtime_config,
        warmup_models=warmup_models,
        readiness_timeout_seconds=readiness_timeout_seconds,
        warmup_timeout_seconds=warmup_timeout_seconds,
    )
    return StartupDiagnosticsReport(outcomes=tuple(outcomes), enabled=True)


def _log_diagnostics_complete(report: StartupDiagnosticsReport, mode: str) -> None:
    failure_count = _failure_count(report)
    logger.bind(
        checked_count=report.checked_count,
        failure_count=failure_count,
        mode=mode,
    ).info("startup.diagnostics.complete")


def _raise_if_strict_failure(
    report: StartupDiagnosticsReport,
    mode: str,
) -> None:
    if report.has_failures and mode == "strict":
        failure_count = _failure_count(report)
        logger.bind(failure_count=failure_count).error("startup.diagnostics.strict_fail")
        raise ConfigError(_build_strict_fail_message(report))


def _failure_count(report: StartupDiagnosticsReport) -> int:
    return sum(1 for outcome in report.outcomes if _outcome_has_failure(outcome))


async def _probe_slot(
    runtime_config: IrisRuntimeConfig,
    slot: ModelSlotName,
    *,
    warmup_models: bool,
    readiness_timeout_seconds: float,
    warmup_timeout_seconds: float,
) -> DiagnosticsCheckOutcome | None:
    """Probe a single slot and return the outcome (or None for fake slots).

    Args:
        runtime_config: The runtime configuration to probe.
        slot: Slot name to probe.
        warmup_models: Whether warmup should run when the provider
            capability allows it.
        readiness_timeout_seconds: Readiness probe timeout in seconds.
        warmup_timeout_seconds: Warmup probe timeout in seconds. Each of
            ``check_readiness`` and ``warmup`` is wrapped in
            :func:`asyncio.timeout`; a timeout is converted to a
            :class:`ProviderReadinessResult` with status ``FAIL`` and a
            dedicated ``readiness_timeout`` / ``warmup_timeout`` issue.

    Returns:
        The outcome for the slot, or ``None`` when the slot is skipped
        (e.g. the provider is ``fake``).
    """
    logger.bind(slot=slot).info("startup.diagnostics.check")
    model_config = runtime_model_config_for_slot(runtime_config.models, slot)
    try:
        provider_diag = build_provider_diagnostics(model_config, runtime_config)
    except ConfigError as exc:
        failure = _build_construction_failure(slot, model_config, exc)
        _log_outcome_issues(failure, model_config)
        return failure
    if provider_diag is None:
        return None
    resolved_model_config = replace(
        model_config,
        model=resolve_provider_model(model_config, runtime_config),
    )
    readiness = await _probe_stage(
        provider_diag.check_readiness(resolved_model_config.model),
        slot=slot,
        model_config=resolved_model_config,
        timeout_seconds=readiness_timeout_seconds,
        config_key="diagnostics.readiness_timeout_seconds",
        stage="readiness",
    )
    warmup: ProviderReadinessResult | None = None
    if warmup_models and provider_diag.capabilities.warmup:
        warmup = await _probe_stage(
            provider_diag.warmup(resolved_model_config.model),
            slot=slot,
            model_config=resolved_model_config,
            timeout_seconds=warmup_timeout_seconds,
            config_key="diagnostics.warmup_timeout_seconds",
            stage="warmup",
        )
    return DiagnosticsCheckOutcome(
        slot=slot,
        provider=model_config.provider,
        model=resolved_model_config.model,
        readiness=readiness,
        warmup=warmup,
    )


async def _run_with_timeout(
    awaitable: Awaitable[ProviderReadinessResult],
    *,
    timeout_seconds: float,
    config_key: str,
    model_config: RuntimeModelConfig,
    stage: str,
) -> ProviderReadinessResult:
    """Await ``awaitable`` and convert :class:`TimeoutError` into a FAIL outcome.

    Args:
        awaitable: A coroutine returned by ``provider_diag.check_readiness``
            or ``provider_diag.warmup``.
        timeout_seconds: Per-call timeout in seconds.
        config_key: Configuration key path for the error message.
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
                f"{stage.capitalize()} probe exceeded {config_key}=",
                f"{timeout_seconds}s for model '{model_config.model}'",
            )
        )
        logger.bind(
            provider=model_config.provider,
            model=model_config.model,
            stage=stage,
            config_key=config_key,
            timeout_seconds=timeout_seconds,
        ).warning("startup.diagnostics.timeout")
        return ProviderReadinessResult(
            provider=model_config.provider,
            model=model_config.model,
            status=ReadinessStatus.FAIL,
            capabilities=ProviderCapability(),
            model_load_state=ModelLoadState.UNAVAILABLE,
            issues=(
                ProviderDiagnosticIssue(
                    code=issue_code,
                    message=message,
                    severity=ReadinessStatus.FAIL,
                    remediation=f"Raise {config_key} or fix provider endpoint",
                ),
            ),
        )


async def _probe_stage(
    awaitable: Awaitable[ProviderReadinessResult],
    *,
    slot: ModelSlotName,
    model_config: RuntimeModelConfig,
    timeout_seconds: float,
    config_key: str,
    stage: str,
) -> ProviderReadinessResult:
    """単一 stage の probe と structured logging をまとめて実行する。

    Returns:
        構成済みの ProviderReadinessResult。
    """
    result = await _run_with_timeout(
        awaitable,
        timeout_seconds=timeout_seconds,
        config_key=config_key,
        model_config=model_config,
        stage=stage,
    )
    _log_result_event(f"startup.diagnostics.{stage}", result, slot, model_config)
    return result


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
    base_fields = {
        "slot": slot,
        "provider": model_config.provider,
        "model": model_config.model,
        "status": result.status.value,
    }
    for issue in result.issues:
        _log_issue(base_fields, issue)


def _log_result_event(
    event_name: str,
    result: ProviderReadinessResult,
    slot: ModelSlotName,
    model_config: RuntimeModelConfig,
) -> None:
    """結果イベントを 1 回出してから issue を記録する。

    Args:
        event_name: Emit する structured event 名。
        result: readiness / warmup の結果。
        slot: 対象スロット。
        model_config: スロットのモデル設定。
    """
    logger.bind(
        slot=slot,
        provider=model_config.provider,
        model=model_config.model,
        status=result.status.value,
        latency_ms=round(result.latency_ms or 0.0, 2),
    ).info(event_name)
    _log_issues(result, slot, model_config)


def _log_issue(
    base_fields: dict[str, ModelSlotName | str],
    issue: ProviderDiagnosticIssue,
) -> None:
    """1 issue を structured WARNING として出力する。"""
    fields = {
        **base_fields,
        "issue_code": issue.code,
        "severity": issue.severity.value,
    }
    remediation = issue.remediation
    if remediation is not None:
        fields["remediation"] = remediation
    logger.bind(**fields).warning("startup.diagnostics.issue")


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
    _log_result_event(
        "startup.diagnostics.readiness",
        outcome.readiness,
        outcome.slot,
        model_config,
    )


def _build_strict_fail_message(report: StartupDiagnosticsReport) -> str:
    """Build a strict-mode abort message summarizing failed outcomes.

    Args:
        report: Aggregated startup diagnostics report.

    Returns:
        A human-readable abort message listing failed slots and issues.
    """
    lines = ["startup diagnostics failed (mode=strict)"]
    for outcome in report.outcomes:
        for stage, result in _failed_stage_results(outcome):
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


def _outcome_has_failure(outcome: DiagnosticsCheckOutcome) -> bool:
    """Outcome に FAIL ステータスがあれば True を返す。

    Args:
        outcome: 検査対象 outcome。

    Returns:
        readiness または warmup のいずれかが FAIL なら True。
    """
    return bool(_failed_stage_results(outcome))


def _failed_stage_results(
    outcome: DiagnosticsCheckOutcome,
) -> tuple[tuple[str, ProviderReadinessResult], ...]:
    """FAIL の stage/result pair を列挙する。

    Args:
        outcome: 確認対象の outcome。

    Returns:
        FAIL になった stage/result の tuple。
    """
    failed_results: list[tuple[str, ProviderReadinessResult]] = []
    if outcome.readiness.status is ReadinessStatus.FAIL:
        failed_results.append(("readiness", outcome.readiness))
    if outcome.warmup and outcome.warmup.status is ReadinessStatus.FAIL:
        failed_results.append(("warmup", outcome.warmup))
    return tuple(failed_results)


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
        model_load_state=ModelLoadState.UNAVAILABLE,
        issues=(issue,),
    )
    return DiagnosticsCheckOutcome(
        slot=slot,
        provider=model_config.provider,
        model=model_config.model,
        readiness=readiness,
        warmup=None,
    )
