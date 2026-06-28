"""Architecture guards for feature boundaries."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FEATURES_ROOT = PROJECT_ROOT / "iris" / "features"


def _python_files() -> tuple[Path, ...]:
    if not FEATURES_ROOT.is_dir():
        return ()
    return tuple(sorted(FEATURES_ROOT.rglob("*.py")))


def test_features_do_not_return_presented_output() -> None:
    """Feature code must not return PresentedOutput. It should return ReactionCandidate or ActionPlan."""
    violations: list[str] = []
    
    for path in _python_files():
        rel_path = path.relative_to(PROJECT_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if node.returns:
                    returns_str = ast.unparse(node.returns)
                    if "PresentedOutput" in returns_str:
                        violations.append(f"{rel_path}: function '{node.name}' returns PresentedOutput")

    assert not violations, "Feature code must not return PresentedOutput:\n" + "\n".join(violations)

