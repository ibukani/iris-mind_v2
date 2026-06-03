"""Anti-pattern scans and feature boundary rules for v0.1 target architecture.

Rules enforced:
  1. No global mutable registries in new target modules.
  2. No service locator access patterns in new target modules.
  3. No untyped dict[str, Any] public contracts in contracts/.
  4. No action: str dispatcher patterns in new target modules.
  5. No app-specific imports inside cognitive/presentation/safety/contracts/core.
  6. Features must use FeatureDefinition, not core orchestration.
  7. Features must not mutate WorkspaceFrame directly.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Target directories to scan for anti-patterns.
TARGET_DIRS: list[str] = [
    "iris/contracts",
    "iris/core",
    "iris/cognitive",
    "iris/presentation",
    "iris/safety",
    "iris/features",
    "iris/adapters",
    "iris/runtime",
]

# App-specific keywords that should not appear in core layers.
APP_SPECIFIC_KEYWORDS: set[str] = {
    "discord",
    "discord.py",
    "nextcord",
    "py-cord",
    "speechd",
    "azure.cognitiveservices.speech",
    "elevenlabs",
    "openai.whisper",
    "vosk",
    "aiohttp",
    "flask",
    "fastapi",
    "starlette",
    "tortoise",
    "orator",
    "sqlalchemy.ext",
}


def _target_exists(rel_dir: str) -> bool:
    return (PROJECT_ROOT / rel_dir).is_dir()


def _get_python_files(base: Path) -> list[Path]:
    return sorted(base.rglob("*.py"))


def _get_imports(filepath: Path) -> list[str]:
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def _module_level_mutable_objects(tree: ast.Module) -> list[str]:
    """Find module-level mutable objects (registers, global dicts, etc.)."""
    findings: list[str] = []
    for node in ast.iter_child_nodes(tree):
        # Module-level assignments of mutable types
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id.isupper()
                    and isinstance(node.value, (ast.Dict, ast.List, ast.Set))
                ):
                    findings.append(f"global mutable '{target.id}'")
        # Module-level function calls like register(), subscribe()
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Attribute) and func.attr in ("register", "subscribe", "add_hook"):
                findings.append(f"module-level call: {ast.unparse(func)}")
            elif isinstance(func, ast.Name) and func.id in ("register", "subscribe", "add_hook"):
                findings.append(f"module-level call: {func.id}()")
    return findings


def _has_action_str_dispatch(tree: ast.Module) -> list[str]:
    """Find action: str dispatcher patterns (if/elif chains comparing strings)."""
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            _check_if_for_string_dispatch(node, findings)
        # match/case on strings
        if isinstance(node, ast.Match):
            subject = node.subject
            # Check if matching on a simple name like "action" or "action_type"
            if isinstance(subject, ast.Name) and subject.id in ("action", "action_type", "event_type", "command"):
                for case in node.cases:
                    if isinstance(case.pattern, ast.MatchValue) and isinstance(case.pattern.value, ast.Constant):
                        findings.append(f"match/case dispatch on string '{case.pattern.value.value}'")
    return findings


def _check_if_for_string_dispatch(node: ast.If, findings: list[str]) -> None:
    """Recursively check if-elif chains for string comparison dispatch."""

    def _get_compare_str(comparison: ast.Compare | None) -> str | None:
        if comparison is None:
            return None
        if isinstance(comparison.left, ast.Name) and comparison.left.id in ("action", "action_type", "command"):
            for op, right in zip(comparison.ops, comparison.comparators, strict=False):
                if (
                    isinstance(op, (ast.Eq, ast.Is))
                    and isinstance(right, ast.Constant)
                    and isinstance(right.value, str)
                ):
                    return str(right.value)
        return None

    if isinstance(node.test, ast.Compare):
        val = _get_compare_str(node.test)
        if val:
            findings.append(f"if/elif dispatch on '{val}'")

    for child in ast.walk(node):
        if isinstance(child, ast.If) and isinstance(child.test, ast.Compare):
            val = _get_compare_str(child.test)
            if val:
                findings.append(f"if/elif dispatch on '{val}'")


# ── 1. Global mutable registries ───────────────────────────────


@pytest.mark.parametrize("target_dir", sorted(TARGET_DIRS))
def test_no_global_mutable_registries(target_dir: str) -> None:
    """New target modules must not contain global mutable registries."""
    if not _target_exists(target_dir):
        pytest.skip(f"Target layer '{target_dir}' does not exist yet")
    base = PROJECT_ROOT / target_dir
    violations: list[str] = []
    for filepath in _get_python_files(base):
        try:
            tree = ast.parse(filepath.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        findings = _module_level_mutable_objects(tree)
        if findings:
            rel = filepath.relative_to(PROJECT_ROOT).as_posix()
            violations.append(f"  {rel}: {', '.join(findings)}")
    assert not violations, f"Global mutable registries found in {target_dir}:\n" + "\n".join(violations)


# ── 2. Service locator patterns ────────────────────────────────


@pytest.mark.parametrize("target_dir", sorted(TARGET_DIRS))
def test_no_service_locator_patterns(target_dir: str) -> None:
    """New target modules must not use service locator access patterns."""
    if not _target_exists(target_dir):
        pytest.skip(f"Target layer '{target_dir}' does not exist yet")

    forbidden_imports = {
        "iris.kernel.manager",
    }
    forbidden_names = {"resolve", "get_service", "locate", "container"}

    base = PROJECT_ROOT / target_dir
    violations: list[str] = []
    for filepath in _get_python_files(base):
        rel = filepath.relative_to(PROJECT_ROOT).as_posix()
        try:
            text = filepath.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (SyntaxError, FileNotFoundError):
            continue

        # Check imports
        for imp in _get_imports(filepath):
            for f in forbidden_imports:
                if imp.startswith(f):
                    violations.append(f"  {rel}: imports '{imp}' (service locator)")

        # Check function calls
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
                full_name = ".".join(name_parts)
                for fn in forbidden_names:
                    if fn in name_parts and full_name not in {"TypeVar.resolve"}:
                        violations.append(f"  {rel}:{node.lineno} calls '{full_name}' (service locator)")

    assert not violations, f"Service locator patterns found in {target_dir}:\n" + "\n".join(violations)


# ── 3. Untyped dict contracts ────────────────────────────────


def test_contracts_no_untyped_dict_public_api() -> None:
    """Public contracts must not use dict[str, Any] or dict[str, object] as field types.

    Scans iris/contracts/ for dataclass fields annotated with untyped dict.
    """
    contracts_dir = PROJECT_ROOT / "iris" / "contracts"
    if not contracts_dir.is_dir():
        pytest.skip("iris/contracts/ does not exist yet")

    forbidden = {"dict[str, Any]", "dict[str, object]", "Dict[str, Any]", "Dict[str, object]"}
    violations: list[str] = []

    for filepath in _get_python_files(contracts_dir):
        try:
            tree = ast.parse(filepath.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign) and node.annotation:
                ann_str = ast.unparse(node.annotation).lower().replace(" ", "")
                for f in forbidden:
                    if f.lower().replace(" ", "") in ann_str:
                        rel = filepath.relative_to(PROJECT_ROOT).as_posix()
                        line = filepath.read_text(encoding="utf-8").splitlines()[node.lineno - 1]
                        violations.append(f"  {rel}:{node.lineno} {line.strip()}")

    assert not violations, "Untyped dict[str, Any] in public contracts:\n" + "\n".join(violations)


# ── 4. action: str dispatcher ───────────────────────────────


@pytest.mark.parametrize("target_dir", sorted(TARGET_DIRS))
def test_no_action_str_dispatch(target_dir: str) -> None:
    """New target modules must not add action: str dispatcher branches."""
    if not _target_exists(target_dir):
        pytest.skip(f"Target layer '{target_dir}' does not exist yet")

    base = PROJECT_ROOT / target_dir
    violations: list[str] = []
    for filepath in _get_python_files(base):
        try:
            tree = ast.parse(filepath.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        findings = _has_action_str_dispatch(tree)
        if findings:
            rel = filepath.relative_to(PROJECT_ROOT).as_posix()
            for f in findings:
                violations.append(f"  {rel}: {f}")

    assert not violations, f"action: str dispatcher patterns in {target_dir}:\n" + "\n".join(violations)


# ── 5. App-specific imports in core layers ─────────────────────


@pytest.mark.parametrize(
    "layer_dir", ["iris/cognitive", "iris/presentation", "iris/safety", "iris/contracts", "iris/core"]
)
def test_no_app_specific_imports_in_core_layers(layer_dir: str) -> None:
    """Cognitive, presentation, safety, contracts, and core must not import app-specific packages."""
    if not _target_exists(layer_dir):
        pytest.skip(f"Layer '{layer_dir}' does not exist yet")

    base = PROJECT_ROOT / layer_dir
    violations: list[str] = []
    for filepath in _get_python_files(base):
        for imp in _get_imports(filepath):
            imp_lower = imp.lower()
            for keyword in APP_SPECIFIC_KEYWORDS:
                if keyword in imp_lower:
                    rel = filepath.relative_to(PROJECT_ROOT).as_posix()
                    violations.append(f"  {rel}: imports '{imp}' (app-specific: {keyword})")
                    break

    assert not violations, f"App-specific imports in {layer_dir}:\n" + "\n".join(violations)


# ── 6. Feature boundary rules ──────────────────────────────────


def test_features_use_definition_pattern() -> None:
    """Features must use FeatureDefinition for registration.

    Scans iris/features/ for calls to define_feature() or FeatureDefinition usage.
    Any __init__.py or feature.py that imports or registers directly into
    cognitive internals is a violation.
    """
    features_dir = PROJECT_ROOT / "iris" / "features"
    if not features_dir.is_dir():
        pytest.skip("iris/features/ does not exist yet")

    violations: list[str] = []

    for filepath in _get_python_files(features_dir):
        rel = filepath.relative_to(PROJECT_ROOT).as_posix()
        try:
            text = filepath.read_text(encoding="utf-8")
        except Exception:  # noqa: S112
            continue

        # Check that every feature.py uses FeatureDefinition
        if filepath.name == "feature.py" and "FeatureDefinition" not in text and "define_feature" not in text:
            violations.append(f"  {rel}: feature.py does not use FeatureDefinition or define_feature()")

        # Check for direct cognitive internal access
        for imp in _get_imports(filepath):
            if not imp.startswith(("iris.cognitive.cycle", "iris.cognitive.workspace")):
                continue
            # FeatureDefinition is architecturally allowed to import cognitive
            # extension protocols (PipelineStep, PipelineStepResult) from cognitive/cycle/.
            if filepath.name == "definition.py" and imp.startswith("iris.cognitive.cycle"):
                continue
            violations.append(f"  {rel}: imports '{imp}' — features must not import cognitive internals")

    assert not violations, "Feature boundary violations:\n" + "\n".join(violations)


def test_features_no_direct_frame_mutation() -> None:
    """Features must not mutate WorkspaceFrame directly.

    Any import of WorkspaceFrame in features/ should be read-only via
    FrameBuilder or CognitiveCycle, not direct mutation.
    """
    features_dir = PROJECT_ROOT / "iris" / "features"
    if not features_dir.is_dir():
        pytest.skip("iris/features/ does not exist yet")

    violations: list[str] = []
    for filepath in _get_python_files(features_dir):
        rel = filepath.relative_to(PROJECT_ROOT).as_posix()
        try:
            tree = ast.parse(filepath.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        # Check for frame attribute assignment
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "frame"
                    ):
                        violations.append(f"  {rel}: mutates WorkspaceFrame directly")

    assert not violations, "Direct WorkspaceFrame mutation from features:\n" + "\n".join(violations)
