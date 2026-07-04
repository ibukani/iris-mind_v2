"""小型テキスト分類器 adapter tests。"""

from __future__ import annotations

from iris.adapters.classifiers.fake import FakeClassificationCase, FakeTextClassifier
from iris.adapters.classifiers.rule import ClassificationRule, RuleBasedTextClassifier
from iris.contracts.classification import ClassificationFallbackPolicy, ClassificationRequest
from iris.contracts.model_policy import ModelCallKind
from tests.helpers.approx import approx


def test_fake_text_classifier_returns_deterministic_fixture_result() -> None:
    """FakeTextClassifier は同一入力に同一分類を返す。"""
    classifier = FakeTextClassifier(
        (
            FakeClassificationCase(
                text="hello iris",
                label="intent.chat",
                confidence=0.95,
                reason="fixture",
            ),
        )
    )
    request = ClassificationRequest(text="hello iris", model_slot="fast_judge")

    first = classifier.classify(request)
    second = classifier.classify(request)

    assert first == second
    assert first.label == "intent.chat"
    assert first.confidence == approx(0.95)
    assert first.reason == "fixture"
    assert first.model_metadata.call_kind is ModelCallKind.SMALL_CLASSIFIER
    assert first.model_metadata.provider == "fake"
    assert first.model_metadata.model_slot == "fast_judge"


def test_fake_text_classifier_unknowns_missing_fixture() -> None:
    """未定義入力は unknown に落ちる。"""
    classifier = FakeTextClassifier()

    result = classifier.classify(ClassificationRequest(text="unseen"))

    assert result.label == "unknown"
    assert result.confidence == approx(0.0)
    assert result.reason == "no fake classification fixture matched"


def test_fake_text_classifier_applies_low_confidence_fallback() -> None:
    """低信頼 fixture は fallback policy で unknown に正規化される。"""
    classifier = FakeTextClassifier(
        (FakeClassificationCase(text="maybe", label="intent.chat", confidence=0.4),),
        fallback_policy=ClassificationFallbackPolicy(confidence_threshold=0.7),
    )

    result = classifier.classify(ClassificationRequest(text="maybe"))

    assert result.label == "unknown"
    assert result.original_label == "intent.chat"
    assert result.fallback_applied is True


def test_rule_based_text_classifier_matches_keywords_in_order() -> None:
    """RuleBasedTextClassifier は上から順に keyword rule を評価する。"""
    classifier = RuleBasedTextClassifier(
        (
            ClassificationRule(
                label="risk.self_harm",
                keywords=("危険",),
                confidence=0.9,
                reason="risk keyword",
            ),
            ClassificationRule(label="intent.chat", keywords=("こんにちは",), confidence=0.8),
        )
    )

    result = classifier.classify(ClassificationRequest(text="これは危険かも"))

    assert result.label == "risk.self_harm"
    assert result.confidence == approx(0.9)
    assert result.reason == "risk keyword"
    assert result.model_metadata.provider == "rule"


def test_rule_based_text_classifier_respects_candidate_labels() -> None:
    """候補外 label は unknown に正規化される。"""
    classifier = RuleBasedTextClassifier(
        (ClassificationRule(label="risk.self_harm", keywords=("危険",), confidence=0.9),)
    )

    result = classifier.classify(
        ClassificationRequest(
            text="危険",
            candidate_labels=("intent.chat", "unknown"),
        )
    )

    assert result.label == "unknown"
    assert result.confidence == approx(0.0)
    assert result.reason == "classification label outside candidate labels"
