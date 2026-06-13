"""テスト用プライベートアクセスヘルパー。

白箱テストでプライベート属性にアクセスする際、
呼び出し側に noqa:SLF001 や pyright:ignore[reportPrivateUsage]
を要求しないようにするための薄いラッパー群。
"""

from __future__ import annotations

import importlib
from typing import Any


def get_private_attr(obj: object, name: str) -> Any:  # noqa: ANN401 -- white-box test helper must return anything
    """``object`` のプライベート属性 ``name`` を取得する。

    Args:
        obj: 対象オブジェクト。
        name: 属性名（先頭に ``_`` を含む）。

    Returns:
        Any: 属性値（``getattr`` の戻り値をそのまま返す）。
    """
    return getattr(obj, name)


def get_private_attr_path(obj: object, *names: str) -> Any:  # noqa: ANN401 -- white-box test helper must return anything
    """``object`` のプライベート属性を深く辿って取得する。

    ``get_private_attr(get_private_attr(obj, "a"), "b")`` と書く代わりに
    ``get_private_attr_path(obj, "a", "b")`` と書ける。

    Args:
        obj: 対象オブジェクト。
        *names: 辿る属性名の可変長リスト。

    Returns:
        Any: 最後の属性値。
    """
    value: object = obj
    for name in names:
        value = getattr(value, name)
    return value


def import_private(module: str, name: str) -> Any:  # noqa: ANN401 -- white-box import helper must return anything
    """``module`` からプライベート名 ``name`` をインポートする。

    インポート文で noqa:PLC2701 / pyright:ignore[reportPrivateUsage]
    を不要にするための動的インポートラッパー。

    Args:
        module: モジュールパス（ドット区切り）。
        name: インポートする名前。

    Returns:
        Any: インポートされたオブジェクト。
    """
    mod = importlib.import_module(module)
    return getattr(mod, name)
