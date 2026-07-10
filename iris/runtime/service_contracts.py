"""Runtime service の transport-independent contracts と extension ports。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from iris.runtime.ingress.observation_ingress import (
    trusted_adapter_ingress,
    unauthenticated_external_ingress,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.contracts.actions import PresentedOutput
    from iris.contracts.delivery import DeliveryRouteHint
    from iris.contracts.learning import RuntimeLearningEvent
    from iris.contracts.observations import ActivityEventObservation, Observation
    from iris.contracts.workspace_context import SituationContextSnapshot
    from iris.core.ids import CorrelationId
    from iris.runtime.ingress.observation_ingress import (
        ObservationCapability,
        ObservationIngressContext,
    )
    from iris.runtime.ingress.observation_integrator import ObservationIntegrator
    from iris.runtime.observability.ports import (
        RuntimeLatencyBudget,
        RuntimeObservationObserver,
    )


@dataclass(frozen=True)
class ObservationEnvelope:
    """受信観測を入れるトランスポート非依存コンテナ。"""

    observation: Observation
    ingress: ObservationIngressContext
    correlation_id: CorrelationId | None = None

    @classmethod
    def external_client(
        cls,
        *,
        observation: Observation,
        correlation_id: CorrelationId | None = None,
    ) -> ObservationEnvelope:
        """外部 client request 用の capability なし envelope を作成する。

        Returns:
            未認証 ingress を持つ ObservationEnvelope。
        """
        return cls(
            observation=observation,
            ingress=unauthenticated_external_ingress(),
            correlation_id=correlation_id,
        )

    @classmethod
    def trusted_adapter(
        cls,
        *,
        observation: Observation,
        adapter_id: str,
        provider: str | None = None,
        capabilities: frozenset[ObservationCapability] | set[ObservationCapability],
        correlation_id: CorrelationId | None = None,
        delivery_route: DeliveryRouteHint | None = None,
    ) -> ObservationEnvelope:
        """信頼済み adapter observation 用の capability 付き envelope を作成する。

        Args:
            observation: Observation。
            adapter_id: 信頼済み adapter の識別子。
            provider: 任意の provider 名。
            capabilities: 呼び出し側が明示する capability。
            correlation_id: 任意の correlation ID。
            delivery_route: 任意の配送 route hint。

        Returns:
            認証済み ingress を持つ ObservationEnvelope。
        """
        return cls(
            observation=observation,
            ingress=trusted_adapter_ingress(
                adapter_id=adapter_id,
                provider=provider,
                capabilities=capabilities,
                delivery_route=delivery_route,
            ),
            correlation_id=correlation_id,
        )


@dataclass(frozen=True)
class RuntimeResponse:
    """IrisRuntimeService が返すトランスポート非依存の結果。"""

    output: PresentedOutput
    correlation_id: CorrelationId | None = None


class ObservationRuntimeService(Protocol):
    """観測を処理して RuntimeResponse を返す runtime 境界 port。"""

    async def handle_observation(self, envelope: ObservationEnvelope) -> RuntimeResponse:
        """観測を処理し、出力と correlation id を返す。

        Returns:
            PresentedOutput と保持された correlation ID。
        """
        ...


class ObservationProcessingPipeline(Protocol):
    """RuntimeService の observation 統合境界。"""

    async def integrate_observation(
        self,
        observation: Observation,
        ingress: ObservationIngressContext,
    ) -> None:
        """Observation claim を runtime state へ統合する。"""
        ...


class WorkspaceContextProvider(Protocol):
    """RuntimeService に状況 context を供給する境界。"""

    async def assemble(self, observation: Observation) -> SituationContextSnapshot | None:
        """Observation から workspace context を組み立てる。

        Returns:
            組み立てた状況 context。利用できない場合は None。
        """
        ...


class ConversationTurnRuntime(Protocol):
    """Cognitive route 前後の短期会話 context 境界。"""

    async def load_context(
        self,
        observation: Observation,
        base: SituationContextSnapshot | None,
    ) -> SituationContextSnapshot:
        """過去会話を状況 context へ追加する。

        Returns:
            会話 window を含む状況 context。
        """
        ...

    async def record_response(
        self,
        observation: Observation,
        output: PresentedOutput,
    ) -> None:
        """成功した sendable turn を記録する。"""
        ...


class ActivityEventReactionPipeline(Protocol):
    """Activity event reaction の runtime 境界。"""

    async def handle(
        self,
        observation: ActivityEventObservation,
        situation_context: SituationContextSnapshot | None,
        ingress: ObservationIngressContext,
    ) -> PresentedOutput:
        """Activity event に対する reaction output を返す。

        Returns:
            Event reaction output。
        """
        ...


class RuntimeLearningEventRunner(Protocol):
    """Runtime outcome 学習イベントを副作用境界へ渡す runner。"""

    async def run(self, event: RuntimeLearningEvent) -> None:
        """Runtime learning event を処理する。"""
        ...


@dataclass(frozen=True)
class RuntimeServiceExtensions:
    """RuntimeService へ注入する任意の副作用境界。"""

    observation_observer: RuntimeObservationObserver | None = None
    conversation_runtime: ConversationTurnRuntime | None = None
    runtime_learning_hook_runner: RuntimeLearningEventRunner | None = None
    latency_budget: RuntimeLatencyBudget | None = None


@dataclass(frozen=True)
class IntegratingObservationPipeline:
    """複数の observation integrator を一つの runtime 境界として実行する。"""

    integrators: Sequence[ObservationIntegrator]

    async def integrate_observation(
        self,
        observation: Observation,
        ingress: ObservationIngressContext,
    ) -> None:
        """登録された integrator を順に実行する。"""
        for integrator in self.integrators:
            await integrator.integrate_observation(observation, ingress)
