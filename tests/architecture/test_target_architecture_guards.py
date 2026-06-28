"""恒久的なターゲットアーキテクチャガード。

適用事項:
  1. 削除されたパッケージがディスク上に存在したりインポート可能であってはならない。
  2. アクティブなソースコードに禁止概念があってはならない。
  3. 層の依存方向（contracts → core → cognitive → runtime）。
  4. ランタイムエントリポイントルール（main.py、cli.py、wiring/）。
  5. 公開__init__.pyは重い/削除されたモジュールをインポートしてはならない。
  6. ターゲットモジュールにサービスロケータ/隠れレジストリがないこと。
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
    "iris/runtime/activity",
    "iris/runtime/availability",
    "iris/runtime/context",
    "iris/runtime/event_reaction",
    "iris/runtime/observations",
    "iris/runtime/presence",
    "iris/runtime/proactive",
    "iris/runtime/spaces",
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
    "iris.runtime.activity",
    "iris.runtime.availability",
    "iris.runtime.context",
    "iris.runtime.event_reaction",
    "iris.runtime.observations",
    "iris.runtime.presence",
    "iris.runtime.proactive",
    "iris.runtime.spaces",
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
    (
        "iris/adapters",
        "iris/adapters/grpc/mappers/observations.py",
        "iris.runtime.service",
        "gRPC ingress maps transport DTOs to runtime service envelope/response",
    ),
    (
        "iris/adapters",
        "iris/adapters/grpc/mappers/observations.py",
        "iris.runtime.ingress.observation_ingress",
        "gRPC ingress mapper needs ObservationCapability for adapter capabilities typing",
    ),
    (
        "iris/adapters",
        "iris/adapters/grpc/mappers/observations.py",
        "iris.runtime.auth.principals",
        "gRPC mapper reads ClientPrincipal to select trusted/external ingress path",
    ),
    (
        "iris/adapters",
        "iris/adapters/grpc/server.py",
        "iris.runtime.service",
        "gRPC transport adapter delegates to IrisRuntimeService boundary",
    ),
    (
        "iris/adapters",
        "iris/adapters/grpc/server.py",
        "iris.runtime.auth.context",
        "gRPC servicer reads current_principal from contextvars for authz",
    ),
    (
        "iris/adapters",
        "iris/adapters/grpc/server.py",
        "iris.runtime.auth.errors",
        "gRPC servicer maps RuntimePermissionDeniedError to PERMISSION_DENIED status",
    ),
    (
        "iris/adapters",
        "iris/adapters/grpc/server.py",
        "iris.runtime.auth.policy",
        "gRPC servicer holds RuntimeAuthorizationPolicy for per-RPC scope checks",
    ),
    (
        "iris/adapters",
        "iris/adapters/grpc/auth_interceptor.py",
        "iris.runtime.auth.context",
        "gRPC auth interceptor binds/resets ClientPrincipal via contextvars",
    ),
    (
        "iris/adapters",
        "iris/adapters/grpc/auth_interceptor.py",
        "iris.runtime.auth.errors",
        "gRPC auth interceptor catches RuntimeUnauthenticatedError to abort with UNAUTHENTICATED",
    ),
    (
        "iris/adapters",
        "iris/adapters/grpc/auth_interceptor.py",
        "iris.runtime.auth.principals",
        "gRPC auth interceptor constructs local_dev_principal for unauthenticated loopback",
    ),
    (
        "iris/adapters",
        "iris/adapters/grpc/auth_interceptor.py",
        "iris.runtime.auth.static_tokens",
        "gRPC auth interceptor holds StaticBearerTokenVerifier to verify bearer tokens",
    ),
    (
        "iris/adapters",
        "iris/adapters/grpc/auth_interceptor.py",
        "iris.runtime.config.auth",
        "gRPC auth interceptor reads RuntimeAuthConfig to select auth mode",
    ),
    (
        "iris/adapters",
        "iris/adapters/persistence/sqlite/stores/activity_journal.py",
        "iris.runtime.state.activity_journal",
        "SQLite activity adapter implements the runtime-owned ActivityJournal port",
    ),
]

ENTRYPOINT_FILES: set[str] = {
    "main.py",
    "iris/runtime/cli.py",
    "iris/runtime/server.py",
    "iris/runtime/app.py",
}

WIRING_FILES: set[str] = {
    "iris/runtime/wiring/app.py",
    "iris/runtime/wiring/availability.py",
    "iris/runtime/wiring/cognitive.py",
    "iris/runtime/wiring/context.py",
    "iris/runtime/wiring/delivery.py",
    "iris/runtime/wiring/event_reaction.py",
    "iris/runtime/wiring/features.py",
    "iris/runtime/wiring/grpc.py",
    "iris/runtime/wiring/llm.py",
    "iris/runtime/wiring/memory.py",
    "iris/runtime/wiring/presentation.py",
    "iris/runtime/wiring/runtime.py",
    "iris/runtime/wiring/scheduler.py",
    "iris/runtime/wiring/state.py",
    "iris/runtime/wiring/state_policy.py",
}

# ── Helpers ──────────────────────────────────────────────────────


def _skip_if_missing(rel_dir: str) -> None:
    assert (PROJECT_ROOT / rel_dir).is_dir(), f"Target layer '{rel_dir}' must exist"


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


# ═══════════════════════════════════════════════════════════════════
# 1.  Deleted packages must not exist
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("pkg_dir", sorted(DELETED_PACKAGES))
def test_deleted_packages_do_not_exist(pkg_dir: str) -> None:
    """削除されたパッケージがディスク上に存在しないことを確認する。"""
    pkg_path = PROJECT_ROOT / pkg_dir
    assert not pkg_path.exists(), f"Deleted package '{pkg_dir}' still exists"


@pytest.mark.parametrize("pkg_name", sorted(DELETED_IMPORTS))
def test_deleted_packages_not_importable(pkg_name: str) -> None:
    """削除されたパッケージがインポート時にModuleNotFoundErrorを発生させることを確認する。"""
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
    """禁止概念がアクティブなソースコードに出現してはならない。"""
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
    """アクティブなソースファイルは削除されたパッケージをインポートしてはならない。"""
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


def _is_import_allowed_by_exceptions(
    rel_path: str,
    imp: str,
    layer_dir: str,
    exceptions: list[tuple[str, str, str, str]],
) -> bool:
    """Check if a forbidden import is explicitly allowed by a layer exception rule.

    Returns:
        True if the import is covered by an exception for this layer.
    """
    for exc_layer, exc_file, exc_prefix, _ in exceptions:
        if exc_layer == layer_dir and exc_file == rel_path and imp.startswith(exc_prefix):
            return True
    return False


def _check_file_layer_imports(
    tree: ast.Module,
    rel_path: str,
    layer_dir: str,
    forbidden: set[str],
    exceptions: list[tuple[str, str, str, str]],
) -> list[str]:
    """Check all imports in a single file against forbidden layer prefixes.

    Returns:
        Violation message list for this file.
    """
    violations: list[str] = []
    for imp in _all_imports(tree):
        if not imp.startswith("iris."):
            continue
        for forbidden_prefix in forbidden:
            if not imp.startswith(forbidden_prefix):
                continue
            if _is_import_allowed_by_exceptions(rel_path, imp, layer_dir, exceptions):
                continue
            violations.append(f"  {rel_path}: imports '{imp}' (forbidden for {layer_dir})")
    return violations


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
        violations.extend(
            _check_file_layer_imports(tree, rel_path, layer_dir, forbidden, exceptions)
        )
    return violations


@pytest.mark.parametrize(("layer_dir", "forbidden"), sorted(LAYER_RULES.items()))
def test_layer_dependency_direction(layer_dir: str, forbidden: set[str]) -> None:
    """各層は許可された方向以外の上位/兄弟層からインポートしてはならない。"""
    _skip_if_missing(layer_dir)
    violations = _check_layer_imports(layer_dir, forbidden, LAYER_EXCEPTIONS)
    assert not violations, f"Layer '{layer_dir}' imports from forbidden layers:\n" + "\n".join(
        violations
    )


def test_adapter_runtime_imports_are_explicitly_allowlisted() -> None:
    """Adapter から runtime への import 例外を file/import pair 単位で固定する。"""
    allowed_pairs = {
        (rel_path, import_prefix)
        for layer_dir, rel_path, import_prefix, _reason in LAYER_EXCEPTIONS
        if layer_dir == "iris/adapters" and import_prefix.startswith("iris.runtime")
    }
    violations: list[str] = []
    adapters_root = PROJECT_ROOT / "iris/adapters"

    for filepath in _get_python_files(adapters_root):
        rel_path = filepath.relative_to(PROJECT_ROOT).as_posix()
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
        for imported in _all_imports(tree):
            if not imported.startswith("iris.runtime"):
                continue
            if (rel_path, imported) in allowed_pairs:
                continue
            violations.append(f" {rel_path}: imports '{imported}'")

    message = (
        "Adapters must not import runtime unless the file/import pair is explicitly "
        "approved with an architecture reason.\n"
    )
    assert not violations, message + "\n".join(violations)


# ═══════════════════════════════════════════════════════════════════
# 4.  Runtime entrypoint rules
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("rel_path", sorted(ENTRYPOINT_FILES | WIRING_FILES))
def test_entrypoint_no_deleted_imports(rel_path: str) -> None:
    """エントリポイントと配線ファイルは削除されたパッケージをインポートしてはならない。"""
    file_path = PROJECT_ROOT / rel_path
    assert file_path.is_file(), f"Guard file must exist: {rel_path}"
    text = file_path.read_text(encoding="utf-8")
    for prefix in DELETED_IMPORTS:
        if prefix.replace(".", "/") in text or prefix in text:
            # More precise AST check
            tree = ast.parse(text)
            for imp in _all_imports(tree):
                assert not imp.startswith(prefix), f"{rel_path} imports deleted '{imp}'"


def test_main_py_delegates_to_target_runtime() -> None:
    """main.pyがiris.runtimeからインポートすることを確認する。"""
    text = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")
    assert "iris.runtime" in text, "main.py must import from iris.runtime"


def _collect_file_service_locator_calls(fp: Path, rel: str) -> list[str]:
    """Collect service locator call violations from a single file.

    Returns:
        Violation message list for this file.
    """
    violations: list[str] = []
    try:
        tree = ast.parse(fp.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return violations
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
            if any(fn in name_parts for fn in ("resolve", "get_service", "locate")):
                violations.append(f"  {rel}:{node.lineno} calls '{'.'.join(name_parts)}'")
    return violations


def test_wiring_uses_constructor_injection() -> None:
    """配線関数はresolve()、get_service()、locate()を呼び出してはならない。"""
    violations: list[str] = []
    for rel in WIRING_FILES:
        fp = PROJECT_ROOT / rel
        if not fp.is_file():
            continue
        violations.extend(_collect_file_service_locator_calls(fp, rel))
    assert not violations, (
        "Wiring must use constructor injection, not service locator:\n" + "\n".join(violations)
    )


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
    """ターゲットパッケージの__init__.pyは重い/削除されたモジュールをインポートしてはならない。"""
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
    assert not violations, (
        "__init__.py files must not import heavy or deleted modules:\n" + "\n".join(violations)
    )


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
    """ターゲットモジュールはサービスロケータや隠れレジストリパターンを再導入してはならない。"""
    _skip_if_missing(target_dir)
    violations: list[str] = []
    base = PROJECT_ROOT / target_dir
    for filepath in _get_python_files(base):
        try:
            text = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = filepath.relative_to(PROJECT_ROOT).as_posix()
        violations.extend(
            f"  {rel}: contains '{pattern}'"
            for pattern in SERVICE_LOCATOR_PATTERNS
            if pattern in text
        )
    assert not violations, f"Service locator patterns found in {target_dir}:\n" + "\n".join(
        violations
    )


def _collect_file_registry_violations(filepath: Path) -> list[str]:
    """Collect global mutable registry violations from a single file.

    Returns:
        Violation message list for this file.
    """
    violations: list[str] = []
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return violations
    rel = filepath.relative_to(PROJECT_ROOT).as_posix()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            violations.extend(
                f"  {rel}: global mutable '{target.id}'"
                for target in node.targets
                if isinstance(target, ast.Name)
                and target.id.isupper()
                and isinstance(node.value, (ast.Dict, ast.List, ast.Set))
            )
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            name = ""
            if isinstance(func, ast.Attribute):
                name = ast.unparse(func)
            elif isinstance(func, ast.Name):
                name = func.id
            if name in {"register", "subscribe", "add_hook"}:
                violations.append(f"  {rel}: module-level call '{name}()'")
    return violations


def test_no_global_mutable_registries() -> None:
    """ターゲットモジュールにモジュールレベルの可変レジストリがあってはならない。"""
    violations: list[str] = []
    for filepath in _iter_source_files():
        violations.extend(_collect_file_registry_violations(filepath))
    assert not violations, "Global mutable registries found:\n" + "\n".join(violations)


# ═══════════════════════════════════════════════════════════════════
# 7.  Ports must live in consuming modules, not contracts/
# ═══════════════════════════════════════════════════════════════════


def test_contracts_has_no_ports_file() -> None:
    """contracts/ports.pyは存在してはならない。ポートは消費モジュールに属する。"""
    ports_path = PROJECT_ROOT / "iris" / "contracts" / "ports.py"
    assert not ports_path.is_file(), (
        "contracts/ports.py exists — ports should be defined in consuming modules "
        "(e.g. cognitive/action/ports.py, cognitive/memory/ports.py, "
        "presentation/ports.py, safety/ports.py, adapters/app_gateway/ports.py)"
    )


# ═══════════════════════════════════════════════════════════════════
# 8.  WIRING_FILES completeness
# ═══════════════════════════════════════════════════════════════════


WIRING_FILES_EXPECTED: set[str] = WIRING_FILES


def test_required_wiring_files_exist() -> None:
    """必要な配線ファイルがディスク上に存在しなければならない。"""
    missing = [rel for rel in WIRING_FILES_EXPECTED if not (PROJECT_ROOT / rel).is_file()]
    assert not missing, "Required wiring files missing:\n" + "\n".join(missing)
