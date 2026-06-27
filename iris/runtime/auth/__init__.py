"""Runtime RPC auth boundary exports."""

from __future__ import annotations

from iris.runtime.auth.context import bind_principal, current_principal, reset_principal
from iris.runtime.auth.errors import (
    RuntimeAuthError,
    RuntimePermissionDeniedError,
    RuntimeUnauthenticatedError,
)
from iris.runtime.auth.policy import ObservationRequestClaims, RuntimeAuthorizationPolicy
from iris.runtime.auth.principals import ClientKind, ClientPrincipal, local_dev_principal
from iris.runtime.auth.scopes import AuthScope

__all__ = [
    "AuthScope",
    "ClientKind",
    "ClientPrincipal",
    "ObservationRequestClaims",
    "RuntimeAuthError",
    "RuntimeAuthorizationPolicy",
    "RuntimePermissionDeniedError",
    "RuntimeUnauthenticatedError",
    "bind_principal",
    "current_principal",
    "local_dev_principal",
    "reset_principal",
]
