"""LLM 起動時診断のファクトリ・ランナーテスト。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import pytest

from iris.adapters.llm.diagnostics import (
    LLMProviderDiagnostics,
    ProviderCapability,
    ProviderReadinessResult,
    ReadinessStatus,
)
from iris.adapters.llm.ollama_diagnostics import OllamaDiagnostics
from iris.adapters.llm.openai_diagnostics import OpenAIDiagnostics
from iris.runtime.config import (
    ConfigError,
    IrisRuntimeConfig,
    RuntimeDiagnosticsConfig,
    RuntimeModelConfig,
    default_runtime_config,
)
from iris.runtime.observability.diagnostics import (
    DiagnosticsCheckOutcome,
    StartupDiagnosticsReport,
    run_startup_diagnostics,
)
from iris.runtime.wiring.llm import build_provider_diagnostics
from tests.helpers.immutability import assert_frozen_field
from tests.helpers.private_access import get_private_attr_path_as

if TYPE_CHECKING:
    from iris.runtime.config.llm import LLMProvider, ModelSlotName


@dataclass(frozen=True)
class _OutcomeSpec:
    """スタブ診断が返す readiness / warmup のステータス指定。"""

    readiness: ReadinessStatus
    warmup: ReadinessStatus | None = None


class _StubDiagnostics:
    """runner のテスト用スタブ LLMProviderDiagnostics。

    Protocol の ``provider`` / ``capabilities`` 要件は instance attribute
    として満たす。 property だと Protocol の invariance 検査で拒否される
    ため、 ``__init__`` で通常フィールドとして設定する。
    """

    def __init__(
        self,
        provider_name: str,
        capability: ProviderCapability,
        outcome: _OutcomeSpec,
    ) -> None:
        """スタブ診断を初期化する。

        Args:
            provider_name: ``provider`` 属性として公開する名前。
            capability: ``capabilities`` 属性として公開する capability。
            outcome: readiness / warmup の戻り値スペック。
        """
        self.provider = provider_name
        self.capabilities = capability
        self.outcome = outcome
        self.check_readiness_calls = 0
        self.warmup_calls = 0

    async def check_readiness(self, model: str) -> ProviderReadinessResult:
        """Return a canned readiness result and increment the call counter.

        Args:
            model: Model name being probed.

        Returns:
            Configured readiness result.
        """
        self.check_readiness_calls += 1
        return ProviderReadinessResult(
            provider=self.provider,
            model=model,
            status=self.outcome.readiness,
            capabilities=self.capabilities,
            issues=(),
        )

    async def warmup(self, model: str) -> ProviderReadinessResult:
        """Return a canned warmup result and increment the call counter.

        Args:
            model: Model name being warmed up.

        Returns:
            Configured warmup result.
        """
        self.warmup_calls += 1
        assert self.outcome.warmup is not None
        return ProviderReadinessResult(
            provider=self.provider,
            model=model,
            status=self.outcome.warmup,
            capabilities=self.capabilities,
            issues=(),
        )


# ---------------------------------------------------------------------------
# ファクトリ
# ---------------------------------------------------------------------------


def test_build_provider_diagnostics_returns_none_for_fake() -> None:
    """Fake プロバイダは診断対象外として None を返す。"""
    config = default_runtime_config()
    model_config = config.models.default_chat  # provider="fake"

    result = build_provider_diagnostics(model_config, config)

    assert result is None


def test_build_provider_diagnostics_returns_ollama_diagnostics() -> None:
    """Ollama プロバイダは OllamaDiagnostics を組み立てる。"""
    config = _set_default_slot(default_runtime_config(), provider="ollama", model="qwen3:8b")

    result = build_provider_diagnostics(config.models.default_chat, config)

    assert isinstance(result, OllamaDiagnostics)


def test_build_provider_diagnostics_returns_openai_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Openai プロバイダは OpenAIDiagnostics を組み立てる。"""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    config = _set_default_slot(
        default_runtime_config(),
        provider="openai",
        model="gpt-test",
    )

    result = build_provider_diagnostics(config.models.default_chat, config)

    assert isinstance(result, OpenAIDiagnostics)
    assert get_private_attr_path_as(result, ("_config", "model"), str) == "gpt-test"


