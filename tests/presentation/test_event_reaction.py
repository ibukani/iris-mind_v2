"""Event reaction presentation tests."""

from __future__ import annotations

from iris.contracts.event_reaction import EventReactionKind, ReactionCandidate
from iris.presentation.event_reaction import EventReactionPresenter


def test_event_reaction_presenter_converts_candidate_to_output() -> None:
    """ReactionCandidateをPresentedOutputへ変換する。"""
    candidate = ReactionCandidate(
        kind=EventReactionKind.GREETING,
        text="Welcome back.",
        reason="voice joined",
        priority=7,
        interruptible=False,
    )

    output = EventReactionPresenter.present(candidate)

    assert output.text == "Welcome back."
    assert output.priority == 7
    assert output.interruptible is False
    assert output.style_hint == "event_reaction"
