"""event reaction policy tests。"""

from __future__ import annotations

import pytest

from iris.contracts.activity import ActivityKind
from iris.contracts.availability import AvailabilityStatus
from iris.features.event_reaction.policy import EventReactionPolicy, default_event_reaction_policy


@pytest.fixture
def policy() -> EventReactionPolicy:
    """デフォルトのevent reactionポリシーを提供する。

    Returns:
        EventReactionPolicy: デフォルトポリシー。
    """
    return default_event_reaction_policy()


@pytest.mark.parametrize(
    "status",
    [
        AvailabilityStatus.AVAILABLE,
        AvailabilityStatus.INTERRUPTIBLE,
        AvailabilityStatus.PASSIVE,
    ],
)
def test_voice_joined_allowed(
    policy: EventReactionPolicy,
    status: AvailabilityStatus,
) -> None:
    """VOICE_JOINEDはAVAILABLE/INTERRUPTIBLE/PASSIVEで許可される。"""
    assert policy.allows(ActivityKind.VOICE_JOINED, status)


@pytest.mark.parametrize(
    "status",
    [
        AvailabilityStatus.AVAILABLE,
        AvailabilityStatus.INTERRUPTIBLE,
    ],
)
def test_app_opened_allowed(
    policy: EventReactionPolicy,
    status: AvailabilityStatus,
) -> None:
    """APP_OPENEDはAVAILABLE/INTERRUPTIBLEで許可される。"""
    assert policy.allows(ActivityKind.APP_OPENED, status)


def test_app_opened_rejected_passive(policy: EventReactionPolicy) -> None:
    """APP_OPENEDはPASSIVEでは許可されない。"""
    assert not policy.allows(ActivityKind.APP_OPENED, AvailabilityStatus.PASSIVE)


@pytest.mark.parametrize(
    "status",
    [
        AvailabilityStatus.AVAILABLE,
        AvailabilityStatus.INTERRUPTIBLE,
        AvailabilityStatus.PASSIVE,
        AvailabilityStatus.UNKNOWN,
        AvailabilityStatus.BUSY,
        AvailabilityStatus.UNAVAILABLE,
        None,
    ],
)
def test_voice_left_rejected(
    policy: EventReactionPolicy,
    status: AvailabilityStatus | None,
) -> None:
    """VOICE_LEFTはどのavailabilityでも許可されない。"""
    assert not policy.allows(ActivityKind.VOICE_LEFT, status)


@pytest.mark.parametrize(
    "kind",
    [
        ActivityKind.ACTOR_TYPING_STARTED,
        ActivityKind.SYSTEM_INTERACTION,
    ],
)
def test_unsupported_kinds_rejected(
    policy: EventReactionPolicy,
    kind: ActivityKind,
) -> None:
    """ポリシーに含まれないactivity kindは許可されない。"""
    assert not policy.allows(kind, AvailabilityStatus.AVAILABLE)


def test_custom_policy_allows_specific_kind_and_availability() -> None:
    """カスタムポリシーが指定したkind/availabilityのみ許可する。"""
    custom = EventReactionPolicy(
        kind_availability={
            ActivityKind.APP_CLOSED: frozenset({AvailabilityStatus.AVAILABLE}),
        },
    )

    assert custom.allows(ActivityKind.APP_CLOSED, AvailabilityStatus.AVAILABLE)
    assert not custom.allows(ActivityKind.APP_CLOSED, AvailabilityStatus.BUSY)
    assert not custom.allows(ActivityKind.VOICE_JOINED, AvailabilityStatus.AVAILABLE)
