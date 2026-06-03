from __future__ import annotations

from dataclasses import replace

from iris.cognitive.cycle.models import RelationshipResult, StepStatus
from iris.cognitive.cycle.pipeline import PipelineStep
from iris.cognitive.workspace.frame import AffectSnapshot, RelationshipSnapshot, WorkspaceFrame
from iris.core.ids import UserId


class InMemoryRelationshipState:
    def __init__(self) -> None:
        self._snapshots: dict[UserId, RelationshipSnapshot] = {}

    def get(self, user_id: UserId, user_label: str | None = None) -> RelationshipSnapshot:
        snapshot = self._snapshots.get(user_id)
        if snapshot is not None:
            return snapshot
        return RelationshipSnapshot(
            user_label=user_label,
            affinity=0.0,
            trust=0.5,
            familiarity=0.0,
            relationship_summary=_summarize(user_label, 0.0, 0.5, 0.0),
        )

    def set(self, user_id: UserId, snapshot: RelationshipSnapshot) -> None:
        self._snapshots[user_id] = snapshot


class RelationshipStep(PipelineStep[RelationshipResult]):
    name = "relationship"

    def __init__(self, state: InMemoryRelationshipState | None = None) -> None:
        self._state = state if state is not None else InMemoryRelationshipState()

    async def run(self, frame: WorkspaceFrame) -> RelationshipResult:
        actor = frame.observation.actor
        if actor is None:
            return RelationshipResult(
                step_name=self.name,
                status=StepStatus.SKIPPED,
                reason="no actor identity",
            )

        snapshot = self._state.get(actor.user_id, actor.display_name)
        updated = update_relationship(snapshot, frame.affect)
        self._state.set(actor.user_id, updated)
        return RelationshipResult(
            step_name=self.name,
            status=StepStatus.OK,
            user_label=updated.user_label,
            affinity=updated.affinity,
            trust=updated.trust,
            familiarity=updated.familiarity,
            relationship_summary=updated.relationship_summary,
        )


def update_relationship(
    current: RelationshipSnapshot,
    affect: AffectSnapshot,
) -> RelationshipSnapshot:
    familiarity = _clamp01(current.familiarity + 0.02)
    affinity = _clamp_signed(current.affinity + affect.valence * 0.04)
    trust_delta = 0.015 if affect.valence > 0.1 else -0.01 if affect.valence < -0.1 else 0.0
    trust = _clamp01(current.trust + trust_delta)
    return replace(
        current,
        familiarity=familiarity,
        affinity=affinity,
        trust=trust,
        relationship_summary=_summarize(current.user_label, affinity, trust, familiarity),
    )


def _summarize(user_label: str | None, affinity: float, trust: float, familiarity: float) -> str:
    label = user_label or "unknown user"
    return f"{label} relationship(affinity={affinity:.2f}, trust={trust:.2f}, familiarity={familiarity:.2f})"


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _clamp_signed(value: float) -> float:
    return max(-1.0, min(1.0, value))
