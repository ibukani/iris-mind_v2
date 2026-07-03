"""Issue #87 diagnostics model resolution regression tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from iris.adapters.llm.diagnostics import (
    ProviderCapability,
    ProviderReadinessResult,
    ReadinessStatus,
)
from iris.adapters.llm.lifecycle import ModelLoadState
from iris.runtime.config import IrisRuntimeConfig, RuntimeModelConfig, default_runtime_config
from iris.runtime.config.llm import LLMProvider
import iris.runtime.observability.diagnostics as diagnostics_module
from iris.runtime.observability.diagnostics import run_startup_diagnostics


class _ResolvedModelStubDiagnostics:
    """Stub diagnostics that records the model names passed by the runner."""

    provider = "ollama"
    capabilities = ProviderCapability(
        health_check=True,
        model_availability_check=True,
        model_loaded_check=True,
        warmup=True,
    )

    def __init__(self) -> None:
        """Initialize call recorders."""
        self.check_readiness_models: list[str] = []
        self.warmup_models: list[str] = []

    async def check_readiness(self, model: str) -> ProviderReadinessResult:
        """Record and return a successful readiness result."""
        self.check_readiness_models.append(model)
        return ProviderReadinessResult(
            provider=self.provider,
            model=model,
            status=ReadinessStatus.OK,
            capabilities=self.capabilities,
            model_load_state=ModelLoadState.WARM,
        )

    async def warmup(self, model: str) -> ProviderReadinessResult:
        """Record and return a successful warmup result."""
        self.warmup_models.append(model)
        return ProviderReadinessResult(
            provider=self.provider,
            model=model,
            status=ReadinessStatus.OK,
            capabilities=self.capabilities,
            model_load_state=ModelLoadState.WARM,
        )


def _ollama_sentinel_config() -> IrisRuntimeConfig:
    """Build config where an Ollama slot still carries the fake sentinel model."""
    config = default_runtime_config()
    return replace(
        config,
        models=replace(
            config.models,
            default_chat=RuntimeModelConfig(
                provider=LLMProvider.OLLAMA,
                model="fake-llm",
            ),
        ),
        diagnostics=replace(config.diagnostics, warmup_models=True),
    )


@pytest.mark.anyio
async def test_startup_diagnostics_probe_provider_resolved_ollama_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Diagnostics and warmup use the Ollama-resolved model name."""
    stub = _ResolvedModelStubDiagnostics()

    def _factory(
        model_config: RuntimeModelConfig,
        runtime_config: IrisRuntimeConfig,
    ) -> _ResolvedModelStubDiagnostics:
        return stub

    monkeypatch.setattr(diagnostics_module, "build_provider_diagnostics", _factory)

    report = await run_startup_diagnostics(_ollama_sentinel_config())

    assert stub.check_readiness_models == ["qwen3:8b"]
    assert stub.warmup_models == ["qwen3:8b"]
    outcome = report.outcomes[0]
    assert outcome.model == "qwen3:8b"
    assert outcome.readiness.model == "qwen3:8b"
    assert outcome.warmup is not None
    assert outcome.warmup.model == "qwen3:8b"
