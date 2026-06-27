"""Runtime auth principal context。"""

from __future__ import annotations

from contextvars import ContextVar, Token

from iris.runtime.auth.principals import ClientPrincipal, local_dev_principal

_PRINCIPAL: ContextVar[ClientPrincipal | None] = ContextVar(
    "iris_runtime_client_principal",
    default=None,
)


def current_principal() -> ClientPrincipal:
    """現在の RPC principal を返す。

    Returns:
        束縛済み principal。未束縛なら local_dev principal。
    """
    principal = _PRINCIPAL.get()
    if principal is None:
        return local_dev_principal()
    return principal


def bind_principal(principal: ClientPrincipal) -> Token[ClientPrincipal | None]:
    """現在の context に RPC principal を束縛する。

    Returns:
        reset 用 token。
    """
    return _PRINCIPAL.set(principal)


def reset_principal(token: Token[ClientPrincipal | None]) -> None:
    """以前の RPC principal context へ戻す。"""
    _PRINCIPAL.reset(token)
