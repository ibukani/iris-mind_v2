"""Architecture guard: suppression debt registry must not grow without human approval.

The committed snapshot file ``.agents/approved-suppression-debt.toml.snap``
records the SHA-256 hash of the approved registry.  Any change to the registry
(adding entries, extending expiration dates, weakening reasons) will change
the hash and cause this test to fail.

Removing entries also changes the hash; humans may update both the registry
and the snapshot together as part of a dedicated approval task.

Coding agents must not edit either file during normal implementation tasks.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY_PATH = PROJECT_ROOT / ".agents" / "approved-suppression-debt.toml"
SNAPSHOT_PATH = PROJECT_ROOT / ".agents" / "approved-suppression-debt.toml.snap"


def _compute_registry_hash() -> str:
    """Compute the SHA-256 hash of the registry file.

    Returns:
        Hex-encoded SHA-256 digest.
    """
    content = REGISTRY_PATH.read_bytes()
    return hashlib.sha256(content).hexdigest()


def _read_snapshot_hash() -> str | None:
    """Read the expected hash from the snapshot file.

    Returns:
        Whitespace-stripped hash string, or None if the snapshot is missing.
    """
    if not SNAPSHOT_PATH.is_file():
        return None
    return SNAPSHOT_PATH.read_text(encoding="utf-8").strip()


def test_suppression_debt_registry_matches_committed_snapshot() -> None:
    """Registry hash must match the committed snapshot.

    Any change to the registry requires a human-approved snapshot update.

    Raises:
        AssertionError: If the snapshot is missing or the hash does not match.
    """
    current_hash = _compute_registry_hash()
    snapshot_hash = _read_snapshot_hash()

    if snapshot_hash is None:
        msg = (
            "missing snapshot file .agents/approved-suppression-debt.toml.snap\n"
            f"current registry hash: {current_hash}\n"
            "create the snapshot file with this hash as part of a human approval task"
        )
        raise AssertionError(msg)

    if current_hash != snapshot_hash:
        msg = (
            "suppression debt registry changed without human approval\n"
            f"current hash:  {current_hash}\n"
            f"snapshot hash: {snapshot_hash}\n"
            "if this change is human-approved, update the snapshot file with the new hash"
        )
        raise AssertionError(msg)
