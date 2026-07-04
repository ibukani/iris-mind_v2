"""ランタイム設定メタデータの正規仕様。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from iris.contracts.llm import DEFAULT_FAKE_LLM_MODEL
from iris.contracts.model_policy import CascadeFallbackBehavior, ModelCallSite
from iris.runtime.config.errors import ConfigError
from iris.runtime.config.model_slots import model_slot_specs
from iris.runtime.config.prompt_budget import (
    default_prompt_budget_config,
    iter_profile_sections,
    prompt_overflow_behavior_values,
    prompt_profile_names,
)

if TYPE_CHECKING:
    from iris.contracts.prompting import PromptProfileName, PromptSectionKind
    from iris.runtime.config.prompt_budget import (
        RuntimePromptProfileBudget,
        RuntimePromptSectionBudget,
    )


class ConfigValueType(StrEnum):
    """設定値の型。"""

    STR = "str"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    ENUM = "enum"
    OPTIONAL_STR = "optional_str"
    OPTIONAL_INT = "optional_int"
    OPTIONAL_FLOAT = "optional_float"


type ConfigDefault = str | int | float | bool | None

RUNTIME_CONFIG_VERSION = 2


@dataclass(frozen=True)
class ConfigFieldSpec:
    """1つのランタイム設定フィールドの機械可読メタデータ。"""

    path: str
    value_type: ConfigValueType
    default: ConfigDefault
    description: str
    toml: bool = True
    env: str | None = None
    cli: str | None = None
    secret: bool = False
    control_plane_editable: bool = True
    example: bool = True
    allowed_values: tuple[str, ...] = ()
    deprecated: bool = False


_RATE_LIMIT_RESERVED_DESC = (
    "予約済み: 現在の DeliverySafetyGate では未使用。"
    "プロアクティブ送信頻度は scheduler.min_interval_per_target_seconds で制御する。"
)


def _latency_budget_specs() -> tuple[ConfigFieldSpec, ...]:
    """Runtime latency budget の ConfigSpec 群を返す。

    Returns:
        observability.latency_budget 配下の設定仕様。
    """
    return (
        ConfigFieldSpec(
            "observability.latency_budget.enabled",
            ConfigValueType.BOOL,
            default=True,
            description="Runtime response latency event を有効化する。",
        ),
        ConfigFieldSpec(
            "observability.latency_budget.slow_warning_enabled",
            ConfigValueType.BOOL,
            default=True,
            description="Latency budget 超過時の slow warning event を有効化する。",
        ),
        ConfigFieldSpec(
            "observability.latency_budget.handle_observation_ms",
            ConfigValueType.FLOAT,
            3000.0,
            "handle_observation 全体の latency budget ミリ秒。",
        ),
        ConfigFieldSpec(
            "observability.latency_budget.observation_integration_ms",
            ConfigValueType.FLOAT,
            50.0,
            "Observation integration の latency budget ミリ秒。",
        ),
        ConfigFieldSpec(
            "observability.latency_budget.workspace_context_assembly_ms",
            ConfigValueType.FLOAT,
            100.0,
            "Workspace context assembly の latency budget ミリ秒。",
        ),
        ConfigFieldSpec(
            "observability.latency_budget.conversation_context_load_ms",
            ConfigValueType.FLOAT,
            100.0,
            "Conversation context load の latency budget ミリ秒。",
        ),
        ConfigFieldSpec(
            "observability.latency_budget.cognitive_processing_ms",
            ConfigValueType.FLOAT,
            2500.0,
            "Cognitive processing の latency budget ミリ秒。",
        ),
        ConfigFieldSpec(
            "observability.latency_budget.llm_generate_ms",
            ConfigValueType.FLOAT,
            2200.0,
            "LLM generate call の latency budget ミリ秒。",
        ),
        ConfigFieldSpec(
            "observability.latency_budget.conversation_record_ms",
            ConfigValueType.FLOAT,
            100.0,
            "Conversation record の latency budget ミリ秒。",
        ),
        ConfigFieldSpec(
            "observability.latency_budget.transcript_append_ms",
            ConfigValueType.FLOAT,
            100.0,
            "Transcript append の latency budget ミリ秒。",
        ),
        ConfigFieldSpec(
            "observability.latency_budget.runtime_learning_hook_ms",
            ConfigValueType.FLOAT,
            200.0,
            "Runtime learning hook の latency budget ミリ秒。",
        ),
        ConfigFieldSpec(
            "observability.latency_budget.background_enqueue_ms",
            ConfigValueType.FLOAT,
            100.0,
            "Background job enqueue の latency budget ミリ秒。",
        ),
        ConfigFieldSpec(
            "observability.latency_budget.classifier_call_ms",
            ConfigValueType.FLOAT,
            50.0,
            "Classifier call の latency budget ミリ秒。",
        ),
        ConfigFieldSpec(
            "observability.latency_budget.embedding_call_ms",
            ConfigValueType.FLOAT,
            150.0,
            "Embedding call の latency budget ミリ秒。",
        ),
        ConfigFieldSpec(
            "observability.latency_budget.reranker_call_ms",
            ConfigValueType.FLOAT,
            100.0,
            "Reranker call の latency budget ミリ秒。",
        ),
    )


@dataclass(frozen=True)
class _ModelCallBudgetSpecDefaults:
    """ConfigSpec 生成用の model call budget default 群。"""

    site: ModelCallSite
    large_llm_max_calls: int
    small_classifier_max_calls: int
    embedding_max_calls: int
    reranker_max_calls: int
    background_llm_max_calls: int
    confidence_threshold: float
    low_confidence_fallback: str
    high_risk_escalation_allowed: bool
    uncertain_escalation_allowed: bool
    enqueue_only: bool


_MODEL_CALL_BUDGET_DEFAULTS: tuple[_ModelCallBudgetSpecDefaults, ...] = (
    _ModelCallBudgetSpecDefaults(
        site=ModelCallSite.USER_RESPONSE_HOT_PATH,
        large_llm_max_calls=1,
        small_classifier_max_calls=1,
        embedding_max_calls=1,
        reranker_max_calls=1,
        background_llm_max_calls=0,
        confidence_threshold=0.65,
        low_confidence_fallback=CascadeFallbackBehavior.DETERMINISTIC_BASELINE.value,
        high_risk_escalation_allowed=True,
        uncertain_escalation_allowed=True,
        enqueue_only=False,
    ),
    _ModelCallBudgetSpecDefaults(
        site=ModelCallSite.PROACTIVE,
        large_llm_max_calls=1,
        small_classifier_max_calls=1,
        embedding_max_calls=1,
        reranker_max_calls=0,
        background_llm_max_calls=1,
        confidence_threshold=0.65,
        low_confidence_fallback=CascadeFallbackBehavior.DEFER.value,
        high_risk_escalation_allowed=True,
        uncertain_escalation_allowed=True,
        enqueue_only=False,
    ),
    _ModelCallBudgetSpecDefaults(
        site=ModelCallSite.MEMORY_EXTRACTION,
        large_llm_max_calls=0,
        small_classifier_max_calls=1,
        embedding_max_calls=1,
        reranker_max_calls=0,
        background_llm_max_calls=1,
        confidence_threshold=0.65,
        low_confidence_fallback=CascadeFallbackBehavior.ENQUEUE_BACKGROUND.value,
        high_risk_escalation_allowed=False,
        uncertain_escalation_allowed=False,
        enqueue_only=False,
    ),
    _ModelCallBudgetSpecDefaults(
        site=ModelCallSite.REFLECTION,
        large_llm_max_calls=0,
        small_classifier_max_calls=0,
        embedding_max_calls=1,
        reranker_max_calls=0,
        background_llm_max_calls=1,
        confidence_threshold=0.65,
        low_confidence_fallback=CascadeFallbackBehavior.DEFER.value,
        high_risk_escalation_allowed=False,
        uncertain_escalation_allowed=False,
        enqueue_only=False,
    ),
    _ModelCallBudgetSpecDefaults(
        site=ModelCallSite.RELATIONSHIP_UPDATE,
        large_llm_max_calls=0,
        small_classifier_max_calls=1,
        embedding_max_calls=1,
        reranker_max_calls=0,
        background_llm_max_calls=1,
        confidence_threshold=0.65,
        low_confidence_fallback=CascadeFallbackBehavior.NO_OP.value,
        high_risk_escalation_allowed=False,
        uncertain_escalation_allowed=False,
        enqueue_only=False,
    ),
    _ModelCallBudgetSpecDefaults(
        site=ModelCallSite.INTERACTION_POLICY_CANDIDATE,
        large_llm_max_calls=0,
        small_classifier_max_calls=1,
        embedding_max_calls=1,
        reranker_max_calls=1,
        background_llm_max_calls=1,
        confidence_threshold=0.65,
        low_confidence_fallback=CascadeFallbackBehavior.REJECT.value,
        high_risk_escalation_allowed=False,
        uncertain_escalation_allowed=False,
        enqueue_only=False,
    ),
    _ModelCallBudgetSpecDefaults(
        site=ModelCallSite.RUNTIME_LEARNING_HOOK,
        large_llm_max_calls=0,
        small_classifier_max_calls=0,
        embedding_max_calls=0,
        reranker_max_calls=0,
        background_llm_max_calls=1,
        confidence_threshold=0.65,
        low_confidence_fallback=CascadeFallbackBehavior.ENQUEUE_BACKGROUND.value,
        high_risk_escalation_allowed=False,
        uncertain_escalation_allowed=False,
        enqueue_only=True,
    ),
)


def _prompt_budget_specs() -> tuple[ConfigFieldSpec, ...]:
    """Prompt budget の ConfigSpec 群を返す。

    Returns:
        prompt_budget 配下の設定仕様。
    """
    defaults = default_prompt_budget_config()
    return (
        ConfigFieldSpec(
            "prompt_budget.enabled",
            ConfigValueType.BOOL,
            default=defaults.enabled,
            description="Prompt section budget と deterministic overflow policy を有効化する。",
        ),
        ConfigFieldSpec(
            "prompt_budget.chat_profile",
            ConfigValueType.ENUM,
            default=defaults.chat_profile.value,
            description="通常 chat response generation で使う prompt budget profile。",
            allowed_values=tuple(profile.value for profile in prompt_profile_names()),
        ),
        ConfigFieldSpec(
            "prompt_budget.proactive_profile",
            ConfigValueType.ENUM,
            default=defaults.proactive_profile.value,
            description="proactive text generation で使う短い prompt budget profile。",
            allowed_values=tuple(profile.value for profile in prompt_profile_names()),
        ),
        *tuple(
            spec
            for profile_name in prompt_profile_names()
            for spec in _prompt_profile_specs(profile_name, defaults.profile_budget(profile_name))
        ),
    )


def _prompt_profile_specs(
    profile_name: PromptProfileName,
    profile: RuntimePromptProfileBudget,
) -> tuple[ConfigFieldSpec, ...]:
    prefix = f"prompt_budget.{profile_name.value}"
    return (
        ConfigFieldSpec(
            f"{prefix}.total_max_chars",
            ConfigValueType.INT,
            profile.total_max_chars,
            f"{profile_name.value} profile の prompt 全体最大文字数。",
        ),
        *tuple(
            spec
            for section, budget in iter_profile_sections(profile)
            for spec in _prompt_section_specs(profile_name, section, budget)
        ),
    )


def _prompt_section_specs(
    profile_name: PromptProfileName,
    section: PromptSectionKind,
    budget: RuntimePromptSectionBudget,
) -> tuple[ConfigFieldSpec, ...]:
    prefix = f"prompt_budget.{profile_name.value}.{section.value}"
    label = f"{profile_name.value}.{section.value}"
    return (
        ConfigFieldSpec(
            f"{prefix}.max_chars",
            ConfigValueType.INT,
            budget.max_chars,
            f"{label} section の最大文字数。",
        ),
        ConfigFieldSpec(
            f"{prefix}.max_items",
            ConfigValueType.INT,
            budget.max_items,
            f"{label} section の最大 item 数。",
        ),
        ConfigFieldSpec(
            f"{prefix}.priority",
            ConfigValueType.INT,
            budget.priority,
            f"{label} section の total overflow 時優先度。",
        ),
        ConfigFieldSpec(
            f"{prefix}.overflow_behavior",
            ConfigValueType.ENUM,
            budget.overflow_behavior.value,
            f"{label} section の overflow 挙動。",
            allowed_values=prompt_overflow_behavior_values(),
        ),
    )


def _inference_scheduler_specs() -> tuple[ConfigFieldSpec, ...]:
    """Local inference resource scheduler の ConfigSpec 群を返す。

    Returns:
        inference_scheduler 配下の設定仕様。
    """
    return (
        ConfigFieldSpec(
            "inference_scheduler.enabled",
            ConfigValueType.BOOL,
            default=False,
            description="ローカル推論資源 scheduler boundary を有効化する。",
        ),
        ConfigFieldSpec(
            "inference_scheduler.large_llm_concurrency_limit",
            ConfigValueType.INT,
            1,
            "large LLM / background LLM の同時実行上限。現在は 1 のみ許可する。",
        ),
        ConfigFieldSpec(
            "inference_scheduler.small_classifier_concurrency_limit",
            ConfigValueType.INT,
            4,
            "small classifier 用の別枠同時実行上限。",
        ),
        ConfigFieldSpec(
            "inference_scheduler.embedding_concurrency_limit",
            ConfigValueType.INT,
            2,
            "embedding 用の別枠同時実行上限。",
        ),
        ConfigFieldSpec(
            "inference_scheduler.reranker_concurrency_limit",
            ConfigValueType.INT,
            2,
            "reranker 用の別枠同時実行上限。",
        ),
        ConfigFieldSpec(
            "inference_scheduler.preempt_background_for_user_facing",
            ConfigValueType.BOOL,
            default=True,
            description=(
                "user-facing request 到着時に低優先度 large LLM lease を cooperative cancel する。"
            ),
        ),
        ConfigFieldSpec(
            "inference_scheduler.background_when_busy",
            ConfigValueType.ENUM,
            "defer",
            "busy 時の background LLM job の挙動。",
            allowed_values=("defer", "cancel", "no_send"),
        ),
        ConfigFieldSpec(
            "inference_scheduler.proactive_when_busy",
            ConfigValueType.ENUM,
            "no_send",
            "busy 時の proactive generation の挙動。",
            allowed_values=("defer", "cancel", "no_send"),
        ),
        ConfigFieldSpec(
            "inference_scheduler.low_priority_when_warming",
            ConfigValueType.ENUM,
            "defer",
            "warming 時の低優先度 work の挙動。",
            allowed_values=("defer", "cancel", "no_send"),
        ),
        ConfigFieldSpec(
            "inference_scheduler.background_when_unavailable",
            ConfigValueType.ENUM,
            "cancel",
            "unavailable 時の background LLM job の挙動。",
            allowed_values=("defer", "cancel", "no_send", "denied"),
        ),
        ConfigFieldSpec(
            "inference_scheduler.proactive_when_unavailable",
            ConfigValueType.ENUM,
            "no_send",
            "unavailable 時の proactive generation の挙動。",
            allowed_values=("defer", "cancel", "no_send", "denied"),
        ),
        ConfigFieldSpec(
            "inference_scheduler.user_facing_when_unavailable",
            ConfigValueType.ENUM,
            "denied",
            "unavailable 時の user-facing generation の挙動。",
            allowed_values=("defer", "cancel", "no_send", "denied"),
        ),
    )


def _model_call_budget_specs() -> tuple[ConfigFieldSpec, ...]:
    """Feature 別 model call budget の ConfigSpec 群を返す。

    Returns:
        tuple[ConfigFieldSpec, ...]: model_call_budget 配下の設定仕様。
    """
    return (
        ConfigFieldSpec(
            "model_call_budget.enabled",
            ConfigValueType.BOOL,
            default=True,
            description="Feature 別 model call budget と cascade policy を有効化する。",
        ),
        *tuple(
            spec
            for defaults in _MODEL_CALL_BUDGET_DEFAULTS
            for spec in _feature_model_call_budget_specs(defaults)
        ),
    )


def _feature_model_call_budget_specs(
    defaults: _ModelCallBudgetSpecDefaults,
) -> tuple[ConfigFieldSpec, ...]:
    """単一 call site の model call budget 設定仕様を返す。

    Returns:
        tuple[ConfigFieldSpec, ...]: call site ごとの budget 設定仕様。
    """
    prefix = f"model_call_budget.{defaults.site.value}"
    label = defaults.site.value
    return (
        ConfigFieldSpec(
            f"{prefix}.large_llm_max_calls",
            ConfigValueType.INT,
            defaults.large_llm_max_calls,
            f"{label} で許可する large LLM 最大呼び出し数。",
        ),
        ConfigFieldSpec(
            f"{prefix}.small_classifier_max_calls",
            ConfigValueType.INT,
            defaults.small_classifier_max_calls,
            f"{label} で許可する small classifier 最大呼び出し数。",
        ),
        ConfigFieldSpec(
            f"{prefix}.embedding_max_calls",
            ConfigValueType.INT,
            defaults.embedding_max_calls,
            f"{label} で許可する embedding 最大呼び出し数。",
        ),
        ConfigFieldSpec(
            f"{prefix}.reranker_max_calls",
            ConfigValueType.INT,
            defaults.reranker_max_calls,
            f"{label} で許可する reranker 最大呼び出し数。",
        ),
        ConfigFieldSpec(
            f"{prefix}.background_llm_max_calls",
            ConfigValueType.INT,
            defaults.background_llm_max_calls,
            f"{label} で許可する background LLM job 最大呼び出し数。",
        ),
        ConfigFieldSpec(
            f"{prefix}.confidence_threshold",
            ConfigValueType.FLOAT,
            defaults.confidence_threshold,
            f"{label} で low-confidence fallback を開始する信頼度閾値。",
        ),
        ConfigFieldSpec(
            f"{prefix}.low_confidence_fallback",
            ConfigValueType.ENUM,
            defaults.low_confidence_fallback,
            f"{label} の low-confidence / budget exceeded fallback 挙動。",
            allowed_values=tuple(item.value for item in CascadeFallbackBehavior),
        ),
        ConfigFieldSpec(
            f"{prefix}.high_risk_escalation_allowed",
            ConfigValueType.BOOL,
            defaults.high_risk_escalation_allowed,
            f"{label} で high-risk 低信頼時の上位モデル escalation を許可する。",
        ),
        ConfigFieldSpec(
            f"{prefix}.uncertain_escalation_allowed",
            ConfigValueType.BOOL,
            defaults.uncertain_escalation_allowed,
            f"{label} で uncertain 低信頼時の上位モデル escalation を許可する。",
        ),
        ConfigFieldSpec(
            f"{prefix}.enqueue_only",
            ConfigValueType.BOOL,
            defaults.enqueue_only,
            f"{label} を同期 model call 禁止の enqueue-only 経路として扱う。",
        ),
    )


def runtime_config_specs() -> tuple[ConfigFieldSpec, ...]:
    """全ユーザー向けランタイム設定フィールドの正規仕様を返す。

    Returns:
        安定順序の設定フィールド仕様。
    """
    model_specs = tuple(
        spec
        for slot in model_slot_specs()
        for spec in (
            ConfigFieldSpec(
                f"models.{slot.name}.provider",
                ConfigValueType.ENUM,
                "fake",
                f"{slot.name}モデルスロットのプロバイダ。",
                env=f"IRIS_{slot.name.upper()}_PROVIDER",
                allowed_values=("fake", "ollama", "openai"),
            ),
            ConfigFieldSpec(
                f"models.{slot.name}.model",
                ConfigValueType.STR,
                DEFAULT_FAKE_LLM_MODEL,
                f"{slot.name}モデルスロットのモデル名。",
                env=f"IRIS_{slot.name.upper()}_MODEL",
            ),
            ConfigFieldSpec(
                f"models.{slot.name}.temperature",
                ConfigValueType.FLOAT,
                0.0,
                f"{slot.name}モデルスロットのtemperature。",
                env=f"IRIS_{slot.name.upper()}_TEMPERATURE",
            ),
            ConfigFieldSpec(
                f"models.{slot.name}.max_output_tokens",
                ConfigValueType.OPTIONAL_INT,
                slot.default_max_output_tokens,
                f"{slot.name}モデルスロットの最大出力トークン数。",
                env=f"IRIS_{slot.name.upper()}_MAX_OUTPUT_TOKENS",
            ),
        )
    )
    return (
        ConfigFieldSpec(
            "config.version",
            ConfigValueType.INT,
            2,
            "ランタイム設定ファイル形式のバージョン。",
            control_plane_editable=False,
        ),
        ConfigFieldSpec(
            "server.host",
            ConfigValueType.STR,
            "127.0.0.1",
            "gRPCサーバーのbind host。",
            env="IRIS_SERVER_HOST",
            cli="--host",
        ),
        ConfigFieldSpec(
            "server.port",
            ConfigValueType.INT,
            50051,
            "gRPCサーバーのbind port。",
            env="IRIS_SERVER_PORT",
            cli="--port",
        ),
        ConfigFieldSpec(
            path="server.local_only",
            value_type=ConfigValueType.BOOL,
            default=True,
            description="loopback hostのみを許可する。",
        ),
        ConfigFieldSpec(
            "server.shutdown_grace_seconds",
            ConfigValueType.FLOAT,
            5.0,
            "gRPCサーバー停止時の猶予秒数。",
        ),
        ConfigFieldSpec(
            "learning.enabled",
            ConfigValueType.BOOL,
            default=True,
            description="配送結果後の学習 dispatch を有効化する。",
        ),
        ConfigFieldSpec(
            "learning.background_jobs_enabled",
            ConfigValueType.BOOL,
            default=True,
            description="バックグラウンドジョブループを有効化する。",
        ),
        ConfigFieldSpec(
            "learning.background_job_interval_seconds",
            ConfigValueType.FLOAT,
            10.0,
            "バックグラウンドジョブ実行間隔秒数。",
        ),
        ConfigFieldSpec(
            "learning.max_jobs_per_run",
            ConfigValueType.INT,
            5,
            "1回のバックグラウンド処理上限件数。",
        ),
        ConfigFieldSpec(
            "learning.max_attempts",
            ConfigValueType.INT,
            3,
            "学習ジョブの既定最大試行回数。",
        ),
        ConfigFieldSpec(
            path="learning.implicit_candidates_enabled",
            value_type=ConfigValueType.BOOL,
            default=True,
            description="Runtime outcome から implicit memory candidate を候補化する。",
        ),
        ConfigFieldSpec(
            "learning.implicit_candidate_min_confidence",
            ConfigValueType.FLOAT,
            0.35,
            "Review store に入れる implicit candidate の最小 confidence。",
        ),
        ConfigFieldSpec(
            "learning.implicit_candidate_max_text_length",
            ConfigValueType.INT,
            1000,
            "Review store に入れる implicit candidate の最大文字数。",
        ),
        ConfigFieldSpec(
            "learning.background_job_policy.enabled",
            ConfigValueType.BOOL,
            default=False,
            description=(
                "BackgroundJobQueue の metrics / backpressure policy を明示的に有効化する。"
            ),
        ),
        ConfigFieldSpec(
            "learning.background_job_policy.default_concurrency_limit",
            ConfigValueType.INT,
            1,
            "background job kind ごとの既定同時 lease 上限。",
        ),
        ConfigFieldSpec(
            "learning.background_job_policy.default_timeout_seconds",
            ConfigValueType.FLOAT,
            30.0,
            "background job worker の既定 soft timeout 秒数。",
        ),
        ConfigFieldSpec(
            "learning.background_job_policy.default_max_pending_jobs",
            ConfigValueType.INT,
            100,
            "kind ごとの既定 pending job 上限。",
        ),
        ConfigFieldSpec(
            "learning.background_job_policy.retry_backoff_base_seconds",
            ConfigValueType.FLOAT,
            30.0,
            "retry storm を避ける指数 backoff の基準秒数。",
        ),
        ConfigFieldSpec(
            "learning.background_job_policy.retry_backoff_max_seconds",
            ConfigValueType.FLOAT,
            1800.0,
            "retry storm を避ける指数 backoff の最大秒数。",
        ),
        ConfigFieldSpec(
            "learning.background_job_policy.defer_seconds_when_saturated",
            ConfigValueType.FLOAT,
            30.0,
            "backpressure で defer するときの not_before 延長秒数。",
        ),
        ConfigFieldSpec(
            "learning.background_job_policy.backpressure_mode",
            ConfigValueType.ENUM,
            "defer",
            "kind pressure 発生時の既定 enqueue 方針。",
            allowed_values=("accept", "defer", "reject"),
        ),
        ConfigFieldSpec(
            "learning.background_job_policy.kinds.memory_extraction.concurrency_limit",
            ConfigValueType.INT,
            1,
            "memory_extraction job の同時 lease 上限。",
        ),
        ConfigFieldSpec(
            "learning.background_job_policy.kinds.memory_extraction.timeout_seconds",
            ConfigValueType.FLOAT,
            30.0,
            "memory_extraction job worker の soft timeout 秒数。",
        ),
        ConfigFieldSpec(
            "learning.background_job_policy.kinds.memory_extraction.max_pending_jobs",
            ConfigValueType.INT,
            100,
            "memory_extraction job の pending 上限。",
        ),
        ConfigFieldSpec(
            "learning.background_job_policy.kinds.memory_extraction.uses_llm",
            ConfigValueType.BOOL,
            default=True,
            description="memory_extraction job が LLM 資源を使う可能性を示す。",
        ),
        ConfigFieldSpec(
            "learning.background_job_policy.kinds.memory_extraction.idle_only",
            ConfigValueType.BOOL,
            default=False,
            description="memory_extraction job を idle 時だけ enqueue する。",
        ),
        ConfigFieldSpec(
            "learning.background_job_policy.kinds.reflection.concurrency_limit",
            ConfigValueType.INT,
            1,
            "reflection job の同時 lease 上限。",
        ),
        ConfigFieldSpec(
            "learning.background_job_policy.kinds.reflection.timeout_seconds",
            ConfigValueType.FLOAT,
            60.0,
            "reflection job worker の soft timeout 秒数。",
        ),
        ConfigFieldSpec(
            "learning.background_job_policy.kinds.reflection.max_pending_jobs",
            ConfigValueType.INT,
            50,
            "reflection job の pending 上限。",
        ),
        ConfigFieldSpec(
            "learning.background_job_policy.kinds.reflection.uses_llm",
            ConfigValueType.BOOL,
            default=True,
            description="reflection job が LLM 資源を使う可能性を示す。",
        ),
        ConfigFieldSpec(
            "learning.background_job_policy.kinds.reflection.idle_only",
            ConfigValueType.BOOL,
            default=True,
            description="reflection job を idle 時だけ enqueue する。",
        ),
        *_inference_scheduler_specs(),
        *_model_call_budget_specs(),
        *_prompt_budget_specs(),
        ConfigFieldSpec(
            "server.tls.enabled",
            ConfigValueType.BOOL,
            default=False,
            description="gRPC server TLS を有効化する。",
        ),
        ConfigFieldSpec(
            "server.tls.cert_chain_path",
            ConfigValueType.OPTIONAL_STR,
            None,
            "TLS certificate chain path。",
        ),
        ConfigFieldSpec(
            "server.tls.private_key_path",
            ConfigValueType.OPTIONAL_STR,
            None,
            "TLS private key path。",
            secret=True,
            control_plane_editable=False,
            example=False,
        ),
        ConfigFieldSpec(
            "server.tls.client_ca_path",
            ConfigValueType.OPTIONAL_STR,
            None,
            "Optional mTLS client CA path。",
        ),
        ConfigFieldSpec(
            "server.tls.require_client_cert",
            ConfigValueType.BOOL,
            default=False,
            description="gRPC TLS client certificate を要求する。",
        ),
        ConfigFieldSpec(
            "auth.mode",
            ConfigValueType.ENUM,
            "local_dev",
            "Runtime RPC auth mode。",
            env="IRIS_RUNTIME_AUTH_MODE",
            allowed_values=("local_dev", "required"),
        ),
        ConfigFieldSpec(
            "auth.allow_unauthenticated_loopback",
            ConfigValueType.BOOL,
            default=True,
            description="local_dev loopback の unauthenticated RPC を許可する。",
        ),
        ConfigFieldSpec(
            "auth.require_tls_for_remote",
            ConfigValueType.BOOL,
            default=True,
            description="(非推奨) remote bind では TLS が常に要求されます。",
            control_plane_editable=False,
        ),
        ConfigFieldSpec(
            "auth.allow_insecure_remote",
            ConfigValueType.BOOL,
            default=False,
            description="開発用に remote insecure bind を明示許可する。",
            control_plane_editable=False,
        ),
        ConfigFieldSpec(
            "auth.static_tokens_env",
            ConfigValueType.STR,
            "IRIS_RUNTIME_TOKENS",
            "Static bearer token hashes を読む環境変数名。",
            secret=True,
            control_plane_editable=False,
            example=False,
        ),
        ConfigFieldSpec(
            "state.backend",
            ConfigValueType.ENUM,
            "memory",
            "ランタイム状態の永続化backend。",
            env="IRIS_STATE_BACKEND",
            allowed_values=("memory", "sqlite"),
        ),
        ConfigFieldSpec(
            "state.sqlite_path",
            ConfigValueType.STR,
            ".iris/runtime/state.sqlite3",
            "SQLite状態ファイルのパス。",
            env="IRIS_STATE_SQLITE_PATH",
        ),
        ConfigFieldSpec(
            "memory.vector.enabled",
            ConfigValueType.BOOL,
            default=False,
            description="SQLite memory の hybrid vector retrieval を有効化する。",
        ),
        ConfigFieldSpec(
            "memory.vector.backend",
            ConfigValueType.ENUM,
            "in_memory",
            "派生 vector index backend。",
            allowed_values=("in_memory", "qdrant"),
        ),
        ConfigFieldSpec(
            "memory.vector.collection",
            ConfigValueType.STR,
            "iris_memory",
            "vector index collection 名。",
        ),
        ConfigFieldSpec(
            "memory.vector.rebuild_on_startup",
            ConfigValueType.BOOL,
            default=True,
            description="起動時に正本 MemoryStore から index を同期する。",
        ),
        ConfigFieldSpec(
            "memory.vector.fail_open_on_index_error",
            ConfigValueType.BOOL,
            default=True,
            description="index 障害時も canonical memory write を保持する。",
        ),
        ConfigFieldSpec(
            "memory.embedding.provider",
            ConfigValueType.ENUM,
            "fake",
            "memory embedding provider。",
            allowed_values=("fake",),
        ),
        ConfigFieldSpec(
            "memory.embedding.model",
            ConfigValueType.STR,
            "fake-v1",
            "embedding model 識別子。",
        ),
        ConfigFieldSpec(
            "memory.embedding.dimension",
            ConfigValueType.INT,
            32,
            "embedding vector 次元数。",
        ),
        ConfigFieldSpec(
            "memory.embedding.batch_size",
            ConfigValueType.INT,
            32,
            "rebuild 時の embedding batch size。",
        ),
        ConfigFieldSpec(
            "memory.vector.qdrant.url",
            ConfigValueType.STR,
            "http://localhost:6333",
            "Qdrant REST endpoint。",
        ),
        ConfigFieldSpec(
            "memory.vector.qdrant.api_key_env",
            ConfigValueType.OPTIONAL_STR,
            None,
            "Qdrant API key を読む環境変数名。",
            example=False,
        ),
        ConfigFieldSpec(
            "memory.vector.qdrant.prefer_grpc",
            ConfigValueType.BOOL,
            default=False,
            description="Qdrant gRPC transport 選択予約。現在は REST のみ。",
        ),
        ConfigFieldSpec(
            "scheduler.enabled",
            ConfigValueType.BOOL,
            default=False,
            description="RuntimeScheduler lifecycle loop を有効化する。",
        ),
        ConfigFieldSpec(
            "scheduler.interval_seconds",
            ConfigValueType.FLOAT,
            30.0,
            "scheduler loop の実行間隔秒数。",
        ),
        ConfigFieldSpec(
            "scheduler.idle_threshold_seconds",
            ConfigValueType.FLOAT,
            600.0,
            "IdleTickObservation を発火する idle 秒数。",
        ),
        ConfigFieldSpec(
            "scheduler.min_interval_per_target_seconds",
            ConfigValueType.FLOAT,
            1800.0,
            "target ごとの proactive tick 最小間隔秒数。",
        ),
        ConfigFieldSpec(
            "scheduler.target_stale_after_seconds",
            ConfigValueType.FLOAT,
            604800.0,
            "target が stale になるまでの idle 秒数 (デフォルト7日)。",
            env="IRIS_SCHEDULER_TARGET_STALE_AFTER_SECONDS",
        ),
        ConfigFieldSpec(
            "scheduler.max_due_per_run",
            ConfigValueType.INT,
            10,
            "scheduler run 1回あたりの最大 due observation 数。",
        ),
        ConfigFieldSpec(
            "conversation.max_window_records",
            ConfigValueType.INT,
            20,
            "LLMへ渡す短期会話windowの最大record数。",
        ),
        ConfigFieldSpec(
            "conversation.max_history_chars",
            ConfigValueType.INT,
            8000,
            "LLMへ渡す短期会話windowの最大文字数。0なら過去会話を渡さない。",
        ),
        ConfigFieldSpec(
            "conversation.summary_enabled",
            ConfigValueType.BOOL,
            default=True,
            description="長期会話windowの古いturnをsummary contextへ畳む。",
        ),
        ConfigFieldSpec(
            "conversation.summary_max_chars",
            ConfigValueType.INT,
            1600,
            "会話summary contextの最大文字数。0ならsummaryを渡さない。",
        ),
        ConfigFieldSpec(
            "conversation.summary_min_records",
            ConfigValueType.INT,
            12,
            "summary生成を検討する最小record数。",
        ),
        ConfigFieldSpec(
            "conversation.transcript.enabled",
            ConfigValueType.BOOL,
            default=False,
            description=(
                "confirmed conversation transcript の永続保存を有効化する。"
                "true は state.backend=sqlite を要求する。"
            ),
        ),
        ConfigFieldSpec(
            "conversation.transcript.retention_days",
            ConfigValueType.INT,
            30,
            "transcript record の保持日数。0なら期限なし。",
        ),
        ConfigFieldSpec(
            "conversation.transcript.max_records_per_key",
            ConfigValueType.INT,
            1000,
            "conversation keyごとのtranscript保持上限。",
        ),
        ConfigFieldSpec(
            "delivery.enabled",
            ConfigValueType.BOOL,
            default=True,
            description="DeliveryOutbox と PollAppActions API を有効化する。",
        ),
        ConfigFieldSpec(
            "delivery.max_outbox_depth_per_provider",
            ConfigValueType.INT,
            100,
            "provider ごとの最大 outbox depth。",
        ),
        ConfigFieldSpec(
            "delivery.lease_seconds",
            ConfigValueType.FLOAT,
            30.0,
            "PollAppActions が取得する lease 秒数。",
        ),
        ConfigFieldSpec(
            "delivery.max_attempts",
            ConfigValueType.INT,
            3,
            "配送 item ごとの最大試行回数。",
        ),
        ConfigFieldSpec(
            "delivery.retry_backoff_seconds",
            ConfigValueType.FLOAT,
            30.0,
            "失敗後に retry 可能になるまでの秒数。",
        ),
        ConfigFieldSpec(
            "delivery.rate_limit_window_seconds",
            ConfigValueType.FLOAT,
            1800.0,
            _RATE_LIMIT_RESERVED_DESC,
        ),
        ConfigFieldSpec(
            "delivery.quiet_hours.enabled",
            ConfigValueType.BOOL,
            default=False,
            description="quiet hours による配送 block を有効化する。",
        ),
        ConfigFieldSpec(
            "delivery.quiet_hours.start",
            ConfigValueType.STR,
            "22:00",
            "quiet hours 開始 HH:MM。",
        ),
        ConfigFieldSpec(
            "delivery.quiet_hours.end",
            ConfigValueType.STR,
            "08:00",
            "quiet hours 終了 HH:MM。",
        ),
        ConfigFieldSpec(
            "delivery.quiet_hours.timezone",
            ConfigValueType.STR,
            "Asia/Tokyo",
            "quiet hours 判定 timezone。",
        ),
        *model_specs,
        ConfigFieldSpec(
            "ollama.base_url",
            ConfigValueType.STR,
            "http://localhost:11434",
            "Ollama APIのbase URL。",
            env="IRIS_OLLAMA_HOST",
        ),
        ConfigFieldSpec(
            "ollama.timeout_seconds",
            ConfigValueType.FLOAT,
            120.0,
            "Ollama request timeout秒数。",
            env="IRIS_OLLAMA_TIMEOUT_SECONDS",
        ),
        ConfigFieldSpec(
            "ollama.keep_alive",
            ConfigValueType.OPTIONAL_STR,
            None,
            "Ollamaモデルのkeep-alive指定。",
            env="IRIS_OLLAMA_KEEP_ALIVE",
        ),
        ConfigFieldSpec(
            "ollama.warmup_prompt",
            ConfigValueType.OPTIONAL_STR,
            None,
            "Ollama warmup 時に送る任意 prompt。未設定なら load-only request。",
            env="IRIS_OLLAMA_WARMUP_PROMPT",
        ),
        ConfigFieldSpec(
            "ollama.think",
            ConfigValueType.OPTIONAL_STR,
            default=False,
            description="Ollamaの推論思考設定 (true/false/low/highなど)。",
            env="IRIS_OLLAMA_THINK",
        ),
        ConfigFieldSpec(
            "openai.model",
            ConfigValueType.STR,
            "gpt-5-mini",
            "OpenAI providerの既定モデル。",
            env="IRIS_OPENAI_MODEL",
        ),
        ConfigFieldSpec(
            "openai.timeout_seconds",
            ConfigValueType.OPTIONAL_FLOAT,
            None,
            "OpenAI request timeout秒数。",
            env="IRIS_OPENAI_TIMEOUT_SECONDS",
        ),
        ConfigFieldSpec(
            "openai.max_output_tokens",
            ConfigValueType.OPTIONAL_INT,
            None,
            "OpenAI providerの最大出力トークン数。",
            env="IRIS_OPENAI_MAX_OUTPUT_TOKENS",
        ),
        ConfigFieldSpec(
            "logging.level",
            ConfigValueType.ENUM,
            "INFO",
            "ランタイムログレベル。",
            env="IRIS_LOG_LEVEL",
            allowed_values=("TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        ),
        ConfigFieldSpec(
            "logging.format",
            ConfigValueType.ENUM,
            "text",
            "ランタイムログ形式。",
            env="IRIS_LOG_FORMAT",
            allowed_values=("text", "json"),
        ),
        ConfigFieldSpec(
            "logging.file_path",
            ConfigValueType.OPTIONAL_STR,
            None,
            "任意のログ出力ファイルパス。",
            env="IRIS_LOG_FILE",
            example=False,
        ),
        ConfigFieldSpec(
            "logging.rotation",
            ConfigValueType.STR,
            "10 MB",
            "ログファイルrotation指定。",
        ),
        ConfigFieldSpec(
            "logging.retention",
            ConfigValueType.STR,
            "7 days",
            "ログファイルretention指定。",
        ),
        ConfigFieldSpec(
            "safety.mode",
            ConfigValueType.ENUM,
            "development",
            "出力safety gateの動作モード。",
            env="IRIS_SAFETY_MODE",
            allowed_values=("development", "basic", "strict"),
        ),
        ConfigFieldSpec(
            "safety.max_output_chars",
            ConfigValueType.INT,
            4000,
            "出力可能な最大文字数。",
            env="IRIS_SAFETY_MAX_OUTPUT_CHARS",
        ),
        *_latency_budget_specs(),
        ConfigFieldSpec(
            "diagnostics.mode",
            ConfigValueType.ENUM,
            "warn",
            "起動時 LLM プロバイダ診断の動作モード。",
            env="IRIS_DIAGNOSTICS_MODE",
            allowed_values=("off", "warn", "strict"),
        ),
        ConfigFieldSpec(
            "diagnostics.timeout_seconds",
            ConfigValueType.FLOAT,
            5.0,
            "診断チェック 1 件あたりのタイムアウト秒数。",
            env="IRIS_DIAGNOSTICS_TIMEOUT_SECONDS",
        ),
        ConfigFieldSpec(
            "diagnostics.readiness_timeout_seconds",
            ConfigValueType.FLOAT,
            5.0,
            "readiness 診断チェックのタイムアウト秒数。",
            env="IRIS_DIAGNOSTICS_READINESS_TIMEOUT_SECONDS",
        ),
        ConfigFieldSpec(
            "diagnostics.warmup_timeout_seconds",
            ConfigValueType.FLOAT,
            120.0,
            "warmup 診断チェックのタイムアウト秒数。",
            env="IRIS_DIAGNOSTICS_WARMUP_TIMEOUT_SECONDS",
        ),
        ConfigFieldSpec(
            "diagnostics.warmup_models",
            ConfigValueType.BOOL,
            default=False,
            description="診断後に provider 固有の warmup を実行する。",
            env="IRIS_DIAGNOSTICS_WARMUP_MODELS",
        ),
    )


def runtime_config_specs_for_version(version: int) -> tuple[ConfigFieldSpec, ...]:
    """指定versionに対応するランタイム設定仕様を返す。

    Args:
        version: TOMLから読み取った設定version。

    Returns:
        指定versionの設定フィールド仕様。

    Raises:
        ConfigError: versionが未対応の場合。
    """
    if version == RUNTIME_CONFIG_VERSION:
        return tuple(_v2_user_spec(spec) for spec in runtime_config_specs())
    message = f"Unsupported runtime config version: {version}. Supported version: 2"
    raise ConfigError(message)


def _v2_user_spec(spec: ConfigFieldSpec) -> ConfigFieldSpec:
    """反復policy fieldをv2 advanced sparse override namespaceへ移す。

    Returns:
        v2 user configで利用するfield spec。
    """
    path = spec.path
    prompt_detail = path.startswith("prompt_budget.") and path not in {
        "prompt_budget.enabled",
        "prompt_budget.chat_profile",
        "prompt_budget.proactive_profile",
    }
    model_call_detail = (
        path.startswith("model_call_budget.") and path != "model_call_budget.enabled"
    )
    inference_scheduler_detail = (
        path.startswith("inference_scheduler.") and path != "inference_scheduler.enabled"
    )
    if not (prompt_detail or model_call_detail or inference_scheduler_detail):
        if path == "config.version":
            return ConfigFieldSpec(
                path=path,
                value_type=spec.value_type,
                default=2,
                description=spec.description,
                toml=spec.toml,
                env=spec.env,
                cli=spec.cli,
                secret=spec.secret,
                control_plane_editable=spec.control_plane_editable,
                example=spec.example,
                allowed_values=spec.allowed_values,
                deprecated=spec.deprecated,
            )
        return spec
    return ConfigFieldSpec(
        path=f"advanced.{path}",
        value_type=spec.value_type,
        default=spec.default,
        description=spec.description,
        toml=spec.toml,
        env=spec.env,
        cli=spec.cli,
        secret=spec.secret,
        control_plane_editable=spec.control_plane_editable,
        example=False,
        allowed_values=spec.allowed_values,
        deprecated=spec.deprecated,
    )
