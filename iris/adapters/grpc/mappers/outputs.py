"""runtime output contractからgRPC DTOへのmapper。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.generated.iris.api.v1 import outputs_pb2

if TYPE_CHECKING:
    from iris.contracts.actions import PresentedOutput


def presented_output_to_proto(output: PresentedOutput) -> outputs_pb2.PresentedOutput:
    """PresentedOutputをprotobuf DTOへ変換する。

    Returns:
        protobuf PresentedOutput。
    """
    return outputs_pb2.PresentedOutput(
        text=output.text or "",
        style_hint=output.style_hint or "",
        emotion_hint=output.emotion_hint or "",
        expression_hint=output.expression_hint or "",
        delay_ms=output.delay_ms,
        priority=output.priority,
        interruptible=output.interruptible,
    )
