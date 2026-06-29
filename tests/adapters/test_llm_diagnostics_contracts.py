"""Tests for provider-neutral LLM diagnostics contracts."""

from __future__ import annotations

from types import MappingProxyType

import pytest

from iris.adapters.llm.diagnostics import (
    LLMProviderAuthenticationError,
    LLMProviderConnectionError,
    LLMProviderDiagnostics,
    LLMProviderError,
    LLMProviderInvalidResponseError,
    LLMProviderModelUnavailableError,
    LLMProviderQuotaError,
    LLMProviderRateLimitError,
    LLMProviderTimeoutError,
    ProviderCapability,
    ProviderDiagnosticIssue,
    ProviderReadinessResult,
    ReadinessStatus,
    aggregate_issue_severity,
    build_provider_readiness_result,
)
from tests.helpers.immutability import assert_frozen_field


def test_readiness_status_values_are_stable() -> None:
    """ReadinessStatus values are stable string literals."""
    assert ReadinessStatus.OK.value == "ok"
    assert ReadinessStatus.WARN.value == "warn"
    assert ReadinessStatus.FAIL.value == "fail"
    assert ReadinessStatus.SKIPPED.value == "skipped"


def test_provider_capability_defaults_are_conservative() -> None:
    """ProviderCapability defaults to health check only."""
    capability = ProviderCapability()

    assert capability.health_check is True
    assert capability.model_availability_check is False
    assert capability.model_loaded_check is False
    assert capability.warmup is False


def test_provider_capability_is_frozen() -> None:
    """ProviderCapability rejects field mutation."""
    capability = ProviderCapability()
    replacement = True

    assert_frozen_field(capability, "warmup", replacement)


def test_provider_diagnostic_issue_is_frozen() -> None:
    """ProviderDiagnosticIssue rejects field mutation."""
    issue = ProviderDiagnosticIssue(
        code="x",
        message="x",
        severity=ReadinessStatus.OK,
    )

    assert_frozen_field(issue, "code", "y")


def test_provider_readiness_result_is_frozen() -> None:
    """ProviderReadinessResult rejects field mutation."""
    result = ProviderReadinessResult(
        provider="fake",
        model="fake-llm",
        status=ReadinessStatus.OK,
        capabilities=ProviderCapability(),
    )

    assert_frozen_field(result, "model", "other")


def test_provider_readiness_result_defaults_issues_and_metadata() -> None:
    """ProviderReadinessResult defaults issues and metadata to safe sentinels."""
    result = ProviderReadinessResult(
        provider="fake",
        model="fake-llm",
        status=ReadinessStatus.OK,
        capabilities=ProviderCapability(),
    )

    assert result.issues == ()
    assert result.latency_ms is None
    assert result.metadata is None


def test_aggregate_issue_severity_prefers_fail_then_warn() -> None:
    """aggregate_issue_severity collapses issue severities deterministically."""
    assert aggregate_issue_severity(()) is ReadinessStatus.OK
    assert (
        aggregate_issue_severity(
            (
                ProviderDiagnosticIssue(
                    code="x",
                    message="x",
                    severity=ReadinessStatus.SKIPPED,
                ),
            ),
        )
        is ReadinessStatus.SKIPPED
    )
    assert (
        aggregate_issue_severity(
            (
                ProviderDiagnosticIssue(
                    code="x",
                    message="x",
                    severity=ReadinessStatus.WARN,
                ),
                ProviderDiagnosticIssue(
                    code="y",
                    message="y",
                    severity=ReadinessStatus.SKIPPED,
                ),
            ),
        )
        is ReadinessStatus.WARN
    )
    assert (
        aggregate_issue_severity(
            (
                ProviderDiagnosticIssue(
                    code="x",
                    message="x",
                    severity=ReadinessStatus.FAIL,
                ),
                ProviderDiagnosticIssue(
                    code="y",
                    message="y",
                    severity=ReadinessStatus.WARN,
                ),
            ),
        )
        is ReadinessStatus.FAIL
    )


def test_build_provider_readiness_result_sets_status_and_metadata() -> None:
    """Builder は provider metadata の防御的な読み取り専用コピーを保持する。"""
    metadata = {"k": "v"}
    result = build_provider_readiness_result(
        provider="demo",
        model="m",
        capabilities=ProviderCapability(warmup=True),
        issues=(
            ProviderDiagnosticIssue(
                code="issue",
                message="issue",
                severity=ReadinessStatus.WARN,
            ),
        ),
        latency_ms=12.5,
        metadata=metadata,
    )
    metadata["k"] = "changed"

    assert result.provider == "demo"
    assert result.model == "m"
    assert result.capabilities.warmup is True
    assert result.status is ReadinessStatus.WARN
    assert result.latency_ms is not None
    assert abs(result.latency_ms - 12.5) < 1e-9
    assert result.metadata == {"k": "v"}
    assert isinstance(result.metadata, MappingProxyType)


@pytest.mark.parametrize(
    ("error_cls", "base_cls"),
    [
        (LLMProviderConnectionError, LLMProviderError),
        (LLMProviderTimeoutError, LLMProviderError),
        (LLMProviderAuthenticationError, LLMProviderError),
        (LLMProviderRateLimitError, LLMProviderError),
        (LLMProviderQuotaError, LLMProviderError),
        (LLMProviderModelUnavailableError, LLMProviderError),
        (LLMProviderInvalidResponseError, LLMProviderError),
    ],
)
def test_provider_error_hierarchy_is_subclass_of_base(
    error_cls: type[LLMProviderError],
    base_cls: type[LLMProviderError],
) -> None:
    """Each provider error is a subclass of LLMProviderError and RuntimeError."""
    assert issubclass(error_cls, base_cls)
    assert issubclass(error_cls, RuntimeError)


def test_provider_error_carries_message() -> None:
    """LLMProviderError preserves the message supplied to the constructor."""
    error = LLMProviderConnectionError("endpoint unreachable")

    assert str(error) == "endpoint unreachable"
    assert isinstance(error, RuntimeError)


class _FakeProviderDiagnostics:
    """Protocol-compatible fake provider diagnostics."""

    def __init__(self, capabilities: ProviderCapability) -> None:
        self.provider = "fake"
        self.capabilities = capabilities
        self.check_calls: list[str] = []
        self.warmup_calls: list[str] = []

    async def check_readiness(self, model: str) -> ProviderReadinessResult:
        self.check_calls.append(model)
        return ProviderReadinessResult(
            provider=self.provider,
            model=model,
            status=ReadinessStatus.OK,
            capabilities=self.capabilities,
        )

    async def warmup(self, model: str) -> ProviderReadinessResult:
        self.warmup_calls.append(model)
        return ProviderReadinessResult(
            provider=self.provider,
            model=model,
            status=ReadinessStatus.OK,
            capabilities=self.capabilities,
        )


def test_protocol_compatible_fake_satisfies_interface() -> None:
    """A class with the required attributes satisfies the protocol structurally."""
    fake = _FakeProviderDiagnostics(ProviderCapability())
    assert isinstance(fake, LLMProviderDiagnostics)


@pytest.mark.anyio
async def test_protocol_compatible_fake_records_check_and_warmup_calls() -> None:
    """The fake implementation records the model passed to both methods."""
    fake = _FakeProviderDiagnostics(ProviderCapability(warmup=True))

    check_result = await fake.check_readiness("test-model")
    warmup_result = await fake.warmup("test-model")

    assert fake.check_calls == ["test-model"]
    assert fake.warmup_calls == ["test-model"]
    assert check_result.status is ReadinessStatus.OK
    assert warmup_result.status is ReadinessStatus.OK
