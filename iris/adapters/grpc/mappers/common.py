"""gRPC mapper群で共有する検証・変換primitive。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, NoReturn

from google.protobuf.timestamp_pb2 import Timestamp

if TYPE_CHECKING:
    from collections.abc import Mapping


class GrpcMappingError(ValueError):
    """gRPC DTOをIris contractへ変換できない場合の例外。"""


def metadata_dict(metadata: Mapping[str, str]) -> dict[str, str]:
    """Protobuf mapを通常の辞書へコピーする。

    Returns:
        コピー済みmetadata。
    """
    return dict(metadata.items())


def datetime_from_proto_timestamp(timestamp: Timestamp, *, field_name: str) -> datetime:
    """Protobuf Timestampをtimezone-aware datetimeへ変換する。

    Returns:
        UTC timezoneを持つdatetime。
    """
    try:
        value = timestamp.ToDatetime(tzinfo=UTC)
    except (OverflowError, ValueError) as exc:
        raise_mapping_error(f"{field_name} is invalid", cause=exc)
    if value.tzinfo is None:
        raise_mapping_error(f"{field_name} must be timezone-aware")
    return value


def timestamp_from_datetime(value: datetime) -> Timestamp:
    """timezone-aware datetimeをprotobuf Timestampへ変換する。

    Returns:
        protobuf Timestamp。
    """
    timestamp = Timestamp()
    timestamp.FromDatetime(value)
    return timestamp


def raise_mapping_error(
    message: str,
    *,
    cause: BaseException | None = None,
) -> NoReturn:
    """GrpcMappingErrorを送出する。

    Raises:
        GrpcMappingError: 常に送出。
    """
    if cause is None:
        raise GrpcMappingError(message)
    raise GrpcMappingError(message) from cause
