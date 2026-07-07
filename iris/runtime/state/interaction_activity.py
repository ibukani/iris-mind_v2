"""認証済みinteraction activityのprocess-local projection。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Protocol, override

from iris.contracts.activity import (
    ActivityEventRecord,
    ActivityKind,
    InteractionActivityChannel,
    InteractionActivitySnapshot,
    InteractionModality,
)

if TYPE_CHECKING:
    from iris.core.ids import AccountId, ActorId, SpaceId
    from iris.runtime.ingress.observation_ingress import ObservationIngressContext

_MODALITY_KEY = "modality"
_REASON_KEY = "reason"
_EXPIRES_AT_KEY = "expires_at"


class InteractionActivityProjectionStore(Protocol):
    """Delivery / proactiveがinteraction stateを参照するruntime port。"""

    async def apply(self, snapshot: InteractionActivitySnapshot) -> None:
        """認証済みsnapshotをprojectionへ反映する。"""
        ...

    async def active_for_target(
        self,
        *,
        provider: str | None,
        actor_id: ActorId | None,
        account_id: AccountId | None,
        space_id: SpaceId | None,
        now: datetime,
    ) -> tuple[InteractionActivitySnapshot, ...]:
        """対象scopeで未失効のactive stateを返す。

        Returns:
            Scopeに一致するactive snapshot。
        """
        ...


class InMemoryInteractionActivityProjectionStore(InteractionActivityProjectionStore):
    """Adapter/provider/subject/space/channel別のephemeral projection。"""

    def __init__(self) -> None:
        """空のprojectionを初期化する。"""
        self._snapshots: dict[_InteractionActivityKey, InteractionActivitySnapshot] = {}
        self._latest_snapshots: dict[_InteractionActivityKey, InteractionActivitySnapshot] = {}

    @override
    async def apply(self, snapshot: InteractionActivitySnapshot) -> None:
        """同一scope/channelの状態を新しい観測時刻のsnapshotで置き換える。"""
        key = _key_from_snapshot(snapshot)
        latest_snapshot = self._latest_snapshots.get(key)
        if latest_snapshot is not None and _is_older_snapshot(snapshot, latest_snapshot):
            return
        self._latest_snapshots[key] = snapshot
        self._snapshots[key] = snapshot

    @override
    async def active_for_target(
        self,
        *,
        provider: str | None,
        actor_id: ActorId | None,
        account_id: AccountId | None,
        space_id: SpaceId | None,
        now: datetime,
    ) -> tuple[InteractionActivitySnapshot, ...]:
        """対象scopeで未失効のactive stateを返す。

        Returns:
            Scopeに一致するactive snapshot。
        """
        self._prune_expired(now)
        return tuple(
            snapshot
            for snapshot in self._snapshots.values()
            if snapshot.active
            and snapshot.expires_at > now
            and snapshot.provider == provider
            and snapshot.actor_id == actor_id
            and snapshot.account_id == account_id
            and snapshot.space_id == space_id
        )

    def _prune_expired(self, now: datetime) -> None:
        expired = tuple(
            key for key, snapshot in self._snapshots.items() if snapshot.expires_at <= now
        )
        for key in expired:
            del self._snapshots[key]


@dataclass(frozen=True)
class _InteractionActivityKey:
    adapter_id: str
    provider: str | None
    actor_id: ActorId | None
    account_id: AccountId | None
    space_id: SpaceId | None
    channel: InteractionActivityChannel


def interaction_snapshot_from_event(
    event: ActivityEventRecord,
    ingress: ObservationIngressContext,
    *,
    now: datetime,
    max_ttl_seconds: float,
) -> InteractionActivitySnapshot | None:
    """Activity eventをserver-side TTL付きinteraction snapshotへ変換する。

    Returns:
        Interaction kindならsnapshot、それ以外はNone。
    """
    transition = _transition(event.kind)
    if transition is None:
        return None
    channel, active = transition
    expires_at = _bounded_expiry(event, now=now, max_ttl_seconds=max_ttl_seconds)
    return InteractionActivitySnapshot(
        adapter_id=ingress.adapter_id,
        provider=ingress.provider,
        actor_id=event.actor_id,
        account_id=event.account_id,
        space_id=event.space_id,
        channel=channel,
        active=active,
        modality=_modality(event),
        reason=event.metadata.get(_REASON_KEY),
        provider_sequence=event.provider_sequence,
        observed_at=event.occurred_at,
        received_at=event.received_at,
        expires_at=expires_at if active else now,
    )


def _transition(kind: ActivityKind) -> tuple[InteractionActivityChannel, bool] | None:
    transitions = {
        ActivityKind.ACTOR_INPUT_STARTED: (InteractionActivityChannel.ACTOR_INPUT, True),
        ActivityKind.ACTOR_INPUT_STOPPED: (InteractionActivityChannel.ACTOR_INPUT, False),
        ActivityKind.APP_OUTPUT_STARTED: (InteractionActivityChannel.APP_OUTPUT, True),
        ActivityKind.APP_OUTPUT_STOPPED: (InteractionActivityChannel.APP_OUTPUT, False),
    }
    return transitions.get(kind)


def _bounded_expiry(
    event: ActivityEventRecord,
    *,
    now: datetime,
    max_ttl_seconds: float,
) -> datetime:
    server_expiry = now + timedelta(seconds=max_ttl_seconds)
    advisory_expiry = _parse_advisory_expiry(event.metadata.get(_EXPIRES_AT_KEY))
    if advisory_expiry is None:
        return server_expiry
    if advisory_expiry <= now:
        return now
    return min(advisory_expiry, server_expiry)


def _parse_advisory_expiry(raw_expiry: str | None) -> datetime | None:
    if raw_expiry is None:
        return None
    try:
        advisory_expiry = datetime.fromisoformat(raw_expiry)
    except ValueError:
        return None
    if advisory_expiry.tzinfo is None:
        return None
    return advisory_expiry


def _modality(event: ActivityEventRecord) -> InteractionModality:
    raw_modality = event.metadata.get(_MODALITY_KEY, InteractionModality.UNKNOWN.value)
    try:
        return InteractionModality(raw_modality)
    except ValueError:
        return InteractionModality.UNKNOWN


def _key_from_snapshot(snapshot: InteractionActivitySnapshot) -> _InteractionActivityKey:
    return _InteractionActivityKey(
        adapter_id=snapshot.adapter_id,
        provider=snapshot.provider,
        actor_id=snapshot.actor_id,
        account_id=snapshot.account_id,
        space_id=snapshot.space_id,
        channel=snapshot.channel,
    )


def _is_older_snapshot(
    candidate: InteractionActivitySnapshot,
    latest: InteractionActivitySnapshot,
) -> bool:
    if candidate.provider_sequence is not None and latest.provider_sequence is not None:
        return (
            candidate.provider_sequence,
            candidate.observed_at,
            candidate.received_at,
        ) < (
            latest.provider_sequence,
            latest.observed_at,
            latest.received_at,
        )
    return (candidate.observed_at, candidate.received_at) < (
        latest.observed_at,
        latest.received_at,
    )
