"""Runtime model call budget gate and request-local scope."""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from iris.contracts.model_policy import (
    CascadeDecision,
    CascadeResult,
    ModelCallDescriptor,
    ModelCallKind,
    ModelCallSite,
)
from iris.runtime.config.model_call_budget import (
    RuntimeFeatureModelCallBudget,
    RuntimeModelCallBudgetConfig,
    feature_budget_for_site,
)
from iris.runtime.observability.context import increment_avoided_large_llm_call

if TYPE_CHECKING:
    from collections.abc import Generator


@dataclass(frozen=True)
class ModelCallBudgetKey:
    """Request-local budget counter key."""

    call_site: ModelCallSite
    call_kind: ModelCallKind


def _new_budget_counter() -> Counter[ModelCallBudgetKey]:
    """空の model call budget counter を返す。

    Returns:
        Counter[ModelCallBudgetKey]: request-local counter。
    """
    return Counter()


@dataclass
class _ModelCallBudgetScope:
    """1 request 内のモデル呼び出し回数を保持する。"""

    counters: Counter[ModelCallBudgetKey] = field(default_factory=_new_budget_counter)

    def used(self, descriptor: ModelCallDescriptor) -> int:
        """Descriptor に対応する既使用回数を返す。

        Returns:
            int: request-local scope 内の既使用回数。
        """
        return self.counters[ModelCallBudgetKey(descriptor.call_site, descriptor.call_kind)]

    def record(self, descriptor: ModelCallDescriptor) -> None:
        """Descriptor に対応する使用回数を増やす。"""
        self.counters[ModelCallBudgetKey(descriptor.call_site, descriptor.call_kind)] += 1


_CURRENT_MODEL_CALL_BUDGET_SCOPE: ContextVar[_ModelCallBudgetScope | None] = ContextVar(
    "iris_model_call_budget_scope",
    default=None,
)
_CURRENT_MODEL_CALL_SITE: ContextVar[ModelCallSite | None] = ContextVar(
    "iris_model_call_site",
    default=None,
)


@contextmanager
def bind_model_call_budget_scope() -> Generator[None]:
    """現在の async context に request-local model call budget scope を束縛する。"""
    token = _CURRENT_MODEL_CALL_BUDGET_SCOPE.set(_ModelCallBudgetScope())
    try:
        yield
    finally:
        _CURRENT_MODEL_CALL_BUDGET_SCOPE.reset(token)


@contextmanager
def bind_model_call_site(site: ModelCallSite) -> Generator[None]:
    """現在の async context に既定の model call site を束縛する。"""
    token = _CURRENT_MODEL_CALL_SITE.set(site)
    try:
        yield
    finally:
        _CURRENT_MODEL_CALL_SITE.reset(token)


def current_model_call_site(default: ModelCallSite) -> ModelCallSite:
    """現在の call site scope を返し、未束縛なら default を返す。

    Returns:
        ModelCallSite: 束縛中の call site、または default。
    """
    site = _CURRENT_MODEL_CALL_SITE.get()
    if site is None:
        return default
    return site


