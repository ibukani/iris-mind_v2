"""ローカル推論資源 scheduler boundary の共有モデル。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
import threading
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from iris.contracts.metadata import ImmutableMetadata
from iris.contracts.model_policy import ModelCallSite
from iris.core.metadata import immutable_metadata


class InferenceCancellationCallback(Protocol):
    """協調キャンセル要求時の同期 callback。"""

    def __call__(self) -> None:
        """停止処理を同期実行する。"""
        ...


def _empty_callbacks() -> list[InferenceCancellationCallback]:
    return []


class InferenceResourceState(StrEnum):
    """ローカル推論資源の外部観測可能な状態。"""

    IDLE = "idle"
    BUSY = "busy"
    WARMING = "warming"
    UNAVAILABLE = "unavailable"


class InferenceSlotKind(StrEnum):
    """scheduler が管理する推論 slot 種別。"""

    LARGE_LLM = "large_llm"
    BACKGROUND_LLM = "background_llm"
    SMALL_CLASSIFIER = "small_classifier"
    EMBEDDING = "embedding"
    RERANKER = "reranker"


class InferenceWorkPriority(StrEnum):
    """推論資源 lease 要求の優先度。"""

    USER_FACING_RESPONSE = "user_facing_response"
    SAFETY_CRITICAL = "safety_critical"
    BACKGROUND = "background"
    PROACTIVE = "proactive"


class InferenceLeaseDecision(StrEnum):
    """非blocking lease 判定。"""

    ACQUIRED = "acquired"
    DEFER = "defer"
    CANCEL = "cancel"
    NO_SEND = "no_send"
    DENIED = "denied"


class InferenceLeaseRequest(BaseModel):
    """推論資源 lease の安全な要求メタデータ。"""

    model_config = ConfigDict(frozen=True)

    slot_kind: InferenceSlotKind
    priority: InferenceWorkPriority
    call_site: ModelCallSite
    model_slot: str | None = None
    model_name: str | None = None
    preemptible: bool = False
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)


@dataclass
class InferenceLeaseCancellationToken:
    """Preemptible lease の協調キャンセル状態。

    background LLM worker は provider call を開始する前、または provider 側の
    cancellation callback からこの token を確認し、停止できた時点で
    acknowledge_stopped() を呼ぶ。scheduler は acknowledge 済みの低優先度
    lease だけを user-facing lease に置き換える。
    """

    lease_id: str
    _cancel_requested: threading.Event = field(
        default_factory=threading.Event,
        init=False,
        repr=False,
        compare=False,
    )
    _stopped: threading.Event = field(
        default_factory=threading.Event,
        init=False,
        repr=False,
        compare=False,
    )
    _callbacks: list[InferenceCancellationCallback] = field(
        default_factory=_empty_callbacks,
        init=False,
        repr=False,
        compare=False,
    )
    _lock: threading.RLock = field(
        default_factory=threading.RLock,
        init=False,
        repr=False,
        compare=False,
    )

    @property
    def cancellation_requested(self) -> bool:
        """Preemption が要求済みなら True。"""
        return self._cancel_requested.is_set()

    @property
    def stopped(self) -> bool:
        """Worker / provider call が停止済みなら True。"""
        return self._stopped.is_set()

    def request_cancellation(self) -> None:
        """協調キャンセルを要求し、登録済み callback を同期実行する。"""
        with self._lock:
            self._cancel_requested.set()
            callbacks = tuple(self._callbacks)
            self._callbacks.clear()
        for callback in callbacks:
            callback()

    def register_cancellation_callback(self, callback: InferenceCancellationCallback) -> None:
        """キャンセル要求時に呼ばれる callback を登録する。

        既にキャンセル要求済みの場合は即時に callback を呼ぶ。
        """
        call_now = False
        with self._lock:
            if self._cancel_requested.is_set():
                call_now = True
            else:
                self._callbacks.append(callback)
        if call_now:
            callback()

    def acknowledge_stopped(self) -> None:
        """Worker / provider call が停止済みであることを通知する。"""
        self._stopped.set()


class InferenceResourceSnapshot(BaseModel):
    """scheduler の観測可能な resource snapshot。"""

    model_config = ConfigDict(frozen=True)

    state: InferenceResourceState
    active_large_slots: int = 0
    active_small_classifier_slots: int = 0
    active_embedding_slots: int = 0
    active_reranker_slots: int = 0
    busy_since: datetime | None = None
    busy_duration_seconds: float | None = None


class InferenceLeaseResult(BaseModel):
    """lease acquisition の決定論的な結果。"""

    model_config = ConfigDict(frozen=True)

    decision: InferenceLeaseDecision
    reason: str
    request: InferenceLeaseRequest
    snapshot: InferenceResourceSnapshot
    lease_id: str | None = None

    @property
    def acquired(self) -> bool:
        """推論資源を取得できた場合に True。"""
        return self.decision is InferenceLeaseDecision.ACQUIRED


def model_call_site_priority(site: ModelCallSite) -> InferenceWorkPriority:
    """ModelCallSite を #93 scheduler priority に写像する。

    Returns:
        InferenceWorkPriority: site に対応する推論資源優先度。
    """
    if site is ModelCallSite.USER_RESPONSE_HOT_PATH:
        return InferenceWorkPriority.USER_FACING_RESPONSE
    if site is ModelCallSite.PROACTIVE:
        return InferenceWorkPriority.PROACTIVE
    return InferenceWorkPriority.BACKGROUND
