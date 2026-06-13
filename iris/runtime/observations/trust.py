"""observation claimのcapability-based trust policy。"""

from __future__ import annotations

from dataclasses import dataclass

from iris.runtime.observations.ingress import (
    ObservationCapability,
    ObservationIngressContext,
)


@dataclass(frozen=True)
class ObservationTrustPolicy:
    """外部observation claimが内部stateへ影響できるcapabilityを検査する。"""

    @staticmethod
    def can_integrate_activity_event(
        ingress: ObservationIngressContext,
    ) -> bool:
        """Activity integration capabilityがあるか返す。

        Returns:
            許可されている場合はTrue。
        """
        return (
            ingress.authenticated
            and ObservationCapability.INTEGRATE_ACTIVITY in ingress.capabilities
        )

    @staticmethod
    def can_integrate_presence_signal(
        ingress: ObservationIngressContext,
    ) -> bool:
        """Presence integration capabilityがあるか返す。

        Returns:
            許可されている場合はTrue。
        """
        return (
            ingress.authenticated
            and ObservationCapability.INTEGRATE_PRESENCE in ingress.capabilities
        )

    @staticmethod
    def can_update_space_occupancy(
        ingress: ObservationIngressContext,
    ) -> bool:
        """Space occupancy update capabilityがあるか返す。

        Returns:
            許可されている場合はTrue。
        """
        return (
            ingress.authenticated
            and ObservationCapability.UPDATE_SPACE_OCCUPANCY in ingress.capabilities
        )


def default_observation_trust_policy() -> ObservationTrustPolicy:
    """capability検査のみを行う初期policyを返す。

    Returns:
        初期trust policy。
    """
    return ObservationTrustPolicy()
