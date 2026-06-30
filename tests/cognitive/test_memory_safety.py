"""Memory safety helper tests."""

from __future__ import annotations

from iris.cognitive.memory.safety import is_safe_preferred_name


def test_is_safe_preferred_name_accepts_japanese_names_with_particle_kana() -> None:
    """助詞にも使われる仮名を含む普通の呼称は reject しない。"""
    assert is_safe_preferred_name("にこ")
    assert is_safe_preferred_name("でん")
    assert is_safe_preferred_name("へい")


def test_is_safe_preferred_name_rejects_object_labeling_values() -> None:
    """対象物への命名指示から切り出された値は reject する。"""
    assert not is_safe_preferred_name("この変数をx")
    assert not is_safe_preferred_name("彼を太郎")
    assert not is_safe_preferred_name("this variable")
