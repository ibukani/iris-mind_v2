"""LLM クライアントのワイヤリングと応答生成器の実装。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from iris.adapters.llm.fake import FakeLLMClient
from iris.adapters.llm.observability import ObservableLLMClient
from iris.adapters.llm.ollama import OllamaConfig, OllamaLLMClient
from iris.adapters.llm.ollama_diagnostics import OllamaDiagnostics
from iris.adapters.llm.ollama_lifecycle import OllamaModelLifecycleProbe
from iris.adapters.llm.openai import OpenAIAdapterError, OpenAIConfig, OpenAILLMClient
from iris.adapters.llm.openai_diagnostics import OpenAIDiagnostics
from iris.adapters.llm.ports import LLMClient, LLMRequest
from iris.contracts.llm import DEFAULT_FAKE_LLM_MODEL
from iris.contracts.model_policy import (
    CascadeDecision,
    CascadeFallbackBehavior,
    CascadeResult,
    ModelCallDescriptor,
    ModelCallKind,
    ModelCallSite,
)
from iris.core.metadata import immutable_metadata
from iris.features.chat.definition import GeneratedResponse, ResponseGenerator, ResponsePrompt
from iris.runtime.config import ConfigError, IrisRuntimeConfig, RuntimeModelConfig
from iris.runtime.config.llm import LLMProvider
from iris.runtime.inference.models import (
    InferenceLeaseDecision,
    InferenceLeaseRequest,
    InferenceLeaseResult,
    InferenceSlotKind,
    model_call_site_priority,
)
from iris.runtime.inference.observability import inference_lease_log_fields
from iris.runtime.model_call_budget import ModelCallBudgetGate, current_model_call_site
from iris.runtime.observability.context import trace_counter_extra
from iris.runtime.observability.llm import RuntimeLLMRequestObserver
from iris.runtime.observability.logger import LoguruRuntimeLogger
from iris.runtime.prompting.assembler import RuntimePromptAssembler
from iris.runtime.prompting.observability import record_prompt_assembly_report

if TYPE_CHECKING:
    from iris.adapters.llm.diagnostics import LLMProviderDiagnostics
    from iris.adapters.llm.lifecycle import ModelLifecycleProbe
    from iris.runtime.config.model_call_budget import RuntimeModelCallBudgetConfig
    from iris.runtime.config.prompt_budget import RuntimePromptBudgetConfig
    from iris.runtime.inference.scheduler import LocalInferenceResourceScheduler
    from iris.runtime.observability.ports import RuntimeLatencyBudget, RuntimeLogger
    from iris.runtime.persona.prompt_builder import SystemPromptBuilder


_KNOWN_LLM_PROVIDERS: frozenset[LLMProvider] = frozenset(LLMProvider)
_DETERMINISTIC_BASELINE_TEXT = "受け取りました。必要なら、もう少し詳しく教えてください。"


@dataclass(frozen=True)
class LLMResponseGeneratorOptions:
    """LLMResponseGenerator の任意設定を束ねる。"""

    temperature: float = 0.0
    max_tokens: int | None = None
    prompt_assembler: RuntimePromptAssembler | None = None
    runtime_logger: RuntimeLogger | None = None
    inference_scheduler: LocalInferenceResourceScheduler | None = None


@dataclass(frozen=True)
class ResponseGeneratorWiringOptions:
    """wire_response_generator の任意設定を束ねる。"""

    model: str = DEFAULT_FAKE_LLM_MODEL
    temperature: float = 0.0
    max_tokens: int | None = None
    prompt_budget_config: RuntimePromptBudgetConfig | None = None
    runtime_logger: RuntimeLogger | None = None
    inference_scheduler: LocalInferenceResourceScheduler | None = None
    system_prompt_builder: SystemPromptBuilder | None = None


class LLMResponseGenerator(ResponseGenerator):
    """LLM クライアントをバックエンドとする ResponseGenerator。"""

    def __init__(
        self,
        client: LLMClient,
        model: str = DEFAULT_FAKE_LLM_MODEL,
        *,
        options: LLMResponseGeneratorOptions | None = None,
    ) -> None:
        """LLM バックエンドの応答生成器を作成する。

        Args:
            client: LLM クライアント。
            model: LLM プロバイダに渡すモデル名。
            options: prompt assembly / logging / scheduler を束ねた任意設定。
        """
        resolved_options = options or LLMResponseGeneratorOptions()
        self._client = client
        self._model = model
        self._temperature = resolved_options.temperature
        self._max_tokens = resolved_options.max_tokens
        self._prompt_assembler = resolved_options.prompt_assembler or RuntimePromptAssembler()
        self._logger = resolved_options.runtime_logger or LoguruRuntimeLogger()
        self._inference_scheduler = resolved_options.inference_scheduler

    @override
    async def generate_response(self, prompt: ResponsePrompt) -> GeneratedResponse:
        """プロンプトに対する応答テキストを生成する。

        Args:
            prompt: 応答生成プロンプト。

        Returns:
            生成された応答テキストとモデルメタデータ。
        """
        assembly = self._prompt_assembler.assemble(prompt)
        record_prompt_assembly_report(assembly.report, runtime_logger=self._logger)
        request = LLMRequest(
            model=self._model,
            messages=assembly.messages,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        inference_scheduler = self._inference_scheduler
        lease_result = await self._acquire_inference_lease()
        if lease_result is not None:
            self._logger.info(
                "runtime.inference.lease_decision",
                **inference_lease_log_fields(lease_result),
            )
            if not lease_result.acquired:
                return _inference_scheduler_fallback_response(
                    lease_result.decision,
                    lease_result.reason,
                    self._model,
                )
        try:
            response = await self._client.generate(request)
        finally:
            if (
                inference_scheduler is not None
                and lease_result is not None
                and lease_result.lease_id is not None
            ):
                await inference_scheduler.release(lease_result.lease_id)
        return GeneratedResponse(text=response.text, model=response.model)

    async def _acquire_inference_lease(self) -> InferenceLeaseResult | None:
        if self._inference_scheduler is None:
            return None
        call_site = current_model_call_site(ModelCallSite.USER_RESPONSE_HOT_PATH)
        return await self._inference_scheduler.acquire(
            InferenceLeaseRequest(
                slot_kind=InferenceSlotKind.LARGE_LLM,
                priority=model_call_site_priority(call_site),
                call_site=call_site,
                model_slot="default_chat",
                model_name=self._model,
                metadata=immutable_metadata(
                    {
                        "model_slot": "default_chat",
                        "model": self._model,
                        "call_kind": ModelCallKind.LARGE_LLM.value,
                        "call_site": call_site.value,
                    }
                ),
            )
        )


class BudgetedResponseGenerator(ResponseGenerator):
    """ResponseGenerator の前段で user-facing large LLM budget を固定する wrapper。

    classifier / embedding / reranker の budget は `ModelCallBudgetGate` contract に含まれるが、
    この wrapper は LLM response generation だけを担当する。後続 feature は各 adapter / worker
    の呼び出し境界で同じ gate を使う。
    """

    def __init__(
        self,
        generator: ResponseGenerator,
        gate: ModelCallBudgetGate,
        *,
        model_name: str,
        model_slot: str,
        default_call_site: ModelCallSite = ModelCallSite.USER_RESPONSE_HOT_PATH,
        runtime_logger: RuntimeLogger | None = None,
    ) -> None:
        """予算 gate と実体 generator を明示注入して初期化する。"""
        self._generator = generator
        self._gate = gate
        self._model_name = model_name
        self._model_slot = model_slot
        self._default_call_site = default_call_site
        self._logger = runtime_logger or LoguruRuntimeLogger()

    @override
    async def generate_response(self, prompt: ResponsePrompt) -> GeneratedResponse:
        """Budget gate が許可した場合だけ実体 generator を呼ぶ。

        Returns:
            GeneratedResponse: cascade result 付きの生成結果。
        """
        descriptor = self._descriptor()
        cascade_result = self._gate.check_and_record(descriptor)
        self._record_cascade_result(cascade_result, descriptor)
        if cascade_result.decision is not CascadeDecision.ACCEPT:
            return self._fallback_response(cascade_result)

        generated = await self._generator.generate_response(prompt)
        if generated.cascade_result is not None and not generated.cascade_result.accepted:
            return generated
        return GeneratedResponse(
            text=generated.text,
            model=generated.model,
            cascade_result=cascade_result,
        )

    def _descriptor(self) -> ModelCallDescriptor:
        call_site = current_model_call_site(self._default_call_site)
        return ModelCallDescriptor(
            call_kind=ModelCallKind.LARGE_LLM,
            call_site=call_site,
            model_slot=self._model_slot,
            model_name=self._model_name,
            metadata=immutable_metadata(
                {
                    "model_slot": self._model_slot,
                    "model": self._model_name,
                    "call_kind": ModelCallKind.LARGE_LLM.value,
                    "call_site": call_site.value,
                }
            ),
        )

    def _fallback_response(self, cascade_result: CascadeResult) -> GeneratedResponse:
        """Cascade fallback behavior を実際の user-facing 挙動へ写像する。

        `escalate` はこの wrapper では上位モデル配線を持たないため、暗黙に
        LLM を再呼び出しせず `defer` へ正規化する。

        Returns:
            GeneratedResponse: fallback 実行結果。
        """
        text = ""
        model = self._model_name
        result = cascade_result

        if cascade_result.decision is CascadeDecision.ESCALATE:
            result = _normalized_cascade_result(
                cascade_result,
                decision=CascadeDecision.DEFER,
                reason=f"{cascade_result.reason}; escalation target is not wired",
                fallback_behavior=CascadeFallbackBehavior.DEFER,
            )
        elif cascade_result.fallback_behavior is CascadeFallbackBehavior.DETERMINISTIC_BASELINE:
            text = _DETERMINISTIC_BASELINE_TEXT
            model = f"{self._model_name}:deterministic_baseline"
        elif cascade_result.fallback_behavior in {
            CascadeFallbackBehavior.DEFER,
            CascadeFallbackBehavior.ENQUEUE_BACKGROUND,
        }:
            result = _normalized_cascade_result(
                cascade_result,
                decision=CascadeDecision.DEFER,
                reason=f"{cascade_result.reason}; fallback deferred",
                fallback_behavior=cascade_result.fallback_behavior,
            )
        elif cascade_result.fallback_behavior is CascadeFallbackBehavior.REJECT:
            result = _normalized_cascade_result(
                cascade_result,
                decision=CascadeDecision.DENY,
                reason=f"{cascade_result.reason}; fallback rejected",
                fallback_behavior=CascadeFallbackBehavior.REJECT,
            )

        return GeneratedResponse(text=text, model=model, cascade_result=result)

    def _record_cascade_result(
        self,
        cascade_result: CascadeResult,
        descriptor: ModelCallDescriptor,
    ) -> None:
        fields = trace_counter_extra()
        fields.update(
            {
                "call_site": descriptor.call_site.value,
                "call_kind": descriptor.call_kind.value,
                "decision": cascade_result.decision.value,
                "reason": cascade_result.reason,
                "confidence": cascade_result.confidence,
                "fallback_behavior": _fallback_behavior_value(cascade_result),
                "model_slot": self._model_slot,
                "model": self._model_name,
            }
        )
        self._logger.info("runtime.model_call.cascade_result", **fields)


def _inference_scheduler_fallback_response(
    decision: InferenceLeaseDecision,
    reason: str,
    model_name: str,
) -> GeneratedResponse:
    fallback_behavior = _inference_fallback_behavior(decision)
    cascade_decision = _inference_cascade_decision(decision)
    text = ""
    model = model_name
    if fallback_behavior is CascadeFallbackBehavior.DETERMINISTIC_BASELINE:
        text = _DETERMINISTIC_BASELINE_TEXT
        model = f"{model_name}:inference_scheduler_baseline"
    return GeneratedResponse(
        text=text,
        model=model,
        cascade_result=CascadeResult(
            decision=cascade_decision,
            reason=f"local inference resource {decision.value}: {reason}",
            confidence=1.0,
            fallback_behavior=fallback_behavior,
            model_metadata=immutable_metadata(
                {
                    "call_kind": ModelCallKind.LARGE_LLM.value,
                    "scheduler_decision": decision.value,
                }
            ),
        ),
    )


def _inference_cascade_decision(decision: InferenceLeaseDecision) -> CascadeDecision:
    if decision is InferenceLeaseDecision.DEFER:
        return CascadeDecision.DEFER
    if decision is InferenceLeaseDecision.DENIED:
        return CascadeDecision.FALLBACK
    return CascadeDecision.DENY


def _inference_fallback_behavior(
    decision: InferenceLeaseDecision,
) -> CascadeFallbackBehavior | None:
    behavior_by_decision = {
        InferenceLeaseDecision.DEFER: CascadeFallbackBehavior.DEFER,
        InferenceLeaseDecision.DENIED: CascadeFallbackBehavior.DETERMINISTIC_BASELINE,
        InferenceLeaseDecision.CANCEL: CascadeFallbackBehavior.REJECT,
        InferenceLeaseDecision.NO_SEND: CascadeFallbackBehavior.NO_OP,
    }
    return behavior_by_decision.get(decision)


def wire_fake_llm_client(responses: tuple[str, ...] | None = None) -> FakeLLMClient:
    """決定論的なフェイク LLM クライアントを組み立てる。

    Args:
        responses: 任意の canned 応答文字列。

    Returns:
        FakeLLMClient インスタンス。
    """
    return FakeLLMClient(responses=responses)


def wire_response_generator(
    client: LLMClient | None = None,
    *,
    options: ResponseGeneratorWiringOptions | None = None,
) -> LLMResponseGenerator:
    """応答生成器を組み立てる。

    Args:
        client: 任意の LLM クライアント。省略時はフェイククライアントを使用。
        options: model / prompt budget / scheduler などの任意設定。

    Returns:
        LLMResponseGenerator インスタンス。
    """
    if client is None:
        client = wire_fake_llm_client()
    resolved_options = options or ResponseGeneratorWiringOptions()
    return LLMResponseGenerator(
        client,
        resolved_options.model,
        options=LLMResponseGeneratorOptions(
            temperature=resolved_options.temperature,
            max_tokens=resolved_options.max_tokens,
            prompt_assembler=RuntimePromptAssembler(
                resolved_options.prompt_budget_config,
                system_prompt_builder=resolved_options.system_prompt_builder,
            ),
            runtime_logger=resolved_options.runtime_logger,
            inference_scheduler=resolved_options.inference_scheduler,
        ),
    )


def wire_budgeted_response_generator(
    generator: ResponseGenerator,
    config: RuntimeModelCallBudgetConfig,
    *,
    model: str,
    model_slot: str,
) -> BudgetedResponseGenerator:
    """ResponseGenerator に model call budget gate を被せる。

    Returns:
        BudgetedResponseGenerator インスタンス。
    """
    return BudgetedResponseGenerator(
        generator,
        ModelCallBudgetGate(config),
        model_name=model,
        model_slot=model_slot,
    )


def _normalized_cascade_result(
    cascade_result: CascadeResult,
    *,
    decision: CascadeDecision,
    reason: str,
    fallback_behavior: CascadeFallbackBehavior | None,
) -> CascadeResult:
    return CascadeResult(
        decision=decision,
        reason=reason,
        confidence=cascade_result.confidence,
        fallback_behavior=fallback_behavior,
        model_metadata=cascade_result.model_metadata,
    )


def _fallback_behavior_value(cascade_result: CascadeResult) -> str | None:
    if cascade_result.fallback_behavior is None:
        return None
    return cascade_result.fallback_behavior.value


def wire_openai_llm_client(config: OpenAIConfig) -> LLMClient:
    """OpenAI LLM クライアントを組み立てる。

    Args:
        config: OpenAI 設定。

    Returns:
        OpenAILLMClient インスタンス。
    """
    return OpenAILLMClient(config)


def wire_ollama_llm_client(config: OllamaConfig) -> LLMClient:
    """Ollama LLM クライアントを組み立てる。

    Args:
        config: Ollama アダプタ設定。

    Returns:
        OllamaLLMClient インスタンス。
    """
    return OllamaLLMClient(config)


class LLMClientFactory:
    """プロバイダ固有の LLM クライアントを組み立てる明示的なランタイムファクトリ。"""

    def __init__(self) -> None:
        """既知の LLM provider 集合を共有参照する。"""
        self._known_providers = _KNOWN_LLM_PROVIDERS

    def create_client(
        self,
        model_config: RuntimeModelConfig,
        runtime_config: IrisRuntimeConfig,
    ) -> LLMClient:
        """ランタイムモデルスロット向けの LLM クライアントを生成する。

        Args:
            model_config: モデルスロット設定。
            runtime_config: ランタイム設定全体。

        Returns:
            プロバイダ中立な LLM クライアント。
        """
        provider = _require_known_provider(
            model_config.provider,
            "Unknown LLM provider",
            self._known_providers,
        )
        client = _build_llm_client(provider, model_config, runtime_config)
        return _wrap_with_observer(
            client,
            lifecycle_probe=_build_model_lifecycle_probe(
                provider,
                model_config,
                runtime_config,
            ),
            latency_budget=runtime_config.observability.latency_budget,
        )

    def resolve_model(
        self,
        model_config: RuntimeModelConfig,
        runtime_config: IrisRuntimeConfig,
    ) -> str:
        """プロバイダ中立な LLMRequest で送るモデル名を解決する。

        Args:
            model_config: モデルスロット設定。
            runtime_config: ランタイム設定全体。

        Returns:
            応答生成に渡すモデル名。
        """
        return resolve_provider_model(
            model_config,
            runtime_config,
            known_providers=self._known_providers,
        )


def resolve_provider_model(
    model_config: RuntimeModelConfig,
    runtime_config: IrisRuntimeConfig,
    *,
    known_providers: frozenset[LLMProvider] = _KNOWN_LLM_PROVIDERS,
) -> str:
    """Provider に実際に渡すモデル名を解決する。

    生成、startup diagnostics、runtime doctor、warmup が同じ provider-visible
    model 名を見るための単一解決点。

    Args:
        model_config: モデルスロット設定。
        runtime_config: ランタイム設定全体。
        known_providers: 許可する provider の集合。

    Returns:
        Provider adapter に渡す実モデル名。
    """
    provider = _require_known_provider(
        model_config.provider,
        "Unknown LLM provider",
        known_providers,
    )
    if provider == LLMProvider.OLLAMA:
        return _resolve_ollama_model(model_config.model)
    if provider == LLMProvider.OPENAI:
        return _resolve_openai_model(model_config.model, runtime_config)
    return model_config.model


def build_provider_diagnostics(
    model_config: RuntimeModelConfig,
    runtime_config: IrisRuntimeConfig,
) -> LLMProviderDiagnostics | None:
    """モデルスロット設定からプロバイダ診断を組み立てる。

    ``provider == "fake"`` の場合は ``None`` を返し、診断対象外であることを示す。
    openai プロバイダは SDK 不在 / API key 不在時に ``OpenAIAdapterError`` を
    送出し、この関数では ``ConfigError`` に翻訳して再送出する。
    呼び出し側は ``ConfigError`` のみ catch すればよく、 concrete adapter
    シンボルへの依存なしで構築失敗を扱える。

    Args:
        model_config: モデルスロット設定。
        runtime_config: ランタイム設定全体。

    Returns:
        組み立てた診断インスタンス。 fake プロバイダなら ``None``。

    """
    provider = _require_known_provider(
        model_config.provider,
        "Unknown LLM provider for diagnostics",
    )
    return _build_provider_diagnostics(provider, model_config, runtime_config)


def _require_known_provider(
    provider: LLMProvider,
    message_prefix: str,
    known_providers: frozenset[LLMProvider] = _KNOWN_LLM_PROVIDERS,
) -> LLMProvider:
    """既知のプロバイダか検証する。

    Args:
        provider: 検証対象のプロバイダ。
        message_prefix: エラーメッセージの先頭。
        known_providers: 許可する provider の集合。

    Returns:
        検証済みプロバイダ。

    Raises:
        ConfigError: provider が未対応の場合。
    """
    if provider not in known_providers:
        message = f"{message_prefix}: {provider}"
        raise ConfigError(message)
    return provider


def _build_llm_client(
    provider: LLMProvider,
    model_config: RuntimeModelConfig,
    runtime_config: IrisRuntimeConfig,
) -> LLMClient:
    """Provider ごとの LLM client を組み立てる。

    Returns:
        構成済みの LLM client。
    """
    match provider:
        case LLMProvider.FAKE:
            return FakeLLMClient(model=model_config.model)
        case LLMProvider.OLLAMA:
            return wire_ollama_llm_client(
                ollama_adapter_config(model_config, runtime_config),
            )
        case LLMProvider.OPENAI:
            return wire_openai_llm_client(
                openai_adapter_config(model_config, runtime_config),
            )


def _build_provider_diagnostics(
    provider: LLMProvider,
    model_config: RuntimeModelConfig,
    runtime_config: IrisRuntimeConfig,
) -> LLMProviderDiagnostics | None:
    """Provider ごとの診断を組み立てる。

    Returns:
        構成済みの provider diagnostics。 fake provider なら None。

    Raises:
        ConfigError: openai diagnostics 構築失敗時。
    """
    try:
        match provider:
            case LLMProvider.FAKE:
                return None
            case LLMProvider.OLLAMA:
                return OllamaDiagnostics(
                    ollama_adapter_config(model_config, runtime_config),
                )
            case LLMProvider.OPENAI:
                return OpenAIDiagnostics(
                    openai_adapter_config(model_config, runtime_config),
                )
    except OpenAIAdapterError as exc:
        message = f"Failed to build openai provider diagnostics: {exc}"
        raise ConfigError(message) from exc


def ollama_adapter_config(
    model_config: RuntimeModelConfig,
    runtime_config: IrisRuntimeConfig,
) -> OllamaConfig:
    """RuntimeModelConfig + IrisRuntimeConfig を Ollama アダプタ用 OllamaConfig に変換する。

    Args:
        model_config: モデルスロット設定。
        runtime_config: ランタイム設定全体。

    Returns:
        ``OllamaLLMClient`` / ``OllamaDiagnostics`` が受け取る ``OllamaConfig``。
    """
    model = _resolve_ollama_model(model_config.model)
    return OllamaConfig(
        model=model,
        base_url=runtime_config.ollama.base_url,
        timeout_seconds=runtime_config.ollama.timeout_seconds,
        temperature=model_config.temperature,
        max_output_tokens=model_config.max_output_tokens,
        keep_alive=runtime_config.ollama.keep_alive,
        warmup_prompt=runtime_config.ollama.warmup_prompt,
        think=runtime_config.ollama.think,
    )


def ollama_lifecycle_probe_config(
    model_config: RuntimeModelConfig,
    runtime_config: IrisRuntimeConfig,
) -> OllamaConfig:
    """Runtime config を request-time Ollama lifecycle probe 用に変換する。

    Returns:
        短い readiness timeout を持つ ``OllamaModelLifecycleProbe`` 用 config。
    """
    model = _resolve_ollama_model(model_config.model)
    return OllamaConfig(
        model=model,
        base_url=runtime_config.ollama.base_url,
        timeout_seconds=runtime_config.diagnostics.readiness_timeout_seconds,
        temperature=model_config.temperature,
        max_output_tokens=model_config.max_output_tokens,
        keep_alive=runtime_config.ollama.keep_alive,
        warmup_prompt=runtime_config.ollama.warmup_prompt,
        think=runtime_config.ollama.think,
    )


def openai_adapter_config(
    model_config: RuntimeModelConfig,
    runtime_config: IrisRuntimeConfig,
) -> OpenAIConfig:
    """RuntimeModelConfig + IrisRuntimeConfig を OpenAI アダプタ用 OpenAIConfig に変換する。

    Args:
        model_config: モデルスロット設定。
        runtime_config: ランタイム設定全体。

    Returns:
        ``OpenAILLMClient`` / ``OpenAIDiagnostics`` が受け取る ``OpenAIConfig``。
        API key は環境変数 ``OPENAI_API_KEY`` から解決される。
    """
    model = _resolve_openai_model(model_config.model, runtime_config)
    max_output_tokens = model_config.max_output_tokens
    if max_output_tokens is None:
        max_output_tokens = runtime_config.openai.max_output_tokens
    return OpenAIConfig.from_env(
        model=model,
        timeout_seconds=runtime_config.openai.timeout_seconds,
        max_output_tokens=max_output_tokens,
    )


def _wrap_with_observer(
    client: LLMClient,
    *,
    lifecycle_probe: ModelLifecycleProbe | None,
    latency_budget: RuntimeLatencyBudget,
) -> LLMClient:
    """LLM client を既定の request lifecycle observer で包む。

    Runtime の LLM client factory は、cognitive-cycle log と provider latency /
    error rate を対応付けられるように、構造化された request telemetry を常に
    出力する。wrapper は request / response / exception propagation の呼び出し
    契約を保つため、既存の呼び出し側には影響しない。

    Args:
        client: provider constructor が返した素の LLM client。
        lifecycle_probe: 任意の request-time local model lifecycle probe。
        latency_budget: Runtime LLM generation latency budget。

    Returns:
        :class:`RuntimeLLMRequestObserver` を持つ :class:`ObservableLLMClient` で
        包んだ LLM client。
    """
    return ObservableLLMClient(
        client,
        RuntimeLLMRequestObserver(latency_budget=latency_budget),
        lifecycle_probe=lifecycle_probe,
    )


def _build_model_lifecycle_probe(
    provider: LLMProvider,
    model_config: RuntimeModelConfig,
    runtime_config: IrisRuntimeConfig,
) -> ModelLifecycleProbe | None:
    """Provider ごとの request-time lifecycle probe を組み立てる。

    Returns:
        ローカル lifecycle state を観測できる provider では probe、非対応 provider
        では ``None``。
    """
    if provider is LLMProvider.OLLAMA:
        return OllamaModelLifecycleProbe(
            ollama_lifecycle_probe_config(model_config, runtime_config),
        )
    return None


def _is_fake_llm_model(model: str) -> bool:
    """Fake LLM sentinel model か判定する。

    Returns:
        fake センチネルなら True。
    """
    return model == DEFAULT_FAKE_LLM_MODEL


def _resolve_ollama_model(model: str) -> str:
    """Ollama 用の実際のモデル名を解決する。

    Returns:
        実際に Ollama へ渡すモデル名。
    """
    if _is_fake_llm_model(model):
        return OllamaConfig().model
    return model


def _resolve_openai_model(model: str, runtime_config: IrisRuntimeConfig) -> str:
    """OpenAI 用の実際のモデル名を解決する。

    Returns:
        実際に OpenAI へ渡すモデル名。
    """
    if _is_fake_llm_model(model):
        return runtime_config.openai.model
    return model
