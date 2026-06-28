"""OpenAI provider diagnostics implementation.

Implements :class:`LLMProviderDiagnostics` for the OpenAI Responses API
adapter. Uses the ``/models`` endpoint to verify that the configured
API key is valid and that the requested model is available.

The OpenAI provider does not have a meaningful warmup action, so
:func:`warmup` always returns :class:`ReadinessStatus.SKIPPED` with an
explanatory issue.
"""

from __future__ import annotations

from typing import Protocol, override

from iris.adapters.llm.diagnostics import (
    LLMProviderDiagnostics,
    ProviderCapability,
    ProviderDiagnosticIssue,
    ProviderReadinessResult,
    ReadinessStatus,
    build_provider_readiness_result,
)
from iris.adapters.llm.openai import (
    OpenAIAdapterError,
    OpenAIConfig,
    openai_sdk,
)
from iris.adapters.llm.type_utils import is_object_sequence

_OPENAI_DIAGNOSTICS_PROVIDER = "openai"

_OPENAI_DIAGNOSTICS_CAPABILITIES = ProviderCapability(
    health_check=True,
    model_availability_check=True,
    model_loaded_check=False,
    warmup=False,
)


class OpenAIModelPage(Protocol):
    """Subset of the openai ``AsyncPage[Model]`` interface used by diagnostics."""

    @property
    def data(self) -> tuple[object, ...]:
        """Return the page entries."""
        ...


class OpenAIModelsResource(Protocol):
    """Subset of the openai ``AsyncModels`` resource used by diagnostics."""

    async def list(self) -> object:
        """List available models."""
        ...


class OpenAIClientProtocol(Protocol):
    """Subset of the openai ``AsyncOpenAI`` client used by diagnostics."""

    @property
    def models(self) -> OpenAIModelsResource:
        """Return the models resource."""
        ...


class OpenAIDiagnostics(LLMProviderDiagnostics):
    """OpenAI-specific :class:`LLMProviderDiagnostics` implementation."""

    provider: str = _OPENAI_DIAGNOSTICS_PROVIDER
    capabilities: ProviderCapability = _OPENAI_DIAGNOSTICS_CAPABILITIES

    def __init__(
        self,
        config: OpenAIConfig | None = None,
        *,
        client: OpenAIClientProtocol | None = None,
    ) -> None:
        """Create an OpenAI diagnostics instance.

        Args:
            config: Adapter-local OpenAI configuration.
            client: Optional injected client for tests.
        """
        self._config = config or OpenAIConfig(model="gpt-5-mini")
        self._client = client or _build_client(self._config)

    @override
    async def check_readiness(self, model: str) -> ProviderReadinessResult:
        """Probe OpenAI and the configured model for readiness.

        Args:
            model: Model name to probe.

        Returns:
            Aggregated readiness result for the configured OpenAI host.
        """
        try:
            listed = await self._client.models.list()
        except OpenAIAdapterError as exc:
            return _build_failure(
                model=model,
                code="openai_sdk_missing",
                message=str(exc),
            )
        except openai_sdk.APIError as exc:
            return _translate_list_error(exc, model)

        available = _extract_model_ids(listed)
        if available is None:
            return _build_failure(
                model=model,
                code="openai_list_invalid",
                message="OpenAI /models response did not contain a model list",
            )

        issues: tuple[ProviderDiagnosticIssue, ...] = ()
        if model not in available:
            issues = (
                ProviderDiagnosticIssue(
                    code="model_not_available",
                    message=f"Model '{model}' is not listed in OpenAI /models",
                    severity=ReadinessStatus.FAIL,
                    remediation=("Verify the model name and the API key's account permissions"),
                ),
            )

        return _build_result(
            model=model,
            issues=issues,
            available_count=len(available),
        )

    @override
    async def warmup(self, model: str) -> ProviderReadinessResult:
        """Report that the OpenAI provider has no warmup action.

        Args:
            model: Model name; kept for symmetry with other providers.

        Returns:
            A :class:`ReadinessStatus.SKIPPED` result with an explanatory
            issue.
        """
        return _build_result(
            model=model,
            issues=(
                ProviderDiagnosticIssue(
                    code="warmup_not_supported",
                    message=(
                        "OpenAI provider does not support warmup; "
                        "the first request will initialize the model server-side"
                    ),
                    severity=ReadinessStatus.SKIPPED,
                ),
            ),
            available_count=None,
        )


