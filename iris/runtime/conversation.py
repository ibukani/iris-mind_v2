"""短期会話windowのruntime統合。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict

from iris.contracts.conversation import ConversationRecord, ConversationRole, ConversationWindow
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
class ConversationHistoryPolicy:
    """LLMへ渡す短期会話windowの決定論的budget。"""

    max_window_records: int = 20
    max_history_chars: int = 8000

    def trim(self, records: tuple[ConversationRecord, ...]) -> tuple[ConversationRecord, ...]:
        """最新側の連続したrecordを件数・文字数budget内で返す。

        Recordは切断せず、budgetを超える古いrecord以降を除外する。

        Returns:
            時系列順を保ったtrim済みrecord。
        """
        if self.max_window_records <= 0 or self.max_history_chars <= 0:
            return ()
        selected: list[ConversationRecord] = []
        used_chars = 0
        candidates = records[-self.max_window_records :]
        for record in reversed(candidates):
            record_chars = len(record.content)
            if used_chars + record_chars > self.max_history_chars:
                break
            selected.append(record)
            used_chars += record_chars
        selected.reverse()
        return tuple(selected)


class _SituationContextUpdate(TypedDict):
    """SituationContextSnapshot.model_copy用の型付き差分。"""

    conversation_window: ConversationWindow


@dataclass(frozen=True)
class ShortTermConversationRuntime:
    """会話履歴のload/record責務をruntime serviceから分離する。"""

    store: ConversationHistoryStore
    policy: ConversationHistoryPolicy = ConversationHistoryPolicy()
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
            self.policy.max_window_records,
        )
        window = ConversationWindow(records=self.policy.trim(window.records))
        current = base or SituationContextSnapshot()
        update = _SituationContextUpdate(conversation_window=window)
        return current.model_copy(update=update)

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
