"""observation trust policy tests。"""

from __future__ import annotations

from iris.runtime.ingress.observation_ingress import (
    ObservationCapability,
    ObservationIngressContext,
    trusted_adapter_ingress,
    unauthenticated_external_ingress,
)
from iris.runtime.ingress.observation_trust import ObservationTrustPolicy


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
    """can_react_to_activity_eventはREACT_TO_ACTIVITYを要求し、INTEGRATE_ACTIVITYとは独立。"""
    policy = ObservationTrustPolicy()

    assert policy.can_react_to_activity_event(_ingress(ObservationCapability.REACT_TO_ACTIVITY))

    assert not policy.can_react_to_activity_event(
        _ingress(ObservationCapability.REACT_TO_ACTIVITY, authenticated=False)
    )

    assert not policy.can_react_to_activity_event(
        _ingress(ObservationCapability.INTEGRATE_ACTIVITY)
    )

    assert not policy.can_react_to_activity_event(
        _ingress(ObservationCapability.INTEGRATE_PRESENCE)
    )


def test_integrate_activity_alone_does_not_imply_reaction() -> None:
    """INTEGRATE_ACTIVITYのみではreaction permissionにならない。"""
    policy = ObservationTrustPolicy()

    assert policy.can_integrate_activity_event(_ingress(ObservationCapability.INTEGRATE_ACTIVITY))
    assert not policy.can_react_to_activity_event(
        _ingress(ObservationCapability.INTEGRATE_ACTIVITY)
    )


def test_unauthenticated_external_ingress_has_no_capabilities() -> None:
    """unauthenticated_external_ingressは認証なし、capability空を返す。"""
    ingress = unauthenticated_external_ingress()
    assert not ingress.authenticated
    assert ingress.capabilities == frozenset()
    assert ingress.adapter_id == "external_client"
    assert ingress.provider is None


def test_trusted_adapter_ingress_has_authenticated_and_capabilities() -> None:
    """trusted_adapter_ingressは認証済み、指定capabilityを持つ。"""
    ingress = trusted_adapter_ingress(
        adapter_id="discord-gw",
        provider="discord",
        capabilities={
            ObservationCapability.INTEGRATE_ACTIVITY,
            ObservationCapability.REACT_TO_ACTIVITY,
        },
    )
    assert ingress.authenticated
    assert ingress.adapter_id == "discord-gw"
    assert ingress.provider == "discord"
    assert ObservationCapability.INTEGRATE_ACTIVITY in ingress.capabilities
    assert ObservationCapability.REACT_TO_ACTIVITY in ingress.capabilities
    assert ObservationCapability.INTEGRATE_PRESENCE not in ingress.capabilities


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
