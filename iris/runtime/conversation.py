"""短期会話windowのruntime統合。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from iris.contracts.conversation import ConversationRecord, ConversationRole
from iris.contracts.workspace_context import SituationContextSnapshot
from iris.core.datetime_utils import now_utc
from iris.runtime.observation_router import actor_message_observation
from iris.runtime.state.conversation import conversation_key_for

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from iris.contracts.actions import PresentedOutput
    from iris.contracts.observations import Observation
    from iris.runtime.state.conversation import ConversationHistoryStore


@dataclass(frozen=True)
class ShortTermConversationRuntime:
    """会話履歴のload/record責務をruntime serviceから分離する。"""

    store: ConversationHistoryStore
    window_limit: int = 20
    now: Callable[[], datetime] = now_utc

    async def load_context(
        self,
        observation: Observation,
        base: SituationContextSnapshot | None,
    ) -> SituationContextSnapshot:
        """対象会話の直近windowを状況contextへ追加する。

        Returns:
            会話windowを含む状況context。
        """
        window = await self.store.recent_window(
            conversation_key_for(observation),
            self.window_limit,
        )
        current = base or SituationContextSnapshot()
        return SituationContextSnapshot(
            latest_activity=current.latest_activity,
            presence=current.presence,
            space_occupancy=current.space_occupancy,
            availability=current.availability,
            conversation_window=window,
        )

    async def record_response(
        self,
        observation: Observation,
        output: PresentedOutput,
    ) -> None:
        """Sendable actor message turnだけを履歴へ追記する。"""
        actor_message = actor_message_observation(observation)
        if actor_message is None or not output.is_sendable:
            return
        context = actor_message.context
        await self.store.append(
            conversation_key_for(observation),
            (
                ConversationRecord(
                    role=ConversationRole.USER,
                    content=actor_message.text,
                    occurred_at=actor_message.occurred_at,
                    observation_id=actor_message.observation_id,
                    session_id=actor_message.session_id,
                    actor_id=context.actor_id,
                    account_id=context.account_id,
                    space_id=context.space_id,
                ),
                ConversationRecord(
                    role=ConversationRole.ASSISTANT,
                    content=output.text or "",
                    occurred_at=self.now(),
                    observation_id=actor_message.observation_id,
                    session_id=actor_message.session_id,
                    actor_id=context.actor_id,
                    account_id=context.account_id,
                    space_id=context.space_id,
                ),
            ),
        )
