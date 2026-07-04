"""高リスク安全文脈を検出する副作用なしの認知ステップ。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from iris.cognitive.cycle.models import SafetyContextResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.cognitive.workspace.frame import interpreted_input_text
from iris.contracts.observations import ActorMessageObservation, IdleTickObservation
from iris.contracts.safety import (
    SafetyContext,
    SafetyContextCategory,
    SafetyContextReason,
    SafetyContextSeverity,
    SafetyContextSource,
    SafetyResponseDirective,
)

if TYPE_CHECKING:
    from iris.cognitive.workspace.frame import WorkspaceFrame


@dataclass(frozen=True)
class SafetyContextClassification:
    """分類器が返す安全文脈の集合。"""

    contexts: tuple[SafetyContext, ...] = ()


class DeterministicSafetyContextClassifier:
    """外部 provider に依存しない決定論的な初期安全文脈分類器。"""

    @staticmethod
    def classify(
        *,
        text: str | None,
        source: SafetyContextSource,
    ) -> SafetyContextClassification:
        """入力テキストを高リスク安全文脈へ分類する。

        Raw text は返却せず、固定 reason code と説明だけを返す。

        Args:
            text: 判定対象の解釈済み入力。None または空白のみなら文脈なし。
            source: 入力の発生源。

        Returns:
            検出した安全文脈の集合。
        """
        if text is None or not text.strip():
            return SafetyContextClassification()
        normalized = text.casefold()
        contexts = tuple(_classify_text(normalized, source))
        return SafetyContextClassification(contexts=contexts)


class SafetyContextClassificationStep(PipelineStep[SafetyContextResult]):
    """policy enforcement 前に typed safety context を生成するステップ。"""

    name = "safety_context_classification"

    def __init__(
        self,
        classifier: DeterministicSafetyContextClassifier | None = None,
    ) -> None:
        """分類器を注入して初期化する。

        Args:
            classifier: 副作用なしの安全文脈分類器。省略時は決定論的分類器。
        """
        self._classifier = classifier or DeterministicSafetyContextClassifier()

    @override
    async def run(self, frame: WorkspaceFrame) -> SafetyContextResult:
        """WorkspaceFrame から安全文脈を分類する。

        Returns:
            typed safety context を含むステップ結果。
        """
        classification = self._classifier.classify(
            text=interpreted_input_text(frame),
            source=_source_for_frame(frame),
        )
        return SafetyContextResult(
            step_name=self.name,
            status=StepStatus.OK,
            safety_contexts=classification.contexts,
        )


def _source_for_frame(frame: WorkspaceFrame) -> SafetyContextSource:
    observation = frame.observation
    if isinstance(observation, ActorMessageObservation):
        return SafetyContextSource.USER_INITIATED
    if isinstance(observation, IdleTickObservation):
        return SafetyContextSource.PROACTIVE
    return SafetyContextSource.USER_INITIATED


def _classify_text(
    normalized: str,
    source: SafetyContextSource,
) -> tuple[SafetyContext, ...]:
    context: SafetyContext | None = None
    if _mentions_self_harm(normalized):
        context = _self_harm_context(normalized, source)
    elif _mentions_abuse(normalized):
        context = _abuse_context(source)
    elif _requests_dangerous_instruction(normalized):
        context = _dangerous_instruction_context(source)
    elif _requests_personal_data_misuse(normalized):
        context = _personal_data_context(source)
    return () if context is None else (context,)


def _mentions_self_harm(normalized: str) -> bool:
    terms = (
        "kill myself",
        "suicide",
        "self harm",
        "self-harm",
        "end my life",
        "自殺",
        "自傷",
        "死にたい",
    )
    return any(term in normalized for term in terms)


def _mentions_abuse(normalized: str) -> bool:
    terms = ("abuse", "abused", "domestic violence", "虐待", "dv")
    return any(term in normalized for term in terms)


def _requests_dangerous_instruction(normalized: str) -> bool:
    dangerous_terms = ("bomb", "poison", "weapon", "爆弾", "毒物", "武器")
    instruction_terms = ("how to", "make", "build", "create", "作り方", "作る")
    return any(term in normalized for term in dangerous_terms) and any(
        term in normalized for term in instruction_terms
    )


def _requests_personal_data_misuse(normalized: str) -> bool:
    credential_terms = ("password", "token", "api key", "credential", "パスワード")
    misuse_terms = ("steal", "leak", "exfiltrate", "bypass", "盗", "漏洩")
    return any(term in normalized for term in credential_terms) and any(
        term in normalized for term in misuse_terms
    )


def _self_harm_context(
    normalized: str,
    source: SafetyContextSource,
) -> SafetyContext:
    directive = SafetyResponseDirective.ALLOW_SUPPORT
    reason = _reason(
        code="self_harm_support_signal",
        description="Input indicates self-harm distress; supportive response is allowed.",
    )
    if _asks_for_self_harm_method(normalized):
        directive = SafetyResponseDirective.SAFE_REDIRECT
        reason = _reason(
            code="self_harm_method_request",
            description="Input requests actionable self-harm guidance; safe redirect is required.",
        )
    return SafetyContext(
        category=SafetyContextCategory.SELF_HARM,
        severity=SafetyContextSeverity.HIGH,
        source=source,
        confidence=0.9,
        reasons=(reason,),
        directive=directive,
    )


def _asks_for_self_harm_method(normalized: str) -> bool:
    request_terms = ("how to", "method", "way to", "tell me how", "方法", "やり方")
    return any(term in normalized for term in request_terms)


def _abuse_context(source: SafetyContextSource) -> SafetyContext:
    return SafetyContext(
        category=SafetyContextCategory.ABUSE,
        severity=SafetyContextSeverity.MEDIUM,
        source=source,
        confidence=0.78,
        reasons=(
            _reason(
                code="abuse_or_violence_disclosure",
                description="Input indicates possible abuse or interpersonal violence disclosure.",
            ),
        ),
        directive=SafetyResponseDirective.ALLOW_SUPPORT,
    )


def _dangerous_instruction_context(source: SafetyContextSource) -> SafetyContext:
    return SafetyContext(
        category=SafetyContextCategory.ILLEGAL_OR_DANGEROUS,
        severity=SafetyContextSeverity.HIGH,
        source=source,
        confidence=0.86,
        reasons=(
            _reason(
                code="dangerous_instruction_request",
                description="Input requests instructions for dangerous physical harm capability.",
            ),
        ),
        directive=SafetyResponseDirective.REFUSE,
    )


def _personal_data_context(source: SafetyContextSource) -> SafetyContext:
    return SafetyContext(
        category=SafetyContextCategory.PERSONAL_DATA,
        severity=SafetyContextSeverity.HIGH,
        source=source,
        confidence=0.82,
        reasons=(
            _reason(
                code="personal_data_misuse_request",
                description="Input requests credential or personal data misuse.",
            ),
        ),
        directive=SafetyResponseDirective.REFUSE,
    )


def _reason(*, code: str, description: str) -> SafetyContextReason:
    return SafetyContextReason(code=code, description=description)