def test_build_provider_diagnostics_raises_for_unknown_provider() -> None:
    """未知のプロバイダは ConfigError を送出する。"""
    config = default_runtime_config()
    model_config = RuntimeModelConfig(provider="fake", model="x")
    model_config.__dict__["provider"] = "unknown"

    with pytest.raises(ConfigError, match="Unknown LLM provider for diagnostics"):
        build_provider_diagnostics(model_config, config)


def test_build_provider_diagnostics_openai_missing_api_key_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Openai は api_key 未設定 + 注入 client なしで ConfigError を送出。"""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = _set_default_slot(
        default_runtime_config(),
        provider="openai",
        model="gpt-test",
    )

    with pytest.raises(ConfigError, match="Failed to build openai"):
        build_provider_diagnostics(config.models.default_chat, config)


# ---------------------------------------------------------------------------
# ランナー
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_run_startup_diagnostics_returns_empty_when_disabled() -> None:
    """diagnostics.enabled=False のときは空レポートを返す。"""
    config = _with_diagnostics(default_runtime_config(), enabled=False)

    report = await run_startup_diagnostics(config)

    assert report.enabled is False
    assert report.outcomes == ()
    assert report.checked_count == 0
    assert report.has_failures is False
    assert report.all_ok is False


@pytest.mark.anyio
async def test_run_startup_diagnostics_skips_fake_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fake プロバイダのスロットはスキップされる。"""
    config = default_runtime_config()  # 全 fake
    _install_factory(monkeypatch, _passthrough_factory())

    report = await run_startup_diagnostics(config)

    assert report.enabled is True
    assert report.outcomes == ()


@pytest.mark.anyio
async def test_run_startup_diagnostics_probes_each_non_fake_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """non-fake スロットはそれぞれ probe され outcome に集約される。"""
    config = _with_providers(
        default_runtime_config(),
        default_chat=("ollama", "qwen3:8b"),
        fast_judge=("ollama", "fast-model"),
        reasoning=("fake", "fake-llm"),
    )
    default_stub = _ok_stub("ollama")
    fast_stub = _ok_stub("ollama")
    _install_factory(
        monkeypatch,
        _slot_stub_factory(
            {
                "default_chat": default_stub,
                "fast_judge": fast_stub,
            },
        ),
    )

    report = await run_startup_diagnostics(config)

    assert report.checked_count == 2
    assert default_stub.check_readiness_calls == 1
    assert fast_stub.check_readiness_calls == 1
    slots = {outcome.slot for outcome in report.outcomes}
    assert slots == {"default_chat", "fast_judge"}


@pytest.mark.anyio
async def test_run_startup_diagnostics_calls_warmup_when_enabled_and_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warmup_models=True かつ capability.warmup=True のときのみ warmup を呼ぶ。"""
    config = _with_providers(
        default_runtime_config(),
        default_chat=("ollama", "qwen3:8b"),
        fast_judge=("fake", "fake-llm"),
        reasoning=("fake", "fake-llm"),
    )
    config = _with_diagnostics(config, warmup_models=True)
    ollama_capability = ProviderCapability(
        health_check=True,
        model_availability_check=True,
        model_loaded_check=True,
        warmup=True,
    )
    default_stub = _StubDiagnostics(
        provider_name="ollama",
        capability=ollama_capability,
        outcome=_OutcomeSpec(
            readiness=ReadinessStatus.OK,
            warmup=ReadinessStatus.OK,
        ),
    )
    _install_factory(
        monkeypatch,
        _slot_stub_factory({"default_chat": default_stub}),
    )

    report = await run_startup_diagnostics(config)

    assert default_stub.warmup_calls == 1
    assert report.outcomes[0].warmup is not None
    assert report.outcomes[0].warmup.status is ReadinessStatus.OK


@pytest.mark.anyio
async def test_run_startup_diagnostics_skips_warmup_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warmup_models=False のとき warmup は呼ばれない。"""
    config = _with_providers(
        default_runtime_config(),
        default_chat=("ollama", "qwen3:8b"),
        fast_judge=("fake", "fake-llm"),
        reasoning=("fake", "fake-llm"),
    )
    config = _with_diagnostics(config, warmup_models=False)
    ollama_capability = ProviderCapability(
        health_check=True,
        model_availability_check=True,
        model_loaded_check=True,
        warmup=True,
    )
    default_stub = _StubDiagnostics(
        provider_name="ollama",
        capability=ollama_capability,
        outcome=_OutcomeSpec(
            readiness=ReadinessStatus.OK,
            warmup=ReadinessStatus.OK,
        ),
    )
    _install_factory(
        monkeypatch,
        _slot_stub_factory({"default_chat": default_stub}),
    )

    report = await run_startup_diagnostics(config)

    assert default_stub.warmup_calls == 0
    assert report.outcomes[0].warmup is None


