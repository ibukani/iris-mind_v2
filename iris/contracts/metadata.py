"""契約境界で使用する不変メタデータ型。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated

from pydantic import AfterValidator, PlainSerializer

from iris.core.metadata import immutable_metadata


def _serialize_metadata(metadata: Mapping[str, str]) -> dict[str, str]:
    """不変メタデータをJSON互換dictへ変換する。

    Returns:
        シリアライズ可能な防御的コピー。
    """
    return dict(metadata)


ImmutableMetadata = Annotated[
    Mapping[str, str],
    AfterValidator(immutable_metadata),
    PlainSerializer(_serialize_metadata, return_type=dict[str, str]),
]
"""検証時に防御的コピーされ、JSONへdictとして出力されるメタデータ。"""
