"""ランタイムサービスと周辺コンポーネントのワイヤリング。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.adapters.app_gateway.identity_resolver import AccountBackedIdentityResolver
from iris.adapters.app_gateway.space_resolver import EphemeralSpaceResolver
from iris.core.datetime_utils import now_utc
from iris.runtime.conversation import DeliveryConversationHistoryHook, ShortTermConversationRuntime
from iris.runtime.ingress.activity_event_reaction import ActivityEventReactionHandler
from iris.runtime.ingress.observation_trust import ObservationTrustPolicy
from iris.runtime.learning.hooks import LearningHookRunner, RuntimeLearningHookRunner
from iris.runtime.learning.memory_worker import DeterministicMemoryConsolidationWorker
from iris.runtime.learning.runner import BackgroundJobRunner
from iris.runtime.observability.events import LoggingRuntimeObservationObserver
from iris.runtime.scheduler.availability import DeliveryAvailabilityResolverAdapter
from iris.runtime.service import (
    IntegratingObservationPipeline,
    IrisRuntimeService,
    RuntimeServiceExtensions,
)
from iris.runtime.state.activity_integrator import ActivityIntegrator
from iris.runtime.state.presence_integrator import PresenceIntegrator
from iris.runtime.state.scheduler_target_integrator import SchedulerTargetIntegrator
from iris.runtime.state.space_occupancy_integrator import SpaceOccupancyIntegrator
from iris.runtime.wiring.app import AppStateDependencies, build_app_from_config
from iris.runtime.wiring.availability import wire_availability_resolver
from iris.runtime.wiring.context import wire_workspace_context_assembler
from iris.runtime.wiring.delivery import wire_app_action_broker, wire_delivery_safety_gate
from iris.runtime.wiring.event_reaction import wire_event_reaction_decision_pipeline
from iris.runtime.wiring.features import (
    RuntimeFeatureCatalog,
    collect_action_plan_presenters,
    collect_learning_hooks,
    collect_runtime_learning_hooks,
    wire_runtime_features,
)
from iris.runtime.wiring.presentation import wire_output_pipeline
from iris.runtime.wiring.scheduler import wire_runtime_scheduler, wire_scheduler_runner
from iris.runtime.wiring.state import RuntimeStateStores, wire_runtime_state

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from iris.adapters.app_gateway.ports import AppActionBroker
    from iris.features.definition import LearningHook
    from iris.runtime.app import IrisApp
    from iris.runtime.config import IrisRuntimeConfig
    from iris.runtime.output_pipeline import RuntimeOutputPipeline
    from iris.runtime.scheduler.runner import SchedulerRunner


@dataclass(frozen=True)
class RuntimeComponents:
    """ランタイムサーバー起動前に組み立てるコンポーネント群。"""

    stores: RuntimeStateStores
    runtime_service: IrisRuntimeService
    identity_resolver: AccountBackedIdentityResolver
    space_resolver: EphemeralSpaceResolver
    app_action_broker: AppActionBroker | None
    scheduler_runner: SchedulerRunner
    background_job_runner: BackgroundJobRunner


@dataclass(frozen=True)
class RuntimeServiceBuildOptions:
    """RuntimeService組み立てに使う境界横断オプション。"""

    target_stale_after_seconds: float
    runtime_learning_hook_runner: RuntimeLearningHookRunner | None = None
    now: Callable[[], datetime] | None = None


@dataclass(frozen=True)
class _RuntimeGatewayComponents:
    """Iris runtime の gateway 系コンポーネント群。"""

    identity_resolver: AccountBackedIdentityResolver
    space_resolver: EphemeralSpaceResolver
    app_action_broker: AppActionBroker | None
    availability_provider: DeliveryAvailabilityResolverAdapter


def build_runtime_service(
    app: IrisApp,
    stores: RuntimeStateStores,
    *,
    feature_catalog: RuntimeFeatureCatalog,
    output_pipeline: RuntimeOutputPipeline,
    options: RuntimeServiceBuildOptions,
) -> IrisRuntimeService:
    """IrisApp とランタイムstateストアからサービス境界を組み立てる。

    Activity / presence / occupancy 統合、availability 解決、
    workspace context assembly を同一ストアインスタンスで配線する。

    Args:
        app: アプリケーション定義。
        stores: ランタイムstateストア。
        feature_catalog: 有効なフィーチャー定義の集合。
        output_pipeline: presentation と safety を適用する共有出力境界。
        options: target stale policy、現在時刻、runtime hook runner。

    Returns:
        構成済みの IrisRuntimeService。
    """
    trust_policy = ObservationTrustPolicy()
    current_now = options.now or now_utc
    observation_pipeline = _wire_observation_pipeline(
        stores,
        trust_policy=trust_policy,
        now=current_now,
        target_stale_after_seconds=options.target_stale_after_seconds,
    )
    availability_resolver = wire_availability_resolver()
    workspace_context_assembler = wire_workspace_context_assembler(
        activity_projection_store=stores.activity_projection_store,
        presence_store=stores.presence_store,
        occupancy_store=stores.space_occupancy_store,
        availability_resolver=availability_resolver,
        now=current_now,
    )
    activity_event_reaction_handler = _wire_activity_event_reaction_handler(
        trust_policy=trust_policy,
        feature_catalog=feature_catalog,
        output_pipeline=output_pipeline,
    )
    return IrisRuntimeService(
        app,
        observation_pipeline=observation_pipeline,
        workspace_context_assembler=workspace_context_assembler,
        activity_event_reaction_handler=activity_event_reaction_handler,
        extensions=RuntimeServiceExtensions(
            observation_observer=LoggingRuntimeObservationObserver(),
            conversation_runtime=ShortTermConversationRuntime(stores.conversation_history_store),
            runtime_learning_hook_runner=options.runtime_learning_hook_runner,
        ),
        now=current_now,
    )


def build_runtime_components(config: IrisRuntimeConfig) -> RuntimeComponents:
    """ランタイム設定から永続ストアとサービス境界を組み立てる。

    `wire_runtime_state` で組み立てたメモリストアを `build_app_from_config` に
    明示注入する。埋め込み関数がない SQLite は FTS5 専用検索を使う。

    Args:
        config: ランタイム設定。

    Returns:
        ランタイムコンポーネント。
    """
    stores = wire_runtime_state(config)
    feature_catalog = wire_runtime_features()
    output_pipeline = wire_output_pipeline(
        safety_config=config.safety,
        extension_presenters=collect_action_plan_presenters(feature_catalog.features),
    )
    app = build_app_from_config(
        config,
        state=AppStateDependencies(
            memory_store=stores.memory_store,
            relationship_store=stores.relationship_store,
            affect_store=stores.affect_store,
        ),
        output_pipeline=output_pipeline,
        features=feature_catalog.features,
    )
    runtime_service = build_runtime_service(
        app,
        stores,
        feature_catalog=feature_catalog,
        output_pipeline=output_pipeline,
        options=RuntimeServiceBuildOptions(
            target_stale_after_seconds=config.scheduler.target_stale_after_seconds,
            runtime_learning_hook_runner=_wire_runtime_learning_hook_runner(
                config,
                feature_catalog,
            ),
        ),
    )
    gateway_components = _wire_runtime_gateway_components(config, stores, feature_catalog)
    background_job_runner = BackgroundJobRunner(
        stores.background_job_queue,
        (DeterministicMemoryConsolidationWorker(stores.memory_store),),
        max_jobs_per_run=config.learning.max_jobs_per_run,
    )
    scheduler_runner = wire_scheduler_runner(
        runtime_service=runtime_service,
        scheduler=wire_runtime_scheduler(stores.scheduler_target_store, config),
        delivery_gate=wire_delivery_safety_gate(config.delivery),
        outbox=stores.delivery_outbox,
        config=config,
        availability_provider=gateway_components.availability_provider,
    )
    return RuntimeComponents(
        stores=stores,
        runtime_service=runtime_service,
        identity_resolver=gateway_components.identity_resolver,
        space_resolver=gateway_components.space_resolver,
        app_action_broker=gateway_components.app_action_broker,
        scheduler_runner=scheduler_runner,
        background_job_runner=background_job_runner,
    )


def _wire_observation_pipeline(
    stores: RuntimeStateStores,
    *,
    trust_policy: ObservationTrustPolicy,
    now: Callable[[], datetime],
    target_stale_after_seconds: float,
) -> IntegratingObservationPipeline:
    """観測統合 pipeline を組み立てる。

    Returns:
        構成済みの IntegratingObservationPipeline。
    """
    activity_integrator = ActivityIntegrator(
        journal=stores.activity_journal,
        projections=stores.activity_projection_store,
        trust_policy=trust_policy,
        now=now,
    )
    presence_integrator = PresenceIntegrator(
        store=stores.presence_store,
        trust_policy=trust_policy,
        now=now,
    )
    occupancy_integrator = SpaceOccupancyIntegrator(
        store=stores.space_occupancy_store,
        trust_policy=trust_policy,
        now=now,
    )
    scheduler_target_integrator = SchedulerTargetIntegrator(
        target_store=stores.scheduler_target_store,
        target_stale_after_seconds=target_stale_after_seconds,
    )
    return IntegratingObservationPipeline(
        (
            activity_integrator,
            presence_integrator,
            occupancy_integrator,
            scheduler_target_integrator,
        )
    )


def _wire_activity_event_reaction_handler(
    *,
    trust_policy: ObservationTrustPolicy,
    feature_catalog: RuntimeFeatureCatalog,
    output_pipeline: RuntimeOutputPipeline,
) -> ActivityEventReactionHandler:
    """Event reaction handler を組み立てる。

    Returns:
        構成済みの ActivityEventReactionHandler。
    """
    decision_pipeline = wire_event_reaction_decision_pipeline(feature_catalog.features)
    return ActivityEventReactionHandler(
        trust_policy=trust_policy,
        decision_pipeline=decision_pipeline,
        output_pipeline=output_pipeline,
    )


def _wire_runtime_gateway_components(
    config: IrisRuntimeConfig,
    stores: RuntimeStateStores,
    feature_catalog: RuntimeFeatureCatalog,
) -> _RuntimeGatewayComponents:
    """App gateway と delivery 周辺の依存をまとめて組み立てる。

    Returns:
        まとめた gateway 系コンポーネント。
    """
    identity_resolver = AccountBackedIdentityResolver(account_store=stores.account_store)
    space_resolver = EphemeralSpaceResolver()
    app_action_broker = (
        wire_app_action_broker(
            stores.delivery_outbox,
            config.delivery,
            learning_hook_runner=LearningHookRunner(
                _wire_action_result_hooks(config, stores, feature_catalog)
            ),
            learning_dispatch_store=stores.learning_dispatch_store,
        )
        if config.delivery.enabled
        else None
    )
    availability_provider = DeliveryAvailabilityResolverAdapter(
        resolver=wire_availability_resolver(),
        presence_store=stores.presence_store,
        activity_projection_store=stores.activity_projection_store,
    )
    return _RuntimeGatewayComponents(
        identity_resolver=identity_resolver,
        space_resolver=space_resolver,
        app_action_broker=app_action_broker,
        availability_provider=availability_provider,
    )


def _wire_action_result_hooks(
    config: IrisRuntimeConfig,
    stores: RuntimeStateStores,
    feature_catalog: RuntimeFeatureCatalog,
) -> tuple[LearningHook, ...]:
    """配送結果後に実行する hook 群を組み立てる。

    History finalization は learning.enabled に関係なく配送境界の一部として
    実行し、追加の feature-owned learning hooks だけを learning.enabled で制御する。

    Returns:
        登録順に実行する action-result hook 群。
    """
    feature_hooks = (
        collect_learning_hooks(feature_catalog.features) if config.learning.enabled else ()
    )
    return (
        DeliveryConversationHistoryHook(stores.conversation_history_store),
        *feature_hooks,
    )


def _wire_runtime_learning_hook_runner(
    config: IrisRuntimeConfig,
    feature_catalog: RuntimeFeatureCatalog,
) -> RuntimeLearningHookRunner | None:
    """Runtime outcome後に実行する feature-owned hook runner を組み立てる。

    Returns:
        learning無効またはhook未登録ならNone。
    """
    if not config.learning.enabled:
        return None
    hooks = collect_runtime_learning_hooks(feature_catalog.features)
    if not hooks:
        return None
    return RuntimeLearningHookRunner(hooks)
