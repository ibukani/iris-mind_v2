"""runtime output contractからgRPC DTOへのmapper。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.generated.iris.api.v1 import outputs_pb2
from iris.generated.iris.runtime.v1 import runtime_pb2

if TYPE_CHECKING:
    from iris.contracts.actions import PresentedOutput
    from iris.runtime.service import RuntimeResponse


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


def runtime_response_to_proto(
    response: RuntimeResponse,
) -> runtime_pb2.SubmitObservationResponse:
    """RuntimeResponseをSubmitObservationResponseへ変換する。

    Returns:
        protobuf SubmitObservationResponse。
    """
    return runtime_pb2.SubmitObservationResponse(
        correlation_id=str(response.correlation_id or ""),
        output=presented_output_to_proto(response.output),
    )
