"""LLM request observability wrapper and logging observer tests."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.llm.lifecycle import (
    ModelLoadState,
)
from iris.adapters.llm.observability import (
    LoggingRequestObserver,
    ObservableLLMClient,
)
from iris.adapters.llm.ports import LLMMessage, LLMRequest, LLMResponse, LLMRole
from tests.helpers.approx import approx
from tests.helpers.exact_eq import assert_exact_eq
from tests.helpers.private_access import get_private_attr_as

if TYPE_CHECKING:
    from collections.abc import Sequence


class _RecordingObserver:
    """Test observer that records every lifecycle event it receives."""

    def __init__(self) -> None:
        self.started: list[tuple[str, ModelLoadState]] = []
        self.successes: list[
            tuple[str, float, str, ModelLoadState, float | None, float | None]
        ] = []
        self.errors: list[
            tuple[str, float, BaseException, ModelLoadState, float | None, float | None]
        ] = []

    def on_request_start(
        self,
        *,
        model: str,
        model_load_state: ModelLoadState = ModelLoadState.UNKNOWN,
    ) -> None:
        self.started.append((model, model_load_state))

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
        self.successes.append(
            (
                model,
                latency_ms,
                finish_reason,
                model_load_state,
                generation_latency_ms,
                cold_start_latency_ms,
            )
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
        self.errors.append(
            (
                model,
                latency_ms,
                error,
                model_load_state,
                generation_latency_ms,
                cold_start_latency_ms,
            )
        )


def _build_request(model: str = "test-model") -> LLMRequest:
    """Build a minimal LLM request for tests.

    Args:
        model: Model name to set on the request.

    Returns:
        A request with a single user message.
    """
    return LLMRequest(
        model=model,
        messages=(LLMMessage(role=LLMRole.USER, content="hello"),),
    )


def _assert_extra(record: logging.LogRecord, name: str) -> object:
    """Fetch a single ``extra`` attribute from a captured log record.

    Args:
        record: The log record to inspect.
        name: The extra attribute name to fetch.

    Returns:
        The value attached via ``extra=``.
    """
    value: object = getattr(record, name)
    return value


def test_observable_llm_client_satisfies_llm_client_protocol() -> None:
    """ObservableLLMClient は LLMClient Protocol の構造を満たす。"""
    client = ObservableLLMClient(FakeLLMClient(), _RecordingObserver())

    generate = getattr(client, "generate", None)
    assert callable(generate)


@pytest.mark.anyio
async def test_observable_llm_client_reports_start_and_success() -> None:
    """成功時に start → success の順でフックが呼ばれる。"""
    observer = _RecordingObserver()
    client = ObservableLLMClient(
        FakeLLMClient(responses=("ok",)),
        observer,
    )

    response = await client.generate(_build_request("model-a"))

    assert response.text == "ok"
    assert observer.started == [("model-a", ModelLoadState.UNKNOWN)]
    assert len(observer.successes) == 1
    success = observer.successes[0]
    assert success[0] == "model-a"
    assert success[1] >= 0.0
    assert success[2] == "stop"
    assert observer.errors == []


@pytest.mark.anyio
async def test_observable_llm_client_reports_error_and_reraises() -> None:
    """失敗時に start → error の順でフックが呼ばれ例外は再送出される。"""

    class _BoomError(Exception):
        pass

    class _ExplodingClient:
        async def generate(self, request: LLMRequest) -> LLMResponse:
            boom_message = f"kaboom for {request.model}"
            raise _BoomError(boom_message)

    observer = _RecordingObserver()
    client = ObservableLLMClient(_ExplodingClient(), observer)

    with pytest.raises(_BoomError, match="kaboom for model-b"):
        await client.generate(_build_request("model-b"))

    assert observer.started == [("model-b", ModelLoadState.UNKNOWN)]
    assert observer.successes == []
    assert len(observer.errors) == 1
    error = observer.errors[0]
    assert error[0] == "model-b"
    assert error[1] >= 0.0
    assert isinstance(error[2], _BoomError)


@pytest.mark.anyio
async def test_observable_llm_client_propagates_response_finish_reason() -> None:
    """Wrapped 応答の finish_reason が observer に伝わる。"""

    class _FixedFinishClient:
        async def generate(self, request: LLMRequest) -> LLMResponse:
            return LLMResponse(text="hi", model=request.model, finish_reason="length")

    observer = _RecordingObserver()
    client = ObservableLLMClient(_FixedFinishClient(), observer)

    await client.generate(_build_request("model-c"))

    assert observer.successes[0][2] == "length"


def test_logging_observer_emits_debug_on_start(caplog: pytest.LogCaptureFixture) -> None:
    """LoggingRequestObserver は start イベントを DEBUG で出力する。"""
    observer = LoggingRequestObserver()
    with caplog.at_level(logging.DEBUG, logger="iris.adapters.llm.observability"):
        observer.on_request_start(model="m")
    start_records = [record for record in caplog.records if record.message == "llm.request.start"]
    assert len(start_records) == 1
    assert_exact_eq(_assert_extra(start_records[0], "model"), "m")
    assert_exact_eq(_assert_extra(start_records[0], "model_load_state"), "unknown")


def test_logging_observer_emits_info_on_success(caplog: pytest.LogCaptureFixture) -> None:
    """LoggingRequestObserver は success イベントを INFO で出力する。"""
    observer = LoggingRequestObserver()
    with caplog.at_level(logging.INFO, logger="iris.adapters.llm.observability"):
        observer.on_request_success(model="m", latency_ms=12.5, finish_reason="stop")
    success_records = [
        record for record in caplog.records if record.message == "llm.request.success"
    ]
    assert len(success_records) == 1
    record = success_records[0]
    assert record.levelno == logging.INFO
    assert_exact_eq(_assert_extra(record, "model"), "m")
    assert _assert_extra(record, "latency_ms") == approx(12.5)
    assert_exact_eq(_assert_extra(record, "finish_reason"), "stop")
    assert_exact_eq(_assert_extra(record, "model_load_state"), "unknown")


def test_logging_observer_emits_warning_on_error(caplog: pytest.LogCaptureFixture) -> None:
    """LoggingRequestObserver は error イベントを WARNING で出力する。"""
    observer = LoggingRequestObserver()
    with caplog.at_level(logging.WARNING, logger="iris.adapters.llm.observability"):
        observer.on_request_error(
            model="m",
            latency_ms=42.0,
            error=RuntimeError("boom"),
        )
    error_records = [record for record in caplog.records if record.message == "llm.request.error"]
    assert len(error_records) == 1
    record = error_records[0]
    assert record.levelno == logging.WARNING
    assert_exact_eq(_assert_extra(record, "model"), "m")
    assert _assert_extra(record, "latency_ms") == approx(42.0)
    assert_exact_eq(_assert_extra(record, "error_type"), "RuntimeError")
    assert_exact_eq(_assert_extra(record, "error_message"), "boom")
    assert_exact_eq(_assert_extra(record, "model_load_state"), "unknown")


def test_logging_observer_uses_provided_logger() -> None:
    """LoggingRequestObserver は注入ロガーを使う。"""
    custom = logging.getLogger("test.custom.logger")
    observer = LoggingRequestObserver(logger=custom)
    stored: object = get_private_attr_as(observer, "_logger", logging.Logger)
    assert stored is custom


def test_logging_observer_defaults_to_module_logger() -> None:
    """LoggingRequestObserver はデフォルトでモジュールロガーを使う。"""
    observer = LoggingRequestObserver()
    stored_object: object = get_private_attr_as(observer, "_logger", logging.Logger)
    assert isinstance(stored_object, logging.Logger)
    logger_typed: logging.Logger = stored_object
    assert logger_typed.name == "iris.adapters.llm.observability"


@pytest.mark.anyio
async def test_observable_llm_client_with_logging_observer(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """エンドツーエンド: LoggingRequestObserver と FakeLLMClient の組み合わせでログが出る。"""
    observer = LoggingRequestObserver()
    client = ObservableLLMClient(FakeLLMClient(responses=("hi",)), observer)

    with caplog.at_level(logging.DEBUG, logger="iris.adapters.llm.observability"):
        await client.generate(_build_request("end-to-end"))

    messages: Sequence[str] = [record.message for record in caplog.records]
    assert "llm.request.start" in messages
    assert "llm.request.success" in messages
