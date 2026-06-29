"""Architecture guards for runtime composition boundaries."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RUNTIME_ROOT = PROJECT_ROOT / "iris" / "runtime"
WIRING_ROOT = RUNTIME_ROOT / "wiring"

CONCRETE_ADAPTER_IMPORTS: frozenset[str] = frozenset(
    {
        "iris.adapters.llm.fake",
        "iris.adapters.llm.openai",
        "iris.adapters.memory.fake",
        "iris.adapters.memory.langchain",
        "iris.adapters.memory.vector",
    }
)

ENTRYPOINT_RUNTIME_FILES: frozenset[Path] = frozenset(
    {
        Path("iris/runtime/app.py"),
        Path("iris/runtime/cli.py"),
        Path("iris/runtime/server.py"),
    }
)


def _python_files(root: Path) -> tuple[Path, ...]:
    """Return Python files under a root if it exists."""
    if not root.is_dir():
        return ()
    return tuple(sorted(root.rglob("*.py")))


def _imports(path: Path) -> tuple[str, ...]:
    """Return imports found in a Python file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.append(node.module)
    return tuple(imports)


def _is_wiring_file(path: Path) -> bool:
    """Return whether a file lives under runtime/wiring."""
    return path.is_relative_to(WIRING_ROOT)


def test_concrete_adapter_imports_are_confined_to_runtime_wiring() -> None:
    """Runtime entrypoints must not import provider implementations directly."""
    violations: list[str] = []

    for path in _python_files(RUNTIME_ROOT):
        if _is_wiring_file(path):
            continue
        rel_path = path.relative_to(PROJECT_ROOT)
        violations.extend(
            f"{rel_path}: imports concrete adapter {imported}"
            for imported in _imports(path)
            if imported in CONCRETE_ADAPTER_IMPORTS
        )

    assert not violations, "concrete adapter imports outside runtime/wiring:\n" + "\n".join(
        violations,
    )


def test_runtime_entrypoints_do_not_import_features_directly() -> None:
    """Feature composition belongs in runtime/wiring, not thin runtime entrypoints."""
    violations: list[str] = []

    for rel_path in sorted(ENTRYPOINT_RUNTIME_FILES):
        path = PROJECT_ROOT / rel_path
        if not path.is_file():
            continue
        violations.extend(
            f"{rel_path}: imports {imported}"
            for imported in _imports(path)
            if imported.startswith("iris.features")
        )

    assert not violations, "runtime entrypoints import features directly:\n" + "\n".join(
        violations,
    )


def test_runtime_wiring_does_not_import_feature_internals() -> None:
    """Runtime wiring must compose features using FeatureDefinition, not feature internals."""
    violations: list[str] = []

    # Features expose definition via their package __init__ or definition.py
    # Importing internals like planner, policy, templates, scoring is a violation.
    forbidden_internals = {"planner", "policy", "templates", "scoring"}

    for path in _python_files(WIRING_ROOT):
        rel_path = path.relative_to(PROJECT_ROOT)
        for imported in _imports(path):
            if not imported.startswith("iris.features."):
                continue

            parts = imported.split(".")
            # iris.features.<feature_name>.<internal>
            if len(parts) > 3 and parts[-1] in forbidden_internals:
                violations.append(f"{rel_path}: imports feature internal {imported}")

    assert not violations, "runtime wiring imports feature internals directly:\n" + "\n".join(
        violations,
    )
