# Copyright (c) 2026 Iris contributors
"""Print a compact git-aware completion report skeleton for coding agents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess  # noqa: S404 -- local report helper runs fixed git command tuples only
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class CommandResult:
    """Captured command result."""

    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


def run_git(args: tuple[str, ...]) -> CommandResult:
    """Run a git command if git is available.

    Returns:
        Captured git command result, or a synthetic failure when git is missing.
    """
    git_path = shutil.which("git")
    if git_path is None:
        return CommandResult(("git", *args), 127, "", "git executable not found")

    command = (git_path, *args)
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return CommandResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )


def bullet_lines(value: str) -> list[str]:
    """Convert command output to bullet lines.

    Returns:
        Non-empty lines suitable for a markdown bullet list.
    """
    if not value:
        return ["なし"]
    return [line for line in value.splitlines() if line.strip()]


def write_bullets(title: str, lines: list[str]) -> None:
    """Write a Japanese report section."""
    sys.stdout.write(f"{title}\n")
    for line in lines:
        sys.stdout.write(f"- {line}\n")
    sys.stdout.write("\n")


def output_or_notice(result: CommandResult) -> str:
    """Return stdout or a compact unavailable notice."""
    if result.returncode == 0:
        return result.stdout
    if result.stderr:
        return f"git unavailable: {result.stderr}"
    return f"git unavailable: exit {result.returncode}"


def main() -> int:
    """Print the report skeleton.

    Returns:
        Always zero because this command should still be useful outside git.
    """
    inside_work_tree = run_git(("rev-parse", "--is-inside-work-tree"))
    if inside_work_tree.returncode == 0:
        status = run_git(("status", "--short"))
        diff_stat = run_git(("diff", "--stat"))
        changed_files = output_or_notice(status)
        diff_summary = output_or_notice(diff_stat)
    else:
        changed_files = output_or_notice(inside_work_tree)
        diff_summary = "git diff unavailable outside a git working tree"

    write_bullets("変更ファイル", bullet_lines(changed_files))
    write_bullets("差分概要", bullet_lines(diff_summary))
    write_bullets(
        "検証",
        [
            "make ai-test-target TARGET=<必要なテスト>",
            "make ai-quick",
            "make ai-check",
        ],
    )
    write_bullets(
        "残リスク",
        [
            "未実行コマンドがある場合はここに書く",
            "既存失敗がある場合は最初の失敗をここに書く",
        ],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
