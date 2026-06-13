"""Observation ingress の trust/capability 境界テスト。"""

from __future__ import annotations

from iris.runtime.observations.ingress import (
    ObservationCapability,
    trusted_adapter_ingress,
    unauthenticated_external_ingress,
)
from iris.runtime.observations.trust import ObservationTrustPolicy


def test_external_client_ingress_is_unauthenticated_without_capabilities() -> None:
    """外部 client ingress は未認証かつ capability なし。"""
    ingress = unauthenticated_external_ingress()
    assert ingress.adapter_id == "external_client"
    assert not ingress.authenticated
    assert ingress.provider is None
    assert ingress.capabilities == frozenset()


def test_trusted_adapter_ingress_is_authenticated_with_explicit_capabilities() -> None:
    """Trusted adapter ingress は認証済みで明示 capability だけを持つ。"""
    ingress = trusted_adapter_ingress(
        adapter_id="adapter-1",
        provider="local",
        capabilities={ObservationCapability.INTEGRATE_ACTIVITY},
    )
    assert ingress.authenticated
    assert ingress.adapter_id == "adapter-1"
    assert ingress.provider == "local"
    assert ingress.capabilities == frozenset({ObservationCapability.INTEGRATE_ACTIVITY})


def test_integrate_activity_capability_only_enables_activity_integration() -> None:
    """INTEGRATE_ACTIVITY は activity integration だけを許可する。"""
    policy = ObservationTrustPolicy()
    ingress = trusted_adapter_ingress(
        adapter_id="adapter-1",
        provider=None,
        capabilities={ObservationCapability.INTEGRATE_ACTIVITY},
    )
    assert policy.can_integrate_activity_event(ingress)
    assert not policy.can_integrate_presence_signal(ingress)
    assert not policy.can_update_space_occupancy(ingress)
    assert not policy.can_react_to_activity_event(ingress)


def test_integrate_presence_capability_only_enables_presence_integration() -> None:
    """INTEGRATE_PRESENCE は presence integration だけを許可する。"""
    policy = ObservationTrustPolicy()
    ingress = trusted_adapter_ingress(
        adapter_id="adapter-1",
        provider=None,
        capabilities={ObservationCapability.INTEGRATE_PRESENCE},
    )
    assert not policy.can_integrate_activity_event(ingress)
    assert policy.can_integrate_presence_signal(ingress)
    assert not policy.can_update_space_occupancy(ingress)
    assert not policy.can_react_to_activity_event(ingress)


def test_update_space_occupancy_capability_only_enables_occupancy_update() -> None:
    """UPDATE_SPACE_OCCUPANCY は occupancy update だけを許可する。"""
    policy = ObservationTrustPolicy()
    ingress = trusted_adapter_ingress(
        adapter_id="adapter-1",
        provider=None,
        capabilities={ObservationCapability.UPDATE_SPACE_OCCUPANCY},
    )
    assert not policy.can_integrate_activity_event(ingress)
    assert not policy.can_integrate_presence_signal(ingress)
    assert policy.can_update_space_occupancy(ingress)
    assert not policy.can_react_to_activity_event(ingress)
