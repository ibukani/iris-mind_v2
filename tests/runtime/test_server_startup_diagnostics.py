"""Runtime server startup diagnostics wiring tests."""

from __future__ import annotations

import asyncio
from dataclasses import replace
import inspect
from types import SimpleNamespace
from typing import TYPE_CHECKING, Protocol
from unittest.mock import AsyncMock

from loguru import logger
import pytest

from iris.adapters.llm.diagnostics import (
    ProviderCapability,
    ProviderDiagnosticIssue,
    ProviderReadinessResult,
    ReadinessStatus,
)
from iris.runtime.config import (
    ConfigError,
    DiagnosticsMode,
    IrisRuntimeConfig,
    RuntimeDiagnosticsConfig,
    RuntimeModelConfig,
    RuntimeModelsConfig,
    default_runtime_config,
)
from iris.runtime.observability.diagnostics import (
    StartupDiagnosticsReport,
    run_startup_diagnostics,
)
from iris.runtime.server import serve

if TYPE_CHECKING:
    from collections.abc import Iterator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _with_diagnostics(
    config: IrisRuntimeConfig,
    *,
    mode: DiagnosticsMode = "warn",
    warmup_models: bool = False,
) -> IrisRuntimeConfig:
    """Return a copy of ``config`` with the given diagnostics config.

    Args:
        config: Base runtime config.
        mode: Diagnostics mode (``off``/``warn``/``strict``).
        warmup_models: Whether warmup should run.

    Returns:
        Updated runtime config.
    """
    new_diag = RuntimeDiagnosticsConfig(
        mode=mode,
        warmup_models=warmup_models,
    )
    return replace(config, diagnostics=new_diag)


def _with_ollama_slots(
    config: IrisRuntimeConfig,
    *,
    model: str = "qwen3:8b",
) -> IrisRuntimeConfig:
    """Replace all model slots with a single Ollama configuration.

    Args:
        config: Base runtime config.
        model: Ollama model name to use for every slot.

    Returns:
        Updated runtime config.
    """
    new_models = RuntimeModelsConfig(
        default_chat=RuntimeModelConfig(provider="ollama", model=model),
        fast_judge=RuntimeModelConfig(provider="ollama", model=model),
        reasoning=RuntimeModelConfig(provider="ollama", model=model),
    )
    return replace(config, models=new_models)


class _StubProviderDiagnostics:
    """Stub LLMProviderDiagnostics that returns canned results.

    The stub implements the LLMProviderDiagnostics Protocol by exposing
    ``provider`` / ``capabilities`` as instance attributes.
    """

    def __init__(
        self,
        *,
        provider: str,
        status: ReadinessStatus,
        issue_code: str | None = None,
    ) -> None:
        """Initialize the stub.

        Args:
            provider: Provider name.
            status: Aggregate readiness status to return.
            issue_code: Optional single issue code to attach to the
                readiness result.
        """
        self.provider = provider
        self.capabilities = ProviderCapability(
            health_check=True,
            model_availability_check=True,
            model_loaded_check=True,
            warmup=True,
        )
        self._status = status
        self._issue_code = issue_code
        self.check_readiness_calls = 0
        self.warmup_calls = 0

    async def check_readiness(self, model: str) -> ProviderReadinessResult:
        """Return a canned readiness result.

        Args:
            model: Model name being probed.

        Returns:
            Stub readiness result.
        """
        self.check_readiness_calls += 1
        issues: tuple[ProviderDiagnosticIssue, ...] = ()
        if self._issue_code is not None:
            issues = (
                ProviderDiagnosticIssue(
                    code=self._issue_code,
                    message=f"synthetic issue: {self._issue_code}",
                    severity=ReadinessStatus.FAIL,
                ),
            )
        return ProviderReadinessResult(
            provider=self.provider,
            model=model,
            status=self._status,
            capabilities=self.capabilities,
            issues=issues,
        )

    async def warmup(self, model: str) -> ProviderReadinessResult:
        """Return a canned warmup result.

        Args:
            model: Model name being warmed up.

        Returns:
            Stub warmup result.
        """
        self.warmup_calls += 1
        return ProviderReadinessResult(
            provider=self.provider,
            model=model,
            status=ReadinessStatus.OK,
            capabilities=self.capabilities,
        )


class _StubFactory(Protocol):
    """Callable factory used in place of ``build_provider_diagnostics``."""

    def __call__(
        self,
        model_config: object,
        runtime_config: IrisRuntimeConfig,
    ) -> object: ...


def _stub_factory(
    *,
    status: ReadinessStatus = ReadinessStatus.OK,
    issue_code: str | None = None,
) -> _StubFactory:
    """Return a factory closure that produces stub diagnostics.

    Args:
        status: Aggregate status to emit for every probed slot.
        issue_code: Optional issue code to attach to readiness results.

    Returns:
        Factory closure.
    """

    def factory(
        model_config: object,
        runtime_config: IrisRuntimeConfig,
    ) -> object:
        _ = runtime_config
        provider_value = getattr(model_config, "provider", None)
        if provider_value == "fake":
            return None
        return _StubProviderDiagnostics(
            provider=str(provider_value),
            status=status,
            issue_code=issue_code,
        )

    return factory


# ---------------------------------------------------------------------------
# serve() wiring
# ---------------------------------------------------------------------------


