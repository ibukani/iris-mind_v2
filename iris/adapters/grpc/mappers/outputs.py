"""runtime output contractからgRPC DTOへのmapper。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.contracts.presentation_hints import PresentationHints, PresentationModality
from iris.generated.iris.api.v1 import outputs_pb2

if TYPE_CHECKING:
    from iris.contracts.actions import PresentedOutput


_PRESENTATION_MODALITY_TO_PROTO_NAME: dict[PresentationModality, str] = {
    PresentationModality.TEXT: "PRESENTATION_MODALITY_TEXT",
    PresentationModality.VOICE: "PRESENTATION_MODALITY_VOICE",
    PresentationModality.BOTH: "PRESENTATION_MODALITY_BOTH",
    PresentationModality.NOTIFICATION: "PRESENTATION_MODALITY_NOTIFICATION",
    PresentationModality.UNKNOWN: "PRESENTATION_MODALITY_UNKNOWN",
}


def presented_output_to_proto(output: PresentedOutput) -> outputs_pb2.PresentedOutput:
    """PresentedOutputをprotobuf DTOへ変換する。

    Returns:
        protobuf PresentedOutput。
    """
    hints = presentation_hints_to_proto(output.presentation_hints)
    return outputs_pb2.PresentedOutput(
        text=output.text or "",
        style_hint=hints.style_hint,
        emotion_hint=hints.emotion_hint,
        expression_hint=hints.expression_hint,
        delay_ms=hints.delay_ms,
        priority=hints.priority,
        interruptible=hints.interruptible,
        presentation_hints=hints,
    )


def presentation_hints_to_proto(
    hints: PresentationHints,
) -> outputs_pb2.PresentationHints:
    """正本の提示ヒントを共有protobuf DTOへ写像する。

    Returns:
        protobuf PresentationHints DTO。
    """
    return outputs_pb2.PresentationHints(
        style_hint=hints.style_hint or "",
        emotion_hint=hints.emotion_hint or "",
        expression_hint=hints.expression_hint or "",
        delay_ms=hints.delay_ms,
        priority=hints.priority,
        interruptible=hints.interruptible,
        modality=outputs_pb2.PresentationModality.Value(
            _PRESENTATION_MODALITY_TO_PROTO_NAME[hints.modality]
        ),
    )
