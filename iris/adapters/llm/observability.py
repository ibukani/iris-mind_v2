"""LLM request-time observability hooks and logging observer.

Provider-neutral abstractions for observing the lifecycle of an
:func:`iris.adapters.llm.ports.LLMClient.generate` call. The
:func:`ObservableLLMClient` wrapper times the request and reports
start, success, and error events to a configured
:class:`LLMRequestObserver`. The default
:class:`LoggingRequestObserver` emits structured ``logging`` records
so operators can monitor provider latency and error rates without
pulling in a dedicated metrics stack.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Protocol

from iris.adapters.llm.diagnostics import LLMProviderModelUnavailableError
from iris.adapters.llm.lifecycle import (
    ModelLifecycleProbe,
    ModelLifecycleSnapshot,
    ModelLoadState,
    cold_start_latency_ms,
    generation_latency_ms,
    generation_model_load_state,
)

if TYPE_CHECKING:
    from iris.adapters.llm.ports import LLMClient, LLMRequest, LLMResponse

_LOGGER_NAME = "iris.adapters.llm.observability"


class LLMRequestObserver(Protocol):
    """Provider-neutral observer for an LLM client request lifecycle."""

    def on_request_start(
        self,
        *,
        model: str,
        model_load_state: ModelLoadState = ModelLoadState.UNKNOWN,
    ) -> None:
        """Called before the wrapped client issues the request.

        Args:
            model: The model name being called.
            model_load_state: Best known load state before generation.
        """
        ...

    def on_request_success(
        self,
        *,
        model: str,
        latency_ms: float,
        finish_reason: str,
        model_load_state: ModelLoadState = ModelLoadState.UNKNOWN,
        generation_latency_ms: float | None = None,
        cold_start_latency_ms: float | None = None,
    ) -> None:
        """Called after the wrapped client returns successfully.

        Args:
            model: The model name that was called.
            latency_ms: Elapsed time in milliseconds.
            finish_reason: Provider-reported finish reason.
            model_load_state: Best known load state for the generation.
            generation_latency_ms: Provider split generation latency if known.
            cold_start_latency_ms: Provider split model-load latency if the
                generation incurred cold start.
        """
        ...

    def on_request_error(
        self,
        *,
        model: str,
        latency_ms: float,
        error: BaseException,
        model_load_state: ModelLoadState = ModelLoadState.UNKNOWN,
        generation_latency_ms: float | None = None,
        cold_start_latency_ms: float | None = None,
    ) -> None:
        """Called when the wrapped client raises an exception.

        Args:
            model: The model name that was called.
            latency_ms: Elapsed time in milliseconds.
            error: The exception raised by the wrapped client.
            model_load_state: Best known load state for the generation attempt.
            generation_latency_ms: Provider split generation latency if known.
            cold_start_latency_ms: Provider split model-load latency if the
                attempt incurred cold start.
        """
        ...


class LoggingRequestObserver:
    """Observer that emits structured ``logging`` records for each event."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        """Create a logging observer.

        Args:
            logger: Optional logger to emit records to. Defaults to
                the module-level ``iris.adapters.llm.observability``
                logger.
        """
        self._logger = logger or logging.getLogger(_LOGGER_NAME)

    def on_request_start(
        self,
        *,
        model: str,
        model_load_state: ModelLoadState = ModelLoadState.UNKNOWN,
    ) -> None:
        """Emit a debug record for the start of an LLM request.

        Args:
            model: The model name being called.
            model_load_state: Best known load state before generation.
        """
        self._logger.debug(
            "llm.request.start",
            extra={"model": model, "model_load_state": model_load_state.value},
        )

    def on_request_success(
        self,
        *,
        model: str,
        latency_ms: float,
        finish_reason: str,
        model_load_state: ModelLoadState = ModelLoadState.UNKNOWN,
        generation_latency_ms: float | None = None,
        cold_start_latency_ms: float | None = None,
    ) -> None:
        """Emit an info record for a successful LLM request.

        Args:
            model: The model name that was called.
            latency_ms: Elapsed time in milliseconds.
            finish_reason: Provider-reported finish reason.
            model_load_state: Best known load state for the generation.
            generation_latency_ms: Provider split generation latency if known.
            cold_start_latency_ms: Provider split model-load latency if the
                generation incurred cold start.
        """
        self._logger.info(
            "llm.request.success",
            extra={
                "model": model,
                "latency_ms": latency_ms,
                "finish_reason": finish_reason,
                "model_load_state": model_load_state.value,
                "generation_latency_ms": generation_latency_ms,
                "cold_start_latency_ms": cold_start_latency_ms,
            },
        )

    def on_request_error(
        self,
        *,
        model: str,
        latency_ms: float,
        error: BaseException,
        model_load_state: ModelLoadState = ModelLoadState.UNKNOWN,
        generation_latency_ms: float | None = None,
        cold_start_latency_ms: float | None = None,
    ) -> None:
        """Emit a warning record for a failed LLM request.

        Args:
            model: The model name that was called.
            latency_ms: Elapsed time in milliseconds.
            error: The exception raised by the wrapped client.
            model_load_state: Best known load state for the generation attempt.
            generation_latency_ms: Provider split generation latency if known.
            cold_start_latency_ms: Provider split model-load latency if the
                attempt incurred cold start.
        """
        self._logger.warning(
            "llm.request.error",
            extra={
                "model": model,
                "latency_ms": latency_ms,
                "error_type": type(error).__name__,
                "error_message": str(error),
                "model_load_state": model_load_state.value,
                "generation_latency_ms": generation_latency_ms,
                "cold_start_latency_ms": cold_start_latency_ms,
            },
        )


class ObservableLLMClient:
    """Wrapper around an :class:`LLMClient` that reports request lifecycle events."""

    def __init__(
        self,
        client: LLMClient,
        observer: LLMRequestObserver,
        lifecycle_probe: ModelLifecycleProbe | None = None,
    ) -> None:
        """Create an observable client.

        Args:
            client: The underlying LLM client to wrap.
            observer: The observer to notify on each request.
            lifecycle_probe: Optional local model lifecycle probe.
        """
        self._client = client
        self._observer = observer
        self._lifecycle_probe = lifecycle_probe

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate a response and report timing and outcome to the observer.

        Args:
            request: Provider-neutral LLM request.

        Returns:
            Provider-neutral LLM response returned by the wrapped client.
        """
        model = request.model
        snapshot = await self._snapshot(model)
        self._observer.on_request_start(model=model, model_load_state=snapshot.load_state)
        started = time.perf_counter()
        if snapshot.load_state is ModelLoadState.UNAVAILABLE:
            self._raise_unavailable(model=model, snapshot=snapshot, started=started)
        try:
            response = await self._client.generate(request)
        except BaseException as exc:
            latency_ms = (time.perf_counter() - started) * 1000.0
            self._observer.on_request_error(
                model=model,
                latency_ms=latency_ms,
                error=exc,
                model_load_state=snapshot.load_state,
                generation_latency_ms=latency_ms,
            )
            raise
        latency_ms = (time.perf_counter() - started) * 1000.0
        model_load_state = generation_model_load_state(
            before=snapshot.load_state,
            load_latency_ms=response.load_latency_ms,
        )
        provider_generation_latency_ms = generation_latency_ms(
            provider_generation_latency_ms=response.generation_latency_ms,
            fallback_latency_ms=latency_ms,
        )
        provider_cold_start_latency_ms = cold_start_latency_ms(
            load_state=model_load_state,
            load_latency_ms=response.load_latency_ms,
            fallback_latency_ms=latency_ms,
        )
        self._observer.on_request_success(
            model=model,
            latency_ms=latency_ms,
            finish_reason=response.finish_reason,
            model_load_state=model_load_state,
            generation_latency_ms=provider_generation_latency_ms,
            cold_start_latency_ms=provider_cold_start_latency_ms,
        )
        return response

    async def _snapshot(self, model: str) -> ModelLifecycleSnapshot:
        if self._lifecycle_probe is None:
            return ModelLifecycleSnapshot(provider="unknown", model=model)
        return await self._lifecycle_probe.snapshot(model)

    def _raise_unavailable(
        self,
        *,
        model: str,
        snapshot: ModelLifecycleSnapshot,
        started: float,
    ) -> None:
        reason = snapshot.reason or "model_unavailable"
        message = f"Local model {model!r} is unavailable before generation: {reason}"
        error = LLMProviderModelUnavailableError(message)
        latency_ms = (time.perf_counter() - started) * 1000.0
        self._observer.on_request_error(
            model=model,
            latency_ms=latency_ms,
            error=error,
            model_load_state=ModelLoadState.UNAVAILABLE,
            generation_latency_ms=latency_ms,
        )
        raise error
