"""小型モデル adapter 呼び出しで共有する provider-neutral metadata。"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from iris.contracts.metadata import ImmutableMetadata
from iris.contracts.model_policy import ModelCallKind
from iris.core.metadata import immutable_metadata

NonEmptyModelText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ModelInvocationMetadata(BaseModel):
    """小型モデル呼び出し結果に付与する安全なモデル識別 metadata。"""

    model_config = ConfigDict(frozen=True)

    call_kind: ModelCallKind
    provider: NonEmptyModelText
    model_name: NonEmptyModelText
    adapter_name: NonEmptyModelText
    model_version: NonEmptyModelText | None = None
    model_slot: NonEmptyModelText | None = None
    metadata: ImmutableMetadata = Field(default_factory=immutable_metadata)
