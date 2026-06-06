"""Iris 観測のための、トランスポート非依存ランタイムサービス境界。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.contracts.actions import PresentedOutput
    from iris.contracts.observations import Observation
    from iris.core.ids import CorrelationId
    from iris.runtime.app import IrisApp


@dataclass(frozen=True)
class ObservationEnvelope:
    """受信観測を入れるトランスポート非依存コンテナ。"""

    observation: Observation
    correlation_id: CorrelationId | None = None


@dataclass(frozen=True)
class RuntimeResponse:
    """IrisRuntimeService が返すトランスポート非依存の結果。"""

    output: PresentedOutput
    correlation_id: CorrelationId | None = None


class IrisRuntimeService:
    """観測を IrisApp へ委譲する薄いランタイムサービス。"""

    def __init__(self, app: IrisApp) -> None:
        """明示的に注入された IrisApp でサービスを生成する。"""
        self._app = app

    async def handle_observation(self, envelope: ObservationEnvelope) -> RuntimeResponse:
        """ObservationEnvelope を IrisApp 経由で処理する。

        Returns:
            RuntimeResponse: PresentedOutput と保持された correlation ID。
        """
        output = await self._app.process_observation(envelope.observation)
        return RuntimeResponse(output=output, correlation_id=envelope.correlation_id)
