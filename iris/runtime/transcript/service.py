"""Transcript read-only query / export service。"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, ValidationError

from iris.contracts.transcript import (
    TranscriptExport,
    TranscriptExportRequest,
    TranscriptPage,
    TranscriptPageRequest,
    TranscriptQuery,
    TranscriptRecord,
)
from iris.core.ids import TranscriptId
from iris.runtime.auth.policy import RuntimeAuthorizationPolicy

if TYPE_CHECKING:
    from iris.runtime.auth.principals import ClientPrincipal
    from iris.runtime.state.transcript import TranscriptStore


class TranscriptQueryError(ValueError):
    """Transcript cursor または query が不正な場合のエラー。"""


class _TranscriptCursor(BaseModel):
    """Opaque cursor の検証済み payload。"""

    model_config = ConfigDict(frozen=True)

    occurred_at: datetime
    transcript_id: TranscriptId


class TranscriptReadService:
    """Authorization と owner scope を通す transcript read-only service。"""

    def __init__(
        self,
        store: TranscriptStore,
        *,
        authorization_policy: RuntimeAuthorizationPolicy | None = None,
    ) -> None:
        """Transcript store と runtime authorization policy を注入する。"""
        self._store = store
        self._authorization_policy = authorization_policy or RuntimeAuthorizationPolicy()

    async def query(
        self,
        principal: ClientPrincipal,
        request: TranscriptPageRequest,
    ) -> TranscriptPage:
        """Authorization 済み scope の transcript page を返す。

        Returns:
            bounded transcript page。
        """
        self._authorization_policy.require_transcript_read(principal)
        cursor = _decode_cursor(request.cursor) if request.cursor is not None else None
        records = await self._store.query(
            TranscriptQuery(
                actor_id=request.scope.actor_id,
                account_id=request.scope.account_id,
                space_id=request.scope.space_id,
                session_id=request.scope.session_id,
                occurred_after=request.time_range.start,
                occurred_before=request.time_range.end,
                after_occurred_at=cursor.occurred_at if cursor is not None else None,
                after_transcript_id=cursor.transcript_id if cursor is not None else None,
                limit=request.limit + 1,
            )
        )
        page_records = records[: request.limit]
        next_cursor = _cursor_for(page_records[-1]) if len(records) > request.limit else None
        return TranscriptPage(records=page_records, next_cursor=next_cursor)

    async def export(
        self,
        principal: ClientPrincipal,
        request: TranscriptExportRequest,
    ) -> TranscriptExport:
        """Authorization 済み scope の bounded transcript export を返す。

        Returns:
            bounded transcript export。
        """
        self._authorization_policy.require_transcript_read(principal)
        records = await self._store.query(
            TranscriptQuery(
                actor_id=request.scope.actor_id,
                account_id=request.scope.account_id,
                space_id=request.scope.space_id,
                session_id=request.scope.session_id,
                occurred_after=request.time_range.start,
                occurred_before=request.time_range.end,
                limit=request.max_records + 1,
            )
        )
        export_records = records[: request.max_records]
        truncated = len(records) > request.max_records
        next_cursor = _cursor_for(export_records[-1]) if truncated else None
        return TranscriptExport(
            records=export_records,
            truncated=truncated,
            next_cursor=next_cursor,
        )


def _cursor_for(record: TranscriptRecord) -> str:
    """Record の stable ordering key を opaque cursor に変換する。

    Returns:
        次 page の start position を表す opaque cursor。
    """
    payload = _TranscriptCursor(
        occurred_at=record.occurred_at,
        transcript_id=record.transcript_id,
    )
    return base64.urlsafe_b64encode(payload.model_dump_json().encode("utf-8")).decode("ascii")


def _decode_cursor(value: str) -> _TranscriptCursor:
    """Opaque cursor を検証する。

    Returns:
        検証済み cursor payload。

    Raises:
        TranscriptQueryError: cursor の decode または validation に失敗した場合。
    """
    try:
        decoded = base64.urlsafe_b64decode(value.encode("ascii"))
        return _TranscriptCursor.model_validate_json(decoded)
    except (binascii.Error, UnicodeDecodeError, ValidationError, ValueError) as error:
        message = "invalid transcript cursor"
        raise TranscriptQueryError(message) from error
