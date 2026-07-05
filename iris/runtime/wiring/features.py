"""機能拡張された認知サイクル向けのワイヤリング関数。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from iris.features.basic_action.definition import define_basic_action_feature
from iris.features.event_reaction.definition import define_event_reaction_feature
from iris.features.proactive_talk.definition import define_proactive_talk_feature
from iris.runtime.wiring.cognitive import (
    CognitiveCycleStores,
    wire_core_cognitive_cycle,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.cognitive.cycle.models import PipelineStepResult
    from iris.cognitive.cycle.pipeline import PipelineStep
    from iris.cognitive.cycle.service import CognitiveCycle
    from iris.contracts.memory import MemoryStore
    from iris.contracts.presentation import ActionPlanPresenter
    from iris.contracts.relationship import RelationshipStore
    from iris.features.definition import (
        BackgroundLoopTask,
        FeatureDefinition,
        FeatureKind,
        LearningHook,
        RuntimeLearningHook,
    )
    from iris.runtime.config import IrisRuntimeConfig


class RuntimeFeatureMode(StrEnum):
    """Feature selection が用いる runtime mode。"""

    DEVELOPMENT = "development"
    PRODUCTION_LIKE = "production_like"


class RuntimeFeatureDisabledReason(StrEnum):
    """Feature が標準 catalog から除外された理由。"""

    PRODUCTION_LIKE_MODE = "production_like_mode"


@dataclass(frozen=True)
class DisabledRuntimeFeature:
    """無効化された feature と理由。"""

    name: str
    kind: FeatureKind
    reason: RuntimeFeatureDisabledReason


@dataclass(frozen=True)
class RuntimeFeatureCatalog:
    """標準ランタイムで選択されたフィーチャー定義の集合。"""

    features: tuple[FeatureDefinition, ...]
    disabled_features: tuple[DisabledRuntimeFeature, ...] = ()
    mode: RuntimeFeatureMode = RuntimeFeatureMode.DEVELOPMENT


@dataclass(frozen=True)
class RuntimeFeatureSelectionOptions:
    """feature selection に必要な既存 runtime mode の snapshot。"""

    safety_mode: str = "development"

    @classmethod
    def from_config(cls, config: IrisRuntimeConfig) -> RuntimeFeatureSelectionOptions:
        """Runtime config から feature selection option を抽出する。

        Returns:
            feature selection 用の最小設定。
        """
        return cls(safety_mode=config.safety.mode)


def wire_runtime_features(
    options: RuntimeFeatureSelectionOptions | IrisRuntimeConfig | None = None,
) -> RuntimeFeatureCatalog:
    """標準ランタイムのフィーチャー集合を組み立てる。

    diagnostic feature は既存の safety.mode が development の場合だけ登録する。
    production-like mode では通常応答候補に混ぜない。

    配送結果だけでは明示的ユーザー入力を復元できないため、標準 catalog は
    memory enqueue hook を登録しない。十分な typed context を持つ integration が
    `LearningHook` として明示注入する。

    Returns:
        選択済みフィーチャー定義と無効化理由。
    """
    selection_options = _normalize_feature_selection_options(options)
    mode = _runtime_feature_mode(selection_options.safety_mode)
    companion_features = (define_event_reaction_feature(),)
    diagnostic_feature = define_basic_action_feature()
    if mode is RuntimeFeatureMode.DEVELOPMENT:
        return RuntimeFeatureCatalog(
            features=(diagnostic_feature, *companion_features),
            mode=mode,
        )
    return RuntimeFeatureCatalog(
        features=companion_features,
        disabled_features=(
            DisabledRuntimeFeature(
                name=diagnostic_feature.name,
                kind=diagnostic_feature.kind,
                reason=RuntimeFeatureDisabledReason.PRODUCTION_LIKE_MODE,
            ),
        ),
        mode=mode,
    )


def _normalize_feature_selection_options(
    options: RuntimeFeatureSelectionOptions | IrisRuntimeConfig | None,
) -> RuntimeFeatureSelectionOptions:
    if options is None:
        return RuntimeFeatureSelectionOptions()
    if isinstance(options, RuntimeFeatureSelectionOptions):
        return options
    return RuntimeFeatureSelectionOptions.from_config(options)


def _runtime_feature_mode(safety_mode: str) -> RuntimeFeatureMode:
    if safety_mode == "development":
        return RuntimeFeatureMode.DEVELOPMENT
    return RuntimeFeatureMode.PRODUCTION_LIKE


def collect_cognitive_steps(
    features: Sequence[FeatureDefinition],
) -> tuple[PipelineStep[PipelineStepResult], ...]:
    """有効なフィーチャーの認知ステップを登録順に収集する。

    Args:
        features: composition root で有効化されたフィーチャー定義。

    Returns:
        CognitiveCycle の拡張位置へ注入する認知ステップ。
    """
    return collect_feature_items(tuple(feature.cognitive_steps for feature in features))


def collect_action_plan_presenters(
    features: Sequence[FeatureDefinition],
) -> tuple[ActionPlanPresenter, ...]:
    """有効なフィーチャーのプレゼンターを登録順に収集する。

    Args:
        features: composition root で有効化されたフィーチャー定義。

    Returns:
        PresentationSuite へ注入するプレゼンター。
    """
    return collect_feature_items(
        tuple(feature.action_plan_presenters for feature in features),
    )


def collect_learning_hooks(
    features: Sequence[FeatureDefinition],
) -> tuple[LearningHook, ...]:
    """学習フックをフィーチャー登録順に収集する。

    Returns:
        登録順の学習フック。
    """
    return collect_feature_items(tuple(feature.learning_hooks for feature in features))


def collect_runtime_learning_hooks(
    features: Sequence[FeatureDefinition],
) -> tuple[RuntimeLearningHook, ...]:
    """runtime学習フックをフィーチャー登録順に収集する。

    Returns:
        登録順のruntimeフック。
    """
    return collect_feature_items(tuple(feature.runtime_learning_hooks for feature in features))


def collect_background_loop_tasks(
    features: Sequence[FeatureDefinition],
) -> tuple[BackgroundLoopTask, ...]:
    """Feature-owned periodic task をフィーチャー登録順に収集する。

    Returns:
        登録順の periodic task。
    """
    return collect_feature_items(tuple(feature.background_loop_tasks for feature in features))


def wire_proactive_talk_feature(salience_threshold: float = 0.5) -> FeatureDefinition:
    """Proactive talk 機能の定義を組み立てる。

    Args:
        salience_threshold: 能動的開始を行うためのサリエンス最小値。

    Returns:
        proactive talk 用の FeatureDefinition。
    """
    return define_proactive_talk_feature(salience_threshold=salience_threshold)


def collect_feature_items[FeatureItemT](
    feature_item_groups: Sequence[Sequence[FeatureItemT]],
) -> tuple[FeatureItemT, ...]:
    """FeatureDefinition 群の属性列を順序どおりに平坦化する。

    Returns:
        順序を保って連結した要素列。
    """
    return tuple(item for group in feature_item_groups for item in group)


def wire_proactive_talk_cognitive_cycle(
    memory_store: MemoryStore | None = None,
    relationship_store: RelationshipStore | None = None,
    salience_threshold: float = 0.5,
) -> CognitiveCycle:
    """Proactive talk 機能で拡張された認知サイクルを組み立てる。

    Args:
        memory_store: 任意の取得用メモリストア。
        relationship_store: 任意の共有関係性 state store。
        salience_threshold: 能動的開始を行うためのサリエンス最小値。

    Returns:
        知覚・メモリ・感情・ポリシー・proactive talk パイプラインステップを含む CognitiveCycle。
    """
    feature = wire_proactive_talk_feature(salience_threshold=salience_threshold)
    return wire_core_cognitive_cycle(
        stores=CognitiveCycleStores(
            memory_store=memory_store,
            relationship_store=relationship_store,
        ),
        extension_steps=collect_cognitive_steps((feature,)),
    )
