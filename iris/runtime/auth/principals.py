"""Runtime RPC client principal 型。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from iris.runtime.auth.scopes import AuthScope

if TYPE_CHECKING:
    from iris.runtime.ingress.observation_ingress import ObservationCapability


class ClientKind(StrEnum):
    """Runtime RPC client 種別。"""

    LOCAL_DEV = "local_dev"
    EXTERNAL_CLIENT = "external_client"
    TRUSTED_ADAPTER = "trusted_adapter"
    ADMIN = "admin"


@dataclass(frozen=True)
class ClientPrincipal:
    """認証済み、または local-dev 用の RPC principal。"""

    client_id: str
    client_kind: ClientKind
    provider: str | None
    allowed_providers: frozenset[str]
    scopes: frozenset[AuthScope]
    observation_capabilities: frozenset[ObservationCapability]
    authenticated: bool


def local_dev_principal() -> ClientPrincipal:
    """Local development 用 principal を返す。

    Returns:
        local_dev principal。
    """
    return ClientPrincipal(
        client_id="local_dev",
        client_kind=ClientKind.LOCAL_DEV,
        provider=None,
        allowed_providers=frozenset({"*"}),
        scopes=frozenset(scope for scope in AuthScope),
        observation_capabilities=frozenset(),
        authenticated=False,
    )
