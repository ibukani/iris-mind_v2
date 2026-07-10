"""Runtime doctor report の出力整形。"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.runtime.doctor_models import RuntimeDoctorCheck, RuntimeDoctorReport


def format_json(report: RuntimeDoctorReport) -> str:
    """Doctor report を JSON 文字列へ整形する。

    Returns:
        末尾改行付き JSON。
    """
    payload = {"ok": report.ok, "checks": [_check_payload(check) for check in report.checks]}
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def format_text(report: RuntimeDoctorReport) -> str:
    """Doctor report を人間向けテキストへ整形する。

    Returns:
        末尾改行付きテキスト。
    """
    lines = ["Runtime doctor ok:"] if report.ok else ["Runtime doctor failed:"]
    for check in report.checks:
        lines.extend(_format_check_block(check))
    return "\n".join(lines) + "\n"


def _check_payload(check: RuntimeDoctorCheck) -> dict[str, str | None]:
    return {
        "name": check.name,
        "status": check.status,
        "summary": check.summary,
        "issue": check.issue,
        "next_action": check.next_action,
    }


def _format_check_block(check: RuntimeDoctorCheck) -> list[str]:
    lines = ("", f"* {check.name}: {check.summary} [{check.status}]")
    block = [*lines]
    if check.issue is not None:
        block.append(f"  issue: {check.issue}")
    if check.next_action is not None:
        block.append(f"  next: {check.next_action}")
    return block
