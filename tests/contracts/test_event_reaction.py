"""event reaction contract tests。"""

from __future__ import annotations

from iris.contracts.event_reaction import (
    EventReactionDecision,
    EventReactionKind,
    ReactionCandidate,
)
from tests.helpers.immutability import assert_frozen_field


def test_reaction_candidate_is_frozen_and_copies_metadata() -> None:
    """ReactionCandidateがimmutableでmetadataを防御コピーすることを確認する。"""
    metadata = {"k": "v"}
    candidate = ReactionCandidate(
        kind=EventReactionKind.GREETING,
        text="hello",
        reason="greeting",
        priority=5,
        metadata=metadata,
    )
    metadata["k"] = "x"

    assert candidate.metadata == {"k": "v"}
    assert_frozen_field(candidate, "priority", 99)


def test_event_reaction_decision_defaults_candidate_to_none() -> None:
    """EventReactionDecisionのcandidateがデフォルトでNoneであることを確認する。"""
    decision = EventReactionDecision(should_react=False, reason="no reaction")

    assert decision.candidate is None
