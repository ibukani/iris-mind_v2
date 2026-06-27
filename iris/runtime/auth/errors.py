"""Runtime auth error 型。"""

from __future__ import annotations


class RuntimeAuthError(RuntimeError):
    """Runtime auth 境界の基底例外。"""


class RuntimeUnauthenticatedError(RuntimeAuthError):
    """RPC principal を認証できない場合の例外。"""


class RuntimePermissionDeniedError(RuntimeAuthError):
    """RPC principal に必要な権限がない場合の例外。"""
