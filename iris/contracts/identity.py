from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from iris.core.ids import ExternalRef, UserId


@dataclass(frozen=True)
class Identity:
    user_id: UserId
    display_name: str
    provider: str
    provider_subject: ExternalRef
    metadata: Mapping[str, str] = MappingProxyType({})
