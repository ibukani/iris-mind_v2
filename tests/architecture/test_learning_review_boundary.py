"""Learning candidate review service boundary の architecture guard。"""

from __future__ import annotations

import ast

from tests.architecture.helpers.ast_utils import imported_modules, parse_python_file
from tests.architecture.helpers.import_rules import matches_any_prefix
from tests.architecture.helpers.project_paths import PROJECT_ROOT

REVIEW_SERVICE_PATH = PROJECT_ROOT / "iris/runtime/learning/review_service.py"
REVIEW_CONTRACT_PATH = PROJECT_ROOT / "iris/contracts/review_candidates.py"
FORBIDDEN_CONTRACT_IMPORT_PREFIXES = frozenset(
    {
        "iris.adapters",
        "iris.cognitive",
        "iris.features",
        "iris.runtime",
    }
)


def test_review_contract_does_not_import_runtime_or_adapter_layers() -> None:
    """Review contract は runtime/adapters の内部型に依存しない。"""
    modules = imported_modules(parse_python_file(REVIEW_CONTRACT_PATH))
    violations = sorted(
        module
        for module in modules
        if matches_any_prefix(module, FORBIDDEN_CONTRACT_IMPORT_PREFIXES)
    )

    assert not violations, "\n".join(violations)


def test_review_service_does_not_depend_on_sqlite_or_promotion_workflow() -> None:
    """Review service は SQLite adapter と promotion workflow を直接呼ばない。"""
    tree = parse_python_file(REVIEW_SERVICE_PATH)
    modules = imported_modules(tree)
    forbidden_modules = {
        "iris.adapters.persistence.sqlite",
        "iris.adapters.persistence.sqlite.stores.memory_candidate_reviews",
        "iris.runtime.learning.review_promotion",
    }
    violations = sorted(
        module for module in modules if matches_any_prefix(module, forbidden_modules)
    )

    assert not violations, "\n".join(violations)
    assert "promote" not in _called_attribute_names(tree)


def test_review_service_public_api_does_not_return_store_records() -> None:
    """Review service の public API は store record を返却 annotation にしない。"""
    tree = parse_python_file(REVIEW_SERVICE_PATH)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and not node.name.startswith("_"):
            annotation = node.returns
            if annotation is not None and "MemoryCandidateReviewRecord" in ast.unparse(annotation):
                violations.append(f"{REVIEW_SERVICE_PATH}:{node.lineno}: {node.name}")

    assert not violations, "\n".join(violations)


def _called_attribute_names(tree: ast.AST) -> set[str]:
    """AST 内の attribute call 名を集める。

    Returns:
        呼び出された attribute 名。
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    return names
