"""配送先ユーザー制御状態の runtime store。"""

from __future__ import annotations

from typing import override

from iris.contracts.user_control import DeliveryUserControlStore, UserControlState


class InMemoryDeliveryUserControlStore(DeliveryUserControlStore):
    """Process-local の配送先ユーザー制御状態 store。"""

    def __init__(self) -> None:
        """空の store を作成する。"""
        self._states: dict[str, UserControlState] = {}

    @override
    async def get(self, target_key: str) -> UserControlState | None:
        """Target の制御状態を返す。

        Returns:
            保存済み状態。未保存なら None。
        """
        return self._states.get(target_key)

    @override
    async def set(self, target_key: str, state: UserControlState) -> None:
        """Target の制御状態を保存する。"""
        self._states[target_key] = state

    def states(self) -> dict[str, UserControlState]:
        """テスト・診断用の immutable snapshot を返す。

        Returns:
            現在保持する target と制御状態の snapshot。
        """
        return dict(self._states)
