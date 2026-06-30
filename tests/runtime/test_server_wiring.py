"""Tests for runtime server wiring composition."""

from __future__ import annotations

from dataclasses import replace
import inspect
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

from iris.adapters.app_gateway.space_resolver import EphemeralSpaceResolver
from iris.adapters.memory.in_memory import InMemoryMemoryStore
from iris.adapters.persistence.sqlite.stores.memory import SQLiteMemoryStore
from iris.cognitive.memory.retrieval import MemoryRetrievalStep
from iris.features.definition import FeatureDefinition, LearningHook
from iris.runtime.config import IrisRuntimeConfig, default_runtime_config
from iris.runtime.config.state import RuntimeStateBackend, RuntimeStateConfig
from iris.runtime.conversation import DeliveryConversationHistoryHook
from iris.runtime.server import build_runtime_components
from iris.runtime.wiring.app import AppStateDependencies, build_app_from_config
from iris.runtime.wiring.features import RuntimeFeatureCatalog
from iris.runtime.wiring.memory import SQLiteFTS5MemoryRetriever
from iris.runtime.wiring.state import wire_runtime_state

if TYPE_CHECKING:
    from iris.contracts.learning import LearningEvent
    from iris.runtime.wiring.state import RuntimeStateStores

from tests.helpers.private_access import (
    get_private_attr_as,
    get_private_attr_path_as,
    import_private_as,
)

_MODULE_PATH = Path("iris/runtime/wiring/app.py")


class _WireActionResultHooks(Protocol):
    """Typed access to runtime action-result hook wiring."""

    def __call__(
        self,
        config: IrisRuntimeConfig,
        stores: RuntimeStateStores,
        feature_catalog: RuntimeFeatureCatalog,
    ) -> tuple[LearningHook, ...]:
        """Return action-result hooks in wiring order."""
        ...


class _NoOpLearningHook:
    """Feature-owned hook used to verify learning.enabled filtering."""

    async def after_action_result(self, event: LearningEvent) -> None:
        """Accept a learning event without side effects."""
        _ = event


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


def test_build_app_from_config_requires_typed_state_dependencies() -> None:
    """build_app_from_config は型付き state 依存を必須引数として受け取る。"""
    signature = inspect.signature(build_app_from_config)
    parameters = signature.parameters

    assert "state" in parameters
    state_param = parameters["state"]
    assert state_param.default is inspect.Parameter.empty
    annotation = state_param.annotation
    annotation_text = annotation if isinstance(annotation, str) else str(annotation)
    assert annotation_text == "AppStateDependencies"
    assert AppStateDependencies.__dataclass_fields__["memory_store"].type == "MemoryStore"


def test_action_result_hook_wiring_keeps_delivery_history_when_learning_disabled() -> None:
    """learning.enabled=False でも delivery history finalizer は配線される。"""
    base_config = default_runtime_config()
    config = replace(base_config, learning=replace(base_config.learning, enabled=False))
    stores = wire_runtime_state(config)
    feature_hook = _NoOpLearningHook()
    feature_catalog = RuntimeFeatureCatalog(
        features=(
            FeatureDefinition(
                name="test-learning",
                learning_hooks=(feature_hook,),
            ),
        )
    )
    wire_action_result_hooks = cast(
        "_WireActionResultHooks",
        import_private_as(
            "iris.runtime.wiring.runtime",
            "_wire_action_result_hooks",
            object,
        ),
    )

    hooks = wire_action_result_hooks(config, stores, feature_catalog)

    assert len(hooks) == 1
    assert isinstance(hooks[0], DeliveryConversationHistoryHook)
    assert hooks[0].store is stores.conversation_history_store
    assert feature_hook not in hooks
