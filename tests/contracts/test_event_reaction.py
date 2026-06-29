"""event reaction contract tests。"""

from __future__ import annotations

from iris.contracts.event_reaction import EventReactionDecision


def test_event_reaction_decision_defaults_candidate_to_none() -> None:
    """EventReactionDecisionのcandidateがデフォルトでNoneであることを確認する。"""
    decision = EventReactionDecision(should_react=False, reason="no reaction")

    assert decision.candidate is None
