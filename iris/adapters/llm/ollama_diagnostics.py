"""Ollama provider diagnostics implementation.

Implements :class:`LLMProviderDiagnostics` for the local Ollama adapter.
Probes the Ollama REST API to verify that the daemon is reachable, the
configured model is installed, and (optionally) whether the model is
currently loaded into memory. Supports a minimal warmup action that
issues a load-oriented ``/api/chat`` request and verifies whether
the model becomes loaded via a follow-up ``/api/ps`` probe.
"""

from __future__ import annotations

import json
import time
from typing import override

import httpx

from iris.adapters.llm.diagnostics import (
    LLMProviderDiagnostics,
    LLMProviderInvalidResponseError,
    ProviderCapability,
    ProviderDiagnosticIssue,
    ProviderReadinessResult,
    ReadinessStatus,
)
from iris.adapters.llm.ollama import OllamaConfig

type _JsonScalar = str | int | float | bool | None
type _JsonValue = _JsonScalar | _JsonObject | list[_JsonValue]
type _JsonObject = dict[str, _JsonValue]

_OLLAMA_DIAGNOSTICS_PROVIDER = "ollama"

_OLLAMA_DIAGNOSTICS_CAPABILITIES = ProviderCapability(
    health_check=True,
    model_availability_check=True,
    model_loaded_check=True,
    warmup=True,
)

_HTTP_OK_THRESHOLD = 400
_HTTP_NOT_FOUND = 404