@pytest.mark.anyio
async def test_run_startup_diagnostics_skips_warmup_when_capability_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """capability.warmup=False のときは warmup を呼ばない。"""
    config = _with_providers(
        default_runtime_config(),
        default_chat=("openai", "gpt-test"),
        fast_judge=("fake", "fake-llm"),
        reasoning=("fake", "fake-llm"),
    )
    config = _with_diagnostics(config, warmup_models=True)
    openai_capability = ProviderCapability(
        health_check=True,
        model_availability_check=True,
        model_loaded_check=False,
        warmup=False,
    )
    default_stub = _StubDiagnostics(
        provider_name="openai",
        capability=openai_capability,
        outcome=_OutcomeSpec(readiness=ReadinessStatus.OK),
    )
    _install_factory(
        monkeypatch,
        _slot_stub_factory({"default_chat": default_stub}),
    )

    report = await run_startup_diagnostics(config)

    assert default_stub.warmup_calls == 0
    assert report.outcomes[0].warmup is None


@pytest.mark.anyio
async def test_run_startup_diagnostics_captures_construction_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """build_provider_diagnostics の失敗は FAIL outcome として記録される。"""
    config = _with_providers(
        default_runtime_config(),
        default_chat=("openai", "gpt-test"),
        fast_judge=("ollama", "fast-model"),
        reasoning=("fake", "fake-llm"),
    )
    fast_stub = _ok_stub("ollama")
    _install_factory(
        monkeypatch,
        _factory_with_error(
            ConfigError("openai boom"),
            ollama_fallback=fast_stub,
        ),
    )

    report = await run_startup_diagnostics(config)

    assert report.checked_count == 2
    default_outcome = next(o for o in report.outcomes if o.slot == "default_chat")
    fast_outcome = next(o for o in report.outcomes if o.slot == "fast_judge")
    assert default_outcome.readiness.status is ReadinessStatus.FAIL
    assert default_outcome.readiness.issues[0].code == "diagnostics_build_failed"
    assert fast_outcome.readiness.status is ReadinessStatus.OK


# ---------------------------------------------------------------------------
# レポート
# ---------------------------------------------------------------------------


def test_report_has_failures_when_any_outcome_fails() -> None:
    """FAIL outcome を含むと has_failures=True / all_ok=False。"""
    report = StartupDiagnosticsReport(
        outcomes=(
            DiagnosticsCheckOutcome(
                slot="default_chat",
                provider="ollama",
                model="qwen3:8b",
                readiness=ProviderReadinessResult(
                    provider="ollama",
                    model="qwen3:8b",
                    status=ReadinessStatus.FAIL,
                    capabilities=ProviderCapability(),
                    issues=(),
                ),
            ),
        ),
    )
    assert report.has_failures is True
    assert report.all_ok is False


def test_report_all_ok_when_all_outcomes_ok() -> None:
    """全 outcome が OK なら all_ok=True。"""
    report = StartupDiagnosticsReport(
        outcomes=(
            DiagnosticsCheckOutcome(
                slot="default_chat",
                provider="ollama",
                model="qwen3:8b",
                readiness=ProviderReadinessResult(
                    provider="ollama",
                    model="qwen3:8b",
                    status=ReadinessStatus.OK,
                    capabilities=ProviderCapability(),
                ),
            ),
        ),
    )
    assert report.has_failures is False
    assert report.all_ok is True


def test_report_all_ok_false_when_empty() -> None:
    """Outcomes が空のときは all_ok=False (何もチェックしていない)。"""
    report = StartupDiagnosticsReport()
    assert report.all_ok is False
    assert report.has_failures is False


