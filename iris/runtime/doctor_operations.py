"""Runtime doctor の runtime wiring・安全性検査。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.runtime.doctor_models import RuntimeDoctorCheck, build_check
from iris.runtime.doctor_state import (
    background_job_status_summary,
    delivery_outbox_status_summary,
    has_background_job_work,
    logging_path_check,
    runtime_learning_state_check,
    sqlite_state_check,
    state_backend_check,
)

if TYPE_CHECKING:
    from iris.runtime.config import IrisRuntimeConfig
    from iris.runtime.wiring.features import DisabledRuntimeFeature
    from iris.runtime.wiring.runtime import RuntimeOperationalWiringDiagnostics


def _server_check(config: IrisRuntimeConfig) -> RuntimeDoctorCheck:
    local = "local-only" if config.server.local_only else "network-visible"
    return build_check(
        "server",
        status="ok",
        summary=f"{config.server.host}:{config.server.port} ({local})",
    )


def _model_slots_check(config: IrisRuntimeConfig) -> RuntimeDoctorCheck:
    slots = (
        f"default_chat={config.models.default_chat.provider.value}:{config.models.default_chat.model}",
        f"fast_judge={config.models.fast_judge.provider.value}:{config.models.fast_judge.model}",
        f"reasoning={config.models.reasoning.provider.value}:{config.models.reasoning.model}",
    )
    return build_check("model-slots", status="ok", summary=", ".join(slots))


def _feature_selection_check(
    wiring: RuntimeOperationalWiringDiagnostics,
) -> RuntimeDoctorCheck:
    enabled = _feature_list_summary(wiring.enabled_feature_names)
    disabled = _disabled_feature_list_summary(wiring.disabled_features)
    return build_check(
        "feature-selection",
        status="ok",
        summary=(f"mode={wiring.runtime_feature_mode} enabled={enabled} disabled={disabled}"),
    )


def _feature_list_summary(values: tuple[str, ...]) -> str:
    if not values:
        return "none"
    return ",".join(values)


def _disabled_feature_list_summary(
    values: tuple[DisabledRuntimeFeature, ...],
) -> str:
    if not values:
        return "none"
    return ",".join(
        f"{feature.name}:{feature.kind.value}:{feature.reason.value}" for feature in values
    )


def _delivery_check(config: IrisRuntimeConfig) -> RuntimeDoctorCheck:
    status = "enabled" if config.delivery.enabled else "disabled"
    return build_check("delivery", status="ok", summary=status)


def _scheduler_check(config: IrisRuntimeConfig) -> RuntimeDoctorCheck:
    status = "enabled" if config.scheduler.enabled else "disabled"
    return build_check("scheduler", status="ok", summary=status)


def _scheduler_runtime_check(
    config: IrisRuntimeConfig,
    wiring: RuntimeOperationalWiringDiagnostics,
) -> RuntimeDoctorCheck:
    enabled = "enabled" if config.scheduler.enabled else "disabled"
    loop = "enabled" if config.scheduler.enabled else "disabled"
    target_store = config.state.backend.value
    summary = (
        f"enabled={enabled} loop={loop} "
        f"runner_wired={_wired_status(wired=wiring.scheduler_runner_wired)} "
        f"target_store={target_store} "
        f"availability_provider={_wired_status(wired=wiring.availability_provider_wired)} "
        f"safety_audit_journal={_wired_status(wired=wiring.safety_audit_journal_wired)}"
    )
    issues = _scheduler_runtime_warning_issues(config, wiring)
    if not issues:
        return build_check("scheduler-runtime", status="ok", summary=summary)
    return build_check(
        "scheduler-runtime",
        status="warn",
        summary=summary,
        issue=_issue_summary(issues),
        next_action="complete scheduler runtime wiring before enabling scheduler",
    )


def _scheduler_runtime_warning_issues(
    config: IrisRuntimeConfig,
    wiring: RuntimeOperationalWiringDiagnostics,
) -> tuple[str, ...]:
    if not config.scheduler.enabled:
        return ()
    warning_checks = (
        (
            not wiring.scheduler_runner_wired,
            "scheduler.enabled=true but scheduler runner is not wired",
        ),
        (
            not wiring.availability_provider_wired,
            "scheduler.enabled=true but availability_provider is not wired",
        ),
        (
            not wiring.safety_audit_journal_wired,
            "scheduler.enabled=true but safety_audit_journal is not wired",
        ),
    )
    return tuple(issue for has_warning, issue in warning_checks if has_warning)


def _delivery_outbox_check(
    config: IrisRuntimeConfig,
    wiring: RuntimeOperationalWiringDiagnostics,
) -> RuntimeDoctorCheck:
    counts = delivery_outbox_status_summary(config)
    backend = config.state.backend.value
    delivery = "enabled" if config.delivery.enabled else "disabled"
    broker = _wired_status(wired=wiring.delivery_broker_wired and config.delivery.enabled)
    summary = f"enabled={delivery} backend={backend} broker={broker}; {counts.summary}"
    if counts.status != "ok":
        return build_check(
            "delivery-outbox",
            status=counts.status,
            summary=summary,
            issue=counts.issue,
            next_action=counts.next_action,
        )
    if not config.delivery.enabled and counts.pending_count > 0:
        return build_check(
            "delivery-outbox",
            status="warn",
            summary=summary,
            issue="delivery outbox has pending items but delivery broker is disabled",
            next_action="enable delivery worker/broker or drain pending outbox items",
        )
    return build_check("delivery-outbox", status="ok", summary=summary)


def _background_jobs_check(config: IrisRuntimeConfig) -> RuntimeDoctorCheck:
    counts = background_job_status_summary(config)
    backend = config.state.backend.value
    loop = "enabled" if config.learning.background_jobs_enabled else "disabled"
    summary = f"loop={loop} backend={backend}; {counts.summary}"
    if counts.status != "ok":
        return build_check(
            "background-jobs",
            status=counts.status,
            summary=summary,
            issue=counts.issue,
            next_action=counts.next_action,
        )
    if not config.learning.background_jobs_enabled and has_background_job_work(counts):
        return build_check(
            "background-jobs",
            status="warn",
            summary=summary,
            issue="background jobs are pending or failed but background job loop is disabled",
            next_action="enable learning.background_jobs_enabled or drain background jobs",
        )
    return build_check("background-jobs", status="ok", summary=summary)


def _proactive_safety_check(
    config: IrisRuntimeConfig,
    wiring: RuntimeOperationalWiringDiagnostics,
) -> RuntimeDoctorCheck:
    proactive = "enabled" if wiring.proactive_talk_enabled else "disabled"
    delivery_safety = _delivery_safety_mode(config, wiring)
    quiet_hours = _quiet_hours_summary(config)
    output_safety = _output_safety_mode(config, wiring)
    audit_journal = _wired_status(wired=wiring.safety_audit_journal_wired)
    summary = (
        f"proactive_talk={proactive} "
        f"generation_mode={wiring.proactive_generation_mode} "
        f"threshold={wiring.proactive_threshold} "
        f"delivery_safety={delivery_safety} "
        f"quiet_hours={quiet_hours} "
        f"output_safety={output_safety} "
        f"safety_audit_journal={audit_journal}"
    )
    issues = _proactive_safety_warning_issues(config, wiring)
    if not issues:
        return build_check("proactive-safety", status="ok", summary=summary)
    return build_check(
        "proactive-safety",
        status="warn",
        summary=summary,
        issue=_issue_summary(issues),
        next_action="complete proactive safety wiring before enabling proactive delivery",
    )


def _proactive_safety_warning_issues(
    config: IrisRuntimeConfig,
    wiring: RuntimeOperationalWiringDiagnostics,
) -> tuple[str, ...]:
    if not wiring.proactive_talk_enabled:
        return ()
    warning_checks = (
        (
            not wiring.delivery_safety_gate_wired,
            "proactive_talk enabled but delivery safety gate is not configured",
        ),
        (
            not wiring.output_safety_gate_wired or config.safety.mode == "development",
            "proactive_talk enabled but output safety gate is not configured",
        ),
        (
            not wiring.safety_audit_journal_wired,
            "proactive_talk enabled but safety_audit_journal is not wired",
        ),
    )
    return tuple(issue for has_warning, issue in warning_checks if has_warning)


def _issue_summary(issues: tuple[str, ...]) -> str:
    return "; ".join(issues)


def _delivery_safety_mode(
    config: IrisRuntimeConfig,
    wiring: RuntimeOperationalWiringDiagnostics,
) -> str:
    if not wiring.delivery_safety_gate_wired:
        return "not_configured"
    if config.safety.mode == "strict":
        return "strict"
    return "basic"


def _output_safety_mode(
    config: IrisRuntimeConfig,
    wiring: RuntimeOperationalWiringDiagnostics,
) -> str:
    if not wiring.output_safety_gate_wired:
        return "not_configured"
    if config.safety.mode in {"basic", "strict"}:
        return "basic_output_filter"
    return "allow_all"


def _quiet_hours_summary(config: IrisRuntimeConfig) -> str:
    quiet_hours = config.delivery.quiet_hours
    status = "enabled" if quiet_hours.enabled else "disabled"
    return f"{status} {quiet_hours.start}-{quiet_hours.end} {quiet_hours.timezone}"


def _wired_status(*, wired: bool) -> str:
    return "wired" if wired else "not_wired"


def runtime_doctor_base_checks(
    config: IrisRuntimeConfig,
    wiring: RuntimeOperationalWiringDiagnostics,
) -> list[RuntimeDoctorCheck]:
    """Runtime doctor の固定チェック群を順序付きで組み立てる。

    Returns:
        順序を保った RuntimeDoctorCheck の list。
    """
    return [
        state_backend_check(config),
        sqlite_state_check(config),
        logging_path_check(config),
        runtime_learning_state_check(config),
        _background_jobs_check(config),
        _server_check(config),
        _model_slots_check(config),
        _feature_selection_check(wiring),
        _delivery_check(config),
        _delivery_outbox_check(config, wiring),
        _scheduler_check(config),
        _scheduler_runtime_check(config, wiring),
        _proactive_safety_check(config, wiring),
    ]