def _build_client(config: OpenAIConfig) -> OpenAIClientProtocol:
    """Construct a default OpenAI client from the given config.

    Args:
        config: Adapter-local OpenAI configuration.

    Returns:
        A live OpenAI async client.

    Raises:
        OpenAIAdapterError: If the openai SDK is not installed or the
            API key is missing.
    """
    if openai_sdk is None:
        sdk_message = "OpenAI SDK is not installed. Install the 'openai' package."
        raise OpenAIAdapterError(sdk_message)
    if config.api_key is None:
        key_message = "OpenAI API key is required when no OpenAI client is injected."
        raise OpenAIAdapterError(key_message)
    client: OpenAIClientProtocol = openai_sdk.AsyncOpenAI(
        api_key=config.api_key,
        timeout=config.timeout_seconds,
    )
    return client


def _translate_list_error(exc: Exception, model: str) -> ProviderReadinessResult:
    """Translate an OpenAI list-models error into a typed readiness result.

    Args:
        exc: The exception raised by ``client.models.list()``.
        model: Model name being probed.

    Returns:
        A typed readiness result with the appropriate diagnostic issue.
    """
    message = f"OpenAI /models request failed: {exc}"
    code = "openai_request_failed"
    severity = ReadinessStatus.FAIL
    lowered = str(exc).lower()
    if "api key" in lowered or "unauthorized" in lowered or "401" in lowered:
        code = "authentication_failed"
    elif "rate limit" in lowered or "429" in lowered:
        code = "rate_limited"
    elif "quota" in lowered:
        code = "quota_exceeded"
    return _build_failure(model=model, code=code, message=message, severity=severity)


def _build_failure(
    *,
    model: str,
    code: str,
    message: str,
    severity: ReadinessStatus = ReadinessStatus.FAIL,
) -> ProviderReadinessResult:
    """Build a single-issue failure result.

    Args:
        model: Model name being probed.
        code: Diagnostic issue code.
        message: Human-readable message.
        severity: Issue severity; defaults to FAIL.

    Returns:
        A typed readiness result with one issue.
    """
    return _build_result(
        model=model,
        issues=(
            ProviderDiagnosticIssue(
                code=code,
                message=message,
                severity=severity,
            ),
        ),
        available_count=None,
    )


def _build_result(
    *,
    model: str,
    issues: tuple[ProviderDiagnosticIssue, ...],
    available_count: int | None,
) -> ProviderReadinessResult:
    """Assemble a :class:`ProviderReadinessResult` from raw inputs.

    Returns:
        A typed readiness result with aggregate status and optional metadata.
    """
    metadata: dict[str, str] | None = None
    if available_count is not None:
        metadata = {"available_models": str(available_count)}
    return build_provider_readiness_result(
        provider=_OPENAI_DIAGNOSTICS_PROVIDER,
        model=model,
        capabilities=_OPENAI_DIAGNOSTICS_CAPABILITIES,
        issues=issues,
        metadata=metadata,
    )


def _extract_model_ids(listed: object) -> frozenset[str] | None:
    """Extract model ids from the openai ``/models`` listing.

    Args:
        listed: The object returned by ``client.models.list()``.

    Returns:
        The set of available model ids, or ``None`` if the response
        does not match the expected shape.
    """
    data_value: object = getattr(listed, "data", None)
    if not is_object_sequence(data_value):
        return None
    names: set[str] = set()
    for entry in data_value:
        identifier: object = getattr(entry, "id", None)
        if isinstance(identifier, str):
            names.add(identifier)
    return frozenset(names)
