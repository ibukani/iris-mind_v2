"""Process-local短期会話履歴ストア。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from iris.contracts.conversation import ConversationWindow

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.contracts.conversation import ConversationRecord
    from iris.contracts.delivery import DeliveryTarget
    from iris.contracts.observations import Observation


class ConversationSubjectKind(StrEnum):
    """会話keyに使う安定subject種別。"""

    ACTOR = "actor"
    ACCOUNT = "account"
    SESSION = "session"


@dataclass(frozen=True)
class ConversationKey:
    """actor/accountを優先し、必要ならspaceで分離する会話key。"""

    subject_kind: ConversationSubjectKind
    subject_id: str
    space_id: str | None = None


class ConversationHistoryStore(Protocol):
    """短期会話windowのprocess-local store境界。"""

    async def recent_window(self, key: ConversationKey, limit: int) -> ConversationWindow:
        """直近レコードを時系列順で返す。"""
        ...

    async def append(
        self,
        key: ConversationKey,
        records: Sequence[ConversationRecord],
    ) -> None:
        """レコードを追記する。"""
        ...


class InMemoryConversationHistoryStore:
    """keyごとの上限を持つasync-safeな短期会話ストア。"""

    def __init__(self, *, max_records: int = 40) -> None:
        """保持する最大レコード数で初期化する。"""
        self._max_records = max_records
        self._records: dict[ConversationKey, tuple[ConversationRecord, ...]] = {}
        self._lock = asyncio.Lock()

    async def recent_window(self, key: ConversationKey, limit: int) -> ConversationWindow:
        """直近レコードを時系列順で返す。

        Returns:
            上限適用済みの会話window。
        """
        async with self._lock:
            records = self._records.get(key, ())
            return ConversationWindow(records=records[-limit:] if limit > 0 else ())

    async def append(
        self,
        key: ConversationKey,
        records: Sequence[ConversationRecord],
    ) -> None:
        """追記後にkey単位の保持上限を適用する。"""
        if not records:
            return
        async with self._lock:
            combined = self._records.get(key, ()) + tuple(records)
            self._records[key] = combined[-self._max_records :]


def conversation_key_for(observation: Observation) -> ConversationKey:
    """解決済みactor、account、sessionの順で安定会話keyを作る。

    ActorはIrisの会話主体なのでaccountと両方ある場合も優先する。actor未解決時は
    accountを使い、identity未解決時だけsessionへfallbackする。Spaceは同じ主体の
    同時会話を分離するためactor/account keyに含め、session fallbackには含めない。

    Returns:
        actor、account、sessionの優先順で作ったkey。
    """
    context = observation.context
    space_id = str(context.space_id) if context.space_id is not None else None
    if context.actor_id is not None:
        return ConversationKey(ConversationSubjectKind.ACTOR, str(context.actor_id), space_id)
    if context.account_id is not None:
        return ConversationKey(ConversationSubjectKind.ACCOUNT, str(context.account_id), space_id)
    return ConversationKey(ConversationSubjectKind.SESSION, str(observation.session_id))


def conversation_key_for_delivery_target(target: DeliveryTarget) -> ConversationKey:
    """Delivery target から confirmed assistant turn 用の会話keyを作る。

    Actor/account を優先し、同一主体の並行会話は space で分離する。

    Returns:
        actor、account、sessionの優先順で作ったkey。
    """
    space_id = str(target.space_id) if target.space_id is not None else None
    if target.actor_id is not None:
        return ConversationKey(ConversationSubjectKind.ACTOR, str(target.actor_id), space_id)
    if target.account_id is not None:
        return ConversationKey(ConversationSubjectKind.ACCOUNT, str(target.account_id), space_id)
    return ConversationKey(ConversationSubjectKind.SESSION, str(target.session_id))
