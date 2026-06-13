"""observation trust policy tests。"""

from __future__ import annotations

from iris.runtime.observations.ingress import (
    ObservationCapability,
    ObservationIngressContext,
)
from iris.runtime.observations.trust import ObservationTrustPolicy


def test_observation_trust_policy_requires_authentication_and_capabilities() -> None:
    """Trust policyがsource文字列ではなくingress capabilityだけを見る。"""
    policy = ObservationTrustPolicy()

    assert policy.can_integrate_activity_event(_ingress(ObservationCapability.INTEGRATE_ACTIVITY))
    assert not policy.can_integrate_activity_event(
        _ingress(ObservationCapability.INTEGRATE_ACTIVITY, authenticated=False)
    )
    assert not policy.can_integrate_activity_event(
        _ingress(ObservationCapability.INTEGRATE_PRESENCE)
    )
    assert policy.can_integrate_presence_signal(_ingress(ObservationCapability.INTEGRATE_PRESENCE))
    assert not policy.can_integrate_presence_signal(
        _ingress(ObservationCapability.UPDATE_SPACE_OCCUPANCY)
    )
    assert policy.can_update_space_occupancy(_ingress(ObservationCapability.UPDATE_SPACE_OCCUPANCY))
    assert not policy.can_update_space_occupancy(_ingress(ObservationCapability.INTEGRATE_PRESENCE))


def test_can_react_to_activity_event_requires_trust() -> None:
    """can_react_to_activity_eventは認証済み + INTEGRATE_ACTIVITYを要求する。"""
    policy = ObservationTrustPolicy()

    assert policy.can_react_to_activity_event(_ingress(ObservationCapability.INTEGRATE_ACTIVITY))

    assert not policy.can_react_to_activity_event(
        _ingress(ObservationCapability.INTEGRATE_ACTIVITY, authenticated=False)
    )

    assert not policy.can_react_to_activity_event(
        _ingress(ObservationCapability.INTEGRATE_PRESENCE)
    )


def _ingress(
    capability: ObservationCapability,
    *,
    authenticated: bool = True,
) -> ObservationIngressContext:
    return ObservationIngressContext(
        adapter_id="trusted-adapter",
        provider="discord",
        authenticated=authenticated,
        capabilities=frozenset({capability}),
    )