class OllamaDiagnostics(LLMProviderDiagnostics):
    """Ollama-specific :class:`LLMProviderDiagnostics` implementation."""

    provider: str = _OLLAMA_DIAGNOSTICS_PROVIDER
    capabilities: ProviderCapability = _OLLAMA_DIAGNOSTICS_CAPABILITIES

    def __init__(
        self,
        config: OllamaConfig | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Create an Ollama diagnostics instance.

        Args:
            config: Adapter-local Ollama configuration.
            client: Optional injected HTTP client.
            transport: Optional HTTP transport used when creating the default client.
        """
        self._config = config or OllamaConfig()
        self._client = client or httpx.AsyncClient(
            base_url=self._config.base_url,
            timeout=self._config.timeout_seconds,
            transport=transport,
        )

    @override
    async def check_readiness(self, model: str) -> ProviderReadinessResult:
        """Probe Ollama and the configured model for readiness.

        Performs up to four lightweight probes:

        1. ``GET /`` to confirm the daemon responds.
        2. ``GET /api/tags`` to confirm the model is installed.
        3. ``POST /api/show`` to confirm model metadata is readable.
        4. ``GET /api/ps`` to confirm the model is currently loaded.

        Args:
            model: Model name to probe.

        Returns:
            Aggregated readiness result for the configured Ollama host.
        """
        started = _now()
        issues: list[ProviderDiagnosticIssue] = []
        metadata: dict[str, str] = {
            "base_url": self._config.base_url,
            "model_installed": "false",
            "model_loaded": "false",
        }

        if not await self._probe_daemon():
            return _build_result(
                model=model,
                issues=(
                    ProviderDiagnosticIssue(
                        code="daemon_unreachable",
                        message=f"Ollama daemon is unreachable at {self._config.base_url}",
                        severity=ReadinessStatus.FAIL,
                        remediation=(
                            "Verify the Ollama service is running and the base_url is correct"
                        ),
                    ),
                ),
                started=started,
                metadata=metadata,
            )

        installed_models = await self._list_models()
        if installed_models is None:
            issues.append(
                ProviderDiagnosticIssue(
                    code="tags_endpoint_unavailable",
                    message="Ollama /api/tags did not return a model list",
                    severity=ReadinessStatus.WARN,
                ),
            )
        else:
            metadata["installed_models"] = ",".join(sorted(installed_models))
            if model not in installed_models:
                issues.append(
                    ProviderDiagnosticIssue(
                        code="model_not_installed",
                        message=f"Model '{model}' is not installed on the Ollama host",
                        severity=ReadinessStatus.FAIL,
                        remediation=f"Pull the model with: ollama pull {model}",
                    ),
                )
            else:
                metadata["model_installed"] = "true"
                if not await self._probe_model_metadata(model):
                    issues.append(
                        ProviderDiagnosticIssue(
                            code="model_metadata_unavailable",
                            message=f"Ollama could not read metadata for model '{model}'",
                            severity=ReadinessStatus.WARN,
                        ),
                    )

        loaded_models = await self._list_loaded_models()
        if loaded_models is None:
            issues.append(
                ProviderDiagnosticIssue(
                    code="ps_endpoint_unavailable",
                    message="Ollama /api/ps did not return a loaded model list",
                    severity=ReadinessStatus.WARN,
                ),
            )
        else:
            metadata["loaded_models"] = ",".join(sorted(loaded_models))
            if model in loaded_models:
                metadata["model_loaded"] = "true"
            elif metadata["model_installed"] == "true":
                issues.append(
                    ProviderDiagnosticIssue(
                        code="model_not_loaded",
                        message=f"Model '{model}' is installed but not currently loaded",
                        severity=ReadinessStatus.WARN,
                        remediation="Run the warmup step (diagnostics.warmup_models=true)",
                    ),
                )

        return _build_result(
            model=model,
            issues=tuple(issues),
            started=started,
            metadata=metadata,
        )

    @override
    async def warmup(self, model: str) -> ProviderReadinessResult:
        """Warm the model by issuing a load-oriented ``/api/chat`` request.

        Sends a single ``/api/chat`` request with the configured
        ``keep_alive`` so Ollama loads the model into memory. After
        the request, ``/api/ps`` is queried again to confirm whether
        the model became loaded. ``/api/ps`` connection failures do
        not hide the warmup outcome: the warmup is treated as
        successful when ``/api/chat`` returned 2xx, even if ``/api/ps``
        could not be read.

        Args:
            model: Model name to warm up.

        Returns:
            Warmup outcome; ``SKIPPED`` if the model is not installed.
        """
        started = _now()
        metadata: dict[str, str] = {
            "base_url": self._config.base_url,
            "model_loaded": "false",
        }

        installed_models = await self._list_models()
        if installed_models is not None and model not in installed_models:
            return _build_result(
                model=model,
                issues=(_warmup_model_missing_issue(model),),
                started=started,
                metadata=metadata,
            )

        chat_outcome = await self._issue_warmup_chat(
            model=model, started=started, metadata=metadata
        )
        if chat_outcome is not None:
            return chat_outcome

        return await self._finalize_warmup_state(model=model, started=started, metadata=metadata)

    async def _issue_warmup_chat(
        self,
        *,
        model: str,
        started: float,
        metadata: dict[str, str],
    ) -> ProviderReadinessResult | None:
        """POST the warmup ``/api/chat`` request and translate transport errors.

        Args:
            model: Model name being warmed up.
            started: Monotonic timestamp recorded before the probe started.
            metadata: Mutable metadata map shared with the caller.

        Returns:
            A typed result if the chat request failed; ``None`` when the chat
            request succeeded and the caller should continue with the loaded
            models probe.
        """
        payload = _build_warmup_payload(model=model, config=self._config)
        try:
            response = await self._client.post("/api/chat", json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            return _build_result(
                model=model,
                issues=(_warmup_status_issue(exc.response.status_code, exc),),
                started=started,
                metadata=metadata,
            )
        except httpx.HTTPError as exc:
            return _build_result(
                model=model,
                issues=(_translate_warmup_error(exc),),
                started=started,
                metadata=metadata,
            )
        return None

    async def _finalize_warmup_state(
        self,
        *,
        model: str,
        started: float,
        metadata: dict[str, str],
    ) -> ProviderReadinessResult:
        """Read ``/api/ps`` after the warmup chat and report the loaded state.

        Args:
            model: Model name being warmed up.
            started: Monotonic timestamp recorded before the probe started.
            metadata: Mutable metadata map shared with the caller.

        Returns:
            The warmup result describing whether the model is now loaded.
        """
        loaded_models = await self._list_loaded_models()
        if loaded_models is None:
            return _build_result(
                model=model,
                issues=(_ps_probe_failed_issue(),),
                started=started,
                metadata=metadata,
            )
        metadata["loaded_models"] = ",".join(sorted(loaded_models))
        if model in loaded_models:
            metadata["model_loaded"] = "true"
            return _build_result(
                model=model,
                issues=(),
                started=started,
                metadata=metadata,
            )
        return _build_result(
            model=model,
            issues=(_model_still_not_loaded_issue(model),),
            started=started,
            metadata=metadata,
        )

    async def _probe_daemon(self) -> bool:
        try:
            response = await self._client.get("/")
        except httpx.HTTPError:
            return False
        return response.status_code < _HTTP_OK_THRESHOLD

    async def _list_models(self) -> frozenset[str] | None:
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
        except httpx.HTTPError:
            return None
        try:
            return _extract_model_names(_safe_json(response))
        except LLMProviderInvalidResponseError:
            return None

    async def _list_loaded_models(self) -> frozenset[str] | None:
        try:
            response = await self._client.get("/api/ps")
            response.raise_for_status()
        except httpx.HTTPError:
            return None
        try:
            return _extract_loaded_model_names(_safe_json(response))
        except LLMProviderInvalidResponseError:
            return None

    async def _probe_model_metadata(self, model: str) -> bool:
        try:
            response = await self._client.post(
                "/api/show",
                json={"name": model},
            )
        except httpx.HTTPError:
            return False
        if response.status_code == _HTTP_NOT_FOUND:
            return False
        return response.status_code < _HTTP_OK_THRESHOLD


def _now() -> float:
    return time.perf_counter()


def _build_warmup_payload(*, model: str, config: OllamaConfig) -> _JsonObject:
    """Build a load-oriented ``/api/chat`` payload for warmup.

    Uses ``messages=[]`` so Ollama treats the request as a load
    operation rather than a generation. Mirrors
    :class:`OllamaLLMClient` request shape so the warmup path keeps
    the same options (``temperature`` and ``num_predict``) and
    ``keep_alive`` semantics.

    Args:
        model: Target model name.
        config: Adapter-local Ollama configuration.

    Returns:
        A JSON object suitable for ``POST /api/chat``.
    """
    options: _JsonObject = {"temperature": config.temperature}
    if config.max_output_tokens is not None:
        options["num_predict"] = config.max_output_tokens
    payload: _JsonObject = {
        "model": model,
        "messages": [],
        "stream": False,
        "options": options,
    }
    if config.keep_alive is not None:
        payload["keep_alive"] = config.keep_alive
    return payload


def _translate_warmup_error(exc: httpx.HTTPError) -> ProviderDiagnosticIssue:
    """Translate an httpx error into a typed warmup diagnostic issue.

    Args:
        exc: The httpx error raised by the warmup request.

    Returns:
        A typed diagnostic issue with the appropriate severity.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return _warmup_status_issue(exc.response.status_code, exc)
    if isinstance(exc, httpx.ConnectError):
        return ProviderDiagnosticIssue(
            code="warmup_failed",
            message=f"Ollama warmup could not connect: {exc}",
            severity=ReadinessStatus.FAIL,
        )
    if isinstance(exc, httpx.TimeoutException):
        return ProviderDiagnosticIssue(
            code="warmup_failed",
            message=f"Ollama warmup timed out: {exc}",
            severity=ReadinessStatus.FAIL,
        )
    return ProviderDiagnosticIssue(
        code="warmup_failed",
        message=f"Ollama warmup failed: {exc}",
        severity=ReadinessStatus.FAIL,
    )


def _warmup_status_issue(status: int, exc: httpx.HTTPStatusError) -> ProviderDiagnosticIssue:
    if status == _HTTP_NOT_FOUND:
        return ProviderDiagnosticIssue(
            code="warmup_skipped_model_missing",
            message=f"Ollama could not find model for warmup: {exc}",
            severity=ReadinessStatus.SKIPPED,
        )
    if status in {401, 403}:
        return ProviderDiagnosticIssue(
            code="warmup_failed",
            message=f"Ollama rejected warmup with HTTP {status}: {exc}",
            severity=ReadinessStatus.FAIL,
        )
    return ProviderDiagnosticIssue(
        code="warmup_failed",
        message=f"Ollama warmup failed with HTTP {status}: {exc}",
        severity=ReadinessStatus.FAIL,
    )


def _warmup_model_missing_issue(model: str) -> ProviderDiagnosticIssue:
    """Build a ``SKIPPED`` issue for warmup when the model is not installed.

    Args:
        model: The model name that was requested for warmup.

    Returns:
        A diagnostic issue explaining why the warmup was skipped.
    """
    return ProviderDiagnosticIssue(
        code="warmup_skipped_model_missing",
        message=f"Ollama could not find model '{model}' for warmup",
        severity=ReadinessStatus.SKIPPED,
        remediation=f"Pull the model with: ollama pull {model}",
    )


def _ps_probe_failed_issue() -> ProviderDiagnosticIssue:
    """Build a ``WARN`` issue for ``/api/ps`` probe failures after warmup.

    Returns:
        A diagnostic issue describing the ``/api/ps`` probe failure and the
        warmup-outcome policy applied when the probe cannot be read.
    """
    return ProviderDiagnosticIssue(
        code="ps_probe_failed_after_warmup",
        message=(
            "Ollama /api/ps could not be read after warmup; "
            "warmup is treated as successful because /api/chat returned 2xx"
        ),
        severity=ReadinessStatus.WARN,
    )


def _model_still_not_loaded_issue(model: str) -> ProviderDiagnosticIssue:
    """Build a ``WARN`` issue when ``/api/chat`` succeeded but the model is unloaded.

    Args:
        model: The model name that was requested for warmup.

    Returns:
        A diagnostic issue describing the inconsistent post-warmup state.
    """
    return ProviderDiagnosticIssue(
        code="model_still_not_loaded",
        message=f"Ollama /api/chat succeeded but '{model}' is not loaded",
        severity=ReadinessStatus.WARN,
    )


def _build_result(
    *,
    model: str,
    issues: tuple[ProviderDiagnosticIssue, ...],
    started: float,
    metadata: dict[str, str],
) -> ProviderReadinessResult:
    severity = _aggregate_severity(issues)
    latency_ms = (_now() - started) * 1000.0
    return ProviderReadinessResult(
        provider=_OLLAMA_DIAGNOSTICS_PROVIDER,
        model=model,
        status=severity,
        capabilities=_OLLAMA_DIAGNOSTICS_CAPABILITIES,
        latency_ms=latency_ms,
        issues=issues,
        metadata=metadata,
    )


def _aggregate_severity(issues: tuple[ProviderDiagnosticIssue, ...]) -> ReadinessStatus:
    if not issues:
        return ReadinessStatus.OK
    severities = {issue.severity for issue in issues}
    if ReadinessStatus.FAIL in severities:
        return ReadinessStatus.FAIL
    if ReadinessStatus.WARN in severities:
        return ReadinessStatus.WARN
    return ReadinessStatus.SKIPPED


def _safe_json(response: httpx.Response) -> _JsonObject:
    try:
        body: _JsonObject = response.json()
    except json.JSONDecodeError as exc:
        message = "Ollama response was not valid JSON"
        raise LLMProviderInvalidResponseError(message) from exc
    return body


def _extract_model_names(body: _JsonObject) -> frozenset[str] | None:
    models_value = body.get("models")
    if not isinstance(models_value, list):
        return None
    names: set[str] = set()
    for entry_value in models_value:
        if isinstance(entry_value, dict):
            name_value = entry_value.get("name")
            if isinstance(name_value, str):
                names.add(name_value)
    return frozenset(names)


def _extract_loaded_model_names(body: _JsonObject) -> frozenset[str] | None:
    models_value = body.get("models")
    if not isinstance(models_value, list):
        return None
    names: set[str] = set()
    for entry_value in models_value:
        if isinstance(entry_value, dict):
            name_value = entry_value.get("name")
            if isinstance(name_value, str):
                names.add(name_value)
    if not names:
        return frozenset()
    return frozenset(names)
