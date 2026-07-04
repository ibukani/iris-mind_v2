"""Companion behavior向け appraisal semantics の型付き契約。"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from iris.contracts.companion_affect import CompanionAffectStateKind
from iris.contracts.metadata import ImmutableMetadata
from iris.core.ids import ObservationId
from iris.core.metadata import immutable_metadata


class AppraisalSignalKind(StrEnum):
    """Appraisal result が表す意味種別。"""

    USER_EMOTION = "user_emotion"
    ATTITUDE_TOWARD_IRIS = "attitude_toward_iris"
    TOPIC_SENTIMENT = "topic_sentiment"
    CARE_INTENT = "care_intent"
    DEPENDENCY_RISK_HINT = "dependency_risk_hint"


class AppraisalSafetyHintKind(StrEnum):
    """Safety boundary が後続で参照できる appraisal hint 種別。"""

    DEPENDENCY_RISK = "dependency_risk"


class AppraisalSourceSpan(BaseModel):
    """Signal の根拠となった入力断片。"""

    model_config = ConfigDict(frozen=True)

    start_index: int = Field(ge=0)
    end_index: int = Field(ge=0)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_span(self) -> AppraisalSourceSpan:
        """Span の index が前方範囲になっていることを検証する。

        Returns:
            AppraisalSourceSpan: 検証済みの self。

        Raises:
            ValueError: end_index が start_index 以下の場合。
        """
        if self.end_index <= self.start_index:
            message = "end_index must be greater than start_index"
            raise ValueError(message)
        return self


class AppraisalSignal(BaseModel):
    """後続の state update / safety が参照する typed appraisal signal。"""

    model_config = ConfigDict(frozen=True)

    kind: AppraisalSignalKind
    label: str = Field(min_length=1)
    polarity: float = Field(default=0.0, ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)
    source_span: AppraisalSourceSpan
    state_boundary: CompanionAffectStateKind | None = None
    safety_hint: AppraisalSafetyHintKind | None = None
    source_observation_id: ObservationId | None = None
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)

    @model_validator(mode="after")
    def _validate_signal_boundary(self) -> AppraisalSignal:
        """Signal kind と state/safety boundary の矛盾を早期に拒否する。

        Returns:
            AppraisalSignal: 検証済みの self。

        Raises:
            ValueError: kind と state/safety boundary が矛盾する場合。
        """
        expected_boundary = appraisal_state_boundary_for_kind(self.kind)
        if self.state_boundary != expected_boundary:
            message = (
                f"{self.kind.value} signal requires state_boundary="
                f"{expected_boundary.value if expected_boundary is not None else None}"
            )
            raise ValueError(message)
        if (
            self.kind is AppraisalSignalKind.DEPENDENCY_RISK_HINT
            and self.safety_hint is not AppraisalSafetyHintKind.DEPENDENCY_RISK
        ):
            message = "dependency_risk_hint requires dependency_risk safety_hint"
            raise ValueError(message)
        if (
            self.kind is not AppraisalSignalKind.DEPENDENCY_RISK_HINT
            and self.safety_hint is not None
        ):
            message = "only dependency_risk_hint may carry a safety_hint in this contract"
            raise ValueError(message)
        return self


class AppraisalSemantics(BaseModel):
    """1ターンの appraisal typed signal 群。"""

    model_config = ConfigDict(frozen=True)

    signals: tuple[AppraisalSignal, ...] = ()
    summary: str | None = None

    def signals_by_kind(self, kind: AppraisalSignalKind) -> tuple[AppraisalSignal, ...]:
        """指定 kind の signal だけを安定順で返す。

        Returns:
            tuple[AppraisalSignal, ...]: 指定 kind の signal 群。
        """
        return tuple(signal for signal in self.signals if signal.kind is kind)


APPRAISAL_RELATIONSHIP_CANDIDATE_SIGNAL_KINDS: tuple[AppraisalSignalKind, ...] = (
    AppraisalSignalKind.ATTITUDE_TOWARD_IRIS,
)
"""Relationship policy v2 が bounded candidate として参照できる appraisal signal kind。"""


APPRAISAL_WORKER_READABLE_SIGNAL_KINDS: tuple[AppraisalSignalKind, ...] = tuple(AppraisalSignalKind)
"""#72 worker が raw score ではなく参照できる typed signal kind。"""


def appraisal_state_boundary_for_kind(
    kind: AppraisalSignalKind,
) -> CompanionAffectStateKind | None:
    """Appraisal signal と #104 state boundary の対応を返す。

    Returns:
        CompanionAffectStateKind | None: signal が所属する state boundary。
    """
    match kind:
        case AppraisalSignalKind.USER_EMOTION:
            return CompanionAffectStateKind.ACTOR_AFFECT_TRACE
        case AppraisalSignalKind.ATTITUDE_TOWARD_IRIS:
            return CompanionAffectStateKind.ACTOR_RELATIONSHIP
        case AppraisalSignalKind.TOPIC_SENTIMENT | AppraisalSignalKind.CARE_INTENT:
            return CompanionAffectStateKind.RECENT_INTERACTION_TONE
        case AppraisalSignalKind.DEPENDENCY_RISK_HINT:
            return None
