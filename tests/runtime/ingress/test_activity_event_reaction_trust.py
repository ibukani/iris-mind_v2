"""Event reaction の trust/capability 境界テスト。"""

from __future__ import annotations

from iris.runtime.ingress.observation_ingress import ObservationCapability, trusted_adapter_ingress
from iris.runtime.ingress.observation_trust import ObservationTrustPolicy


def test_react_to_activity_capability_is_required_for_event_reaction() -> None:
    """REACT_TO_ACTIVITY がある trusted ingress だけが event reaction 可能。"""
    policy = ObservationTrustPolicy()
    ingress = trusted_adapter_ingress(
        adapter_id="adapter-1",
        provider=None,
        capabilities={ObservationCapability.REACT_TO_ACTIVITY},
    )
    assert policy.can_react_to_activity_event(ingress)
    assert not policy.can_integrate_activity_event(ingress)


def test_integrate_activity_alone_does_not_imply_event_reaction() -> None:
    """INTEGRATE_ACTIVITY だけでは REACT_TO_ACTIVITY を含意しない。"""
    policy = ObservationTrustPolicy()
    ingress = trusted_adapter_ingress(
        adapter_id="adapter-1",
        provider=None,
        capabilities={ObservationCapability.INTEGRATE_ACTIVITY},
    )
    assert policy.can_integrate_activity_event(ingress)
    assert not policy.can_react_to_activity_event(ingress)
