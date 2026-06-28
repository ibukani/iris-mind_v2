"""Runtime configuration tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
import tomllib
from typing import TYPE_CHECKING, TypeGuard, override

import pytest

from iris.adapters.llm.ports import LLMClient, LLMRequest, LLMResponse
from iris.adapters.memory.fake import FakeMemoryStore
from iris.cognitive.action.response import ResponseGenerationStep
from iris.contracts.identity import ActorKind, Identity
from iris.contracts.observations import (
    ActorMessageObservation,
    ObservationContext,
    ObservationKind,
)
from iris.core.ids import ActorId, ExternalRef, ObservationId, SessionId
from iris.features.proactive_talk import define_proactive_talk_feature
import iris.runtime.config as config_pkg
from iris.runtime.config import (
    ConfigError,
    DiagnosticsMode,
    IrisRuntimeConfig,
    RuntimeConfigOverrides,
    RuntimeModelConfig,
    RuntimeModelsConfig,
    RuntimeOllamaConfig,
    RuntimeOpenAIConfig,
    default_runtime_config,
    discover_default_config_path,
    load_runtime_config,
    normalize_config_path,
    parse_llm_provider,
)
from iris.runtime.config.llm import LLMProvider
from iris.runtime.state.ephemeral.affect import InMemoryAffectStore
from iris.runtime.state.ephemeral.relationship import InMemoryRelationshipStore
from iris.runtime.wiring.app import AppStateDependencies, build_app_from_config
from iris.runtime.wiring.llm import LLMClientFactory
from iris.runtime.wiring.presentation import wire_output_pipeline

if TYPE_CHECKING:
    from iris.contracts.memory import MemoryQuery, MemorySearchResult

from tests.helpers.approx import approx
from tests.helpers.exact_eq import assert_exact_eq
from tests.helpers.private_access import get_private_attr_as


def _is_object_tuple(value: object) -> TypeGuard[tuple[object, ...]]:
    """値が任意オブジェクトのtupleか判定する。

    Returns:
        tupleの場合はTrue。
    """
    return isinstance(value, tuple)


def test_default_config_uses_fake_default_chat() -> None:
    """Default config uses fake for default_chat."""
    config = default_runtime_config()

    assert config.models.default_chat == RuntimeModelConfig(
        provider=LLMProvider.FAKE,
        model="fake-llm",
        max_output_tokens=512,
    )


def test_default_config_includes_fast_judge_and_reasoning_slots() -> None:
    """Default config includes parsed fast_judge and reasoning slots."""
    config = default_runtime_config()

    assert config.models.fast_judge == RuntimeModelConfig(
        provider=LLMProvider.FAKE,
        model="fake-llm",
        max_output_tokens=128,
    )
    assert config.models.reasoning == RuntimeModelConfig(
        provider=LLMProvider.FAKE,
        model="fake-llm",
        max_output_tokens=1024,
    )


def test_toml_sets_default_chat_slot(tmp_path: Path) -> None:
    """TOML can configure the default_chat slot."""
    config_path = _write_config(
        tmp_path,
        """
        [models.default_chat]
        provider = "ollama"
        model = "qwen3:8b"
        temperature = 0.7
        max_output_tokens = 512
        """,
    )

    config = load_runtime_config(config_path, env={})

    assert config.models.default_chat == RuntimeModelConfig(
        provider=LLMProvider.OLLAMA,
        model="qwen3:8b",
        temperature=0.7,
        max_output_tokens=512,
    )


def test_example_config_parses_successfully() -> None:
    """Committed example config parses through the runtime config loader."""
    config = load_runtime_config(_example_config_path(), env={})

    assert config.models.default_chat.provider == "fake"
    assert config.models.default_chat.model == "fake-llm"
    assert config.ollama.base_url == "http://localhost:11434"


def test_example_config_contains_all_model_slots() -> None:
    """Committed example config includes all supported model slots."""
    config = load_runtime_config(_example_config_path(), env={})

    assert config.models.default_chat.model == "fake-llm"
    assert config.models.fast_judge.model == "fake-llm"
    assert config.models.reasoning.model == "fake-llm"


def test_example_config_contains_no_obvious_secret_fields() -> None:
    """Committed example config does not include API key or token fields."""
    text = _example_config_path().read_text(encoding="utf-8").lower()

    assert "api_key" not in text
    assert "apikey" not in text
    assert "secret" not in text
    assert "access_token" not in text
    assert "auth_token" not in text
    assert "bearer_token" not in text


def test_local_runtime_config_files_are_gitignored() -> None:
    """Local runtime config files are ignored while the committed sample is not."""
    gitignore = _repo_path(".gitignore").read_text(encoding="utf-8")

    assert ".iris/config/runtime.toml" in gitignore
    assert ".iris/config/local.toml" in gitignore
    assert ".iris/config/runtime.example.toml" not in gitignore


def test_toml_sets_fast_judge_and_reasoning_slots(tmp_path: Path) -> None:
    """TOML can configure fast_judge and reasoning slots."""
    config_path = _write_config(
        tmp_path,
        """
        [models.fast_judge]
        provider = "ollama"
        model = "qwen3:4b"
        temperature = 0.0
        max_output_tokens = 128

        [models.reasoning]
        provider = "ollama"
        model = "deepseek-r1:8b"
        temperature = 0.0
        max_output_tokens = 1024
        """,
    )

    config = load_runtime_config(config_path, env={})

    assert config.models.fast_judge == RuntimeModelConfig(
        provider=LLMProvider.OLLAMA,
        model="qwen3:4b",
        max_output_tokens=128,
    )
    assert config.models.reasoning == RuntimeModelConfig(
        provider=LLMProvider.OLLAMA,
        model="deepseek-r1:8b",
        max_output_tokens=1024,
    )


def test_toml_sets_ollama_and_openai_sections(tmp_path: Path) -> None:
    """TOML can configure provider-level Ollama and OpenAI settings."""
    config_path = _write_config(
        tmp_path,
        """
        [ollama]
        base_url = "http://localhost:11434"
        timeout_seconds = 120.0
        keep_alive = "5m"

        [openai]
        model = "gpt-5-mini"
        timeout_seconds = 60.0
        max_output_tokens = 512
        """,
    )

    config = load_runtime_config(config_path, env={})

    assert config.ollama.base_url == "http://localhost:11434"
    assert abs(config.ollama.timeout_seconds - 120.0) < 0.001
    assert config.ollama.keep_alive == "5m"
    assert config.openai.model == "gpt-5-mini"
    assert config.openai.timeout_seconds is not None
    assert abs(config.openai.timeout_seconds - 60.0) < 0.001
    assert config.openai.max_output_tokens == 512


def test_env_vars_override_toml_values(tmp_path: Path) -> None:
    """Environment variables override TOML values."""
    config_path = _write_config(
        tmp_path,
        """
        [models.default_chat]
        provider = "fake"
        model = "toml-model"
        temperature = 0.1
        max_output_tokens = 64

        [ollama]
        base_url = "http://toml-host:11434"
        """,
    )
    env = {
        "IRIS_DEFAULT_CHAT_PROVIDER": "ollama",
        "IRIS_DEFAULT_CHAT_MODEL": "env-model",
        "IRIS_DEFAULT_CHAT_TEMPERATURE": "0.2",
        "IRIS_DEFAULT_CHAT_MAX_OUTPUT_TOKENS": "128",
        "IRIS_OLLAMA_HOST": "http://env-host:11434",
    }

    config = load_runtime_config(config_path, env=env)

    assert config.models.default_chat == RuntimeModelConfig(
        provider=LLMProvider.OLLAMA,
        model="env-model",
        temperature=0.2,
        max_output_tokens=128,
    )
    assert config.ollama.base_url == "http://env-host:11434"


def test_cli_args_override_env_values(tmp_path: Path) -> None:
    """CLI overrides have higher precedence than environment variables."""
    config_path = _write_config(
        tmp_path,
        """
        [models.default_chat]
        provider = "fake"
        model = "toml-model"
        """,
    )
    env = {
        "IRIS_DEFAULT_CHAT_PROVIDER": "openai",
        "IRIS_DEFAULT_CHAT_MODEL": "env-model",
        "IRIS_OLLAMA_HOST": "http://env-host:11434",
    }

    config = load_runtime_config(
        config_path,
        env=env,
        overrides=RuntimeConfigOverrides(
            llm=LLMProvider.OLLAMA,
            model="cli-model",
            ollama_host="http://cli-host:11434",
        ),
    )

    assert config.models.default_chat.provider == "ollama"
    assert config.models.default_chat.model == "cli-model"
    assert config.ollama.base_url == "http://cli-host:11434"


def test_missing_config_path_raises_config_error(tmp_path: Path) -> None:
    """Missing explicit --config path raises ConfigError."""
    missing = tmp_path / "missing.toml"

    with pytest.raises(ConfigError):
        load_runtime_config(missing, env={})


def test_omitted_config_without_default_file_is_allowed(tmp_path: Path) -> None:
    """Omitted config file path uses defaults when no default file exists."""
    config = load_runtime_config(None, env={}, cwd=tmp_path)

    assert config.models.default_chat.provider == "fake"


def test_normalize_config_path_resolves_relative_path_against_cwd(
    tmp_path: Path,
) -> None:
    """Relative config paths are resolved against the provided cwd."""
    assert normalize_config_path("local.toml", cwd=tmp_path) == tmp_path / "local.toml"


def test_discover_default_config_path_prefers_project_config(
    tmp_path: Path,
) -> None:
    """Project-local config is the first default discovery candidate."""
    local_config = tmp_path / ".iris/config/runtime.toml"
    _write_toml(
        local_config,
        """
        [models.default_chat]
        provider = "fake"
        model = "local-model"
        """,
    )

    assert discover_default_config_path(cwd=tmp_path, env={}, home=tmp_path) == local_config


def test_load_runtime_config_uses_project_default_config(tmp_path: Path) -> None:
    """Omitted --config loads .iris/config/runtime.toml when it exists."""
    _write_toml(
        tmp_path / ".iris/config/runtime.toml",
        """
        [models.default_chat]
        provider = "fake"
        model = "local-model"
        """,
    )

    config = load_runtime_config(None, env={}, cwd=tmp_path)

    assert config.models.default_chat.model == "local-model"


def test_explicit_config_replaces_default_discovery(tmp_path: Path) -> None:
    """Explicit --config path wins over discovered defaults."""
    _write_toml(
        tmp_path / ".iris/config/runtime.toml",
        """
        [models.default_chat]
        provider = "fake"
        model = "local-model"
        """,
    )
    explicit_config = _write_toml(
        tmp_path / "explicit.toml",
        """
        [models.default_chat]
        provider = "fake"
        model = "explicit-model"
        """,
    )
    env = {"IRIS_MIND_CONFIG": str(tmp_path / "env.toml")}

    config = load_runtime_config(explicit_config, env=env, cwd=tmp_path)

    assert config.models.default_chat.model == "explicit-model"


def test_load_runtime_config_uses_iris_mind_config_env(tmp_path: Path) -> None:
    """IRIS_MIND_CONFIG points discovery at an explicit environment file."""
    env_config = _write_toml(
        tmp_path / "env.toml",
        """
        [models.default_chat]
        provider = "fake"
        model = "env-file-model"
        """,
    )

    config = load_runtime_config(
        None,
        env={"IRIS_MIND_CONFIG": str(env_config)},
        cwd=tmp_path,
    )

    assert config.models.default_chat.model == "env-file-model"


def test_missing_iris_mind_config_env_raises_config_error(tmp_path: Path) -> None:
    """Missing IRIS_MIND_CONFIG file is an explicit user error."""
    with pytest.raises(ConfigError):
        load_runtime_config(
            None,
            env={"IRIS_MIND_CONFIG": "missing.toml"},
            cwd=tmp_path,
        )


def test_load_runtime_config_uses_xdg_config_home(tmp_path: Path) -> None:
    """XDG config is loaded when no project-local config exists."""
    xdg_config = _write_toml(
        tmp_path / "xdg/iris-mind/runtime.toml",
        """
        [models.default_chat]
        provider = "fake"
        model = "xdg-model"
        """,
    )

    config = load_runtime_config(
        None,
        env={"XDG_CONFIG_HOME": str(xdg_config.parents[1])},
        cwd=tmp_path,
    )

    assert config.models.default_chat.model == "xdg-model"


def test_config_precedence_without_cli_uses_env_then_file(tmp_path: Path) -> None:
    """Environment overrides discovered config, and config overrides defaults."""
    _write_toml(
        tmp_path / ".iris/config/runtime.toml",
        """
        [models.default_chat]
        provider = "fake"
        model = "file-model"
        """,
    )

    file_config = load_runtime_config(None, env={}, cwd=tmp_path)
    env_config = load_runtime_config(
        None,
        env={"IRIS_DEFAULT_CHAT_MODEL": "env-model"},
        cwd=tmp_path,
    )

    assert file_config.models.default_chat.model == "file-model"
    assert env_config.models.default_chat.model == "env-model"


def test_invalid_provider_raises_config_error(tmp_path: Path) -> None:
    """Invalid provider names raise ConfigError."""
    config_path = _write_config(
        tmp_path,
        """
        [models.default_chat]
        provider = "bad-provider"
        model = "x"
        """,
    )

    with pytest.raises(ConfigError):
        load_runtime_config(config_path, env={})


@pytest.mark.parametrize(
    ("env", "error_key"),
    [
        ({"IRIS_DEFAULT_CHAT_TEMPERATURE": "not-float"}, "TEMPERATURE"),
        ({"IRIS_DEFAULT_CHAT_MAX_OUTPUT_TOKENS": "not-int"}, "MAX"),
        ({"IRIS_OLLAMA_TIMEOUT_SECONDS": "not-float"}, "TIMEOUT"),
        ({"IRIS_OPENAI_MAX_OUTPUT_TOKENS": "not-int"}, "OPENAI"),
    ],
)
def test_invalid_env_values_raise_config_error(env: dict[str, str], error_key: str) -> None:
    """Invalid numeric environment overrides raise ConfigError."""
    with pytest.raises(ConfigError, match=error_key):
        load_runtime_config(None, env=env)


@pytest.mark.anyio
async def test_build_app_from_config_uses_default_chat_and_full_cycle() -> None:
    """build_app_from_config wires default_chat into the full cognitive cycle."""
    client = _RecordingLLMClient()
    factory = _RecordingFactory(client)
    memory_store = _RecordingEmptyMemoryStore()
    base = default_runtime_config()
    config = replace(
        base,
        models=replace(
            base.models,
            default_chat=RuntimeModelConfig(
                provider=LLMProvider.FAKE,
                model="slot-model",
                temperature=0.3,
                max_output_tokens=77,
            ),
            fast_judge=RuntimeModelConfig(provider=LLMProvider.FAKE, model="unused-fast"),
            reasoning=RuntimeModelConfig(provider=LLMProvider.FAKE, model="unused-reasoning"),
        ),
    )
    app = build_app_from_config(
        config,
        client_factory=factory,
        state=AppStateDependencies(
            memory_store=memory_store,
            relationship_store=InMemoryRelationshipStore(),
            affect_store=InMemoryAffectStore(),
        ),
        output_pipeline=wire_output_pipeline(safety_config=config.safety),
    )

    await app.process_observation(_actor_observation("I need help with suicide and tea"))

    assert factory.model_config == config.models.default_chat
    assert memory_store.query is not None
    assert memory_store.query.text == "I need help with suicide and tea"
    assert client.request is not None
    assert client.request.model == "slot-model"
    assert client.request.temperature is not None
    assert abs(client.request.temperature - 0.3) < 0.001
    assert client.request.max_tokens == 77
    user_message = client.request.messages[1].content
    assert "Affect context:" in user_message
    assert "Relationship context:" in user_message
    assert "Mina: neutral relationship" in user_message
    assert "Policy constraints:" in user_message
    assert "avoid escalating beyond the safety layer" in user_message


@pytest.mark.anyio
async def test_build_app_from_config_resolves_openai_default_model() -> None:
    """OpenAI provider override without model uses the OpenAI provider default model."""
    client = _RecordingLLMClient()
    factory = _RecordingFactory(client)
    memory_store = FakeMemoryStore()
    base = default_runtime_config()
    config = replace(
        base,
        models=replace(
            base.models,
            default_chat=RuntimeModelConfig(provider=LLMProvider.OPENAI, model="fake-llm"),
        ),
    )
    app = build_app_from_config(
        config,
        client_factory=factory,
        state=AppStateDependencies(
            memory_store=memory_store,
            relationship_store=InMemoryRelationshipStore(),
            affect_store=InMemoryAffectStore(),
        ),
        output_pipeline=wire_output_pipeline(safety_config=config.safety),
    )

    await app.process_observation(_observation("hello"))

    assert client.request is not None
    assert client.request.model == "gpt-5-mini"


def test_build_app_from_config_includes_registered_feature_steps() -> None:
    """標準 app wiring は FeatureDefinition の認知ステップを cycle に含める。"""
    config = default_runtime_config()
    feature = define_proactive_talk_feature()
    app = build_app_from_config(
        config,
        state=AppStateDependencies(
            memory_store=FakeMemoryStore(),
            relationship_store=InMemoryRelationshipStore(),
            affect_store=InMemoryAffectStore(),
        ),
        output_pipeline=wire_output_pipeline(safety_config=config.safety),
        features=(feature,),
    )

    cycle = get_private_attr_as(app, "_cycle", object)
    steps_value = get_private_attr_as(cycle, "_steps", tuple)
    assert _is_object_tuple(steps_value)
    steps = steps_value
    extension_indexes = tuple(steps.index(step) for step in feature.cognitive_steps)
    response_index = len(steps) - 1

    assert isinstance(steps[response_index], ResponseGenerationStep)
    assert extension_indexes == tuple(sorted(extension_indexes))
    assert all(index < response_index for index in extension_indexes)


class _RecordingLLMClient:
    def __init__(self) -> None:
        self.request: LLMRequest | None = None

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.request = request
        return LLMResponse(text="recorded", model=request.model)


class _RecordingEmptyMemoryStore(FakeMemoryStore):
    """Empty FakeMemoryStore that records the query passed by default runtime wiring."""

    def __init__(self) -> None:
        """Initialize empty recording memory store."""
        super().__init__()
        self.query: MemoryQuery | None = None

    @override
    def search(self, query: MemoryQuery) -> tuple[MemorySearchResult, ...]:
        """Record query and return empty fake memory results.

        Returns:
            tuple[MemorySearchResult, ...]: Empty memory search results.
        """
        self.query = query
        return tuple(super().search(query))


class _RecordingFactory(LLMClientFactory):
    def __init__(self, client: LLMClient) -> None:
        super().__init__()
        self._client = client
        self.model_config: RuntimeModelConfig | None = None
        self.runtime_config: IrisRuntimeConfig | None = None

    @override
    def create_client(
        self,
        model_config: RuntimeModelConfig,
        runtime_config: IrisRuntimeConfig,
    ) -> LLMClient:
        self.model_config = model_config
        self.runtime_config = runtime_config
        return self._client


def _write_config(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "runtime.toml"
    path.write_text(content, encoding="utf-8")
    return path


def _write_toml(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _example_config_path() -> Path:
    return _repo_path(".iris/config/runtime.example.toml")


def _repo_path(relative_path: str) -> Path:
    return Path(__file__).resolve().parents[2] / relative_path


def _observation(text: str) -> ActorMessageObservation:
    return ActorMessageObservation(
        observation_id=ObservationId("config-test"),
        session_id=SessionId("config-test"),
        occurred_at=datetime(2026, 6, 4, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
        context=ObservationContext(),
    )


def _actor_observation(text: str) -> ActorMessageObservation:
    return ActorMessageObservation(
        observation_id=ObservationId("config-test-actor"),
        session_id=SessionId("config-test"),
        occurred_at=datetime(2026, 6, 4, tzinfo=UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text=text,
        context=ObservationContext(
            actor=Identity(
                actor_id=ActorId("actor-config"),
                actor_kind=ActorKind.HUMAN,
                display_name="Mina",
                provider="test",
                provider_subject=ExternalRef("mina"),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Package structure and public import compatibility
# ---------------------------------------------------------------------------


def test_public_imports_are_available_from_package_root() -> None:
    """All documented public symbols are re-exported from iris.runtime.config."""
    for name in (
        "ConfigError",
        "apply_runtime_overrides",
        "parse_llm_provider",
    ):
        assert hasattr(config_pkg, name), f"iris.runtime.config missing public symbol: {name}"


def test_config_package_exposes_stable_public_api() -> None:
    """The public config package __all__ is a stable contract."""
    expected = {
        "RuntimeConfigOverrides",
        "RuntimeConfigMetadata",
        "ConfigFieldSpec",
        "ConfigError",
        "IrisRuntimeConfig",
        "LLMProvider",
        "ModelSlotName",
        "RuntimeModelConfig",
        "RuntimeModelsConfig",
        "RuntimeOllamaConfig",
        "RuntimeOpenAIConfig",
        "RuntimeDeliveryConfig",
        "RuntimeLoggingConfig",
        "RuntimeQuietHoursConfig",
        "RuntimeSchedulerConfig",
        "RuntimeServerConfig",
        "RuntimeStateConfig",
        "apply_runtime_overrides",
        "default_runtime_config",
        "discover_default_config_path",
        "load_runtime_config",
        "normalize_config_path",
        "parse_llm_provider",
        "resolve_runtime_config_path",
        "runtime_config_specs",
        "runtime_config_specs_for_version",
        "RuntimeSafetyConfig",
        "RuntimeDiagnosticsConfig",
        "DiagnosticsMode",
        "apply_diagnostics_env",
        "apply_diagnostics_toml",
        "RuntimeAuthConfig",
        "RuntimeAuthMode",
        "all_model_slots_are_fake",
    }
    assert set(config_pkg.__all__) == expected


def test_parse_llm_provider_accepts_known_providers() -> None:
    """parse_llm_provider round-trips the supported provider names."""
    assert parse_llm_provider("fake") == "fake"
    assert parse_llm_provider("ollama") == "ollama"
    assert parse_llm_provider("openai") == "openai"


def test_parse_llm_provider_rejects_unknown_provider() -> None:
    """parse_llm_provider raises ConfigError for unknown provider names."""
    with pytest.raises(ConfigError):
        parse_llm_provider("anthropic")


# ---------------------------------------------------------------------------
# Example config files
# ---------------------------------------------------------------------------


def _example_config_paths() -> tuple[Path, ...]:
    return tuple(sorted(_repo_path("examples/config").glob("*.toml")))


def _is_dict(value: object) -> TypeGuard[dict[str, object]]:
    """Narrow object to dict[str, object] for item iteration.

    Runtime check uses isinstance(dict) which erases type parameters, so the
    narrowed type uses the widest compatible parameter types.

    Returns:
        True if value is a dict, narrowing to the widened type.
    """
    return isinstance(value, dict)


def test_examples_directory_exists() -> None:
    """A committed examples/config directory must exist."""
    assert _repo_path("examples/config").is_dir()


@pytest.mark.parametrize("config_path", _example_config_paths(), ids=lambda p: p.name)
def test_example_config_parses_through_loader(config_path: Path) -> None:
    """Every committed example config must parse via load_runtime_config."""
    config = load_runtime_config(config_path, env={})

    assert isinstance(config, IrisRuntimeConfig)
    assert isinstance(config.models, RuntimeModelsConfig)
    assert isinstance(config.ollama, RuntimeOllamaConfig)
    assert isinstance(config.openai, RuntimeOpenAIConfig)


@pytest.mark.parametrize("config_path", _example_config_paths(), ids=lambda p: p.name)
def test_example_config_contains_no_secret_like_keys(config_path: Path) -> None:
    """Committed example configs must not include API key or token fields."""
    text = config_path.read_text(encoding="utf-8")
    document = tomllib.loads(text)

    forbidden_substrings = (
        "api_key",
        "apikey",
        "secret",
        "access_token",
        "auth_token",
        "bearer_token",
        "password",
        "credential",
    )

    def _walk(value: object, path: str) -> tuple[str, ...]:
        if not _is_dict(value):
            return ()
        table: dict[str, object] = {}
        for k, v in value.items():
            assert isinstance(k, str)
            table[k] = v
        violations: list[str] = []
        for key, child in table.items():
            child_path = f"{path}.{key}" if path else key
            if any(token in key.lower() for token in forbidden_substrings):
                violations.append(child_path)
            violations.extend(_walk(child, child_path))
        return tuple(violations)

    violations = _walk(document, "")
    assert not violations, (
        f"{config_path.name} contains forbidden secret-like keys: {', '.join(violations)}"
    )
    assert not violations, (
        f"{config_path.name} contains forbidden secret-like keys: {', '.join(violations)}"
    )


def test_minimal_example_overrides_only_default_chat() -> None:
    """The minimal example only overrides models.default_chat."""
    minimal = _repo_path("examples/config/minimal.toml")

    config = load_runtime_config(minimal, env={})

    assert config.models.default_chat.provider == "ollama"
    assert config.models.fast_judge.provider == "fake"
    assert config.models.reasoning.provider == "fake"


def test_local_ollama_example_configures_all_slots() -> None:
    """The local Ollama example configures all model slots and shared ollama."""
    local = _repo_path("examples/config/local-ollama.toml")

    config = load_runtime_config(local, env={})

    assert config.models.default_chat.model == "qwen3:8b"
    assert config.models.fast_judge.model == "qwen3:4b"
    assert config.models.reasoning.model == "deepseek-r1:8b"
    assert config.ollama.base_url == "http://localhost:11434"


def test_openai_example_uses_openai_provider() -> None:
    """The OpenAI example configures OpenAI for every model slot."""
    openai = _repo_path("examples/config/openai.toml")

    config = load_runtime_config(openai, env={})

    assert config.models.default_chat.provider == "openai"
    assert config.models.fast_judge.provider == "openai"
    assert config.models.reasoning.provider == "openai"


def test_local_ollama_example_enables_diagnostics() -> None:
    """The local Ollama example enables diagnostics with the documented defaults."""
    local = _repo_path("examples/config/local-ollama.toml")

    config = load_runtime_config(local, env={})

    assert config.diagnostics.mode == DiagnosticsMode.WARN
    assert_exact_eq(config.diagnostics.timeout_seconds, 5.0)
    assert config.diagnostics.warmup_models is False


def test_openai_example_enables_diagnostics() -> None:
    """The OpenAI example enables diagnostics with the documented defaults."""
    openai = _repo_path("examples/config/openai.toml")

    config = load_runtime_config(openai, env={})

    assert config.diagnostics.mode == DiagnosticsMode.WARN
    assert_exact_eq(config.diagnostics.timeout_seconds, 5.0)
    assert config.diagnostics.warmup_models is False


def test_minimal_example_enables_diagnostics() -> None:
    """The minimal example enables diagnostics with the default timeout."""
    minimal = _repo_path("examples/config/minimal.toml")

    config = load_runtime_config(minimal, env={})

    assert config.diagnostics.mode == DiagnosticsMode.WARN
    assert_exact_eq(config.diagnostics.timeout_seconds, 5.0)


# ---------------------------------------------------------------------------
# Precedence regression coverage
# ---------------------------------------------------------------------------


def test_env_overrides_toml_and_cli_overrides_env(tmp_path: Path) -> None:
    """Full precedence stack: defaults < TOML < env < CLI."""
    config_path = _write_config(
        tmp_path,
        """
        [models.default_chat]
        provider = "fake"
        model = "toml-model"
        temperature = 0.1

        [ollama]
        base_url = "http://toml-host:11434"
        """,
    )
    env = {
        "IRIS_DEFAULT_CHAT_PROVIDER": "ollama",
        "IRIS_DEFAULT_CHAT_MODEL": "env-model",
        "IRIS_OLLAMA_HOST": "http://env-host:11434",
    }

    config = load_runtime_config(
        config_path,
        env=env,
        overrides=RuntimeConfigOverrides(
            llm=LLMProvider.FAKE,
            model="cli-model",
            ollama_host="http://cli-host:11434",
        ),
    )

    assert config.models.default_chat.provider == "fake"
    assert config.models.default_chat.model == "cli-model"
    assert config.ollama.base_url == "http://cli-host:11434"
    assert config.models.default_chat.temperature == approx(0.1)


def test_partial_toml_keeps_unset_fields_at_defaults(tmp_path: Path) -> None:
    """A partial TOML only overrides the keys it declares."""
    config_path = _write_config(
        tmp_path,
        """
        [models.default_chat]
        provider = "ollama"
        """,
    )

    config = load_runtime_config(config_path, env={})

    assert config.models.default_chat.provider == "ollama"
    assert config.models.default_chat.model == "fake-llm"
    assert config.ollama.base_url == "http://localhost:11434"
    assert config.openai.model == "gpt-5-mini"


# ---------------------------------------------------------------------------
# Invalid input still raises ConfigError
# ---------------------------------------------------------------------------


def test_invalid_toml_section_type_raises_config_error(tmp_path: Path) -> None:
    """A non-table value where a table is required raises ConfigError."""
    config_path = _write_config(
        tmp_path,
        """
        models = "not-a-table"
        """,
    )

    with pytest.raises(ConfigError):
        load_runtime_config(config_path, env={})


def test_invalid_toml_field_type_raises_config_error(tmp_path: Path) -> None:
    """A wrong-typed TOML field raises ConfigError."""
    config_path = _write_config(
        tmp_path,
        """
        [models.default_chat]
        provider = "ollama"
        model = "x"
        temperature = "not-a-float"
        """,
    )

    with pytest.raises(ConfigError):
        load_runtime_config(config_path, env={})


def test_invalid_env_provider_raises_config_error() -> None:
    """An unknown provider in IRIS_DEFAULT_CHAT_PROVIDER raises ConfigError."""
    with pytest.raises(ConfigError):
        load_runtime_config(None, env={"IRIS_DEFAULT_CHAT_PROVIDER": "anthropic"})
