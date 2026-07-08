"""Architecture guard: scanner exclusions must stay narrow and exact."""

from __future__ import annotations

from tests.architecture import test_suppression_debt_registry as registry

EXPECTED_EXCLUDED_ROOTS: frozenset[str] = frozenset({"iris/generated"})
EXPECTED_SCANNER_FIXTURE_FILES: frozenset[str] = frozenset(
    {
        "tests/architecture/test_quality_escape_hatch_guards.py",
        "tests/architecture/test_suppression_debt_registry.py",
        "tests/architecture/test_suppression_debt_registry_is_frozen.py",
        "tests/architecture/test_workspace_frame_mutation_extended.py",
        "tests/architecture/test_workspace_frame_immutability.py",
    }
)
FORBIDDEN_BROAD_EXCLUSIONS: frozenset[str] = frozenset(
    {"tests", "iris", "iris/adapters", "scripts"}
)


def test_suppression_scanner_excluded_roots_are_minimal() -> None:
    """Suppression scanner directory exclusions must stay minimal."""
    assert registry.EXCLUDED_ROOTS == EXPECTED_EXCLUDED_ROOTS
    assert not (registry.EXCLUDED_ROOTS & FORBIDDEN_BROAD_EXCLUSIONS)


def test_suppression_scanner_fixture_files_are_exact() -> None:
    """Suppression scanner fixture files must remain exact test files."""
    assert registry.SCANNER_FIXTURE_FILES == EXPECTED_SCANNER_FIXTURE_FILES
    assert all(path.startswith("tests/architecture/") for path in registry.SCANNER_FIXTURE_FILES)
    assert not any(
        path.startswith(("iris/", "scripts/")) for path in registry.SCANNER_FIXTURE_FILES
    )
