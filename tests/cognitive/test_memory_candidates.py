"""MemoryCandidate と RuleBasedMemoryCandidateExtractor のテスト。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from iris.cognitive.cycle.frame_builder import FrameBuilder
from iris.cognitive.cycle.models import PerceptionResult, StepStatus
from iris.cognitive.memory.candidates import (
    MemoryCandidateSensitivity,
    MemoryCandidateSource,
    MemoryRetentionPolicy,
)
from iris.cognitive.memory.extraction import RuleBasedMemoryCandidateExtractor
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.memory import MemoryKind
from iris.contracts.observations import ActorMessageObservation, ObservationContext, ObservationKind
from iris.core.ids import ActorId, ExternalRef, ObservationId, SessionId, SpaceId

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import WorkspaceFrame


def _build_frame(text: str) -> WorkspaceFrame:
    """指定テキストを持つ ActorMessageObservation から WorkspaceFrame を構築する。

    Returns:
        WorkspaceFrame: 構築されたフレーム。
    """
    observation = ActorMessageObservation(
        observation_id=ObservationId("obs-1"),
        session_id=SessionId("session-1"),
        context=ObservationContext(),
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
    )
    frame = FrameBuilder().build_initial(observation)
    return FrameBuilder().apply(
        frame,
        PerceptionResult(step_name="perception", status=StepStatus.OK, text=text),
    )


def _build_frame_with_actor(
    text: str, actor_id: str, space_id: str | None = None
) -> WorkspaceFrame:
    """Actor / space コンテキストを持つフレームを構築する。

    Returns:
        WorkspaceFrame: 構築されたフレーム。
    """
    observation = ActorMessageObservation(
        observation_id=ObservationId("obs-1"),
        session_id=SessionId("session-1"),
        context=ObservationContext(
            actor=Identity(
                actor_id=ActorId(actor_id),
                actor_kind=ActorKind.HUMAN,
                display_name="Test",
                provider="test",
                provider_subject=ExternalRef("test"),
            ),
            space_id=SpaceId(space_id) if space_id else None,
        ),
        occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
    )
    frame = FrameBuilder().build_initial(observation)
    return FrameBuilder().apply(
        frame,
        PerceptionResult(step_name="perception", status=StepStatus.OK, text=text),
    )


def test_rule_based_extractor_detects_explicit_remember_request() -> None:
    """「覚えて」パターンから候補が抽出されることを確認する。"""
    extractor = RuleBasedMemoryCandidateExtractor()
    frame = _build_frame("覚えて: 今日の会議は15時から")

    candidates = extractor.extract(frame)
    assert len(candidates) >= 1
    assert any(c.text == "今日の会議は15時から" for c in candidates)
    assert any(c.kind == MemoryKind.NOTE for c in candidates)
    assert candidates[0].source is MemoryCandidateSource.EXPLICIT_USER_REQUEST
    assert candidates[0].retention_policy is MemoryRetentionPolicy.DURABLE
    assert candidates[0].sensitivity is MemoryCandidateSensitivity.NORMAL
    assert candidates[0].reason
    assert candidates[0].review_required is False


def test_rule_based_extractor_detects_user_preference() -> None:
    """「私は〜が好き」パターンから PREFERENCE 候補が抽出されることを確認する。"""
    extractor = RuleBasedMemoryCandidateExtractor()
    frame = _build_frame("私はジャスミン茶が好き")

    candidates = extractor.extract(frame)
    assert len(candidates) >= 1
    assert any(c.kind == MemoryKind.PREFERENCE for c in candidates)
    assert any("ジャスミン茶" in c.text for c in candidates)
    assert candidates[0].source is MemoryCandidateSource.EXPLICIT_PREFERENCE_STATEMENT
    assert candidates[0].retention_policy is MemoryRetentionPolicy.LONG_TERM


def test_rule_based_extractor_detects_explicit_user_name_statement() -> None:
    """明示的な名前文から FACT 候補を抽出する。"""
    extractor = RuleBasedMemoryCandidateExtractor()
    frame = _build_frame("私の名前は太郎です")

    candidates = extractor.extract(frame)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.kind is MemoryKind.FACT
    assert candidate.text == "ユーザーの名前は「太郎」。"
    assert candidate.source is MemoryCandidateSource.EXPLICIT_PROFILE_STATEMENT
    assert candidate.retention_policy is MemoryRetentionPolicy.UNTIL_CHANGED
    assert candidate.sensitivity is MemoryCandidateSensitivity.PERSONAL
    assert candidate.reason == "user stated their name"


def test_rule_based_extractor_detects_preferred_name_request() -> None:
    """希望呼称の明示指示から PREFERENCE 候補を抽出する。"""
    extractor = RuleBasedMemoryCandidateExtractor()
    frame = _build_frame("太郎と呼んで")

    candidates = extractor.extract(frame)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.kind is MemoryKind.PREFERENCE
    assert candidate.text == "ユーザーの希望呼称は「太郎」。"
    assert candidate.source is MemoryCandidateSource.EXPLICIT_PROFILE_STATEMENT
    assert candidate.retention_policy is MemoryRetentionPolicy.UNTIL_CHANGED
    assert candidate.sensitivity is MemoryCandidateSensitivity.PERSONAL
    assert candidate.reason == "user stated their preferred name"


def test_rule_based_extractor_detects_stable_character_preference() -> None:
    """安定した好みの明示文から PREFERENCE 候補を抽出する。"""
    extractor = RuleBasedMemoryCandidateExtractor()
    frame = _build_frame("私はクールなキャラクターが好きです")

    candidates = extractor.extract(frame)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.kind is MemoryKind.PREFERENCE
    assert candidate.text == "ユーザーは「クールなキャラクター」が好き。"
    assert candidate.source is MemoryCandidateSource.EXPLICIT_PREFERENCE_STATEMENT
    assert candidate.retention_policy is MemoryRetentionPolicy.LONG_TERM
    assert candidate.sensitivity is MemoryCandidateSensitivity.NORMAL
    assert candidate.reason == "user stated a stable preference"


def test_rule_based_extractor_detects_response_style_preference() -> None:
    """応答スタイルの明示指示から PREFERENCE 候補を抽出する。"""
    extractor = RuleBasedMemoryCandidateExtractor()
    frame = _build_frame("今後は短めに答えて")

    candidates = extractor.extract(frame)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.kind is MemoryKind.PREFERENCE
    assert candidate.text == "ユーザーは回答を短め・簡潔にすることを希望している。"
    assert candidate.source is MemoryCandidateSource.EXPLICIT_USER_INSTRUCTION
    assert candidate.retention_policy is MemoryRetentionPolicy.UNTIL_CHANGED
    assert candidate.sensitivity is MemoryCandidateSensitivity.NORMAL
    assert candidate.reason == "user stated a response style preference"


def test_rule_based_extractor_detects_language_preference() -> None:
    """言語設定の明示指示から PREFERENCE 候補を抽出する。"""
    extractor = RuleBasedMemoryCandidateExtractor()
    frame = _build_frame("日本語で答えてほしい")

    candidates = extractor.extract(frame)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.kind is MemoryKind.PREFERENCE
    assert candidate.text == "ユーザーは日本語での応答を希望している。"
    assert candidate.source is MemoryCandidateSource.EXPLICIT_USER_INSTRUCTION
    assert candidate.retention_policy is MemoryRetentionPolicy.UNTIL_CHANGED
    assert candidate.sensitivity is MemoryCandidateSensitivity.NORMAL
    assert candidate.reason == "user stated a language preference"


def test_rule_based_extractor_detects_project_doc_language_policy() -> None:
    """「日本語で書いてほしい」パターンから PREFERENCE 候補が抽出されることを確認する。"""
    extractor = RuleBasedMemoryCandidateExtractor()
    frame = _build_frame("Iris の人間向けドキュメントは日本語で書いてほしい")

    candidates = extractor.extract(frame)
    assert len(candidates) >= 1
    assert any(c.kind == MemoryKind.PREFERENCE for c in candidates)
    assert any("Iris" in c.text for c in candidates)
    assert candidates[0].source is MemoryCandidateSource.EXPLICIT_USER_INSTRUCTION


def test_rule_based_extractor_skips_dont_save() -> None:
    """「保存しないで」パターンでは空リストを返すことを確認する。"""
    extractor = RuleBasedMemoryCandidateExtractor()
    frame = _build_frame("この話は保存しないで")

    candidates = extractor.extract(frame)
    assert candidates == ()


def test_rule_based_extractor_returns_empty_for_no_text() -> None:
    """interpreted_input が None の場合、空リストを返すことを確認する。"""
    extractor = RuleBasedMemoryCandidateExtractor()
    frame = _build_frame("")

    candidates = extractor.extract(frame)
    assert candidates == ()


def test_rule_based_extractor_includes_actor_and_space_scope() -> None:
    """抽出された候補に actor_id と space_id が含まれることを確認する。"""
    extractor = RuleBasedMemoryCandidateExtractor()
    frame = _build_frame_with_actor(
        "覚えて: テストメモ",
        actor_id="alice",
        space_id="space-1",
    )

    candidates = extractor.extract(frame)
    assert len(candidates) >= 1
    candidate = candidates[0]
    assert candidate.actor_id == ActorId("alice")
    assert candidate.space_id == SpaceId("space-1")
    assert candidate.source_observation_id == ObservationId("obs-1")
