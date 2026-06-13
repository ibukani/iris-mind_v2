"""observation claimの最小trust policy。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ObservationTrustPolicy:
    """外部observation claimが内部stateへ影響できるsourceを制限する。"""

    trusted_activity_sources: frozenset[str]
    trusted_presence_sources: frozenset[str]

    def can_integrate_activity_event(self, source: str | None) -> bool:
        """Sourceがactivity integrationを許可されているか返す。

        Returns:
            許可されている場合はTrue。
        """
        return source is not None and source in self.trusted_activity_sources

    def can_integrate_presence_signal(self, source: str | None) -> bool:
        """Sourceがpresence integrationを許可されているか返す。

        Returns:
            許可されている場合はTrue。
        """
        return source is not None and source in self.trusted_presence_sources


def default_observation_trust_policy() -> ObservationTrustPolicy:
    """既知のruntime adapter sourceだけを許可する初期policyを返す。

    Returns:
        初期trust policy。
    """
    trusted_sources = frozenset(
        {
            "discord_gateway",
            "iris_discordbot",
            "local_runtime",
            "internal",
        }
    )
    return ObservationTrustPolicy(
        trusted_activity_sources=trusted_sources,
        trusted_presence_sources=trusted_sources,
    )
