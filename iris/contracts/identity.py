"""外部ユーザーまたはアクターを表すアイデンティティ契約。"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.core.ids import ExternalRef, UserId


@dataclass(frozen=True)
class Identity:
    """外部ユーザーまたはアクターのアイデンティティ。"""

    user_id: UserId
    display_name: str
    provider: str
    provider_subject: ExternalRef
    metadata: Mapping[str, str] = MappingProxyType({})
