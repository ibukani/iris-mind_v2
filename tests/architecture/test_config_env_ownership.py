"""Environment variable access is owned by ``iris.runtime.config``.

Direct ``os.environ`` reads outside the runtime config package are
forbidden, with a single temporary exception for the OpenAI adapter
that still surfaces ``OPENAI_API_KEY`` until it is migrated to consume
the typed ``IrisRuntimeConfig``.

Allowed:

- ``iris/runtime/config/**``
- ``iris/adapters/llm/openai.py`` (temporary exception)

Disallowed everywhere else under ``iris/`` and ``main.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

ALLOWED_ROOTS: tuple[Path, ...] = (PROJECT_ROOT / "iris" / "runtime" / "config",)

ALLOWED_FILES: tuple[Path, ...] = (PROJECT_ROOT / "iris" / "adapters" / "llm" / "openai.py",)

SCAN_ROOTS: tuple[Path, ...] = (PROJECT_ROOT / "iris",)

ALLOWED_TEST_FILE: Path = PROJECT_ROOT / "tests" / "runtime" / "test_config.py"


def _python_files(root: Path) -> tuple[Path, ...]:
    if not root.is_dir():
        return ()
    return tuple(sorted(root.rglob("*.py")))


def _reads_environ(tree: ast.Module) -> bool:
    """Return whether the module reads ``os.environ`` directly."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if node.attr != "environ":
            continue
        value = node.value
        if isinstance(value, ast.Name) and value.id == "os":
            return True
    return False


def _is_allowed(path: Path) -> bool:
    if path in ALLOWED_FILES:
        return True
    return any(path.is_relative_to(root) for root in ALLOWED_ROOTS)


def test_direct_os_environ_reads_are_confined_to_runtime_config() -> None:
    """``os.environ`` reads must live under ``iris.runtime.config``.

    The only allowed exception is the OpenAI adapter, which still reads
    ``OPENAI_API_KEY`` directly until the credential is migrated to
    consume the typed ``IrisRuntimeConfig``.
    """
    violations: list[str] = []
    for path in _python_files(PROJECT_ROOT / "iris"):
        if _is_allowed(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        if _reads_environ(tree):
            rel = path.relative_to(PROJECT_ROOT).as_posix()
            violations.append(rel)

    prefix = "os.environ reads must live in iris/runtime/config/** (also openai.py). Violations:\n"
    message = prefix + "\n".join(violations)
    assert not violations, message


def test_main_py_does_not_read_os_environ_directly() -> None:
    """``main.py`` must not introduce a new direct ``os.environ`` read."""
    main_path = PROJECT_ROOT / "main.py"
    if not main_path.is_file():
        pytest.skip("main.py missing")
    tree = ast.parse(main_path.read_text(encoding="utf-8"))
    assert not _reads_environ(tree), (
        "main.py must delegate environment access to iris.runtime.config"
    )


def test_runtime_config_package_is_the_only_environ_owner() -> None:
    """Sanity: the runtime config package itself may read ``os.environ``."""
    config_root = PROJECT_ROOT / "iris" / "runtime" / "config"
    assert config_root.is_dir()
    found = False
    for path in _python_files(config_root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        if _reads_environ(tree):
            found = True
            break
    assert found, "iris/runtime/config is expected to read os.environ in root.py"
