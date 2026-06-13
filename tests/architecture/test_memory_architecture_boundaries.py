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


def test_hybrid_retriever_resolves_records_through_memory_store() -> None:
    """Hybrid retriever は vector id を MemoryStore で record 解決する。"""
    source = HYBRID_RETRIEVER_PATH.read_text(encoding="utf-8")
    assert "self._store.get(" in source
    assert "self._vector.search(" in source
