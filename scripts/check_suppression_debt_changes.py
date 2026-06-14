"""Guard suppression-debt registry changes against silent debt growth.

The registry files ``.agents/approved-suppression-debt.toml`` and its
``.snap`` companion form the human-approved debt ledger. They are normally
read-only for coding agents; only a human-approved task may update them.

This script:

* Computes the merge base against the default branch (``main`` or
  ``origin/main``).
* Lists the files changed on the current branch since that base.
* Fails the gate if either registry file appears in the diff and the
  environment variable ``IRIS_APPROVE_SUPPRESSION_DEBT_UPDATE`` is unset.

The approval signal is intentionally hard to trigger accidentally:

* A single env var name is reserved for this exact use.
* The script does not honour commit-message strings, branch names, or
  file-level markers.
* Only the human reviewer can export the env var, either locally or in
  CI, after a manual review of the proposed debt entries.

This is paired with ``tests/architecture/test_suppression_debt_registry.py``
which validates the entry shape, expiry, and exact line references. The
two layers complement each other:

* The architecture test is run on every push and guarantees the registry
  contents are consistent with the code.
* This script is run on every push and guarantees the registry has not
  been silently expanded without explicit human approval.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import sys
from typing import TYPE_CHECKING

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts._subprocess_runner import run as _run_command

if TYPE_CHECKING:
    from collections.abc import Sequence

PROTECTED_DEBT_PATHS: tuple[str, ...] = (
    ".agents/approved-suppression-debt.toml",
    ".agents/approved-suppression-debt.toml.snap",
)

APPROVAL_ENV_VAR = "IRIS_APPROVE_SUPPRESSION_DEBT_UPDATE"

# Branches that count as a "base" for computing the changed-file set.
# ``main`` is the long-lived default branch. ``origin/main`` is the
# remote mirror that CI sees. Both are tried in order; whichever exists
# wins.
BASE_BRANCH_CANDIDATES: tuple[str, ...] = (
    "origin/main",
    "main",
)

# Minimum parts in a single ``git diff --name-status`` row.
MIN_DIFF_PARTS = 2


@dataclass(frozen=True)
class DebtChange:
    """One registry file changed since the merge base."""

    path: str
    status: str  # git porcelain status code: M, A, D, R, etc.


def _git(*args: str) -> str:
    """Run a git command and return its stdout, or raise on failure.

    Args:
        *args: Arguments appended to ``git`` in the subprocess call.

    Returns:
        Captured standard output of the git invocation.

    Raises:
        RuntimeError: If the git invocation exits with a non-zero status.
    """
    completed = _run_command(
        ("git", *args),
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        msg = (
            f"git {' '.join(args)} failed with exit code {completed.returncode}: "
            f"{(completed.stderr or '').strip()}"
        )
        raise RuntimeError(msg)
    return completed.stdout or ""


def _resolve_merge_base() -> str | None:
    """Return the merge-base commit hash, or None if no candidate branch exists.

    Returns:
        Hex commit hash of the merge base, or None if neither candidate
        branch (``origin/main``, ``main``) resolves locally.
    """
    for candidate in BASE_BRANCH_CANDIDATES:
        completed = _git("rev-parse", "--verify", "--quiet", candidate)
        # ``rev-parse --quiet`` returns empty stdout for unknown refs
        # instead of raising. We treat any empty result as missing.
        if completed.strip():
            merge_base = _git("merge-base", "HEAD", candidate).strip()
            if merge_base:
                return merge_base
    return None


def _parse_name_status(output: str) -> list[DebtChange]:
    """Parse ``git diff --name-status`` output into ``DebtChange`` records.

    Args:
        output: Standard output of ``git diff --name-status -M``.

    Returns:
        List of ``DebtChange`` entries, one per diff line.
    """
    changes: list[DebtChange] = []
    for raw_line in output.splitlines():
        if not raw_line.strip():
            continue
        # ``git diff --name-status -M`` lines look like "M\tpath" or
        # "R100\told\tnew". Use rsplit to keep rename targets intact.
        parts = raw_line.split("\t")
        if len(parts) < MIN_DIFF_PARTS:
            continue
        status = parts[0]
        path = parts[-1]
        changes.append(DebtChange(path=path, status=status))
    return changes


def _detect_debt_changes() -> list[DebtChange]:
    """Return the subset of branch changes that touch the debt registry.

    Returns:
        Registry-file changes detected since the merge base, or an empty
        list if no base branch is available locally.
    """
    merge_base = _resolve_merge_base()
    if merge_base is None:
        # No base branch available (e.g. shallow clone in early CI). The
        # registry validation tests still run, but the merge-base guard
        # cannot. Do not fail the gate; the architecture tests are the
        # last line of defence.
        sys.stdout.write(
            "==> debt registry guard: no base branch found, skipping merge-base diff check\n"
        )
        return []

    diff_output = _git(
        "diff",
        "--name-status",
        "-M",
        f"{merge_base}...HEAD",
        "--",
        ".",
    )
    all_changes = _parse_name_status(diff_output)
    return [c for c in all_changes if c.path in PROTECTED_DEBT_PATHS]


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument sequence (defaults to ``sys.argv[1:]``).

    Returns:
        Parsed namespace.
    """
    parser = argparse.ArgumentParser(
        description=("Guard suppression-debt registry changes against silent debt growth."),
    )
    parser.add_argument(
        "--list-changes",
        action="store_true",
        help="Print the list of changed registry files and exit.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the registry-change guard.

    Args:
        argv: Optional argument sequence; defaults to ``sys.argv[1:]``.

    Returns:
        0 if the guard passes, 1 if it fails.
    """
    args = parse_args(sys.argv[1:] if argv is None else argv)

    debt_changes = _detect_debt_changes()

    if args.list_changes:
        for change in debt_changes:
            sys.stdout.write(f"{change.status}\t{change.path}\n")
        return 0

    if not debt_changes:
        sys.stdout.write("==> debt registry guard: no registry changes detected vs merge base\n")
        return 0

    changed_paths = "\n".join(f"  - {change.status}  {change.path}" for change in debt_changes)
    if os.environ.get(APPROVAL_ENV_VAR) == "1":
        approval_message = (
            f"==> debt registry guard: human approval signal present "
            f"({APPROVAL_ENV_VAR}=1); accepting changes\n"
        )
        sys.stdout.write(approval_message)
        sys.stdout.write(f"==> changed registry files:\n{changed_paths}\n")
        return 0

    failure_header = "==> debt registry guard FAILED: suppression-debt registry changed"
    failure_header += " without human approval"
    sys.stdout.write(f"{failure_header}\n")
    sys.stdout.write("==> Changed registry files (vs merge base with main):\n")
    sys.stdout.write(f"{changed_paths}\n")
    notice_lines = [
        "",
        "==> These files record the only approved suppression debt in the",
        "==> repository. They are normally read-only for coding agents.",
        "==>",
        "==> If this change is part of a human-approved debt update:",
    ]
    export_hint = f"==>   export {APPROVAL_ENV_VAR}=1"
    notice_lines.append(export_hint)
    notice_lines.extend(
        [
            "==>   re-run the gate.",
            "==>",
            "==> If this change is accidental, revert the registry files and",
            "==> rerun. Do not commit them as part of a normal implementation,",
            "==> refactor, test-fix, or feature task. New debt entries require",
            "==> a human reviewer to set the approval signal above.",
            "",
        ]
    )
    failure_notice = "\n".join(notice_lines)
    sys.stdout.write(failure_notice)
    sys.stdout.flush()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
