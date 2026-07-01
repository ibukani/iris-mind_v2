"""開発・テスト用の決定論的埋め込み adapter。"""

from __future__ import annotations

import hashlib


class DeterministicFakeEmbedding:
    """SHA-256 を使う外部依存なしの固定次元埋め込み。"""

    def __init__(self, *, model: str = "fake-v1", dimension: int = 32) -> None:
        """モデル識別子と次元数で初期化する。

        Raises:
            ValueError: 次元数が正でない場合。
        """
        if dimension <= 0:
            msg = "Embedding dimension must be greater than zero"
            raise ValueError(msg)
        self._model_id = model
        self._dimension = dimension

    @property
    def provider(self) -> str:
        """Fake provider 識別子を返す。"""
        return "fake"

    @property
    def model_id(self) -> str:
        """設定されたモデル識別子を返す。"""
        return self._model_id

    @property
    def dimension(self) -> int:
        """出力次元数を返す。"""
        return self._dimension

    def embed(self, text: str) -> tuple[float, ...]:
        """決定論的な単位ベクトルを返す。

        Returns:
            固定次元ベクトル。
        """
        values = [0.0] * self._dimension
        for token in text.casefold().split():
            digest = hashlib.sha256(token.encode()).digest()
            slot = int.from_bytes(digest[:4], "big") % self._dimension
            values[slot] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = sum(value * value for value in values) ** 0.5
        if norm == 0:
            return tuple(values)
        return tuple(value / norm for value in values)

    def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        """入力順に埋め込みを返す。

        Returns:
            入力順の固定次元ベクトル。
        """
        return tuple(self.embed(text) for text in texts)
