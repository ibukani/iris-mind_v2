"""observation trust policy tests。"""

from __future__ import annotations

from iris.runtime.observations.trust import ObservationTrustPolicy


def test_observation_trust_policy_gates_activity_and_presence_sources() -> None:
    """activityとpresenceが個別のtrusted source集合を使うことを確認する。"""
    policy = ObservationTrustPolicy(
        trusted_activity_sources=frozenset({"activity-source"}),
        trusted_presence_sources=frozenset({"presence-source"}),
    )

    assert policy.can_integrate_activity_event("activity-source")
    assert not policy.can_integrate_activity_event("presence-source")
    assert not policy.can_integrate_activity_event(None)
    assert policy.can_integrate_presence_signal("presence-source")
    assert not policy.can_integrate_presence_signal("activity-source")
    assert not policy.can_integrate_presence_signal(None)
