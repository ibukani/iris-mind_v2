"""Runtime feature selection policy のテスト。"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from iris.features.basic_action.definition import DiagnosticEchoActionSelectionStep
from iris.features.definition import FeatureKind
from iris.presentation.action_plan import DefaultActionPlanPresenter
from iris.runtime.config import default_runtime_config
from iris.runtime.wiring.features import (
    RuntimeFeatureDisabledReason,
    RuntimeFeatureMode,
    RuntimeFeatureSelectionOptions,
    collect_action_plan_presenters,
    collect_cognitive_steps,
    wire_runtime_features,
)
from iris.runtime.wiring.runtime import describe_runtime_operational_wiring

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.features.definition import FeatureDefinition


def _feature_names(catalog_features: Sequence[FeatureDefinition]) -> tuple[str, ...]:
    return tuple(feature.name for feature in catalog_features)


def test_development_mode_enables_diagnostic_basic_action() -> None:
    """Development mode では既存 mode 境界により diagnostic basic_action を使える。"""
    catalog = wire_runtime_features(RuntimeFeatureSelectionOptions(safety_mode="development"))

    assert catalog.mode is RuntimeFeatureMode.DEVELOPMENT
    assert _feature_names(catalog.features) == ("basic_action", "event_reaction")
    assert catalog.disabled_features == ()


def test_basic_mode_disables_diagnostic_action() -> None:
    """Basic mode は production-like として diagnostic action を除外する。"""
    catalog = wire_runtime_features(RuntimeFeatureSelectionOptions(safety_mode="basic"))

    assert catalog.mode is RuntimeFeatureMode.PRODUCTION_LIKE
    assert _feature_names(catalog.features) == ("event_reaction",)
    assert len(catalog.disabled_features) == 1
    disabled = catalog.disabled_features[0]
    assert disabled.name == "basic_action"
    assert disabled.kind is FeatureKind.DIAGNOSTIC
    assert disabled.reason is RuntimeFeatureDisabledReason.PRODUCTION_LIKE_MODE


def test_strict_mode_disables_diagnostic_action() -> None:
    """Strict mode でも diagnostic action を通常応答候補から除外する。"""
    catalog = wire_runtime_features(RuntimeFeatureSelectionOptions(safety_mode="strict"))

    assert catalog.mode is RuntimeFeatureMode.PRODUCTION_LIKE
    assert _feature_names(catalog.features) == ("event_reaction",)
    assert catalog.disabled_features[0].reason is RuntimeFeatureDisabledReason.PRODUCTION_LIKE_MODE


def test_production_like_catalog_does_not_collect_diagnostic_steps_or_presenters() -> None:
    """production-like catalog は diagnostic cognitive step / presenter を収集しない。"""
    catalog = wire_runtime_features(RuntimeFeatureSelectionOptions(safety_mode="basic"))

    steps = collect_cognitive_steps(catalog.features)
    assert not any(isinstance(step, DiagnosticEchoActionSelectionStep) for step in steps)
    presenters = collect_action_plan_presenters(catalog.features)
    assert not any(isinstance(presenter, DefaultActionPlanPresenter) for presenter in presenters)


def test_operational_wiring_reports_feature_selection_metadata() -> None:
    """Doctor 用 wiring diagnostics は mode / enabled / disabled feature を保持する。"""
    config = default_runtime_config()
    config = replace(config, safety=replace(config.safety, mode="basic"))

    diagnostics = describe_runtime_operational_wiring(config)

    assert diagnostics.runtime_feature_mode == "production_like"
    assert diagnostics.enabled_feature_names == ("event_reaction",)
    assert len(diagnostics.disabled_features) == 1
    assert diagnostics.disabled_features[0].name == "basic_action"


def test_event_reaction_generation_is_fail_closed_outside_development() -> None:
    """#83未完了のproduction-like modeでは生成器を有効化しない。"""
    base = default_runtime_config()
    config = replace(
        base,
        safety=replace(base.safety, mode="strict"),
        companion_semantics=replace(
            base.companion_semantics,
            event_reaction_generation_enabled=True,
        ),
    )

    diagnostics = describe_runtime_operational_wiring(config)

    assert diagnostics.event_reaction_generation_enabled is False
    assert diagnostics.event_reaction_generation_mode == "blocked_production_like_mode"


def test_proactive_generation_is_enabled_only_in_development() -> None:
    """Proactive generation は development の明示設定だけで feature catalog に入る。"""
    base = default_runtime_config()
    config = replace(
        base,
        companion_semantics=replace(
            base.companion_semantics,
            proactive_talk_generation_enabled=True,
        ),
    )

    diagnostics = describe_runtime_operational_wiring(config)

    assert diagnostics.proactive_talk_enabled is True
    assert diagnostics.proactive_generation_mode == "enabled"
    assert diagnostics.enabled_feature_names == (
        "basic_action",
        "event_reaction",
        "proactive_talk",
    )


def test_proactive_generation_is_fail_closed_outside_development() -> None:
    """#83 完了前の production-like mode では proactive generation を除外する。"""
    base = default_runtime_config()
    config = replace(
        base,
        safety=replace(base.safety, mode="strict"),
        companion_semantics=replace(
            base.companion_semantics,
            proactive_talk_generation_enabled=True,
        ),
    )

    diagnostics = describe_runtime_operational_wiring(config)

    assert diagnostics.proactive_talk_enabled is False
    assert diagnostics.proactive_generation_mode == "blocked_production_like_mode"
    assert tuple(item.name for item in diagnostics.disabled_features) == (
        "basic_action",
        "proactive_talk",
    )
