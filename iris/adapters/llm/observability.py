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

if TYPE_CHECKING:
    from iris.adapters.llm.ports import LLMClient, LLMRequest, LLMResponse

_LOGGER_NAME = "iris.adapters.llm.observability"


class LLMRequestObserver(Protocol):
    """Provider-neutral observer for an LLM client request lifecycle.

    Implementations receive timing and outcome information for every
    call to :func:`LLMClient.generate`. Errors are reported through a
    dedicated callback so observers can distinguish failures from
    successes.
    """

    def on_request_start(self, *, model: str) -> None:
        """Called before the wrapped client issues the request.

        Args:
            model: The model name being called.
        """
        ...

    def on_request_success(
        self,
        *,
        model: str,
        latency_ms: float,
        finish_reason: str,
    ) -> None:
        """Called after the wrapped client returns successfully.

        Args:
            model: The model name that was called.
            latency_ms: Elapsed time in milliseconds.
            finish_reason: Provider-reported finish reason.
        """
        ...

    def on_request_error(
        self,
        *,
        model: str,
        latency_ms: float,
        error: BaseException,
    ) -> None:
        """Called when the wrapped client raises an exception.

        Args:
            model: The model name that was called.
            latency_ms: Elapsed time in milliseconds.
            error: The exception raised by the wrapped client.
        """
        ...


class LoggingRequestObserver:
    """Observer that emits structured ``logging`` records for each event.

    Records are emitted under the ``iris.adapters.llm.observability``
    logger and carry an ``extra`` mapping that downstream log
    formatters can render as structured fields. The observer is the
    default for the runtime's LLM client factory.
    """

    def __init__(self, logger: logging.Logger | None = None) -> None:
        """Create a logging observer.

        Args:
            logger: Optional logger to emit records to. Defaults to
                the module-level ``iris.adapters.llm.observability``
                logger.
        """
        self._logger = logger or logging.getLogger(_LOGGER_NAME)

    def on_request_start(self, *, model: str) -> None:
        """Emit a debug record for the start of an LLM request.

        Args:
            model: The model name being called.
        """
        self._logger.debug("llm.request.start", extra={"model": model})

    def on_request_success(
        self,
        *,
        model: str,
        latency_ms: float,
        finish_reason: str,
    ) -> None:
        """Emit an info record for a successful LLM request.

        Args:
            model: The model name that was called.
            latency_ms: Elapsed time in milliseconds.
            finish_reason: Provider-reported finish reason.
        """
        self._logger.info(
            "llm.request.success",
            extra={
                "model": model,
                "latency_ms": latency_ms,
                "finish_reason": finish_reason,
            },
        )

    def on_request_error(
        self,
        *,
        model: str,
        latency_ms: float,
        error: BaseException,
    ) -> None:
        """Emit a warning record for a failed LLM request.

        Args:
            model: The model name that was called.
            latency_ms: Elapsed time in milliseconds.
            error: The exception raised by the wrapped client.
        """
        self._logger.warning(
            "llm.request.error",
            extra={
                "model": model,
                "latency_ms": latency_ms,
                "error_type": type(error).__name__,
                "error_message": str(error),
            },
        )


class ObservableLLMClient:
    """Wrapper around an :class:`LLMClient` that reports request lifecycle events.

    The wrapper delegates to the wrapped client and times the call
    with ``time.perf_counter``. It invokes the observer's start hook
    before delegation, then either success or error depending on the
    outcome. Errors are re-raised unchanged so the wrapper is
    transparent to callers.
    """

    def __init__(self, client: LLMClient, observer: LLMRequestObserver) -> None:
        """Create an observable client.

        Args:
            client: The underlying LLM client to wrap.
            observer: The observer to notify on each request.
        """
        self._client = client
        self._observer = observer

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate a response and report timing and outcome to the observer.

        Args:
            request: Provider-neutral LLM request.

        Returns:
            Provider-neutral LLM response returned by the wrapped client.
        """
        model = request.model
        self._observer.on_request_start(model=model)
        started = time.perf_counter()
        try:
            response = await self._client.generate(request)
        except BaseException as exc:
            latency_ms = (time.perf_counter() - started) * 1000.0
            self._observer.on_request_error(
                model=model,
                latency_ms=latency_ms,
                error=exc,
            )
            raise
        latency_ms = (time.perf_counter() - started) * 1000.0
        self._observer.on_request_success(
            model=model,
            latency_ms=latency_ms,
            finish_reason=response.finish_reason,
        )
        return response
