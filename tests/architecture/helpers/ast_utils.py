"""Architecture tests 用 AST helper。"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def parse_python_file(path: Path) -> ast.Module:
    """Python ファイルを AST として読む。

    Returns:
        Parsed module AST。
    """
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def imported_modules(tree: ast.AST) -> set[str]:
    """AST 内の import 対象 module 名を集める。

    Returns:
        Imported module names。
    """
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)
    return imports


def name_of(node: ast.AST) -> str | None:
    """AST node が参照する末尾の名前を返す。

    Returns:
        Name or attribute tail name。
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return name_of(node.value)
    return None


def names_in(node: ast.AST) -> set[str]:
    """AST node 以下に現れる名前を集める。

    Returns:
        Names found under the node。
    """
    names: set[str] = set()
    for child in ast.walk(node):
        name = name_of(child)
        if name is not None:
            names.add(name)
    return names
