"""Tests for runtime server wiring composition."""

from __future__ import annotations

from dataclasses import replace
import inspect
from pathlib import Path
from typing import Any

from iris.adapters.app_gateway.space_resolver import EphemeralSpaceResolver
from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.adapters.persistence.sqlite.stores.memory import SQLiteMemoryStore
from iris.cognitive.memory.retrieval import MemoryRetrievalStep
from iris.runtime.config import default_runtime_config
from iris.runtime.config.state import RuntimeStateBackend, RuntimeStateConfig
from iris.runtime.server import build_runtime_components
from iris.runtime.wiring.app import build_app_from_config
from iris.runtime.wiring.memory import SQLiteFTS5MemoryRetriever
from tests.helpers.private_access import get_private_attr_as, get_private_attr_path_as

_MODULE_PATH = Path("iris/runtime/wiring/app.py")


def _read_app_wiring_source() -> str:
    """Read the runtime app wiring module source as text.

    Returns:
        str: The decoded UTF-8 source text of iris/runtime/wiring/app.py.
    """
    return _MODULE_PATH.read_text(encoding="utf-8")


def test_build_runtime_components_uses_fts5_retrieval_for_sqlite(
    tmp_path: Path,
) -> None:
    """埋め込み関数なしのSQLiteバックエンドではFTS5検索が使われる。"""
    db_path = tmp_path / "state.db"
    config = default_runtime_config()
    config = replace(
        config,
        state=RuntimeStateConfig(backend=RuntimeStateBackend.SQLITE, sqlite_path=str(db_path)),
    )

    components = build_runtime_components(config)

    assert isinstance(components.stores.memory_store, SQLiteMemoryStore)
    assert isinstance(components.space_resolver, EphemeralSpaceResolver)
    cycle = get_private_attr_path_as(components.runtime_service, ("_app", "_cycle"), object)
    steps: Any = get_private_attr_as(cycle, "_steps", tuple[object, ...])
    retrieval_steps = [step for step in steps if isinstance(step, MemoryRetrievalStep)]
    assert len(retrieval_steps) == 1
    retriever = get_private_attr_as(retrieval_steps[0], "_retriever", object)
    assert isinstance(retriever, SQLiteFTS5MemoryRetriever)
    assert get_private_attr_as(retriever, "_store", object) is components.stores.memory_store


def test_build_runtime_components_uses_in_memory_store_for_default_backend() -> None:
    """Default in-memory backend wires the InMemoryMemoryStore into the cycle."""
    config = default_runtime_config()

    components = build_runtime_components(config)

    assert isinstance(components.stores.memory_store, InMemoryMemoryStore)
    assert isinstance(components.space_resolver, EphemeralSpaceResolver)
    cycle = get_private_attr_path_as(components.runtime_service, ("_app", "_cycle"), object)
    steps: Any = get_private_attr_as(cycle, "_steps", tuple[object, ...])
    retrieval_steps = [step for step in steps if isinstance(step, MemoryRetrievalStep)]
    assert len(retrieval_steps) == 1
    assert (
        get_private_attr_as(retrieval_steps[0], "_retriever", object)
        is components.stores.memory_store
    )


def test_build_runtime_components_uses_state_account_store_in_identity_resolver(
    tmp_path: Path,
) -> None:
    """build_runtime_components feeds state stores into runtime resolvers."""
    db_path = tmp_path / "state.db"
    config = default_runtime_config()
    config = replace(
        config,
        state=RuntimeStateConfig(backend=RuntimeStateBackend.SQLITE, sqlite_path=str(db_path)),
    )

    components = build_runtime_components(config)

    assert get_private_attr_as(components.identity_resolver, "_account_store", object) is (
        components.stores.account_store
    )


def test_build_app_from_config_does_not_import_fake_memory_store() -> None:
    """Runtime app wiring must not import or use FakeMemoryStore as a production fallback."""
    source = _read_app_wiring_source()

    assert "iris.adapters.memory.fake" not in source, (
        "iris/runtime/wiring/app.py must not import from iris.adapters.memory.fake"
    )
    assert "FakeMemoryStore" not in source, (
        "iris/runtime/wiring/app.py must not reference FakeMemoryStore as a fallback"
    )


def test_build_app_from_config_requires_memory_store() -> None:
    """build_app_from_config must require a memory_store argument typed as MemoryStore."""
    signature = inspect.signature(build_app_from_config)
    parameters = signature.parameters

    assert "memory_store" in parameters, (
        "build_app_from_config must declare a memory_store parameter"
    )
    memory_store_param = parameters["memory_store"]
    assert memory_store_param.default is inspect.Parameter.empty, (
        "memory_store must be a required argument (no default value)"
    )
    annotation = memory_store_param.annotation
    annotation_text = annotation if isinstance(annotation, str) else str(annotation)
    assert annotation_text == "MemoryStore", (
        f"memory_store must be typed as MemoryStore, got: {annotation_text}"
    )
