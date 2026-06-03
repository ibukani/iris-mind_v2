from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from iris.cognitive.cycle.models import AppraisalResult, RelationshipResult, StepStatus
from iris.cognitive.workspace.frame import AffectSnapshot, RelationshipSnapshot


def test_affect_and_relationship_snapshots_are_frozen_and_typed() -> None:
    affect = AffectSnapshot(
        mood_label="positive",
        valence=0.25,
        arousal=0.1,
        dominance=0.0,
        affect_summary="positive VAD(v=0.25, a=0.10, d=0.00)",
    )
    relationship = RelationshipSnapshot(
        user_label="User",
        affinity=0.1,
        trust=0.5,
        familiarity=0.2,
        relationship_summary="User relationship(affinity=0.10, trust=0.50, familiarity=0.20)",
    )

    assert affect.valence == 0.25
    assert relationship.trust == 0.5
    with pytest.raises(FrozenInstanceError):
        affect.valence = 0.0  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        relationship.trust = 0.0  # type: ignore[misc]


def test_existing_affect_result_types_are_reused() -> None:
    appraisal = AppraisalResult(step_name="appraisal", status=StepStatus.OK, valence=0.25)
    relationship = RelationshipResult(step_name="relationship", status=StepStatus.OK, trust=0.5)

    assert type(appraisal).__name__ == "AppraisalResult"
    assert type(relationship).__name__ == "RelationshipResult"
