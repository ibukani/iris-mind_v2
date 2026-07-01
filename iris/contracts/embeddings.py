"""埋め込みモデルのプロバイダ中立契約。"""

from __future__ import annotations

from typing import Protocol


class EmbeddingModel(Protocol):
    """テキストを固定次元ベクトルへ変換する契約。"""

    @property
    def model_id(self) -> str:
        """Index compatibility 判定に使う安定したモデル識別子。"""
        ...

    @property
    def dimension(self) -> int:
        """出力ベクトルの次元数。"""
        ...

    def embed(self, text: str) -> tuple[float, ...]:
        """単一テキストを埋め込む。"""
        ...

    def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        """テキスト群を入力順で埋め込む。"""
        ...
