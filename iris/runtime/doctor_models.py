"""Runtime doctor の結果モデル。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeDoctorCheck:
    """runtime doctor の単一 check 結果。"""

    name: str
    status: str
    summary: str
    issue: str | None = None
    next_action: str | None = None


@dataclass(frozen=True)
class RuntimeDoctorReport:
    """runtime doctor の全体結果。"""

    ok: bool
    checks: tuple[RuntimeDoctorCheck, ...]


@dataclass(frozen=True)
class OperationalStatusSummary:
    """Operational count query の結果状態と危険件数を保持する。"""

    summary: str
    status: str = "ok"
    pending_count: int = 0
    leased_count: int = 0
    failed_count: int = 0
    issue: str | None = None
    next_action: str | None = None


@dataclass(frozen=True)
class SQLiteSchemaGate:
    """read-only SQLite count query の前提状態。"""

    available: bool
    check: RuntimeDoctorCheck | None = None


def build_check(
    name: str,
    *,
    status: str,
    summary: str,
    issue: str | None = None,
    next_action: str | None = None,
) -> RuntimeDoctorCheck:
    """単一 doctor check を構築する。

    Returns:
        指定内容を保持する immutable check。
    """
    return RuntimeDoctorCheck(
        name=name,
        status=status,
        summary=summary,
        issue=issue,
        next_action=next_action,
    )


def build_report(
    checks: tuple[RuntimeDoctorCheck, ...] | list[RuntimeDoctorCheck],
) -> RuntimeDoctorReport:
    """Check 列から doctor report を構築する。

    Returns:
        fail check がなければ ok の report。
    """
    ok = all(check.status != "fail" for check in checks)
    return RuntimeDoctorReport(ok=ok, checks=tuple(checks))