def test_outcome_is_frozen() -> None:
    """DiagnosticsCheckOutcome は frozen。"""
    outcome = DiagnosticsCheckOutcome(
        slot="default_chat",
        provider="ollama",
        model="qwen3:8b",
        readiness=ProviderReadinessResult(
            provider="ollama",
            model="qwen3:8b",
            status=ReadinessStatus.OK,
            capabilities=ProviderCapability(),
        ),
    )
    assert_frozen_field(outcome, "slot", "fast_judge")


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _ok_stub(provider_name: str) -> _StubDiagnostics:
    return _StubDiagnostics(
        provider_name=provider_name,
        capability=ProviderCapability(
            health_check=True,
            model_availability_check=True,
            model_loaded_check=True,
            warmup=True,
        ),
        outcome=_OutcomeSpec(
            readiness=ReadinessStatus.OK,
            warmup=ReadinessStatus.OK,
        ),
    )


def _set_default_slot(
    config: IrisRuntimeConfig,
    *,
    provider: LLMProvider,
    model: str,
) -> IrisRuntimeConfig:
    return replace(
        config,
        models=replace(
            config.models,
            default_chat=RuntimeModelConfig(provider=provider, model=model),
        ),
    )


def _with_diagnostics(
    config: IrisRuntimeConfig,
    *,
    enabled: bool = True,
    warmup_models: bool = False,
) -> IrisRuntimeConfig:
    new_diag = RuntimeDiagnosticsConfig(
        enabled=enabled,
        warmup_models=warmup_models,
    )
    return replace(config, diagnostics=new_diag)


def _with_providers(
    config: IrisRuntimeConfig,
    *,
    default_chat: tuple[LLMProvider, str],
    fast_judge: tuple[LLMProvider, str],
    reasoning: tuple[LLMProvider, str],
) -> IrisRuntimeConfig:
    return replace(
        config,
        models=replace(
            config.models,
            default_chat=RuntimeModelConfig(provider=default_chat[0], model=default_chat[1]),
            fast_judge=RuntimeModelConfig(provider=fast_judge[0], model=fast_judge[1]),
            reasoning=RuntimeModelConfig(provider=reasoning[0], model=reasoning[1]),
        ),
    )


def _install_factory(
    monkeypatch: pytest.MonkeyPatch,
    factory: object,
) -> None:
    monkeypatch.setattr(
        "iris.runtime.observability.diagnostics.build_provider_diagnostics",
        factory,
    )


def _passthrough_factory() -> object:
    """Pass-through factory that calls the real build_provider_diagnostics.

    Returns:
        Factory closure delegating to the real factory.
    """

    def factory(
        model_config: RuntimeModelConfig,
        runtime_config: IrisRuntimeConfig,
    ) -> LLMProviderDiagnostics | None:
        return build_provider_diagnostics(model_config, runtime_config)

    return factory


def _slot_stub_factory(stubs: dict[ModelSlotName, _StubDiagnostics]) -> object:
    """Build a factory that returns the configured stub per slot.

    Args:
        stubs: Mapping from slot name to the stub to return for that slot.

    Returns:
        Factory closure that returns the configured stub per slot, or
        ``None`` for slots not in the mapping.
    """

    def factory(
        model_config: RuntimeModelConfig,
        runtime_config: IrisRuntimeConfig,
    ) -> LLMProviderDiagnostics | None:
        if model_config is runtime_config.models.default_chat:
            return stubs.get("default_chat")
        if model_config is runtime_config.models.fast_judge:
            return stubs.get("fast_judge")
        if model_config is runtime_config.models.reasoning:
            return stubs.get("reasoning")
        return None

    return factory


def _factory_with_error(
    exc: BaseException,
    *,
    ollama_fallback: _StubDiagnostics | None = None,
) -> object:
    """Build a factory that raises for openai and delegates to fallback otherwise.

    Args:
        exc: Exception to raise for openai provider.
        ollama_fallback: Optional stub to return for non-fake, non-openai slots.

    Returns:
        Factory closure with the openai-error semantics.
    """

    def factory(
        model_config: RuntimeModelConfig,
        _runtime_config: IrisRuntimeConfig,
    ) -> LLMProviderDiagnostics | None:
        if model_config.provider == "openai":
            raise exc
        if model_config.provider == "fake":
            return None
        return ollama_fallback

    return factory
