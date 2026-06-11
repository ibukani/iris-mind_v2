"""ランタイム安全性設定。"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True)
class RuntimeSafetyConfig:
    """ランタイム安全性設定。

    mode が "development" の場合、すべての安全性ゲートはパススルーになる。
    mode が "basic" の場合、BasicOutputSafetyGate が使用される。
    """

    mode: str = "development"
    max_output_chars: int = 4000


def apply_safety_env(
    config: RuntimeSafetyConfig,
    env: Mapping[str, str],
) -> RuntimeSafetyConfig:
    """環境変数から安全性設定を適用する。

    Args:
        config: ベースとなる安全性設定。
        env: 環境変数マッピング。

    Returns:
        環境変数値を反映した安全性設定。
    """
    mode = env.get("IRIS_SAFETY_MODE", config.mode)
    max_chars_str = env.get("IRIS_SAFETY_MAX_OUTPUT_CHARS")
    max_output_chars = config.max_output_chars
    if max_chars_str is not None:
        with contextlib.suppress(ValueError):
            max_output_chars = int(max_chars_str)
    return RuntimeSafetyConfig(mode=mode, max_output_chars=max_output_chars)
