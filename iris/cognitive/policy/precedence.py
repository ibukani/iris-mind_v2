"""Safety policy 間で共有する優先度規則。"""

from __future__ import annotations

from iris.contracts.safety import SafetyContextSeverity


def safety_severity_precedence(severity: SafetyContextSeverity) -> int:
    """Safety severity の比較用優先度を返す。

    Returns:
        HIGH、MEDIUM、LOW の順で大きい整数。
    """
    match severity:
        case SafetyContextSeverity.HIGH:
            return 3
        case SafetyContextSeverity.MEDIUM:
            return 2
        case SafetyContextSeverity.LOW:
            return 1
