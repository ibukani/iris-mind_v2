"""Runtime doctor の read-only filesystem 検査。"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import TYPE_CHECKING

from iris.runtime.doctor_models import build_check

if TYPE_CHECKING:
    from pathlib import Path

    from iris.runtime.doctor_models import RuntimeDoctorCheck


@dataclass(frozen=True)
class FilePathCheckSpec:
    """Filesystem path check の表示文言と remediation を束ねる。"""

    name: str
    directory_summary: str
    directory_issue: str
    directory_next_action: str
    existing_ok_summary: str
    existing_fail_summary: str
    existing_fail_issue: str
    existing_fail_next_action: str
    missing_ok_summary: str
    missing_fail_summary: str
    missing_fail_issue: str
    missing_fail_next_action: str


def check_file_path(path: Path, *, spec: FilePathCheckSpec) -> RuntimeDoctorCheck:
    """Path の種別と権限を read-only で検査する。

    Returns:
        path 状態を表す doctor check。
    """
    if path.is_dir():
        return _directory_file_path_check(path, spec=spec)
    if path.exists():
        return _existing_file_path_check(path, spec=spec)
    return _missing_file_path_check(path, spec=spec)


def _directory_file_path_check(path: Path, *, spec: FilePathCheckSpec) -> RuntimeDoctorCheck:
    return _build_file_path_check(
        spec,
        status="fail",
        summary=spec.directory_summary.format(path=path),
        issue=spec.directory_issue,
        next_action=spec.directory_next_action,
    )


def _existing_file_path_check(path: Path, *, spec: FilePathCheckSpec) -> RuntimeDoctorCheck:
    if os.access(path, os.R_OK) and os.access(path, os.W_OK):
        return _build_file_path_check(
            spec,
            status="ok",
            summary=spec.existing_ok_summary.format(path=path, parent=path.parent),
        )
    return _build_file_path_check(
        spec,
        status="fail",
        summary=spec.existing_fail_summary.format(path=path, parent=path.parent),
        issue=spec.existing_fail_issue,
        next_action=spec.existing_fail_next_action,
    )


def _missing_file_path_check(path: Path, *, spec: FilePathCheckSpec) -> RuntimeDoctorCheck:
    parent = path.parent
    if parent.exists() and os.access(parent, os.W_OK | os.X_OK):
        return _build_file_path_check(
            spec,
            status="ok",
            summary=spec.missing_ok_summary.format(path=path, parent=parent),
        )
    return _build_file_path_check(
        spec,
        status="fail",
        summary=spec.missing_fail_summary.format(path=path, parent=parent),
        issue=spec.missing_fail_issue,
        next_action=spec.missing_fail_next_action,
    )


def _build_file_path_check(
    spec: FilePathCheckSpec,
    *,
    status: str,
    summary: str,
    issue: str | None = None,
    next_action: str | None = None,
) -> RuntimeDoctorCheck:
    return build_check(
        spec.name,
        status=status,
        summary=summary,
        issue=issue,
        next_action=next_action,
    )
