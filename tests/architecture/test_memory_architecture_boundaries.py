"""Memory lifecycle owner と vector index の境界を検査する。"""

from __future__ import annotations

import ast

from tests.architecture.helpers.ast_utils import imported_modules, name_of, parse_python_file
from tests.architecture.helpers.project_paths import PROJECT_ROOT

RUNTIME_WIRING_ROOT = PROJECT_ROOT / "iris/runtime/wiring"
VECTOR_INDEX_PATH = PROJECT_ROOT / "iris/adapters/memory/vector_index.py"
HYBRID_RETRIEVER_PATH = PROJECT_ROOT / "iris/cognitive/memory/hybrid.py"


def test_runtime_wiring_does_not_use_vector_store_as_memory_lifecycle_owner() -> None:
    """Runtime wiring は vector-backed MemoryStore を canonical store にしない。"""
    violations: list[str] = []
    for path in sorted(RUNTIME_WIRING_ROOT.rglob("*.py")):
        modules = imported_modules(parse_python_file(path))
        if "iris.adapters.memory.vector" in modules:
            violations.append(str(path))
    assert not violations, "\n".join(violations)


def test_vector_index_does_not_store_full_memory_records() -> None:
    """VectorMemoryIndex は MemoryRecord ではなく memory id/index entry だけを保持する。"""
    tree = parse_python_file(VECTOR_INDEX_PATH)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            annotation_names = {
                name for child in ast.walk(node.annotation) if (name := name_of(child)) is not None
            }
            if "MemoryRecord" in annotation_names:
                annotation = ast.unparse(node.annotation)
                violations.append(f"{VECTOR_INDEX_PATH}:{node.lineno}: {annotation}")
    assert not violations, "\n".join(violations)


def _match_self_attr_call(node: ast.Call, object_name: str, method_name: str) -> bool:
    """self.object_name.method_name() の呼び出しか判定する。

    Returns:
        匹配する場合 True。
    """
    return (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == method_name
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == object_name
        and isinstance(node.func.value.value, ast.Name)
        and node.func.value.value.id == "self"
    )


def _has_attr_call(tree: ast.AST, object_name: str, method_name: str) -> bool:
    """AST 内に object_name.method_name() の呼び出しがあるか。

    Returns:
        該当呼び出しがある場合 True。
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _match_self_attr_call(node, object_name, method_name):
            return True
    return False


def test_hybrid_retriever_resolves_records_through_memory_store() -> None:
    """Hybrid retriever は vector id を MemoryStore で record 解決する。"""
    tree = parse_python_file(HYBRID_RETRIEVER_PATH)
    assert _has_attr_call(tree, "_store", "get"), (
        "hybrid retriever must call self._store.get() for record resolution"
    )
    assert _has_attr_call(tree, "_vector", "search"), (
        "hybrid retriever must call self._vector.search() for vector search"
    )
