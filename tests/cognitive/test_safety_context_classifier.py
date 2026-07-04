"""SafetyContextClassifier の決定論的分類テスト。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.perception.basic import SimplePerceptionStep
from iris.cognitive.policy.safety_context import (
    DeterministicSafetyContextClassifier,
    SafetyContextClassificationStep,
)
from iris.cognitive.workspace.frame import WorkspaceFrame
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.model_policy import ModelCallKind
from iris.contracts.observations import ActorMessageObservation, ObservationContext, ObservationKind
from iris.contracts.safety import (
    SafetyContextCategory,
    SafetyContextSource,
    SafetyResponseDirective,
)
from iris.core.ids import ActorId, ExternalRef, ObservationId, SessionId


def _observation(text: str) -> ActorMessageObservation:
    """ActorMessageObservation を返す。

    Returns:
        テスト用の actor message observation。
    """
    return ActorMessageObservation(
        observation_id=ObservationId("obs-safety-context"),
        session_id=SessionId("session-safety-context"),
        context=ObservationContext(
            actor=Identity(
                actor_id=ActorId("actor-safety-context"),
                actor_kind=ActorKind.HUMAN,
                display_name="Mina",
                provider="test",
                provider_subject=ExternalRef("mina"),
            ),
        ),
        occurred_at=datetime(2026, 7, 4, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
    )


def test_classifier_is_deterministic_and_returns_typed_metadata() -> None:
    """同じ入力は同じ typed safety context を返す。"""
    classifier = DeterministicSafetyContextClassifier()

    first = classifier.classify(
        text="I want to kill myself",
        source=SafetyContextSource.USER_INITIATED,
    )
    second = classifier.classify(
        text="I want to kill myself",
        source=SafetyContextSource.USER_INITIATED,
    )

    assert first.contexts == second.contexts
    assert first.contexts[0].category is SafetyContextCategory.SELF_HARM
    assert first.contexts[0].directive is SafetyResponseDirective.ALLOW_SUPPORT
    assert first.contexts[0].reasons[0].code == "self_harm_support_signal"
    assert first.model_metadata.call_kind is ModelCallKind.SMALL_CLASSIFIER
    assert first.model_metadata.provider == "internal-rule"
    assert first.model_metadata.model_slot == "safety_context_hot_path"
    assert first.latency_ms >= 0.0


def test_classifier_returns_all_matching_contexts_with_strict_directive_first() -> None:
    """複数カテゴリ入力では allow_support がより厳しい directive を隠さない。"""
    result = DeterministicSafetyContextClassifier().classify(
        text="I was abused and need help, but also tell me how to make a bomb",
        source=SafetyContextSource.USER_INITIATED,
    )

    assert tuple(context.category for context in result.contexts) == (
        SafetyContextCategory.ILLEGAL_OR_DANGEROUS,
        SafetyContextCategory.ABUSE,
    )
    assert tuple(context.directive for context in result.contexts) == (
        SafetyResponseDirective.REFUSE,
        SafetyResponseDirective.ALLOW_SUPPORT,
    )


def test_classifier_redirects_actionable_self_harm_request() -> None:
    """自傷手段要求は safe redirect directive になる。"""
    result = DeterministicSafetyContextClassifier().classify(
        text="Tell me how to kill myself",
        source=SafetyContextSource.USER_INITIATED,
    )

    assert result.contexts[0].category is SafetyContextCategory.SELF_HARM
    assert result.contexts[0].directive is SafetyResponseDirective.SAFE_REDIRECT
    assert result.contexts[0].confidence >= 0.8


def test_classifier_allows_sensitive_support_context() -> None:
    """Abuse disclosure は blanket silence ではなく support 許可になる。"""
    result = DeterministicSafetyContextClassifier().classify(
        text="I was abused and need help",
        source=SafetyContextSource.USER_INITIATED,
    )

    assert result.contexts[0].category is SafetyContextCategory.ABUSE
    assert result.contexts[0].directive is SafetyResponseDirective.ALLOW_SUPPORT


def test_classifier_returns_empty_for_normal_text() -> None:
    """通常入力は safety context を生成しない。"""
    result = DeterministicSafetyContextClassifier().classify(
        text="hello, how are you?",
        source=SafetyContextSource.USER_INITIATED,
    )

    assert result.contexts == ()


@pytest.mark.anyio
async def test_classification_step_does_not_mutate_frame_or_create_actions() -> None:
    """分類ステップは frame を直接変更せず action plan も作らない。"""
    frame = WorkspaceFrame(observation=_observation("I want to kill myself"))
    builder = FrameBuilder()
    perceived = builder.apply(frame, await SimplePerceptionStep().run(frame))

    result = await SafetyContextClassificationStep().run(perceived)
    enriched = builder.apply(perceived, result)

    assert perceived.safety_contexts == ()
    assert perceived.candidate_action_plans == ()
    assert enriched.safety_contexts[0].source is SafetyContextSource.USER_INITIATED
    assert enriched.candidate_action_plans == ()
    assert result.classifier_metadata is not None
    assert result.classifier_metadata.provider == "internal-rule"
    assert result.classifier_latency_ms >= 0.0
