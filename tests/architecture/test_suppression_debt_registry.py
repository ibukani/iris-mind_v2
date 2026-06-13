"""Architecture guard: suppression debt must be registered in the approved registry.

Protected layers (iris/contracts, iris/core, iris/cognitive, iris/features,
iris/presentation, iris/safety, iris/runtime) must never contain suppression
escape hatches.

Exception zones (iris/adapters, tests, scripts) may only contain suppression
escape hatches when the exact occurrence is registered in
.agents/approved-suppression-debt.toml.

This guard also validates registry entry integrity.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
import re
import tomllib as _toml_parser
from typing import TYPE_CHECKING, TypeGuard, override

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEBT_REGISTRY_PATH = PROJECT_ROOT / ".agents" / "approved-suppression-debt.toml"

# ---------------------------------------------------------------------------
# Layer classification
# ---------------------------------------------------------------------------

PROTECTED_ROOTS: tuple[str, ...] = (
    "iris/contracts",
    "iris/core",
    "iris/cognitive",
    "iris/features",
    "iris/presentation",
    "iris/safety",
    "iris/runtime",
)

EXCEPTION_ROOTS: tuple[str, ...] = (
    "iris/adapters",
    "tests",
    "scripts",
)

# Files and directories excluded from scanning entirely.
EXCLUDED_ROOTS: frozenset[str] = frozenset(
    {
        "iris/generated",
    }
)

# Architecture scanner files that contain suppression token strings as test
# fixture data.  They are excluded from detection.
SCANNER_FIXTURE_FILES: frozenset[str] = frozenset(
    {
        "tests/architecture/test_no_unapproved_suppressions.py",
        "tests/architecture/test_no_unreasoned_suppressions.py",
        "tests/architecture/test_no_file_level_suppressions.py",
        "tests/architecture/test_no_cast_in_protected_layers.py",
        "tests/architecture/test_suppression_debt_registry.py",
        "tests/architecture/test_suppression_debt_registry_is_frozen.py",
        "tests/architecture/test_workspace_frame_mutation_extended.py",
        "tests/architecture/test_workspace_frame_immutability.py",
    }
)

# ---------------------------------------------------------------------------
# Generic / weak reasons that are always rejected
# ---------------------------------------------------------------------------

GENERIC_REASONS: frozenset[str] = frozenset(
    {
        "fix lint",
        "fix ruff",
        "fix mypy",
        "fix pyright",
        "typing issue",
        "type issue",
        "mypy",
        "ruff",
        "pyright",
        "temporary",
        "temp",
        "ai fix",
        "ai",
        "suppress",
        "suppression",
        "noqa",
        "type ignore",
        "lint",
        "silence",
    }
)

# ---------------------------------------------------------------------------
# Occurrence kind constants
# ---------------------------------------------------------------------------

KIND_NOQA = "noqa"
KIND_TYPE_IGNORE = "type: ignore"
KIND_PYRIGHT_IGNORE = "pyright: ignore"
KIND_TYPING_CAST = "typing.cast"
KIND_OBJECT_SETATTR = "object.__setattr__"

ALL_KINDS: frozenset[str] = frozenset(
    {
        KIND_NOQA,
        KIND_TYPE_IGNORE,
        KIND_PYRIGHT_IGNORE,
        KIND_TYPING_CAST,
        KIND_OBJECT_SETATTR,
    }
)

# ---------------------------------------------------------------------------
# Compiled patterns for comment-based suppressions
# ---------------------------------------------------------------------------

_NOQA_PATTERN = re.compile(r"#[ \t]*noqa(?::[ \t]*([A-Z]+[0-9]+(?:[ \t]*,[ \t]*[A-Z]+[0-9]+)*))?")
_TYPE_IGNORE_PATTERN = re.compile(r"#[ \t]*type:[ \t]*ignore(\[[a-z0-9\-,]+\])?")
_PYRIGHT_IGNORE_PATTERN = re.compile(r"#[ \t]*pyright:[ \t]*ignore(\[[A-Za-z0-9_,]+\])?")

# ---------------------------------------------------------------------------
# Debt entry data class
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DebtEntry:
    """A single approved suppression-debt entry from the TOML registry."""

    path: str
    line: int
    kind: str
    rule_or_error_code: str
    reason: str
    alternative_attempted: str
    expires: str
    owner: str


@dataclass(frozen=True)
class Occurrence:
    """A detected suppression occurrence in source code."""

    path: str
    line: int
    kind: str
    rule_or_error: str
    text: str


# ---------------------------------------------------------------------------
# Registry parsing and validation
# ---------------------------------------------------------------------------


def _require_mapping(value: object, context: str) -> Mapping[str, object]:
    """Validate a TOML-loaded value is a table and normalize string keys.

    Args:
        value: Value from tomllib.load.
        context: Human label for the error message.

    Returns:
        Typed mapping with string keys.

    Raises:
        TypeError: If the value is not a dict.
    """
    if not _is_dict(value):
        msg = f"{context} must be a TOML table"
        raise TypeError(msg)
    return {str(key): item for key, item in value.items()}


def _require_sequence(value: object, context: str) -> Sequence[object]:
    """Validate a TOML-loaded value is an array.

    Args:
        value: Value from tomllib.load.
        context: Human label for the error message.

    Returns:
        Typed sequence.

    Raises:
        TypeError: If the value is not a list.
    """
    if not _is_list(value):
        msg = f"{context} must be a TOML array"
        raise TypeError(msg)
    return value


def _is_dict(value: object) -> TypeGuard[dict[object, object]]:
    """Narrow object to dict[object, object] for item iteration.

    Runtime check uses isinstance(dict) which erases type parameters, so the
    narrowed type uses the widest compatible parameter types.

    Returns:
        True if value is a dict, narrowing to the widened type.
    """
    return isinstance(value, dict)


def _is_list(value: object) -> TypeGuard[list[object]]:
    """Narrow object to list[object] for item iteration.

    Returns:
        True if value is a list, narrowing to the widened type.
    """
    return isinstance(value, list)


def _parse_debt_registry() -> tuple[DebtEntry, ...]:
    """Parse the approved suppression-debt registry TOML file.

    Returns:
        Tuple of validated DebtEntry objects.  Empty if the file does not
        exist or contains no entries.
    """
    if not DEBT_REGISTRY_PATH.exists():
        return ()

    with DEBT_REGISTRY_PATH.open("rb") as fh:
        data = _require_mapping(_toml_parser.load(fh), "debt registry root")

    debt_list = _require_sequence(data.get("debt", []), "debt registry [[debt]]")

    raw_entries: list[dict[str, object]] = [
        dict(_require_mapping(item, f"debt entry #{i}")) for i, item in enumerate(debt_list)
    ]

    entries: list[DebtEntry] = []
    for raw in raw_entries:
        entry = _build_entry_from_raw(raw)
        if entry is not None:
            entries.append(entry)
    return tuple(entries)


def _build_entry_from_raw(raw: dict[str, object]) -> DebtEntry | None:
    """Build a DebtEntry from a raw TOML dictionary, or None if invalid.

    Returns:
        DebtEntry if all fields are present and correctly typed, else None.
    """
    required_str_keys = (
        "path",
        "kind",
        "rule_or_error_code",
        "reason",
        "alternative_attempted",
        "expires",
        "owner",
    )
    values: dict[str, str] = {}
    for key in required_str_keys:
        val = raw.get(key)
        if not isinstance(val, str):
            return None
        values[key] = val

    line_val = raw.get("line")
    if not isinstance(line_val, int):
        return None

    return DebtEntry(
        path=values["path"],
        line=line_val,
        kind=values["kind"],
        rule_or_error_code=values["rule_or_error_code"],
        reason=values["reason"],
        alternative_attempted=values["alternative_attempted"],
        expires=values["expires"],
        owner=values["owner"],
    )


def _validate_registry_entries(entries: tuple[DebtEntry, ...]) -> list[str]:
    """Validate every debt registry entry for integrity.

    Returns:
        List of human-readable violation messages.  Empty when valid.
    """
    violations: list[str] = []
    seen: set[tuple[str, int, str]] = set()

    for entry in entries:
        violations.extend(_validate_single_entry(entry, seen))
    return violations


def _validate_single_entry(entry: DebtEntry, seen: set[tuple[str, int, str]]) -> list[str]:
    """Validate a single debt registry entry.

    Args:
        entry: Debt entry to validate.
        seen: Set of already-seen (path, line, kind) tuples for dedup.

    Returns:
        List of violation messages for this entry.
    """
    # Deduplicate
    key = (entry.path, entry.line, entry.kind)
    if key in seen:
        return [f"registry: duplicate entry {entry.path}:{entry.line} {entry.kind}"]
    seen.add(key)

    return _validate_entry_content(entry)


def _validate_entry_content(entry: DebtEntry) -> list[str]:
    """Validate the content of a single non-duplicate debt registry entry.

    Returns:
        List of violation messages. Empty if the entry is valid.
    """
    # Kind must be known
    if entry.kind not in ALL_KINDS:
        return [f"registry: {entry.path}:{entry.line} unknown kind '{entry.kind}'"]

    # Must not be in a protected layer
    if _in_protected_layer(entry.path):
        msg = (
            f"registry: {entry.path}:{entry.line} {entry.kind}"
            f" — entries in protected layers are forbidden"
        )
        return [msg]

    return _validate_entry_existence_and_content(entry)


def _validate_entry_existence_and_content(entry: DebtEntry) -> list[str]:
    """Validate that the referenced file and occurrence exist.

    Returns:
        Violation messages. Empty if existence checks pass.
    """
    # File must exist
    file_path = PROJECT_ROOT / entry.path
    if not file_path.is_file():
        msg = f"registry: {entry.path}:{entry.line} {entry.kind} — file does not exist"
        return [msg]

    # Occurrence must actually exist in the file
    occurrences = _find_occurrences_in_file(file_path)
    matching = [o for o in occurrences if o.line == entry.line and o.kind == entry.kind]
    if not matching:
        msg = f"registry: {entry.path}:{entry.line} {entry.kind} — occurrence not found in file"
        return [msg]

    return _validate_entry_reason_and_expiration(entry)


def _validate_entry_reason_and_expiration(entry: DebtEntry) -> list[str]:
    """Validate the reason text and expiration date.

    Returns:
        Violation messages. Empty if reason and expiration are valid.
    """
    # Reason must not be generic
    reason_lower = entry.reason.strip().lower()
    if reason_lower in GENERIC_REASONS or len(reason_lower) < 8:
        msg = (
            f"registry: {entry.path}:{entry.line} {entry.kind}"
            f" — reason is too generic: '{entry.reason}'"
        )
        return [msg]

    # Check expiration
    return _validate_expiration(entry)


def _validate_expiration(entry: DebtEntry) -> list[str]:
    """Validate the expiration date of a debt entry.

    Args:
        entry: Debt entry to check.

    Returns:
        Violation message list. Empty if expiration is valid.
    """
    try:
        expire_date = date.fromisoformat(entry.expires)
    except ValueError:
        msg = (
            f"registry: {entry.path}:{entry.line} {entry.kind}"
            f" — invalid expiration date: '{entry.expires}'"
        )
        return [msg]
    today = datetime.now(tz=UTC).date()
    if expire_date <= today:
        msg = f"registry: {entry.path}:{entry.line} {entry.kind} — expired on {entry.expires}"
        return [msg]
    return []


# ---------------------------------------------------------------------------
# File and layer helpers
# ---------------------------------------------------------------------------


def _relative_path(absolute: Path) -> str:
    """Return a project-relative path string."""
    return str(absolute.relative_to(PROJECT_ROOT))


def _in_protected_layer(rel_path: str) -> bool:
    """Return whether a relative path falls under a protected layer."""
    return any(rel_path == root or rel_path.startswith(f"{root}/") for root in PROTECTED_ROOTS)


def _in_exception_zone(rel_path: str) -> bool:
    """Return whether a relative path falls under an exception zone."""
    return any(rel_path == root or rel_path.startswith(f"{root}/") for root in EXCEPTION_ROOTS)


def _should_scan(rel_path: str) -> bool:
    """Return whether a file should be scanned for suppressions.

    Returns:
        True if the file is in scope and not excluded.
    """
    excluded = any(rel_path == root or rel_path.startswith(f"{root}/") for root in EXCLUDED_ROOTS)
    if excluded:
        return False
    return rel_path not in SCANNER_FIXTURE_FILES


def _python_files() -> tuple[Path, ...]:
    """Collect all Python files to scan for suppression occurrences.

    Returns:
        Sorted tuple of absolute paths.
    """
    files: list[Path] = []
    scan_roots = PROTECTED_ROOTS + EXCEPTION_ROOTS
    for root in scan_roots:
        base = PROJECT_ROOT / root
        if base.is_dir():
            files.extend(base.rglob("*.py"))
    main_py = PROJECT_ROOT / "main.py"
    if main_py.is_file():
        files.append(main_py)
    return tuple(sorted(files))


# ---------------------------------------------------------------------------
# Occurrence detection
# ---------------------------------------------------------------------------


def _find_comment_occurrences(path: Path) -> list[Occurrence]:
    """Find comment-based suppression occurrences in a file.

    Returns:
        List of Occurrence objects for each suppression comment.
    """
    occurrences: list[Occurrence] = []
    rel = _relative_path(path)
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        # Check for noqa comment
        match = _NOQA_PATTERN.search(line)
        if match:
            rules = match.group(1)
            occurrences.append(
                Occurrence(
                    path=rel,
                    line=line_number,
                    kind=KIND_NOQA,
                    rule_or_error=rules or "",
                    text=line.strip(),
                )
            )

        # Check for type: ignore comment
        match = _TYPE_IGNORE_PATTERN.search(line)
        if match:
            bracket = match.group(1)
            occurrences.append(
                Occurrence(
                    path=rel,
                    line=line_number,
                    kind=KIND_TYPE_IGNORE,
                    rule_or_error=bracket.strip("[]") if bracket else "",
                    text=line.strip(),
                )
            )

        # Check for pyright: ignore comment
        match = _PYRIGHT_IGNORE_PATTERN.search(line)
        if match:
            bracket = match.group(1)
            occurrences.append(
                Occurrence(
                    path=rel,
                    line=line_number,
                    kind=KIND_PYRIGHT_IGNORE,
                    rule_or_error=bracket.strip("[]") if bracket else "",
                    text=line.strip(),
                )
            )

    return occurrences


def _is_cast_call(node: ast.Call) -> bool:
    """Return whether an AST call invokes typing.cast or an imported cast alias."""
    match node.func:
        case ast.Name(id="cast"):
            return True
        case ast.Attribute(attr="cast"):
            return True
        case _:
            return False


def _is_object_setattr_call(node: ast.Call) -> bool:
    """Return whether an AST call invokes object.__setattr__."""
    return (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "__setattr__"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "object"
    )


class _SetattrVisitor(ast.NodeVisitor):
    """AST visitor that collects object.__setattr__ occurrences.

    Calls inside ``__post_init__`` are exempted (existing convention for
    frozen dataclass metadata normalization).
    """

    def __init__(self, rel_path: str) -> None:
        self.rel_path = rel_path
        self.occurrences: list[Occurrence] = []

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name == "__post_init__":
            return
        self.generic_visit(node)

    @override
    def visit_Call(self, node: ast.Call) -> None:
        if _is_object_setattr_call(node):
            self.occurrences.append(
                Occurrence(
                    path=self.rel_path,
                    line=node.lineno,
                    kind=KIND_OBJECT_SETATTR,
                    rule_or_error="",
                    text="object.__setattr__(...)",
                )
            )
        self.generic_visit(node)


def _find_ast_occurrences(path: Path) -> list[Occurrence]:
    """Find AST-based suppression occurrences (typing.cast, object.__setattr__).

    Returns:
        List of Occurrence objects.
    """
    occurrences: list[Occurrence] = []
    rel_path = _relative_path(path)

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return occurrences

    # typing.cast / cast() calls
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_cast_call(node):
            text = ast.unparse(node) if hasattr(ast, "unparse") else "cast(...)"
            occurrences.append(
                Occurrence(
                    path=rel_path,
                    line=node.lineno,
                    kind=KIND_TYPING_CAST,
                    rule_or_error="",
                    text=text,
                )
            )

    # object.__setattr__ calls
    visitor = _SetattrVisitor(rel_path)
    visitor.visit(tree)
    occurrences.extend(visitor.occurrences)

    return occurrences


def _find_occurrences_in_file(path: Path) -> list[Occurrence]:
    """Find all suppression occurrences in a single file.

    Returns:
        Combined list of comment-based and AST-based suppression occurrences.
    """
    occurrences: list[Occurrence] = []
    occurrences.extend(_find_comment_occurrences(path))
    occurrences.extend(_find_ast_occurrences(path))
    return occurrences


# ---------------------------------------------------------------------------
# Violation detection
# ---------------------------------------------------------------------------


def _check_bare_rule(occ: Occurrence) -> str | None:
    """Return violation message if the occurrence uses a bare suppression.

    Bare ``noqa`` and bare ``type: ignore`` are always forbidden.
    Bare ``pyright: ignore`` without a specific rule is also forbidden.

    Returns:
        Violation message string, or None if the suppression includes a rule code.
    """
    if occ.kind == KIND_NOQA and not occ.rule_or_error:
        return f"{occ.path}:{occ.line}: bare '# noqa' is forbidden — must include rule code"
    if occ.kind == KIND_TYPE_IGNORE and not occ.rule_or_error:
        return (
            f"{occ.path}:{occ.line}: bare '# type: ignore' is forbidden — must include error code"
        )
    if occ.kind == KIND_PYRIGHT_IGNORE and not occ.rule_or_error:
        return (
            f"{occ.path}:{occ.line}: bare '# pyright: ignore' is forbidden — must include rule code"
        )
    return None


def _build_registry_index(
    entries: tuple[DebtEntry, ...],
) -> dict[tuple[str, int, str], DebtEntry]:
    """Build a lookup index from (path, line, kind) to DebtEntry.

    Returns:
        Dictionary mapping occurrence keys to registry entries.
    """
    index: dict[tuple[str, int, str], DebtEntry] = {}
    for entry in entries:
        key = (entry.path, entry.line, entry.kind)
        index[key] = entry
    return index


# ---------------------------------------------------------------------------
# Test functions
# ---------------------------------------------------------------------------


def test_suppression_debt_registry_is_valid() -> None:
    """Debt registry entries must be valid, not expired, and not in protected layers."""
    entries = _parse_debt_registry()
    violations = _validate_registry_entries(entries)
    joined = "\n".join(violations)
    message = f"suppression debt registry integrity violations:\n{joined}"
    assert not violations, message


def test_protected_layers_never_contain_suppression_escape_hatches() -> None:
    """Protected architecture layers must never contain suppression escape hatches."""
    violations: list[str] = []

    for path in _python_files():
        rel_path = _relative_path(path)
        if not _in_protected_layer(rel_path):
            continue
        if not _should_scan(rel_path):
            continue

        for occ in _find_occurrences_in_file(path):
            bare_violation = _check_bare_rule(occ)
            if bare_violation:
                violations.append(bare_violation)
            else:
                rule_part = f"[{occ.rule_or_error}]" if occ.rule_or_error else ""
                violations.append(
                    f"{occ.path}:{occ.line}: {occ.kind}{rule_part} — forbidden in protected layer"
                )

    joined = "\n".join(violations)
    message = f"suppression escape hatches in protected layers:\n{joined}"
    assert not violations, message


def test_exception_zone_suppressions_must_be_in_debt_registry() -> None:
    """Exception zone suppressions must be registered in the approved debt registry."""
    entries = _parse_debt_registry()
    registry_index = _build_registry_index(entries)

    violations: list[str] = []

    for path in _python_files():
        rel_path = _relative_path(path)
        if not _in_exception_zone(rel_path):
            continue
        if not _should_scan(rel_path):
            continue

        for occ in _find_occurrences_in_file(path):
            # Bare rules are always forbidden, regardless of registry
            bare_violation = _check_bare_rule(occ)
            if bare_violation:
                violations.append(bare_violation)
                continue

            key = (occ.path, occ.line, occ.kind)
            if key not in registry_index:
                rule_part = f"[{occ.rule_or_error}]" if occ.rule_or_error else ""
                hint = (
                    " — not registered in .agents/approved-suppression-debt.toml\n"
                    "    add [[debt]] entry with path, line, kind,"
                    " rule_or_error_code, reason, alternative_attempted,"
                    " expires, owner"
                )
                violations.append(f"{occ.path}:{occ.line}: {occ.kind}{rule_part}{hint}")

    joined = "\n".join(violations)
    message = f"unregistered suppression escape hatches in exception zones:\n{joined}"
    assert not violations, message
