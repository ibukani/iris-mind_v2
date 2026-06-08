"""gRPC stub 呼び出し用ヘルパー。

grpc の生成 stub が同期型として型付けされているため、
await する際に ``type: ignore[misc]`` が必要になる。
ヘルパー関数内に閉じ込めることで、呼び出し側のサプレションを不要にする。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from iris.contracts.actions import PresentedOutput
from iris.runtime.service import IrisRuntimeService, RuntimeResponse

if TYPE_CHECKING:
    from iris.runtime.service import ObservationEnvelope


async def grpc_call(coro: object) -> object:
    """Grpc stub 呼び出しの coroutine を await して結果を返す。

    Args:
        coro: grpc stub メソッドの戻り値（実際には awaitable）。

    Returns:
        object: gRPC レスポンスオブジェクト。
    """
    return await coro  # type: ignore[misc]  # grpc generated stub is typed as sync


class RecordingRuntimeService(IrisRuntimeService):
    """Fake runtime service that records envelopes and returns fixed output."""

    def __init__(self, text: str) -> None:
        """Initialize with fixed response text."""
        self._text = text
        self.envelope: ObservationEnvelope | None = None

    @override
    async def handle_observation(self, envelope: ObservationEnvelope) -> RuntimeResponse:
        """Record envelope and return fixed RuntimeResponse.

        Returns:
            RuntimeResponse: Fixed runtime response.
        """
        self.envelope = envelope
        return RuntimeResponse(
            output=PresentedOutput(text=self._text),
            correlation_id=envelope.correlation_id,
        )
