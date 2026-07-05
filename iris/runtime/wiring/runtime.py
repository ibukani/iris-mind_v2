"""ランタイムサービスと周辺コンポーネントのワイヤリング。"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING

from iris.adapters.app_gateway.identity_resolver import AccountBackedIdentityResolver
from iris.adapters.app_gateway.space_resolver import EphemeralSpaceResolver
from iris.adapters.embeddings.fake import DeterministicFakeEmbedding
from iris.adapters.memory.qdrant import QdrantVectorMemoryIndex
from iris.adapters.memory.vector_index import InMemoryVectorMemoryIndex
from iris.adapters.persistence.sqlite.stores.memory import SQLiteMemoryStore
from iris.contracts.memory import VectorMemoryIndexError
from iris.core.datetime_utils import now_utc
from iris.runtime.config.memory import MemoryVectorBackend, resolve_qdrant_api_key
from iris.runtime.conversation import (
    ConversationHistoryPolicy,
    DeliveryConversationHistoryHook,
    ShortTermConversationRuntime,
    TranscriptWritePolicy,
)
from iris.runtime.inference.scheduler import LocalInferenceResourceScheduler
from iris.runtime.ingress.activity_event_reaction import ActivityEventReactionHandler
from iris.runtime.ingress.observation_trust import ObservationTrustPolicy
from iris.runtime.learning.hooks import LearningHookRunner, RuntimeLearningHookRunner
from iris.runtime.learning.implicit_candidates import ImplicitCandidateAdmissionPolicy
from iris.runtime.learning.implicit_review_pipeline import (
    AccountAwareImplicitMemoryCandidateWorker,
    FilteringImplicitMemoryCandidateHook,
)
from iris.runtime.learning.jobs import BackgroundJobKind
from iris.runtime.learning.memory_worker import DeterministicMemoryConsolidationWorker
from iris.runtime.learning.policy import (
    BackgroundJobBackpressureMode,
    BackgroundJobKindPolicy,
    BackgroundJobQueuePolicy,
)
from iris.runtime.learning.review_promotion import ApprovedMemoryCandidatePromoter
from iris.runtime.learning.review_service import MemoryCandidateReviewService
from iris.runtime.learning.runner import BackgroundJobRunner, BackgroundJobRunnerOptions
from iris.runtime.memory_vector_rebuilder import MemoryVectorIndexRebuilder
from iris.runtime.observability.events import LoggingRuntimeObservationObserver
from iris.runtime.observability.ports import RuntimeLatencyBudget
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
    DisabledRuntimeFeature,
    RuntimeFeatureCatalog,
    collect_action_plan_presenters,
    collect_learning_hooks,
    collect_runtime_learning_hooks,
    wire_runtime_features,
)
from iris.runtime.wiring.presentation import wire_output_pipeline
from iris.runtime.wiring.scheduler import (
    SchedulerSafetyDependencies,
    wire_runtime_scheduler,
    wire_scheduler_runner,
)
from iris.runtime.wiring.state import RuntimeStateStores, wire_runtime_state

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from iris.adapters.app_gateway.ports import AppActionBroker
    from iris.contracts.embeddings import EmbeddingModel
    from iris.contracts.memory import VectorMemoryIndex
    from iris.features.definition import LearningHook
    from iris.runtime.app import IrisApp
    from iris.runtime.config import IrisRuntimeConfig
    from iris.runtime.config.learning import RuntimeBackgroundJobKindPolicyConfig
    from iris.runtime.output_pipeline import RuntimeOutputPipeline
    from iris.runtime.scheduler.runner import SchedulerRunner

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuntimeOperationalWiringDiagnostics:
    """runtime composition root が提供する read-only wiring diagnostics snapshot。"""

    scheduler_runner_wired: bool = True
    availability_provider_wired: bool = True
    safety_audit_journal_wired: bool = True
    delivery_broker_wired: bool = True
    delivery_safety_gate_wired: bool = True
    output_safety_gate_wired: bool = True
    proactive_talk_enabled: bool = False
    proactive_generation_mode: str = "not_configured"
    proactive_threshold: str = "not_configured"
    inference_scheduler_enabled: bool = False
    runtime_feature_mode: str = "development"
    enabled_feature_names: tuple[str, ...] = ()
    disabled_features: tuple[DisabledRuntimeFeature, ...] = ()


def describe_runtime_operational_wiring(
    config: IrisRuntimeConfig,
) -> RuntimeOperationalWiringDiagnostics:
    """Runtime 起動なしで composition root の標準配線状態を記述する。

    doctor は副作用を避けるため `build_runtime_components()` を呼ばない。
    代わりに、標準 runtime composition root と同じ feature catalog / config
    判定をここへ集約し、将来 config-driven feature enable が追加されたときに
    実配線と diagnostics の乖離をこの層で防ぐ。

    Args:
        config: runtime 設定。

    Returns:
        doctor へ渡す read-only wiring snapshot。
    """
    feature_catalog = wire_runtime_features(config)
    return RuntimeOperationalWiringDiagnostics(
        delivery_broker_wired=config.delivery.enabled,
        proactive_talk_enabled=_feature_enabled(feature_catalog, "proactive_talk"),
        inference_scheduler_enabled=config.inference_scheduler.enabled,
        runtime_feature_mode=feature_catalog.mode.value,
        enabled_feature_names=tuple(feature.name for feature in feature_catalog.features),
        disabled_features=feature_catalog.disabled_features,
    )


def _feature_enabled(catalog: RuntimeFeatureCatalog, feature_name: str) -> bool:
    return any(feature.name == feature_name for feature in catalog.features)


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
    inference_scheduler: LocalInferenceResourceScheduler | None
    memory_candidate_review_service: MemoryCandidateReviewService
    memory_candidate_promoter: ApprovedMemoryCandidatePromoter


@dataclass(frozen=True)
class RuntimeServiceBuildOptions:
    """RuntimeService組み立てに使う境界横断オプション。"""

    target_stale_after_seconds: float
    conversation_max_window_records: int = 20
    conversation_max_history_chars: int = 8000
    conversation_summary_enabled: bool = True
    conversation_summary_max_chars: int = 1600
    conversation_summary_min_records: int = 12
    transcript_retention_days: int = 30
    runtime_learning_hook_runner: RuntimeLearningHookRunner | None = None
    latency_budget: RuntimeLatencyBudget = field(default_factory=RuntimeLatencyBudget)
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
    observation_observer = LoggingRuntimeObservationObserver()
    return IrisRuntimeService(
        app,
        observation_pipeline=observation_pipeline,
        workspace_context_assembler=workspace_context_assembler,
        activity_event_reaction_handler=activity_event_reaction_handler,
        extensions=RuntimeServiceExtensions(
            observation_observer=observation_observer,
            conversation_runtime=ShortTermConversationRuntime(
                stores.conversation_history_store,
                transcript_store=stores.transcript_store,
                policy=_conversation_history_policy_from_config(
                    options.conversation_max_window_records,
                    options.conversation_max_history_chars,
                    summary_enabled=options.conversation_summary_enabled,
                    summary_max_chars=options.conversation_summary_max_chars,
                    summary_min_records=options.conversation_summary_min_records,
                ),
                transcript_policy=TranscriptWritePolicy(options.transcript_retention_days),
                observation_observer=observation_observer,
                latency_budget=options.latency_budget,
            ),
            runtime_learning_hook_runner=options.runtime_learning_hook_runner,
            latency_budget=options.latency_budget,
        ),
        now=current_now,
    )


def _conversation_history_policy_from_config(
    max_window_records: int,
    max_history_chars: int,
    *,
    summary_enabled: bool,
    summary_max_chars: int,
    summary_min_records: int,
) -> ConversationHistoryPolicy:
    """Runtime config から conversation history policy を構築する。

    Returns:
        ConversationHistoryPolicy インスタンス。
    """
    return ConversationHistoryPolicy(
        max_window_records=max_window_records,
        max_history_chars=max_history_chars,
        summary_enabled=summary_enabled,
        summary_max_chars=summary_max_chars,
        summary_min_records=summary_min_records,
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
    vector_index, embedding = _wire_memory_vector(config, stores)
    inference_scheduler = _wire_inference_scheduler(config)
    feature_catalog = wire_runtime_features(config)
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
            vector_index=vector_index,
            embedding=embedding,
        ),
        output_pipeline=output_pipeline,
        features=feature_catalog.features,
        inference_scheduler=inference_scheduler,
    )
    runtime_service = build_runtime_service(
        app,
        stores,
        feature_catalog=feature_catalog,
        output_pipeline=output_pipeline,
        options=RuntimeServiceBuildOptions(
            target_stale_after_seconds=config.scheduler.target_stale_after_seconds,
            conversation_max_window_records=config.conversation.max_window_records,
            conversation_max_history_chars=config.conversation.max_history_chars,
            conversation_summary_enabled=config.conversation.summary_enabled,
            conversation_summary_max_chars=config.conversation.summary_max_chars,
            conversation_summary_min_records=config.conversation.summary_min_records,
            transcript_retention_days=config.conversation.transcript.retention_days,
            latency_budget=config.observability.latency_budget,
            runtime_learning_hook_runner=_wire_runtime_learning_hook_runner(
                config,
                stores,
                feature_catalog,
            ),
        ),
    )
    gateway_components = _wire_runtime_gateway_components(config, stores, feature_catalog)
    background_job_runner = BackgroundJobRunner(
        stores.background_job_queue,
        (
            DeterministicMemoryConsolidationWorker(stores.memory_store),
            AccountAwareImplicitMemoryCandidateWorker(
                stores.memory_candidate_review_store,
                policy=ImplicitCandidateAdmissionPolicy(
                    min_confidence=config.learning.implicit_candidate_min_confidence,
                    max_text_length=config.learning.implicit_candidate_max_text_length,
                ),
            ),
        ),
        options=BackgroundJobRunnerOptions(
            max_jobs_per_run=config.learning.max_jobs_per_run,
            queue_policy=_background_job_queue_policy_from_config(config),
            inference_scheduler=inference_scheduler,
        ),
    )
    scheduler_runner = wire_scheduler_runner(
        runtime_service=runtime_service,
        scheduler=wire_runtime_scheduler(stores.scheduler_target_store, config),
        delivery_gate=wire_delivery_safety_gate(config.delivery, config.safety),
        outbox=stores.delivery_outbox,
        config=config,
        safety=SchedulerSafetyDependencies(
            availability_provider=gateway_components.availability_provider,
            audit_journal=stores.safety_audit_journal,
        ),
    )
    return RuntimeComponents(
        stores=stores,
        runtime_service=runtime_service,
        identity_resolver=gateway_components.identity_resolver,
        space_resolver=gateway_components.space_resolver,
        app_action_broker=gateway_components.app_action_broker,
        scheduler_runner=scheduler_runner,
        background_job_runner=background_job_runner,
        inference_scheduler=inference_scheduler,
        memory_candidate_review_service=MemoryCandidateReviewService(
            stores.memory_candidate_review_store
        ),
        memory_candidate_promoter=ApprovedMemoryCandidatePromoter(
            stores.memory_candidate_review_store,
            stores.memory_store,
        ),
    )


def _wire_inference_scheduler(
    config: IrisRuntimeConfig,
) -> LocalInferenceResourceScheduler | None:
    """Runtime config から local inference resource scheduler を構築する。

    Returns:
        config-gated scheduler。無効時は None。
    """
    if not config.inference_scheduler.enabled:
        return None
    return LocalInferenceResourceScheduler(policy=config.inference_scheduler.to_policy())


def _background_job_queue_policy_from_config(config: IrisRuntimeConfig) -> BackgroundJobQueuePolicy:
    """Runtime config から BackgroundJobQueuePolicy を構築する。

    Returns:
        BackgroundJobQueuePolicy。policy 無効時は permissive policy。
    """
    policy_config = config.learning.background_job_policy
    if not policy_config.enabled:
        return BackgroundJobQueuePolicy(
            default_policy=BackgroundJobKindPolicy(
                concurrency_limit=config.learning.max_jobs_per_run,
                timeout_seconds=policy_config.default_timeout_seconds,
                max_pending_jobs=1_000_000,
                retry_backoff_base_seconds=policy_config.retry_backoff_base_seconds,
                retry_backoff_max_seconds=policy_config.retry_backoff_max_seconds,
                defer_seconds_when_saturated=policy_config.defer_seconds_when_saturated,
                backpressure_mode=BackgroundJobBackpressureMode.ACCEPT,
            ),
            per_kind={},
        )
    default_policy = BackgroundJobKindPolicy(
        concurrency_limit=policy_config.default_concurrency_limit,
        timeout_seconds=policy_config.default_timeout_seconds,
        max_pending_jobs=policy_config.default_max_pending_jobs,
        retry_backoff_base_seconds=policy_config.retry_backoff_base_seconds,
        retry_backoff_max_seconds=policy_config.retry_backoff_max_seconds,
        defer_seconds_when_saturated=policy_config.defer_seconds_when_saturated,
        backpressure_mode=BackgroundJobBackpressureMode(policy_config.backpressure_mode),
    )
    return BackgroundJobQueuePolicy(
        default_policy=default_policy,
        per_kind={
            BackgroundJobKind.MEMORY_EXTRACTION: _background_job_kind_policy(
                policy_config.kinds.memory_extraction,
                default_policy=default_policy,
            ),
            BackgroundJobKind.REFLECTION: _background_job_kind_policy(
                policy_config.kinds.reflection,
                default_policy=default_policy,
            ),
        },
    )


def _background_job_kind_policy(
    config: RuntimeBackgroundJobKindPolicyConfig,
    *,
    default_policy: BackgroundJobKindPolicy,
) -> BackgroundJobKindPolicy:
    """Runtime kind policy config から queue policy を構築する。

    Returns:
        BackgroundJobKindPolicy。
    """
    return BackgroundJobKindPolicy(
        concurrency_limit=config.concurrency_limit,
        timeout_seconds=config.timeout_seconds,
        max_pending_jobs=config.max_pending_jobs,
        retry_backoff_base_seconds=default_policy.retry_backoff_base_seconds,
        retry_backoff_max_seconds=default_policy.retry_backoff_max_seconds,
        defer_seconds_when_saturated=default_policy.defer_seconds_when_saturated,
        backpressure_mode=default_policy.backpressure_mode,
        uses_llm=config.uses_llm,
        idle_only=config.idle_only,
    )


def _wire_memory_vector(
    config: IrisRuntimeConfig,
    stores: RuntimeStateStores,
) -> tuple[VectorMemoryIndex | None, EmbeddingModel | None]:
    """Vector-enabled SQLite memory の派生 index を構築する。

    Returns:
        Index と embedding。無効または fail-open 時は両方 None。

    Raises:
        VectorMemoryIndexError: fail-open 無効時に index 操作が失敗した場合。
    """
    vector_config = config.memory.vector
    if not vector_config.enabled or not isinstance(stores.memory_store, SQLiteMemoryStore):
        return None, None
    embedding_config = config.memory.embedding
    embedding = DeterministicFakeEmbedding(
        model=embedding_config.model,
        dimension=embedding_config.dimension,
    )
    try:
        index = _create_memory_vector_index(config, dimension=embedding.dimension)
        if vector_config.rebuild_on_startup:
            _rebuild_memory_vector(config, stores, index, embedding)
    except VectorMemoryIndexError:
        if not vector_config.fail_open_on_index_error:
            raise
        _LOGGER.exception("memory vector index disabled after startup failure")
        return None, None
    return index, embedding


def _create_memory_vector_index(config: IrisRuntimeConfig, *, dimension: int) -> VectorMemoryIndex:
    """設定された vector backend を構築する。

    Returns:
        構成済み vector index。
    """
    vector_config = config.memory.vector
    if vector_config.backend is MemoryVectorBackend.IN_MEMORY:
        return InMemoryVectorMemoryIndex()
    return QdrantVectorMemoryIndex(
        url=vector_config.qdrant.url,
        collection=vector_config.collection,
        dimension=dimension,
        api_key=resolve_qdrant_api_key(vector_config.qdrant),
    )


def _rebuild_memory_vector(
    config: IrisRuntimeConfig,
    stores: RuntimeStateStores,
    index: VectorMemoryIndex,
    embedding: EmbeddingModel,
) -> None:
    """正本から index を同期し、text を含まない統計を記録する。"""
    stats = MemoryVectorIndexRebuilder(
        store=stores.memory_store,
        index=index,
        embedding=embedding,
        batch_size=config.memory.embedding.batch_size,
    ).rebuild(remove_orphans=True)
    _LOGGER.info(
        "memory vector index rebuild complete",
        extra={
            "embedding_provider": embedding.provider,
            "embedding_model": embedding.model_id,
            "embedding_dimension": embedding.dimension,
            "scanned": stats.scanned,
            "upserted": stats.upserted,
            "unchanged": stats.unchanged,
            "missing": stats.missing,
            "stale": stats.stale,
            "incompatible": stats.incompatible,
            "removed_orphans": stats.removed_orphans,
        },
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
        DeliveryConversationHistoryHook(
            stores.conversation_history_store,
            transcript_store=stores.transcript_store,
            transcript_policy=TranscriptWritePolicy(config.conversation.transcript.retention_days),
            observation_observer=LoggingRuntimeObservationObserver(),
            latency_budget=config.observability.latency_budget,
        ),
        *feature_hooks,
    )


def _wire_runtime_learning_hook_runner(
    config: IrisRuntimeConfig,
    stores_or_feature_catalog: RuntimeStateStores | RuntimeFeatureCatalog,
    feature_catalog: RuntimeFeatureCatalog | None = None,
) -> RuntimeLearningHookRunner | None:
    """Runtime outcome後に実行する hook runner を組み立てる。

    Returns:
        learning無効またはhook未登録ならNone。
    """
    if not config.learning.enabled:
        return None
    stores: RuntimeStateStores | None
    resolved_feature_catalog: RuntimeFeatureCatalog
    if feature_catalog is None:
        stores = None
        resolved_feature_catalog = _require_feature_catalog(stores_or_feature_catalog)
    else:
        stores = _require_runtime_state_stores(stores_or_feature_catalog)
        resolved_feature_catalog = feature_catalog
    hooks = collect_runtime_learning_hooks(resolved_feature_catalog.features)
    built_in_hooks = _wire_builtin_runtime_learning_hooks(config, stores)
    all_hooks = (*built_in_hooks, *hooks)
    if not all_hooks:
        return None
    return RuntimeLearningHookRunner(all_hooks)


def _wire_builtin_runtime_learning_hooks(
    config: IrisRuntimeConfig,
    stores: RuntimeStateStores | None,
) -> tuple[FilteringImplicitMemoryCandidateHook, ...]:
    """Built-in runtime learning hooksを組み立てる。

    Returns:
        Built-in hooks。store未指定または無効なら空。
    """
    if stores is None:
        return ()
    if (
        not config.learning.background_jobs_enabled
        or not config.learning.implicit_candidates_enabled
    ):
        return ()
    return (
        FilteringImplicitMemoryCandidateHook(
            stores.background_job_queue,
            max_attempts=config.learning.max_attempts,
            observation_observer=LoggingRuntimeObservationObserver(),
            latency_budget=config.observability.latency_budget,
            queue_policy=_background_job_queue_policy_from_config(config),
        ),
    )


def _require_feature_catalog(
    value: RuntimeStateStores | RuntimeFeatureCatalog,
) -> RuntimeFeatureCatalog:
    if isinstance(value, RuntimeFeatureCatalog):
        return value
    message = "feature_catalog is required when wiring built-in runtime learning hooks"
    raise TypeError(message)


def _require_runtime_state_stores(
    value: RuntimeStateStores | RuntimeFeatureCatalog,
) -> RuntimeStateStores:
    if isinstance(value, RuntimeStateStores):
        return value
    message = "RuntimeStateStores required for runtime learning hook wiring"
    raise TypeError(message)