def test_serve_invokes_run_startup_diagnostics_before_components(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """serve() must call run_startup_diagnostics() before building components."""
    config = _with_ollama_slots(_with_diagnostics(default_runtime_config(), mode="warn"))
    call_order: list[str] = []

    async def fake_runner(_: IrisRuntimeConfig) -> StartupDiagnosticsReport:
        call_order.append("diagnostics")
        await asyncio.sleep(0)
        return StartupDiagnosticsReport(outcomes=(), enabled=True)

    def fake_build_components(_: IrisRuntimeConfig) -> object:
        call_order.append("components")
        return SimpleNamespace(
            runtime_service=SimpleNamespace(),
            identity_resolver=SimpleNamespace(),
            space_resolver=SimpleNamespace(),
        )

    def fake_create_grpc_server(*_args: object, **_kwargs: object) -> object:
        call_order.append("grpc")
        server = AsyncMock()
        server.start = AsyncMock()

        async def _wait() -> None:
            await asyncio.sleep(0)
            raise asyncio.CancelledError

        server.wait_for_termination = AsyncMock(side_effect=_wait)
        server.stop = AsyncMock()
        return server

    def fake_load_runtime_config(
        _path: object | None = None,
        *,
        env: object | None = None,
        overrides: object | None = None,
        cwd: object | None = None,
    ) -> IrisRuntimeConfig:
        _ = (env, overrides, cwd)
        return config

    def fake_resolve_runtime_config_path(
        _path: object | None = None,
        *,
        env: object | None = None,
        cwd: object | None = None,
    ) -> None:
        _ = (_path, env, cwd)

    def fake_configure_runtime_logging(_config: IrisRuntimeConfig) -> None:
        _ = _config

    monkeypatch.setattr("iris.runtime.server.load_runtime_config", fake_load_runtime_config)
    monkeypatch.setattr(
        "iris.runtime.server.resolve_runtime_config_path",
        fake_resolve_runtime_config_path,
    )
    monkeypatch.setattr(
        "iris.runtime.server.configure_runtime_logging",
        fake_configure_runtime_logging,
    )
    monkeypatch.setattr("iris.runtime.server.run_startup_diagnostics", fake_runner)
    monkeypatch.setattr("iris.runtime.server.build_runtime_components", fake_build_components)
    monkeypatch.setattr("iris.runtime.server.create_grpc_server", fake_create_grpc_server)

    asyncio.run(serve())

    assert call_order == ["diagnostics", "components", "grpc"]


# ---------------------------------------------------------------------------
# fail_fast behavior
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_run_startup_diagnostics_continues_when_fail_fast_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``mode="warn"`` should not raise even if every outcome fails."""
    config = _with_ollama_slots(_with_diagnostics(default_runtime_config(), mode="warn"))
    monkeypatch.setattr(
        "iris.runtime.observability.diagnostics.build_provider_diagnostics",
        _stub_factory(status=ReadinessStatus.FAIL, issue_code="daemon_unreachable"),
    )

    report = await run_startup_diagnostics(config)

    assert report.has_failures is True
    assert all(outcome.readiness.status is ReadinessStatus.FAIL for outcome in report.outcomes)


@pytest.mark.anyio
async def test_run_startup_diagnostics_aborts_when_fail_fast_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``mode="strict"`` should raise ``ConfigError`` on any FAIL outcome."""
    config = _with_ollama_slots(_with_diagnostics(default_runtime_config(), mode="strict"))
    monkeypatch.setattr(
        "iris.runtime.observability.diagnostics.build_provider_diagnostics",
        _stub_factory(status=ReadinessStatus.FAIL, issue_code="daemon_unreachable"),
    )

    with pytest.raises(ConfigError, match="startup diagnostics failed"):
        await run_startup_diagnostics(config)


# ---------------------------------------------------------------------------
# log_issues_as_warnings behavior
# ---------------------------------------------------------------------------


@pytest.fixture
def captured_logs() -> Iterator[list[str]]:
    """Capture loguru records emitted during the test.

    Yields:
        A list of formatted loguru record messages.
    """
    captured: list[str] = []

    def _sink(message: object) -> None:
        captured.append(str(message).rstrip("\n"))

    handler_id: int = logger.add(_sink, level="DEBUG", format="{message}")
    try:
        yield captured
    finally:
        logger.remove(handler_id)


@pytest.mark.anyio
async def test_warn_mode_emits_issue_warnings(
    monkeypatch: pytest.MonkeyPatch,
    captured_logs: list[str],
) -> None:
    """``mode="warn"`` emits one ``startup.diagnostics.issue`` warning per issue."""
    config = _with_ollama_slots(
        _with_diagnostics(
            default_runtime_config(),
            mode="warn",
        )
    )
    monkeypatch.setattr(
        "iris.runtime.observability.diagnostics.build_provider_diagnostics",
        _stub_factory(status=ReadinessStatus.FAIL, issue_code="daemon_unreachable"),
    )

    await run_startup_diagnostics(config)

    issue_records = [record for record in captured_logs if record == "startup.diagnostics.issue"]
    assert len(issue_records) >= 1


@pytest.mark.anyio
async def test_warn_mode_does_not_raise_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``mode="warn"`` returns a report even when every outcome fails."""
    config = _with_ollama_slots(_with_diagnostics(default_runtime_config(), mode="warn"))
    monkeypatch.setattr(
        "iris.runtime.observability.diagnostics.build_provider_diagnostics",
        _stub_factory(status=ReadinessStatus.FAIL, issue_code="daemon_unreachable"),
    )

    report = await run_startup_diagnostics(config)

    assert report.has_failures is True


# ---------------------------------------------------------------------------
# disabled skip
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_off_mode_skips_external_checks() -> None:
    """``mode="off"`` returns an empty report and does not call factory."""
    config = _with_ollama_slots(_with_diagnostics(default_runtime_config(), mode="off"))

    report = await run_startup_diagnostics(config)

    assert report.enabled is False
    assert report.outcomes == ()


# ---------------------------------------------------------------------------
# serve() signature
# ---------------------------------------------------------------------------


def test_serve_signature_is_async() -> None:
    """serve() must be an async coroutine function."""
    assert inspect.iscoroutinefunction(serve)
