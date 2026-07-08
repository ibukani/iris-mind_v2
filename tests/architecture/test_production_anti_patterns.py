"""Production source anti-patterns をまとめて禁止する architecture guard。"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING, TypeGuard

from tests.architecture.helpers.ast_utils import name_of, parse_python_file
from tests.architecture.helpers.project_paths import IRIS_ROOT

if TYPE_CHECKING:
    from collections.abc import Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROTECTED_SOURCE_ROOTS: tuple[Path, ...] = (
    Path("iris/contracts"),
    Path("iris/core"),
    Path("iris/cognitive"),
    Path("iris/features"),
    Path("iris/presentation"),
    Path("iris/safety"),
    Path("iris/runtime"),
)
FULL_SOURCE_ROOTS: tuple[Path, ...] = (*PROTECTED_SOURCE_ROOTS, Path("iris/adapters"))
SCAN_ROOTS: tuple[str, ...] = ("iris", "tests", "scripts")
EXCLUDED_ROOTS: frozenset[str] = frozenset({"iris/generated"})
EXCLUDED_FAKE_SUFFIXES: tuple[str, ...] = (
    "/fake.py",
    "/fake_gateway.py",
    "/fake_resolvers.py",
)


def _relative_path(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _is_generated(path: Path) -> bool:
    rel_path = _relative_path(path)
    return any(
        rel_path == excluded or rel_path.startswith(f"{excluded}/") for excluded in EXCLUDED_ROOTS
    )


def _is_fake_adapter_file(path: Path) -> bool:
    rel_path = _relative_path(path)
    return rel_path.startswith("iris/adapters/") and rel_path.endswith(EXCLUDED_FAKE_SUFFIXES)


def _python_files(root_names: Iterable[str]) -> tuple[Path, ...]:
    paths: list[Path] = []
    for root_name in root_names:
        paths.extend(
            path for path in (PROJECT_ROOT / root_name).rglob("*.py") if not _is_generated(path)
        )
    return tuple(sorted(paths))


def _source_files(roots: Iterable[Path]) -> tuple[Path, ...]:
    paths: list[Path] = []
    for root in roots:
        base = PROJECT_ROOT / root
        if base.is_dir():
            paths.extend(path for path in base.rglob("*.py") if not _is_generated(path))
    return tuple(sorted(paths))


def _production_files_without_fakes() -> tuple[Path, ...]:
    return tuple(
        sorted(
            path
            for path in (PROJECT_ROOT / "iris").rglob("*.py")
            if not _is_generated(path) and not _is_fake_adapter_file(path)
        )
    )


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        if base is None:
            return node.attr
        return f"{base}.{node.attr}"
    return None


def _call_name_parts(node: ast.Call) -> tuple[str, ...]:
    parts: list[str] = []
    current = node.func
    while isinstance(current, ast.Attribute):
        parts.insert(0, current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.insert(0, current.id)
    return tuple(parts)


def _module_imports(tree: ast.Module) -> tuple[str, ...]:
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.append(node.module)
    return tuple(imports)


def _collect_broad_exception_fallbacks() -> list[str]:
    findings: list[str] = []
    for path in _python_files(SCAN_ROOTS):
        rel_path = _relative_path(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if not _is_broad_exception_type(node.type):
                continue
            reason = _broad_exception_fallback_reason(node)
            if reason is not None:
                findings.append(f"{rel_path}:{node.lineno}: broad exception fallback ({reason})")
    return findings


def _is_broad_exception_type(node: ast.AST | None) -> bool:
    if node is None:
        return False
    if isinstance(node, ast.Name):
        return node.id in {"Exception", "BaseException"}
    if isinstance(node, ast.Tuple):
        return any(_is_broad_exception_type(item) for item in node.elts)
    return False


def _is_empty_collection(node: ast.AST) -> bool:
    return isinstance(node, (ast.List, ast.Dict, ast.Set, ast.Tuple)) and not (
        node.elts if isinstance(node, (ast.List, ast.Set, ast.Tuple)) else node.keys
    )


def _is_default_return(node: ast.Return) -> bool:
    value = node.value
    if value is None:
        return True
    if isinstance(value, ast.Constant):
        return value.value in {None, False, True, ""}
    return _is_empty_collection(value)


def _fallback_statement_reason(statement: ast.stmt) -> str | None:
    if isinstance(statement, ast.Pass):
        return "pass"
    if isinstance(statement, ast.Continue):
        return "continue"
    if isinstance(statement, ast.Return) and _is_default_return(statement):
        return "default return"
    return None


def _is_logging_call(node: ast.stmt) -> bool:
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        return False
    func = node.value.func
    return isinstance(func, ast.Attribute) and func.attr in {
        "debug",
        "info",
        "warning",
        "error",
        "exception",
        "critical",
        "log",
    }


def _broad_exception_fallback_reason(handler: ast.ExceptHandler) -> str | None:
    for statement in handler.body:
        reason = _fallback_statement_reason(statement)
        if reason is not None:
            return reason

    non_logging = [statement for statement in handler.body if not _is_logging_call(statement)]
    if (
        len(non_logging) == 1
        and isinstance(non_logging[0], ast.Return)
        and _is_default_return(non_logging[0])
    ):
        return "logging followed by default return"
    return None


def _collect_mutable_state() -> list[str]:
    suspicious_names = {
        "registry",
        "registries",
        "container",
        "containers",
        "cache",
        "caches",
        "handlers",
        "listeners",
    }
    findings: list[str] = []
    for path in _source_files(PROTECTED_SOURCE_ROOTS):
        rel_path = path.relative_to(PROJECT_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                findings.extend(
                    f"{rel_path}:{node.lineno}: {target.id}"
                    for target in node.targets
                    if (
                        isinstance(target, ast.Name)
                        and _value_is_mutable(node.value)
                        and _name_is_suspicious(target.id, suspicious_names)
                    )
                )
            elif (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and _value_is_mutable(node.value)
                and _name_is_suspicious(node.target.id, suspicious_names)
            ):
                findings.append(f"{rel_path}:{node.lineno}: {node.target.id}")
    return findings


def _value_is_mutable(value: ast.AST | None) -> bool:
    mutable_constructors = {"dict", "list", "set", "defaultdict"}
    if isinstance(value, (ast.Dict, ast.List, ast.Set)):
        return True
    if isinstance(value, ast.Call):
        func = value.func
        if isinstance(func, ast.Name) and func.id in mutable_constructors:
            return True
        if isinstance(func, ast.Attribute) and func.attr in mutable_constructors:
            return True
    return False


def _name_is_suspicious(name: str, suspicious_names: set[str]) -> bool:
    lowered = name.lower().lstrip("_")
    return lowered in suspicious_names or any(
        lowered.endswith(f"_{suffix}") for suffix in suspicious_names
    )


def _collect_global_mutable_registries() -> list[str]:
    target_name_parts = (
        "registry",
        "registries",
        "service",
        "services",
        "plugin",
        "plugins",
        "locator",
    )
    findings: list[str] = []
    for path in sorted(IRIS_ROOT.rglob("*.py")):
        tree = parse_python_file(path)
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
                continue
            if not _value_is_mutable(node.value):
                continue
            names = _assigned_names(node)
            if any(part in name.lower() for name in names for part in target_name_parts):
                findings.append(f"{path}:{node.lineno}: {', '.join(names)}")
    return findings


def _assigned_names(node: ast.Assign | ast.AnnAssign) -> tuple[str, ...]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return tuple(target.id for target in targets if isinstance(target, ast.Name))


def _collect_service_locator_patterns() -> list[str]:
    forbidden_import_prefixes = {
        "dependency_injector",
        "injector",
        "punq",
        "lagom",
    }
    forbidden_call_parts = {
        "resolve",
        "resolve_optional",
        "resolve_all",
        "get_service",
        "locate",
        "inject",
    }
    forbidden_text_patterns = {
        "ServiceLocator",
        "ServiceProvider",
        "GlobalRegistry",
        "providers.Container",
        "dependency_injector",
        "resolve_optional(",
        "resolve_all(",
        ".resolve_optional(",
        ".resolve_all(",
        ".get_service(",
        ".locate(",
        ".inject(",
    }
    findings: list[str] = []
    for path in _source_files(FULL_SOURCE_ROOTS):
        rel_path = path.relative_to(PROJECT_ROOT)
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        findings.extend(
            f"{rel_path}: imports {imported}"
            for imported in _module_imports(tree)
            if any(imported.startswith(prefix) for prefix in forbidden_import_prefixes)
        )
        findings.extend(
            f"{rel_path}: contains {pattern!r}"
            for pattern in forbidden_text_patterns
            if pattern in text
        )
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            parts = _call_name_parts(node)
            if any(part in forbidden_call_parts for part in parts) and parts != (
                "TypeVar",
                "resolve",
            ):
                findings.append(f"{rel_path}:{node.lineno}: calls {'.'.join(parts)}")
    return findings


def _collect_stringly_dispatch() -> list[str]:
    target_roots = (IRIS_ROOT / "cognitive", IRIS_ROOT / "runtime", IRIS_ROOT / "features")
    excluded_roots = (IRIS_ROOT / "runtime/config",)
    findings: list[str] = []
    files = sorted(path for root in target_roots for path in root.rglob("*.py"))
    for path in files:
        if any(path.is_relative_to(root) for root in excluded_roots):
            continue
        for node in ast.walk(parse_python_file(path)):
            if (
                isinstance(node, ast.Compare)
                and _is_dispatch_attr(node.left)
                and _has_string_comparator(node)
            ):
                findings.append(f"{path}:{node.lineno}: string dispatch compare")
            elif isinstance(node, ast.Match) and _is_dispatch_attr(node.subject):
                findings.extend(
                    f"{path}:{case.pattern.lineno}: string dispatch match"
                    for case in node.cases
                    if _match_case_is_string_value(case)
                )
    return findings


def _is_dispatch_attr(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr in {"action", "type", "kind"}


def _has_string_comparator(node: ast.Compare) -> bool:
    return any(
        isinstance(item, ast.Constant) and isinstance(item.value, str) for item in node.comparators
    )


def _match_case_is_string_value(case: ast.match_case) -> bool:
    return (
        isinstance(case.pattern, ast.MatchValue)
        and isinstance(case.pattern.value, ast.Constant)
        and isinstance(case.pattern.value.value, str)
    )


def _collect_incomplete_markers() -> list[str]:
    findings: list[str] = []
    for path in sorted(IRIS_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        allowed_ellipsis_ids = _allowed_ellipsis_expr_ids(tree)
        rel_path = path.relative_to(PROJECT_ROOT)
        for node in ast.walk(tree):
            if isinstance(node, ast.Pass):
                findings.append(f"{rel_path}:{node.lineno}: pass hides incomplete implementation")
            if _is_forbidden_ellipsis(node, allowed_ellipsis_ids):
                findings.append(f"{rel_path}:{node.lineno}: ellipsis outside explicit stub")
            if isinstance(node, ast.Raise) and _is_bare_not_implemented(node):
                findings.append(f"{rel_path}:{node.lineno}: NotImplementedError without message")
    return findings


def _allowed_ellipsis_expr_ids(tree: ast.AST) -> set[int]:
    allowed: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and _is_protocol_class(node):
            for item in node.body:
                if _is_function(item):
                    allowed.update(_ellipsis_expr_ids(item.body))
        if _is_function(node) and _is_abstract_function(node):
            allowed.update(_ellipsis_expr_ids(node.body))
    return allowed


def _is_function(node: ast.AST) -> TypeGuard[ast.FunctionDef | ast.AsyncFunctionDef]:
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))


def _ellipsis_expr_ids(statements: list[ast.stmt]) -> set[int]:
    return {
        id(statement)
        for statement in statements
        if isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and statement.value.value is Ellipsis
    }


def _is_forbidden_ellipsis(node: ast.AST, allowed_ellipsis_ids: set[int]) -> TypeGuard[ast.Expr]:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and node.value.value is Ellipsis
        and id(node) not in allowed_ellipsis_ids
    )


def _is_protocol_class(node: ast.ClassDef) -> bool:
    return any(_base_name(base) == "Protocol" for base in node.bases)


def _base_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _base_name(node.value)
    return None


def _is_abstract_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(_decorator_name(decorator) == "abstractmethod" for decorator in node.decorator_list)


def _decorator_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return None


def _is_bare_not_implemented(node: ast.Raise) -> bool:
    exc = node.exc
    if isinstance(exc, ast.Name):
        return exc.id == "NotImplementedError"
    if isinstance(exc, ast.Call):
        return _call_name(exc.func) == "NotImplementedError" and not exc.args
    return False


def _collect_test_double_shortcuts() -> list[str]:
    findings: list[str] = []
    for path in _production_files_without_fakes():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel_path = _relative_path(path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                token in node.name for token in ("Fake", "Dummy", "Mock", "Stub", "Placeholder")
            ):
                findings.append(f"{rel_path}:{node.lineno}: test-double name {node.name}")
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                reason = _test_import_reason(node, include_unittest_mock=True)
                if reason is not None:
                    findings.append(f"{rel_path}:{node.lineno}: {reason}")
    return findings


def _test_import_reason(
    node: ast.Import | ast.ImportFrom, *, include_unittest_mock: bool
) -> str | None:
    forbidden_modules = {"pytest", "tests"}
    if include_unittest_mock:
        forbidden_modules.add("unittest.mock")
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name in forbidden_modules or alias.name.startswith("tests."):
                return f"imports {alias.name}"
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        if module in forbidden_modules or module.startswith("tests."):
            return f"imports {module}"
    return None


def _collect_test_environment_branches() -> list[str]:
    findings: list[str] = []
    for path in _production_files_without_fakes():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel_path = _relative_path(path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                reason = _test_import_reason(node, include_unittest_mock=False)
                if reason is not None:
                    findings.append(f"{rel_path}:{node.lineno}: {reason}")
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value == "PYTEST_CURRENT_TEST"
            ):
                findings.append(f"{rel_path}:{node.lineno}: references PYTEST_CURRENT_TEST")
            if isinstance(node, ast.Call) and _is_pytest_env_lookup(node):
                findings.append(f"{rel_path}:{node.lineno}: reads PYTEST_CURRENT_TEST")
    return findings


def _is_pytest_env_lookup(node: ast.Call) -> bool:
    name = _call_name(node.func)
    if name not in {"os.getenv", "os.environ.get"}:
        return False
    return bool(
        node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "PYTEST_CURRENT_TEST"
    )


def _collect_async_lifecycle_violations() -> list[str]:
    allowed_event_loop_controls = {("iris/runtime/cli.py", "asyncio.run")}
    findings: list[str] = []
    for path in _python_files(SCAN_ROOTS):
        rel_path = _relative_path(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                call_name = _untracked_task_call(node.value)
                if call_name is not None:
                    findings.append(f"{rel_path}:{node.lineno}: {call_name}")
            if rel_path.startswith("iris/") and isinstance(node, ast.Call):
                call_name = _event_loop_control(node)
                is_allowed_control = (rel_path, call_name) in allowed_event_loop_controls
                if call_name is not None and not is_allowed_control:
                    findings.append(f"{rel_path}:{node.lineno}: {call_name}")
    return findings


def _untracked_task_call(node: ast.Call) -> str | None:
    name = _call_name(node.func)
    if name in {"asyncio.create_task", "asyncio.ensure_future"}:
        return name
    if isinstance(node.func, ast.Attribute) and node.func.attr == "create_task":
        return "loop.create_task"
    return None


def _event_loop_control(node: ast.Call) -> str | None:
    name = _call_name(node.func)
    if name == "asyncio.run":
        return name
    if isinstance(node.func, ast.Attribute) and node.func.attr == "run_until_complete":
        return "loop.run_until_complete"
    return None


def _collect_untyped_internal_boundaries() -> list[str]:
    findings: list[str] = []
    for path in _source_files(PROTECTED_SOURCE_ROOTS):
        for node in ast.walk(parse_python_file(path)):
            annotation = getattr(node, "annotation", None)
            if isinstance(annotation, ast.AST) and _is_forbidden_boundary_annotation(annotation):
                line_number = getattr(node, "lineno", 0)
                findings.append(f"{path}:{line_number}: {ast.unparse(annotation)}")
    return findings


def _is_forbidden_boundary_annotation(node: ast.AST) -> bool:
    if not isinstance(node, ast.Subscript):
        return False
    container = name_of(node.value)
    names = _slice_names(node.slice)
    if container in {"dict", "Dict", "Mapping", "MutableMapping"} and len(names) >= 2:
        return names[0] == "str" and names[1] in {"Any", "object"}
    return container == "Callable" and "Any" in names and "Ellipsis" in names


def _slice_names(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Tuple):
        return tuple(_slice_name(elt) for elt in node.elts)
    return (_slice_name(node),)


def _slice_name(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and node.value is Ellipsis:
        return "Ellipsis"
    return name_of(node) or ""


def test_production_source_anti_patterns_are_forbidden() -> None:
    """Production/source scanner guards stay compact but preserve coverage."""
    violation_groups = {
        "broad exception fallback": _collect_broad_exception_fallbacks(),
        "suspicious module mutable state": _collect_mutable_state(),
        "global mutable registry/service locator": _collect_global_mutable_registries(),
        "service locator pattern": _collect_service_locator_patterns(),
        "stringly typed internal dispatch": _collect_stringly_dispatch(),
        "silent incomplete implementation": _collect_incomplete_markers(),
        "production test-double shortcut": _collect_test_double_shortcuts(),
        "production test environment branch": _collect_test_environment_branches(),
        "untracked async lifecycle": _collect_async_lifecycle_violations(),
        "untyped internal boundary": _collect_untyped_internal_boundaries(),
    }
    failures = [
        f"{group}:\n" + "\n".join(violations)
        for group, violations in violation_groups.items()
        if violations
    ]
    assert not failures, "\n\n".join(failures)
