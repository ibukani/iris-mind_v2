"""gRPC stub 呼び出し用ヘルパー。

grpc の生成 stub（非同期）が Awaitable[ProtobufResponse] を返すが、
呼び出し側で protobuf 固有型に依存せず await したい場合に使う。
呼び出し側は結果を ``cast`` で適切な型に復元する。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from iris.contracts.actions import PresentedOutput
from iris.runtime.service import IrisRuntimeService, RuntimeResponse

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from iris.runtime.service import ObservationEnvelope


async def grpc_call(coro: Awaitable[object]) -> object:
    """Grpc stub 呼び出しの awaitable を await して結果を返す。

    Args:
        coro: grpc 非同期 stub メソッドの戻り値。

    Returns:
        object: gRPC レスポンスオブジェクト。
    """
    return await coro


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