class ModelCallBudgetGate:
    """Feature 別 budget と cascade policy に基づいてモデル呼び出しを判定する。"""

    def __init__(self, config: RuntimeModelCallBudgetConfig | None = None) -> None:
        """モデル呼び出し予算設定で gate を初期化する。"""
        self._config = config or RuntimeModelCallBudgetConfig()

    def check_and_record(self, descriptor: ModelCallDescriptor) -> CascadeResult:
        """呼び出し可否を判定し、許可される場合だけ使用回数を記録する。

        Returns:
            CascadeResult: budget / confidence / risk に基づく cascade 判定。
        """
        budget = feature_budget_for_site(self._config, descriptor.call_site)
        result = self._decision_for_budget(descriptor, budget)
        if result.accepted:
            _scope().record(descriptor)
        elif descriptor.call_kind is ModelCallKind.LARGE_LLM:
            increment_avoided_large_llm_call()
        return result

    def _decision_for_budget(
        self,
        descriptor: ModelCallDescriptor,
        budget: RuntimeFeatureModelCallBudget,
    ) -> CascadeResult:
        pre_budget_result = self._pre_budget_decision(descriptor, budget)
        if pre_budget_result is not None:
            return pre_budget_result

        limit = _limit_for_kind(budget, descriptor.call_kind)
        scope = _scope()
        if limit is not None and scope.used(descriptor) < limit:
            return _accepted(descriptor, reason="model call within budget")
        return _fallback(descriptor, reason="model call budget exceeded", budget=budget)

    def _pre_budget_decision(
        self,
        descriptor: ModelCallDescriptor,
        budget: RuntimeFeatureModelCallBudget,
    ) -> CascadeResult | None:
        result: CascadeResult | None = None
        if not self._config.enabled:
            result = _accepted(descriptor, reason="model call budget disabled")
        elif budget.enqueue_only and descriptor.call_kind is ModelCallKind.LARGE_LLM:
            result = _denied(descriptor, reason="call site is enqueue-only", budget=budget)
        elif descriptor.confidence < budget.confidence_threshold:
            result = _low_confidence_result(descriptor, budget)
        elif _limit_for_kind(budget, descriptor.call_kind) is None:
            result = _fallback(descriptor, reason="call kind is not enabled", budget=budget)
        return result


def _scope() -> _ModelCallBudgetScope:
    scope = _CURRENT_MODEL_CALL_BUDGET_SCOPE.get()
    if scope is None:
        scope = _ModelCallBudgetScope()
        _CURRENT_MODEL_CALL_BUDGET_SCOPE.set(scope)
    return scope


def _limit_for_kind(
    budget: RuntimeFeatureModelCallBudget,
    kind: ModelCallKind,
) -> int | None:
    limits = {
        ModelCallKind.LARGE_LLM: budget.large_llm_max_calls,
        ModelCallKind.SMALL_CLASSIFIER: budget.small_classifier_max_calls,
        ModelCallKind.EMBEDDING: budget.embedding_max_calls,
        ModelCallKind.RERANKER: budget.reranker_max_calls,
        ModelCallKind.BACKGROUND_LLM: budget.background_llm_max_calls,
    }
    limit = limits[kind]
    if limit <= 0:
        return None
    return limit


def _low_confidence_result(
    descriptor: ModelCallDescriptor,
    budget: RuntimeFeatureModelCallBudget,
) -> CascadeResult:
    if _escalation_allowed(descriptor, budget):
        return CascadeResult(
            decision=CascadeDecision.ESCALATE,
            reason="low confidence allows escalation",
            confidence=descriptor.confidence,
            fallback_behavior=None,
            model_metadata=descriptor.metadata,
        )
    return _fallback(descriptor, reason="low confidence fallback", budget=budget)


def _escalation_allowed(
    descriptor: ModelCallDescriptor,
    budget: RuntimeFeatureModelCallBudget,
) -> bool:
    high_risk_allowed = descriptor.high_risk and budget.high_risk_escalation_allowed
    uncertain_allowed = descriptor.uncertain and budget.uncertain_escalation_allowed
    return high_risk_allowed or uncertain_allowed


def _accepted(descriptor: ModelCallDescriptor, *, reason: str) -> CascadeResult:
    return CascadeResult(
        decision=CascadeDecision.ACCEPT,
        reason=reason,
        confidence=descriptor.confidence,
        fallback_behavior=None,
        model_metadata=descriptor.metadata,
    )


def _fallback(
    descriptor: ModelCallDescriptor,
    *,
    reason: str,
    budget: RuntimeFeatureModelCallBudget,
) -> CascadeResult:
    return CascadeResult(
        decision=CascadeDecision.FALLBACK,
        reason=reason,
        confidence=descriptor.confidence,
        fallback_behavior=budget.low_confidence_fallback,
        model_metadata=descriptor.metadata,
    )


def _denied(
    descriptor: ModelCallDescriptor,
    *,
    reason: str,
    budget: RuntimeFeatureModelCallBudget,
) -> CascadeResult:
    return CascadeResult(
        decision=CascadeDecision.DENY,
        reason=reason,
        confidence=descriptor.confidence,
        fallback_behavior=budget.low_confidence_fallback,
        model_metadata=descriptor.metadata,
    )
