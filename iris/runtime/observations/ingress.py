"""runtime-owned observation ingress context。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ObservationCapability(StrEnum):
    """runtimeがadapterへ付与するobservation integration capability。"""

    INTEGRATE_ACTIVITY = "integrate_activity"
    INTEGRATE_PRESENCE = "integrate_presence"
    UPDATE_SPACE_OCCUPANCY = "update_space_occupancy"
    REACT_TO_ACTIVITY = "react_to_activity"
    INTERNAL_EVENT = "internal_event"


@dataclass(frozen=True)
class ObservationIngressContext:
    """Observationとは別にruntime boundaryが付与する認証済みingress情報。"""

    adapter_id: str
    provider: str | None
    authenticated: bool
    capabilities: frozenset[ObservationCapability]


def unauthenticated_external_ingress() -> ObservationIngressContext:
    """外部client request用のcapabilityなしingress contextを返す。

    Returns:
        未認証かつcapabilityなしのingress context。
    """
    return ObservationIngressContext(
        adapter_id="external_client",
        provider=None,
        authenticated=False,
        capabilities=frozenset(),
    )


def trusted_adapter_ingress(
    *,
    adapter_id: str,
    provider: str | None,
    capabilities: frozenset[ObservationCapability] | set[ObservationCapability],
) -> ObservationIngressContext:
    """信頼済みadapter用の認証済みingress contextを返す。

    Args:
        adapter_id: 信頼済みadapterの識別子。
        provider: 任意的なprovider名。
        capabilities: 付与するcapabilityの集合。

    Returns:
        認証済みかつ指定されたcapabilityを持つingress context。
    """
    return ObservationIngressContext(
        adapter_id=adapter_id,
        provider=provider,
        authenticated=True,
        capabilities=frozenset(capabilities),
    )
