"""テスト用プライベートアクセスヘルパー。

白箱テストでプライベート属性にアクセスする際、
呼び出し側に noqa:SLF001 や pyright:ignore[reportPrivateUsage]
を要求しないようにするための薄いラッパー群。
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, get_origin

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import TypeGuard


def _check_type(value: object, expected_type: type, label: str) -> object:
    """Validate value against expected_type using isinstance.

    Handles parameterized generics (e.g., ``tuple[object, ...]``) by
    extracting the origin type via ``get_origin`` for the isinstance check.

    Args:
        value: The value to check.
        expected_type: Expected type, may be parameterized.
        label: Human-readable label for the error message.

    Returns:
        The value.

    Raises:
        TypeError: If value does not match expected_type.
    """
    check_type = get_origin(expected_type) or expected_type
    if not isinstance(value, check_type):
        actual = type(value).__name__
        expected = getattr(expected_type, "__name__", str(expected_type))
        msg = f"{label} must be {expected}, got {actual}"
        raise TypeError(msg)
    return value


def get_private_attr_as(obj: object, name: str, expected_type: type) -> object:
    """``object`` のプライベート属性 ``name`` を取得し、型を検証する。

    Args:
        obj: 対象オブジェクト。
        name: 属性名（先頭に ``_`` を含む）。
        expected_type: 期待する型。

    Returns:
        型検証済みの属性値。
    """
    value: object = getattr(obj, name)
    return _check_type(value, expected_type, name)


def get_private_attr_matching(
    obj: object,
    name: str,
    predicate: Callable[[object], TypeGuard[object]],
) -> object:
    """``object`` のプライベート属性 ``name`` を取得し、述語で型を検証する。

    実行時 isinstance が使えない型（例: Callable）向け。

    Args:
        obj: 対象オブジェクト。
        name: 属性名（先頭に ``_`` を含む）。
        predicate: TypeGuard 述語。

    Returns:
        述語検証済みの属性値。

    Raises:
        TypeError: 述語検証に失敗した場合。
    """
    value: object = getattr(obj, name)
    if not predicate(value):
        msg = f"{name} failed private attribute type validation"
        raise TypeError(msg)
    return value


def get_private_attr_path_as(
    obj: object,
    names: tuple[str, ...],
    expected_type: type,
) -> object:
    """``object`` のプライベート属性を深く辿り、型を検証する。

    Args:
        obj: 対象オブジェクト。
        names: 辿る属性名のタプル。
        expected_type: 期待する型。

    Returns:
        型検証済みの最終属性値。
    """
    value: object = obj
    for name in names:
        value = getattr(value, name)
    path = ".".join(names)
    return _check_type(value, expected_type, path)


def import_private_as(module: str, name: str, expected_type: type) -> object:
    """``module`` からプライベート名 ``name`` をインポートし、型を検証する。

    Args:
        module: モジュールパス（ドット区切り）。
        name: インポートする名前。
        expected_type: 期待する型。

    Returns:
        型検証済みのインポートオブジェクト。
    """
    mod = importlib.import_module(module)
    value: object = getattr(mod, name)
    label = f"{module}.{name}"
    return _check_type(value, expected_type, label)


def import_private_matching(
    module: str,
    name: str,
    predicate: Callable[[object], TypeGuard[object]],
) -> object:
    """``module`` からプライベート名 ``name`` をインポートし、述語で型を検証する。

    実行時 isinstance が使えない型（例: Callable）向け。

    Args:
        module: モジュールパス（ドット区切り）。
        name: インポートする名前。
        predicate: TypeGuard 述語。

    Returns:
        述語検証済みのインポートオブジェクト。

    Raises:
        TypeError: 述語検証に失敗した場合。
    """
    mod = importlib.import_module(module)
    value: object = getattr(mod, name)
    if not predicate(value):
        msg = f"{module}.{name} failed private import type validation"
        raise TypeError(msg)
    return value


def _is_callable(value: object) -> TypeGuard[Callable[..., object]]:
    """Runtime-checkable callable TypeGuard.

    Returns:
        TypeGuard result: True if value is callable.
    """
    return callable(value)
