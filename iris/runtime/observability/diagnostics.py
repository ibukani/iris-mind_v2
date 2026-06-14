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

    Args:
        runtime_config: ランタイム設定。

    Returns:
        集計された診断レポート。
    """
    diagnostics_config = runtime_config.diagnostics
    if not diagnostics_config.enabled:
        return StartupDiagnosticsReport(outcomes=(), enabled=False)

    outcomes: list[DiagnosticsCheckOutcome] = []
    for slot in _DIAGNOSTICS_MODEL_SLOTS:
        model_config = _slot_config(runtime_config.models, slot)
        try:
            provider_diag = build_provider_diagnostics(model_config, runtime_config)
        except ConfigError as exc:
            outcomes.append(_build_construction_failure(slot, model_config, exc))
            continue
        if provider_diag is None:
            continue
        readiness = await provider_diag.check_readiness(model_config.model)
        warmup: ProviderReadinessResult | None = None
        if diagnostics_config.warmup_models and provider_diag.capabilities.warmup:
            warmup = await provider_diag.warmup(model_config.model)
        outcomes.append(
            DiagnosticsCheckOutcome(
                slot=slot,
                provider=model_config.provider,
                model=model_config.model,
                readiness=readiness,
                warmup=warmup,
            ),
        )
    return StartupDiagnosticsReport(outcomes=tuple(outcomes), enabled=True)


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
