"""学習フックの分離実行。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import TracebackType

    from iris.contracts.learning import LearningEvent
    from iris.features.definition import LearningHook


class LearningHookRunner:
    """登録順に学習フックを実行し、個別障害を隔離する。"""

    def __init__(self, hooks: Sequence[LearningHook]) -> None:
        """登録順を固定して初期化する。"""
        self._hooks = tuple(hooks)

    async def run(self, event: LearningEvent) -> None:
        """全フックを登録順に実行する。"""
        for hook in self._hooks:
            with _LogLearningHookFailure(hook):
                await hook.after_action_result(event)


class _LogLearningHookFailure:
    """学習フック障害をログして後続実行を許可する。"""

    def __init__(self, hook: LearningHook) -> None:
        self._hook = hook

    def __enter__(self) -> None:
        return None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        _ = exc_type, traceback
        if exc is None or not isinstance(exc, Exception):
            return False
        logger.exception("learning hook failed: {}", type(self._hook).__name__)
        return True
