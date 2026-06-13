"""イベント反応のユーザー向けテキストテンプレート。"""

from __future__ import annotations

from dataclasses import dataclass

from iris.contracts.activity import ActivityKind


@dataclass(frozen=True)
class EventReactionTemplateProvider:
    """ActivityKindからユーザー向けテキストを解決する。"""

    voice_joined_text: str = "Welcome back."
    app_opened_text: str = "Welcome back. I am here if you want to talk."

    def text_for_activity(self, kind: ActivityKind) -> str | None:
        """ActivityKindに対応するテンプレートテキストを返す。

        Returns:
            対応するテキスト、なければNone。
        """
        if kind is ActivityKind.VOICE_JOINED:
            return self.voice_joined_text
        if kind is ActivityKind.APP_OPENED:
            return self.app_opened_text
        return None
