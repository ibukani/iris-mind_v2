"""RUF069 回避用 exact-equality ヘルパー。

テストで ``assert x == 42.0`` と書くと ruff RUF069
（``approx`` や ``is`` を推奨）に引っかかることがある。
意図的な正確な等価比較をヘルパー関数内に閉じ込めることで、
呼び出し側にサプレッションを要求しない。
"""

from __future__ import annotations


def assert_exact_eq(actual: object, expected: object) -> None:
    """正確な等価比較を行い、失敗時に ``AssertionError`` を発生させる。

    Args:
        actual: 実際の値。
        expected: 期待値。
    """
    assert actual == expected
