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
    """協調キャンセル通知を background/provider 文脈で処理する callback。"""

    def __call__(self) -> None:
        """停止処理を呼び出し側の文脈で実行する。"""
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
    execution context でこの token を確認し、停止できた時点で
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
        """協調キャンセルを要求する。

        この method は user-facing hot path の lease acquisition から呼ばれるため、
        登録 callback を同期実行しない。background worker / provider 側は
        cancellation_requested を観測した自分の実行文脈で
        run_cancellation_callbacks() を呼び、停止処理を進める。
        """
        self._cancel_requested.set()

    def register_cancellation_callback(self, callback: InferenceCancellationCallback) -> None:
        """キャンセル要求後に実行できる callback を登録する。

        callback は登録時にも request_cancellation() 時にも実行されない。
        background worker / provider 側が自分の文脈で run_cancellation_callbacks() を
        呼んだときだけ実行される。
        """
        with self._lock:
            if self._stopped.is_set():
                return
            self._callbacks.append(callback)

    def run_cancellation_callbacks(self) -> int:
        """登録 callback を呼び出し側の文脈で実行する。

        Returns:
            実行した callback 件数。
        """
        if not self._cancel_requested.is_set():
            return 0
        with self._lock:
            callbacks = tuple(self._callbacks)
            self._callbacks.clear()
        for callback in callbacks:
            callback()
        return len(callbacks)

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
    if site in {ModelCallSite.PROACTIVE, ModelCallSite.EVENT_REACTION}:
        return InferenceWorkPriority.PROACTIVE
    return InferenceWorkPriority.BACKGROUND
