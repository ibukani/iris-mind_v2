"""短期会話windowのruntime統合。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import hashlib
import logging
from typing import TYPE_CHECKING, TypedDict

from iris.contracts.actions import ActionStatus, SendMessageAction
from iris.contracts.conversation import ConversationRecord, ConversationRole, ConversationWindow
from iris.contracts.transcript import (
    TranscriptRecord,
    TranscriptRole,
    TranscriptSource,
    TranscriptSubjectKind,
)
from iris.contracts.workspace_context import SituationContextSnapshot
from iris.core.datetime_utils import now_utc
from iris.core.ids import ObservationId, TranscriptId
from iris.runtime.observation_router import actor_message_observation
from iris.runtime.state.conversation import (
    ConversationKey,
    ConversationSubjectKind,
    conversation_key_for,
    conversation_key_for_delivery_target,
)
from iris.runtime.state.transcript import NullTranscriptStore

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from iris.contracts.actions import PresentedOutput
    from iris.contracts.learning import LearningEvent
    from iris.contracts.metadata import ImmutableMetadata
    from iris.contracts.observations import ActorMessageObservation, Observation
    from iris.runtime.state.conversation import ConversationHistoryStore
    from iris.runtime.state.transcript import TranscriptStore


@dataclass(frozen=True)
class ConversationHistoryPolicy:
    """LLMへ渡す短期会話windowとsummaryの決定論的budget。"""

    max_window_records: int = 20
    max_history_chars: int = 8000
    summary_enabled: bool = True
    summary_max_chars: int = 1600
    summary_min_records: int = 12

    def trim(self, records: tuple[ConversationRecord, ...]) -> tuple[ConversationRecord, ...]:
        """最新側の連続したrecordを件数・文字数budget内で返す。

        Recordは切断せず、budgetを超える古いrecord以降を除外する。

        Returns:
            時系列順を保ったtrim済みrecord。
        """
        return self._select_recent(records)

    @property
    def load_record_limit(self) -> int:
        """Summary 生成に必要な余裕を含む store 読み込み件数。"""
        return max(self.max_window_records, self.summary_min_records * 2)

    def build_window(self, records: tuple[ConversationRecord, ...]) -> ConversationWindow:
        """Summary context と recent records を分けた会話windowを作る。

        Summary は prompt context 専用であり、assistant/user turn として扱わない。

        Returns:
            summary と recent records を持つ ConversationWindow。
        """
        recent = self._select_recent(records)
        older = records[: len(records) - len(recent)] if recent else records
        summary = self._summarize(older) if self._should_summarize(records, older) else None
        return ConversationWindow(records=recent, summary=summary)

    def _select_recent(
        self,
        records: tuple[ConversationRecord, ...],
    ) -> tuple[ConversationRecord, ...]:
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

    def _should_summarize(
        self,
        records: tuple[ConversationRecord, ...],
        older: tuple[ConversationRecord, ...],
    ) -> bool:
        return (
            self.summary_enabled
            and self.max_history_chars > 0
            and self.summary_max_chars > 0
            and len(records) >= self.summary_min_records
            and bool(older)
        )

    def _summarize(self, records: tuple[ConversationRecord, ...]) -> str:
        lines = tuple(_summary_line(record) for record in records)
        summary = "\n".join(lines)
        if len(summary) <= self.summary_max_chars:
            return summary
        suffix = "…"
        return f"{summary[: self.summary_max_chars - len(suffix)]}{suffix}"


@dataclass(frozen=True)
class TranscriptWritePolicy:
    """Confirmed transcript への書き込み方針。"""

    retention_days: int = 30

    def retention_until(self, recorded_at: datetime) -> datetime | None:
        """保存期限を返す。0日は期限なしとして扱う。

        Returns:
            保存期限。期限なしの場合は None。
        """
        if self.retention_days <= 0:
            return None
        return recorded_at + timedelta(days=self.retention_days)


@dataclass(frozen=True)
class _TranscriptRecordContext:
    """TranscriptRecord 生成に必要な書き込み境界情報。"""

    role: TranscriptRole
    source: TranscriptSource
    recorded_at: datetime
    retention_until: datetime | None
    discriminator: str | None = None
    metadata: ImmutableMetadata | None = None


@dataclass(frozen=True)
class DeliveryConversationHistoryHook:
    """配送成功後に confirmed assistant turn だけを短期履歴へ確定する。"""

    store: ConversationHistoryStore
    transcript_store: TranscriptStore = field(default_factory=NullTranscriptStore)
    transcript_policy: TranscriptWritePolicy = TranscriptWritePolicy()

    async def after_action_result(self, event: LearningEvent) -> None:
        """成功配送のみ assistant turn として確定する。

        Blocked/failed/cancelled delivery は、ユーザーに届いた通常の assistant turn
        として扱わない。
        """
        if event.result.status is not ActionStatus.SUCCEEDED or event.target is None:
            return
        if not isinstance(event.action, SendMessageAction) or not event.action.text.strip():
            return
        record = _assistant_delivery_record(event)
        key = conversation_key_for_delivery_target(event.target)
        await self.store.append(key, (record,))
        await _append_transcripts_best_effort(
            self.transcript_store,
            (
                _transcript_record(
                    key,
                    record,
                    _TranscriptRecordContext(
                        role=TranscriptRole.ASSISTANT,
                        source=TranscriptSource.DELIVERED_ACTION,
                        recorded_at=event.reported_at,
                        retention_until=self.transcript_policy.retention_until(event.reported_at),
                        discriminator=str(event.action.action_id),
                        metadata={"action_id": str(event.action.action_id)},
                    ),
                ),
            ),
        )


class _SituationContextUpdate(TypedDict):
    """SituationContextSnapshot.model_copy用の型付き差分。"""

    conversation_window: ConversationWindow


@dataclass(frozen=True)
class ShortTermConversationRuntime:
    """会話履歴のload/record責務をruntime serviceから分離する。"""

    store: ConversationHistoryStore
    transcript_store: TranscriptStore = field(default_factory=NullTranscriptStore)
    policy: ConversationHistoryPolicy = ConversationHistoryPolicy()
    transcript_policy: TranscriptWritePolicy = TranscriptWritePolicy()
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
            self.policy.load_record_limit,
        )
        window = self.policy.build_window(window.records)
        current = base or SituationContextSnapshot()
        update = _SituationContextUpdate(conversation_window=window)
        return current.model_copy(update=update)

    async def record_response(
        self,
        observation: Observation,
        output: PresentedOutput,
    ) -> None:
        """Sendable actor message turnだけを履歴と任意transcriptへ追記する。"""
        actor_message = actor_message_observation(observation)
        if actor_message is None or not output.is_sendable:
            return
        key = conversation_key_for(observation)
        recorded_at = self.now()
        records = _inline_records(actor_message, output, recorded_at)
        await self.store.append(key, records)
        await _append_transcripts_best_effort(
            self.transcript_store,
            _inline_transcripts(
                key,
                records,
                recorded_at=recorded_at,
                retention_until=self.transcript_policy.retention_until(recorded_at),
            ),
        )


async def _append_transcripts_best_effort(
    store: TranscriptStore,
    records: tuple[TranscriptRecord, ...],
) -> None:
    """Transcript append failure を user-facing response path から隔離する。"""
    try:
        await store.append(records)
    except Exception:
        _LOGGER.exception("confirmed transcript append failed")


def _inline_records(
    message: ActorMessageObservation,
    output: PresentedOutput,
    assistant_at: datetime,
) -> tuple[ConversationRecord, ConversationRecord]:
    context = message.context
    return (
        ConversationRecord(
            role=ConversationRole.USER,
            content=message.text,
            occurred_at=message.occurred_at,
            observation_id=message.observation_id,
            session_id=message.session_id,
            actor_id=context.actor_id,
            account_id=context.account_id,
            space_id=context.space_id,
        ),
        ConversationRecord(
            role=ConversationRole.ASSISTANT,
            content=output.text or "",
            occurred_at=assistant_at,
            observation_id=message.observation_id,
            session_id=message.session_id,
            actor_id=context.actor_id,
            account_id=context.account_id,
            space_id=context.space_id,
        ),
    )


def _assistant_delivery_record(event: LearningEvent) -> ConversationRecord:
    if event.target is None or not isinstance(event.action, SendMessageAction):
        msg = "successful send message event target is required"
        raise TypeError(msg)
    return ConversationRecord(
        role=ConversationRole.ASSISTANT,
        content=event.action.text,
        occurred_at=event.result.delivered_at or event.reported_at,
        observation_id=event.source_observation_id,
        session_id=event.action.session_id,
        actor_id=event.target.actor_id,
        account_id=event.target.account_id,
        space_id=event.target.space_id,
    )


def _inline_transcripts(
    key: ConversationKey,
    records: tuple[ConversationRecord, ConversationRecord],
    *,
    recorded_at: datetime,
    retention_until: datetime | None,
) -> tuple[TranscriptRecord, TranscriptRecord]:
    return (
        _transcript_record(
            key,
            records[0],
            _TranscriptRecordContext(
                role=TranscriptRole.USER,
                source=TranscriptSource.INLINE_RESPONSE,
                recorded_at=recorded_at,
                retention_until=retention_until,
            ),
        ),
        _transcript_record(
            key,
            records[1],
            _TranscriptRecordContext(
                role=TranscriptRole.ASSISTANT,
                source=TranscriptSource.INLINE_RESPONSE,
                recorded_at=recorded_at,
                retention_until=retention_until,
            ),
        ),
    )


def _transcript_record(
    key: ConversationKey,
    record: ConversationRecord,
    context: _TranscriptRecordContext,
) -> TranscriptRecord:
    return TranscriptRecord(
        transcript_id=_transcript_id(
            key,
            record,
            context.source,
            context.role,
            discriminator=context.discriminator,
        ),
        subject_kind=_transcript_subject_kind(key.subject_kind),
        subject_id=key.subject_id,
        role=context.role,
        source=context.source,
        content=record.content,
        occurred_at=record.occurred_at,
        recorded_at=context.recorded_at,
        session_id=record.session_id,
        observation_id=record.observation_id,
        actor_id=record.actor_id,
        account_id=record.account_id,
        space_id=record.space_id,
        retention_until=context.retention_until,
        metadata=context.metadata or {},
    )


def _transcript_subject_kind(kind: ConversationSubjectKind) -> TranscriptSubjectKind:
    if kind is ConversationSubjectKind.ACTOR:
        return TranscriptSubjectKind.ACTOR
    if kind is ConversationSubjectKind.ACCOUNT:
        return TranscriptSubjectKind.ACCOUNT
    return TranscriptSubjectKind.SESSION


def _transcript_id(
    key: ConversationKey,
    record: ConversationRecord,
    source: TranscriptSource,
    role: TranscriptRole,
    *,
    discriminator: str | None = None,
) -> TranscriptId:
    observation_id = record.observation_id or ObservationId("unknown-observation")
    seed = "|".join(
        (
            str(source),
            str(role),
            str(key.subject_kind),
            key.subject_id,
            key.space_id or "",
            str(record.session_id),
            str(observation_id),
            discriminator or "",
        )
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
    return TranscriptId(f"tr-{digest}")


def _summary_line(record: ConversationRecord) -> str:
    role = "User" if record.role is ConversationRole.USER else "Assistant"
    content = " ".join(record.content.split())
    return f"- {record.occurred_at.isoformat()} {role}: {content}"
