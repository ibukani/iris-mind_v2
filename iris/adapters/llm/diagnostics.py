"""Provider-neutral LLM diagnostics contracts and common provider error taxonomy.

The diagnostics module is the contract layer for runtime startup health
checks, request-time observability hooks, and provider-specific warmup
behavior. It is intentionally provider-neutral: concrete provider
implementations live in sibling modules such as ``ollama_diagnostics`` and
``openai_diagnostics``.

The module also defines the common provider error hierarchy that
provider adapters translate their native exceptions into. The gRPC
ingress layer uses these classes to map provider failures to stable
gRPC status codes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from iris.core.metadata import immutable_metadata

if TYPE_CHECKING:
    from collections.abc import Mapping


class ReadinessStatus(Enum):
    """Readiness severity of a provider/model probe."""

    OK = "ok"
    WARN = "warn"
    FAIL = "fail"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ProviderCapability:
    """Declared capability surface of a provider diagnostics implementation.

    Capability flags are declared statically so the startup runner can
    decide which checks to perform without instantiating the provider
    client.
    """

    health_check: bool = True
    model_availability_check: bool = False
    model_loaded_check: bool = False
    warmup: bool = False


@dataclass(frozen=True)
class ProviderDiagnosticIssue:
    """A single issue found during a readiness probe.

    Attributes:
        code: Stable machine-readable issue code (e.g. ``model_not_found``).
        message: Human-readable description safe for logs.
        severity: Severity classification.
        remediation: Optional remediation hint for operators.
    """

    code: str
    message: str
    severity: ReadinessStatus
    remediation: str | None = None


@dataclass(frozen=True)
class ProviderReadinessResult:
    """Outcome of a single provider/model readiness probe or warmup.

    Attributes:
        provider: Provider name that produced the result.
        model: Model name that was probed.
        status: Aggregate severity for the probe.
        capabilities: Declared capabilities of the implementation.
        latency_ms: Optional measured latency in milliseconds.
        issues: Ordered tuple of issues found during the probe.
        metadata: Optional safe metadata (e.g. base URL, model counts).
    """

    provider: str
    model: str
    status: ReadinessStatus
    capabilities: ProviderCapability
    latency_ms: float | None = None
    issues: tuple[ProviderDiagnosticIssue, ...] = ()
    metadata: Mapping[str, str] | None = None


def aggregate_issue_severity(
    issues: tuple[ProviderDiagnosticIssue, ...],
) -> ReadinessStatus:
    """Aggregate issue severities into a single readiness status.

    Args:
        issues: Ordered diagnostic issues collected for a provider probe.

    Returns:
        ``FAIL`` if any issue failed, ``WARN`` if at least one issue warned,
        ``SKIPPED`` if all issues were skipped, otherwise ``OK``.
    """
    if not issues:
        return ReadinessStatus.OK
    severities = {issue.severity for issue in issues}
    if ReadinessStatus.FAIL in severities:
        return ReadinessStatus.FAIL
    if ReadinessStatus.WARN in severities:
        return ReadinessStatus.WARN
    return ReadinessStatus.SKIPPED


def build_provider_readiness_result(
    *,
    provider: str,
    model: str,
    capabilities: ProviderCapability,
    issues: tuple[ProviderDiagnosticIssue, ...],
    latency_ms: float | None = None,
    metadata: dict[str, str] | None = None,
) -> ProviderReadinessResult:
    """Build a typed readiness result from provider diagnostics input.

    Args:
        provider: Provider name reported in the result.
        model: Model name that was probed.
        capabilities: Provider capability declaration.
        issues: Ordered diagnostic issues found during the probe.
        latency_ms: Optional measured latency in milliseconds.
        metadata: Optional safe metadata from the probe.

    Returns:
        A frozen provider readiness result with aggregate status.
    """
    return ProviderReadinessResult(
        provider=provider,
        model=model,
        status=aggregate_issue_severity(issues),
        capabilities=capabilities,
        latency_ms=latency_ms,
        issues=issues,
        metadata=immutable_metadata(metadata) if metadata is not None else None,
    )


@runtime_checkable
class LLMProviderDiagnostics(Protocol):
    """Provider-neutral diagnostics interface for a single LLM provider.

    Implementations expose:

    - ``provider``: stable provider name used in logs and metadata.
    - ``capabilities``: declared capability flags for the runner.
    - ``check_readiness``: probe the provider/model without external
      side effects beyond lightweight metadata calls.
    - ``warmup``: perform a provider-specific warmup action (e.g.
      loading a model). Must return a ``ProviderReadinessResult`` even
      when the provider has no warmup action.
    """

    provider: str
    capabilities: ProviderCapability

    async def check_readiness(self, model: str) -> ProviderReadinessResult:
        """Probe a model for readiness and return a typed result.

        Args:
            model: Model name to probe.

        Returns:
            Typed readiness outcome with issues and optional metadata.
        """
        ...

    async def warmup(self, model: str) -> ProviderReadinessResult:
        """Warm up a model and return a typed result.

        Args:
            model: Model name to warm up.

        Returns:
            Typed warmup outcome. Providers without warmup support must
            return ``ReadinessStatus.SKIPPED`` with an explanatory issue.
        """
        ...


# ---------------------------------------------------------------------------
# Common provider error taxonomy
# ---------------------------------------------------------------------------


class LLMProviderError(RuntimeError):
    """Base error for LLM provider failures."""


class LLMProviderConnectionError(LLMProviderError):
    """Provider endpoint is unreachable."""


class LLMProviderTimeoutError(LLMProviderError):
    """Provider request timed out."""


class LLMProviderAuthenticationError(LLMProviderError):
    """Provider authentication failed or credentials are missing."""


class LLMProviderRateLimitError(LLMProviderError):
    """Provider rejected the request due to rate limits."""


class LLMProviderQuotaError(LLMProviderError):
    """Provider quota or billing limits were exceeded."""


class LLMProviderModelUnavailableError(LLMProviderError):
    """Configured model is unavailable or not installed."""


class LLMProviderInvalidResponseError(LLMProviderError):
    """Provider returned malformed or unsupported response data."""
