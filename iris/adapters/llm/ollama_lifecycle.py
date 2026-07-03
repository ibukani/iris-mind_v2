"""Request-time Ollama local model lifecycle probe."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
import json
import time
from typing import override

import httpx

from iris.adapters.llm.lifecycle import (
    ModelLifecycleProbe,
    ModelLifecycleSnapshot,
    ModelLoadState,
)
from iris.adapters.llm.ollama import OllamaConfig

type _JsonScalar = str | int | float | bool | None
type _JsonValue = _JsonScalar | _JsonObject | list[_JsonValue]
type _JsonObject = dict[str, _JsonValue]

_OLLAMA_PROVIDER = "ollama"
_HTTP_OK_THRESHOLD = 400


class _EndpointStatus(StrEnum):
    """Internal classification for a lightweight Ollama model-list probe."""

    OK = "ok"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class _ModelNamesProbe:
    """Normalized result for a lightweight Ollama model-list endpoint."""

    status: _EndpointStatus
    names: frozenset[str] = frozenset()
    reason: str | None = None


@dataclass(frozen=True)
class _SnapshotDecision:
    """Internal decision used to build a lifecycle snapshot."""

    load_state: ModelLoadState
    reason: str | None


class OllamaModelLifecycleProbe(ModelLifecycleProbe):
    """Probe Ollama loaded/installed model state before user-facing generation."""

    def __init__(
        self,
        config: OllamaConfig | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Create an Ollama lifecycle probe.

        Args:
            config: Adapter-local Ollama configuration. ``timeout_seconds`` should
                be the short readiness timeout, not the full generation timeout.
            client: Optional injected HTTP client for tests.
            transport: Optional HTTP transport used by the default client.
        """
        self._config = config or OllamaConfig()
        self._client = client or httpx.AsyncClient(
            base_url=self._config.base_url,
            timeout=self._config.timeout_seconds,
            transport=transport,
        )

    @override
    async def snapshot(self, model: str) -> ModelLifecycleSnapshot:
        """Return a safe request-time lifecycle snapshot for an Ollama model."""
        started = time.perf_counter()
        loaded = await self._list_model_names("/api/ps")
        installed = _ModelNamesProbe(_EndpointStatus.UNKNOWN, reason=loaded.reason)
        if loaded.status is not _EndpointStatus.UNAVAILABLE and model not in loaded.names:
            installed = await self._list_model_names("/api/tags")
        decision = _snapshot_decision(model=model, loaded=loaded, installed=installed)
        return _snapshot(
            model=model,
            load_state=decision.load_state,
            started=started,
            reason=decision.reason,
        )

    async def _list_model_names(self, path: str) -> _ModelNamesProbe:
        result: _ModelNamesProbe
        try:
            response = await self._client.get(path)
        except httpx.ConnectError:
            result = _ModelNamesProbe(
                status=_EndpointStatus.UNAVAILABLE,
                reason="daemon_unreachable",
            )
        except httpx.TimeoutException:
            result = _ModelNamesProbe(
                status=_EndpointStatus.UNAVAILABLE,
                reason="lifecycle_probe_timeout",
            )
        except httpx.HTTPError:
            result = _ModelNamesProbe(
                status=_EndpointStatus.UNKNOWN,
                reason=f"{path}_request_failed",
            )
        else:
            result = _model_names_from_response(path=path, response=response)
        return result


def _model_names_from_response(path: str, response: httpx.Response) -> _ModelNamesProbe:
    """Normalize an Ollama model-list HTTP response.

    Returns:
        Model-name probe result.
    """
    if response.status_code >= _HTTP_OK_THRESHOLD:
        return _ModelNamesProbe(
            status=_EndpointStatus.UNKNOWN,
            reason=f"{path}_http_{response.status_code}",
        )
    names = _extract_model_names(response)
    if names is None:
        return _ModelNamesProbe(
            status=_EndpointStatus.UNKNOWN,
            reason=f"{path}_invalid_response",
        )
    return _ModelNamesProbe(status=_EndpointStatus.OK, names=names)


def _snapshot_decision(
    *,
    model: str,
    loaded: _ModelNamesProbe,
    installed: _ModelNamesProbe,
) -> _SnapshotDecision:
    """Derive a snapshot decision from loaded and installed model probes.

    Returns:
        Snapshot decision with state and stable reason.
    """
    state = ModelLoadState.UNKNOWN
    reason = installed.reason or loaded.reason
    if loaded.status is _EndpointStatus.UNAVAILABLE:
        state = ModelLoadState.UNAVAILABLE
        reason = loaded.reason
    elif model in loaded.names:
        state = ModelLoadState.WARM
        reason = "model_loaded"
    elif installed.status is _EndpointStatus.UNAVAILABLE:
        state = ModelLoadState.UNAVAILABLE
        reason = installed.reason
    elif installed.status is _EndpointStatus.UNKNOWN:
        state = ModelLoadState.UNKNOWN
    elif model in installed.names:
        state = _state_for_installed_model(loaded)
        reason = loaded.reason or "model_installed_not_loaded"
    else:
        state = ModelLoadState.UNAVAILABLE
        reason = "model_not_installed"
    return _SnapshotDecision(load_state=state, reason=reason)


def _state_for_installed_model(loaded: _ModelNamesProbe) -> ModelLoadState:
    """Return state for an installed model based on the loaded-model probe.

    Returns:
        ``unknown`` when loaded state could not be read; otherwise ``unloaded``.
    """
    if loaded.status is _EndpointStatus.UNKNOWN:
        return ModelLoadState.UNKNOWN
    return ModelLoadState.UNLOADED


def _snapshot(
    *,
    model: str,
    load_state: ModelLoadState,
    started: float,
    reason: str | None,
) -> ModelLifecycleSnapshot:
    return ModelLifecycleSnapshot(
        provider=_OLLAMA_PROVIDER,
        model=model,
        load_state=load_state,
        checked_at=datetime.now(tz=UTC),
        latency_ms=(time.perf_counter() - started) * 1000.0,
        reason=reason,
    )


def _extract_model_names(response: httpx.Response) -> frozenset[str] | None:
    try:
        body: _JsonObject = response.json()
    except json.JSONDecodeError:
        return None
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
