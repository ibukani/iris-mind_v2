"""ランタイムサービスと周辺コンポーネントのワイヤリング。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.adapters.app_gateway.identity_resolver import AccountBackedIdentityResolver
from iris.adapters.app_gateway.space_resolver import EphemeralSpaceResolver
from iris.core.datetime_utils import now_utc
from iris.runtime.ingress.activity_event_reaction import ActivityEventReactionHandler
from iris.runtime.ingress.observation_trust import ObservationTrustPolicy
from iris.runtime.observability.events import LoggingRuntimeObservationObserver
from iris.runtime.scheduler.availability import DeliveryAvailabilityResolverAdapter
from iris.runtime.service import IntegratingObservationPipeline, IrisRuntimeService
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
    wire_runtime_features,
)
from iris.runtime.wiring.presentation import wire_output_pipeline
from iris.runtime.wiring.scheduler import wire_runtime_scheduler, wire_scheduler_runner
from iris.runtime.wiring.state import RuntimeStateStores, wire_runtime_state

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from iris.adapters.app_gateway.ports import AppActionBroker
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


def build_runtime_service(
    app: IrisApp,
    stores: RuntimeStateStores,
    *,
    feature_catalog: RuntimeFeatureCatalog,
    output_pipeline: RuntimeOutputPipeline,
    target_stale_after_seconds: float,
    now: Callable[[], datetime] | None = None,
) -> IrisRuntimeService:
    """IrisApp とランタイムstateストアからサービス境界を組み立てる。

    Activity / presence / occupancy 統合、availability 解決、
    workspace context assembly を同一ストアインスタンスで配線する。

    Args:
        app: アプリケーション定義。
        stores: ランタイムstateストア。
        feature_catalog: 有効なフィーチャー定義の集合。
        output_pipeline: presentation と safety を適用する共有出力境界。
        target_stale_after_seconds: target が stale になるまでの idle 秒数。
        now: 現在時刻を返す関数。省略時は `datetime.now(UTC)`。

    Returns:
        構成済みの IrisRuntimeService。
    """
    trust_policy = ObservationTrustPolicy()
    current_now = now or now_utc
    activity_integrator = ActivityIntegrator(
        journal=stores.activity_journal,
        projections=stores.activity_projection_store,
        trust_policy=trust_policy,
        now=current_now,
    )
    presence_integrator = PresenceIntegrator(
        store=stores.presence_store,
        trust_policy=trust_policy,
        now=current_now,
    )
    occupancy_integrator = SpaceOccupancyIntegrator(
        store=stores.space_occupancy_store,
        trust_policy=trust_policy,
        now=current_now,
    )
    scheduler_target_integrator = SchedulerTargetIntegrator(
        target_store=stores.scheduler_target_store,
        target_stale_after_seconds=target_stale_after_seconds,
    )
    availability_resolver = wire_availability_resolver()
    workspace_context_assembler = wire_workspace_context_assembler(
        activity_projection_store=stores.activity_projection_store,
        presence_store=stores.presence_store,
        occupancy_store=stores.space_occupancy_store,
        availability_resolver=availability_resolver,
        now=current_now,
    )
    decision_pipeline = wire_event_reaction_decision_pipeline(feature_catalog.features)
    activity_event_reaction_handler = ActivityEventReactionHandler(
        trust_policy=trust_policy,
        decision_pipeline=decision_pipeline,
        output_pipeline=output_pipeline,
    )
    return IrisRuntimeService(
        app,
        observation_pipeline=IntegratingObservationPipeline(
            (
                activity_integrator,
                presence_integrator,
                occupancy_integrator,
                scheduler_target_integrator,
            )
        ),
        workspace_context_assembler=workspace_context_assembler,
        activity_event_reaction_handler=activity_event_reaction_handler,
        observation_observer=LoggingRuntimeObservationObserver(),
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
    runtime_service = build_runtime_service(
        build_app_from_config(
            config,
            state=AppStateDependencies(
                memory_store=stores.memory_store,
                relationship_store=stores.relationship_store,
                affect_store=stores.affect_store,
            ),
            output_pipeline=output_pipeline,
            features=feature_catalog.features,
        ),
        stores,
        feature_catalog=feature_catalog,
        output_pipeline=output_pipeline,
        target_stale_after_seconds=config.scheduler.target_stale_after_seconds,
    )
    identity_resolver = AccountBackedIdentityResolver(account_store=stores.account_store)
    space_resolver = EphemeralSpaceResolver()
    app_action_broker = (
        wire_app_action_broker(stores.delivery_outbox, config.delivery)
        if config.delivery.enabled
        else None
    )
    availability_provider = DeliveryAvailabilityResolverAdapter(
        resolver=wire_availability_resolver(),
        presence_store=stores.presence_store,
        activity_projection_store=stores.activity_projection_store,
    )
    scheduler_runner = wire_scheduler_runner(
        runtime_service=runtime_service,
        scheduler=wire_runtime_scheduler(stores.scheduler_target_store, config),
        delivery_gate=wire_delivery_safety_gate(config.delivery),
        outbox=stores.delivery_outbox,
        config=config,
        availability_provider=availability_provider,
    )
    return RuntimeComponents(
        stores=stores,
        runtime_service=runtime_service,
        identity_resolver=identity_resolver,
        space_resolver=space_resolver,
        app_action_broker=app_action_broker,
        scheduler_runner=scheduler_runner,
    )
