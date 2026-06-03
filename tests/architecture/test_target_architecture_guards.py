"""Permanent target architecture guards.

Enforces:
  1. Deleted packages must not exist on disk or be importable.
  2. No forbidden concepts in active source code.
  3. Layer dependency direction (contracts -> core -> cognitive -> runtime).
  4. Runtime entrypoint rules (main.py, cli.py, wiring/).
  5. Public __init__.py must not import heavy/deleted modules.
  6. No service locator / hidden registry in target modules.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ── Deleted packages ────────────────────────────────────────────

DELETED_PACKAGES: set[str] = {
    "iris/event",
    "iris/kernel",
    "iris/io",
    "iris/account",
    "iris/room",
    "iris/agency",
    "iris/memory",
    "iris/limbic",
    "iris/llm",
    "iris/tools",
    "iris/heartbeat",
    "iris/admin",
}

DELETED_IMPORTS: set[str] = {
    "iris.account",
    "iris.agency",
    "iris.event",
    "iris.heartbeat",
    "iris.io",
    "iris.kernel",
    "iris.limbic",
    "iris.llm",
    "iris.memory",
    "iris.room",
    "iris.tools",
    "iris.admin",
}

# ── Forbidden concepts in source code ───────────────────────────

FORBIDDEN_SYMBOLS: set[str] = {
    "Supervisor",
    "InternalBus",
}

# ── Target layer dependency rules ──────────────────────────────
# Keys: package directory under iris/
# Values: set of iris.* prefixes that files in this layer must NOT import.

LAYER_RULES: dict[str, set[str]] = {
    "iris/contracts": {
        "iris.cognitive",
        "iris.adapters",
        "iris.runtime",
        "iris.features",
        "iris.presentation",
        "iris.safety",
    },
    "iris/core": {
        "iris.cognitive",
        "iris.contracts",
        "iris.adapters",
        "iris.runtime",
        "iris.features",
        "iris.presentation",
        "iris.safety",
    },
    "iris/cognitive": {
        "iris.adapters",
        "iris.runtime",
        "iris.features",
        "iris.presentation",
        "iris.safety",
    },
    "iris/presentation": {
        "iris.adapters",
        "iris.runtime",
        "iris.features",
        "iris.cognitive",
        "iris.safety",
    },
    "iris/safety": {
        "iris.adapters",
        "iris.runtime",
        "iris.features",
        "iris.cognitive",
        "iris.presentation",
    },
    "iris/adapters": {
        "iris.cognitive",
        "iris.runtime",
        "iris.features",
        "iris.presentation",
        "iris.safety",
    },
    "iris/features": {
        "iris.adapters",
        "iris.runtime",
        "iris.presentation",
        "iris.safety",
    },
}

# ── Exceptions: (layer_dir, relative_path, import_prefix, reason)
LAYER_EXCEPTIONS: list[tuple[str, str, str, str]] = [
    # features/definition.py is architecturally allowed to import cognitive cycle
    (
        "iris/features",
        "iris/features/definition.py",
        "iris.cognitive.cycle",
        "FeatureDefinition needs PipelineStep protocol",
    ),
]

ENTRYPOINT_FILES: set[str] = {
    "main.py",
    "iris/runtime/cli.py",
    "iris/runtime/app.py",
}

WIRING_FILES: set[str] = {
    "iris/runtime/wiring/app.py",
    "iris/runtime/wiring/cognitive.py",
}

# ── Helpers ──────────────────────────────────────────────────────


def _skip_if_missing(rel_dir: str) -> None:
    if not (PROJECT_ROOT / rel_dir).is_dir():
        pytest.skip(f"Target layer '{rel_dir}' does not exist yet")


def _get_python_files(base: Path) -> list[Path]:
    return sorted(base.rglob("*.py"))


def _all_imports(tree: ast.Module) -> list[str]:
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def _runtime_imports(tree: ast.Module) -> list[str]:
    imports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
            continue
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


# ═══════════════════════════════════════════════════════════════════
# 1.  Deleted packages must not exist
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("pkg_dir", sorted(DELETED_PACKAGES))
def test_deleted_packages_do_not_exist(pkg_dir: str) -> None:
    pkg_path = PROJECT_ROOT / pkg_dir
    assert not pkg_path.exists(), f"Deleted package '{pkg_dir}' still exists"


@pytest.mark.parametrize("pkg_name", sorted(DELETED_IMPORTS))
def test_deleted_packages_not_importable(pkg_name: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(pkg_name)


# ═══════════════════════════════════════════════════════════════════
# 2.  No forbidden concepts in active source code
# ═══════════════════════════════════════════════════════════════════

SOURCE_DIRECTORIES: set[str] = {
    "iris/core",
    "iris/contracts",
    "iris/cognitive",
    "iris/presentation",
    "iris/safety",
    "iris/features",
    "iris/adapters",
    "iris/runtime",
}

SOURCE_FILES: set[str] = {
    "main.py",
    "iris/__init__.py",
    "iris/errors.py",
}


def _iter_source_files() -> list[Path]:
    files: list[Path] = []
    for rel_dir in SOURCE_DIRECTORIES:
        base = PROJECT_ROOT / rel_dir
        if base.is_dir():
            files.extend(base.rglob("*.py"))
    for rel_file in SOURCE_FILES:
        f = PROJECT_ROOT / rel_file
        if f.is_file():
            files.append(f)
    return files


@pytest.mark.parametrize("symbol", sorted(FORBIDDEN_SYMBOLS))
def test_no_forbidden_concepts_in_source_code(symbol: str) -> None:
    """Forbidden concepts must not appear in active source code."""
    violations: list[str] = []
    for filepath in _iter_source_files():
        try:
            text = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if symbol in text:
            rel = filepath.relative_to(PROJECT_ROOT).as_posix()
            violations.append(f"  {rel}")
    assert not violations, f"Symbol '{symbol}' found in source code:\n" + "\n".join(violations)


def test_no_deleted_imports_in_source_code() -> None:
    """Active source files must not import deleted packages."""
    violations: list[str] = []
    for filepath in _iter_source_files():
        try:
            tree = ast.parse(filepath.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for imp in _all_imports(tree):
            for prefix in DELETED_IMPORTS:
                if imp.startswith(prefix):
                    rel = filepath.relative_to(PROJECT_ROOT).as_posix()
                    violations.append(f"  {rel}: imports '{imp}'")
    assert not violations, "Deleted imports found in source code:\n" + "\n".join(violations)


# ═══════════════════════════════════════════════════════════════════
# 3.  Layer dependency direction
# ═══════════════════════════════════════════════════════════════════


def _check_layer_imports(
    layer_dir: str,
    forbidden: set[str],
    exceptions: list[tuple[str, str, str, str]],
) -> list[str]:
    violations: list[str] = []
    base = PROJECT_ROOT / layer_dir
    if not base.is_dir():
        return violations
    for filepath in _get_python_files(base):
        rel_path = filepath.relative_to(PROJECT_ROOT).as_posix()
        try:
            tree = ast.parse(filepath.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for imp in _all_imports(tree):
            if not imp.startswith("iris."):
                continue
            for forbidden_prefix in forbidden:
                if not imp.startswith(forbidden_prefix):
                    continue
                allowed = False
                for exc_layer, exc_file, exc_prefix, _ in exceptions:
                    if exc_layer == layer_dir and exc_file == rel_path and imp.startswith(exc_prefix):
                        allowed = True
                        break
                if not allowed:
                    violations.append(f"  {rel_path}: imports '{imp}' (forbidden for {layer_dir})")
    return violations


@pytest.mark.parametrize(("layer_dir", "forbidden"), sorted(LAYER_RULES.items()))
def test_layer_dependency_direction(layer_dir: str, forbidden: set[str]) -> None:
    """Each layer must not import from higher/sibling layers outside allowed direction."""
    _skip_if_missing(layer_dir)
    violations = _check_layer_imports(layer_dir, forbidden, LAYER_EXCEPTIONS)
    assert not violations, f"Layer '{layer_dir}' imports from forbidden layers:\n" + "\n".join(violations)


# ═══════════════════════════════════════════════════════════════════
# 4.  Runtime entrypoint rules
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("rel_path", sorted(ENTRYPOINT_FILES | WIRING_FILES))
def test_entrypoint_no_deleted_imports(rel_path: str) -> None:
    """Entrypoint and wiring files must not import deleted packages."""
    file_path = PROJECT_ROOT / rel_path
    if not file_path.is_file():
        pytest.skip(f"Guard file missing (expected for phased rollout): {rel_path}")
    text = file_path.read_text(encoding="utf-8")
    for prefix in DELETED_IMPORTS:
        if prefix.replace(".", "/") in text or prefix in text:
            # More precise AST check
            tree = ast.parse(text)
            for imp in _all_imports(tree):
                assert not imp.startswith(prefix), f"{rel_path} imports deleted '{imp}'"


def test_main_py_delegates_to_target_runtime() -> None:
    text = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")
    assert "iris.runtime" in text, "main.py must import from iris.runtime"


def test_cli_exports_run_one_turn_and_main() -> None:
    cli_path = PROJECT_ROOT / "iris" / "runtime" / "cli.py"
    assert cli_path.is_file()
    text = cli_path.read_text(encoding="utf-8")
    assert "def run_one_turn" in text
    assert "def main()" in text


def test_wiring_uses_constructor_injection() -> None:
    """Wiring functions must not call resolve(), get_service(), or locate()."""
    violations: list[str] = []
    for rel in WIRING_FILES:
        fp = PROJECT_ROOT / rel
        if not fp.is_file():
            continue
        try:
            tree = ast.parse(fp.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name_parts: list[str] = []
                cur = func
                while isinstance(cur, ast.Attribute):
                    name_parts.insert(0, cur.attr)
                    cur = cur.value
                if isinstance(cur, ast.Name):
                    name_parts.insert(0, cur.id)
                if any(fn in name_parts for fn in {"resolve", "get_service", "locate"}):
                    violations.append(f"  {rel}:{node.lineno} calls '{'.'.join(name_parts)}'")
    assert not violations, "Wiring must use constructor injection, not service locator:\n" + "\n".join(violations)


# ═══════════════════════════════════════════════════════════════════
# 5.  Public __init__.py side-effect rules
# ═══════════════════════════════════════════════════════════════════


def _get_top_level_init_files() -> list[Path]:
    inits: list[Path] = []
    for rel_dir in SOURCE_DIRECTORIES | {"iris"}:
        init_path = PROJECT_ROOT / rel_dir / "__init__.py"
        if init_path.is_file():
            inits.append(init_path)
    return inits


HEAVY_INIT_FORBIDDEN: set[str] = {
    "iris.adapters",
    "iris.runtime",
    "iris.features",
} | DELETED_IMPORTS


def test_init_files_no_heavy_imports() -> None:
    """Target package __init__.py must not import heavy/deleted modules."""
    violations: list[str] = []
    for init_path in _get_top_level_init_files():
        try:
            tree = ast.parse(init_path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for imp in _all_imports(tree):
            for forbidden in HEAVY_INIT_FORBIDDEN:
                if imp.startswith(forbidden):
                    rel = init_path.relative_to(PROJECT_ROOT).as_posix()
                    violations.append(f"  {rel}: imports '{imp}'")
    assert not violations, "__init__.py files must not import heavy or deleted modules:\n" + "\n".join(violations)


# ═══════════════════════════════════════════════════════════════════
# 6.  No service locator / hidden registry in target modules
# ═══════════════════════════════════════════════════════════════════


SERVICE_LOCATOR_PATTERNS: list[str] = [
    "ServiceLocator",
    "GlobalRegistry",
    "resolve(",
    "get_service(",
    "locate(",
    ".register(",
    ".subscribe(",
]


@pytest.mark.parametrize("target_dir", sorted(SOURCE_DIRECTORIES))
def test_no_service_locator_patterns(target_dir: str) -> None:
    """Target modules must not reintroduce service locator or hidden registry patterns."""
    _skip_if_missing(target_dir)
    violations: list[str] = []
    base = PROJECT_ROOT / target_dir
    for filepath in _get_python_files(base):
        try:
            text = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = filepath.relative_to(PROJECT_ROOT).as_posix()
        for pattern in SERVICE_LOCATOR_PATTERNS:
            if pattern in text:
                violations.append(f"  {rel}: contains '{pattern}'")
    assert not violations, f"Service locator patterns found in {target_dir}:\n" + "\n".join(violations)


def test_no_global_mutable_registries() -> None:
    """Target modules must not have module-level mutable registries."""
    violations: list[str] = []
    for filepath in _iter_source_files():
        try:
            tree = ast.parse(filepath.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        rel = filepath.relative_to(PROJECT_ROOT).as_posix()
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (
                        isinstance(target, ast.Name)
                        and target.id.isupper()
                        and isinstance(node.value, (ast.Dict, ast.List, ast.Set))
                    ):
                        violations.append(f"  {rel}: global mutable '{target.id}'")
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                func = node.value.func
                name = ""
                if isinstance(func, ast.Attribute):
                    name = ast.unparse(func)
                elif isinstance(func, ast.Name):
                    name = func.id
                if name in ("register", "subscribe", "add_hook"):
                    violations.append(f"  {rel}: module-level call '{name}()'")
    assert not violations, "Global mutable registries found:\n" + "\n".join(violations)


# ═══════════════════════════════════════════════════════════════════
# 7.  Ports must live in consuming modules, not contracts/
# ═══════════════════════════════════════════════════════════════════


def test_contracts_has_no_ports_file() -> None:
    """contracts/ports.py must not exist. Ports belong in consuming modules."""
    ports_path = PROJECT_ROOT / "iris" / "contracts" / "ports.py"
    assert not ports_path.is_file(), (
        "contracts/ports.py exists — ports should be defined in consuming modules "
        "(e.g. cognitive/action/ports.py, cognitive/memory/ports.py, "
        "presentation/ports.py, safety/ports.py, adapters/app_gateway/ports.py)"
    )


# ═══════════════════════════════════════════════════════════════════
# 8.  WIRING_FILES completeness
# ═══════════════════════════════════════════════════════════════════


WIRING_FILES_EXPECTED: set[str] = {
    "iris/runtime/wiring/app.py",
    "iris/runtime/wiring/cognitive.py",
    "iris/runtime/wiring/features.py",
    "iris/runtime/wiring/presentation.py",
}


def test_required_wiring_files_exist() -> None:
    """Required wiring files must exist on disk."""
    missing: list[str] = []
    for rel in WIRING_FILES_EXPECTED:
        if not (PROJECT_ROOT / rel).is_file():
            missing.append(rel)
    assert not missing, "Required wiring files missing:\n" + "\n".join(missing)
