"""Runtime wiring helper tests for scheduler wiring."""

from __future__ import annotations

from dataclasses import replace
from math import isclose
from typing import TYPE_CHECKING

from iris.runtime.app import IrisApp
from iris.runtime.config import default_runtime_config
from iris.runtime.scheduler.idle_tick import IdleTickSchedulePolicy, IdleTickSource
from iris.runtime.state.safety_audit import InMemorySafetyAuditJournal
from iris.runtime.wiring.delivery import wire_delivery_safety_gate
from iris.runtime.wiring.features import wire_runtime_features
from iris.runtime.wiring.presentation import wire_output_pipeline
from iris.runtime.wiring.runtime import RuntimeServiceBuildOptions, build_runtime_service
from iris.runtime.wiring.scheduler import (
    SchedulerSafetyDependencies,
    wire_runtime_scheduler,
    wire_scheduler_runner,
)
from iris.runtime.wiring.state import wire_runtime_state
from tests.helpers.private_access import get_private_attr_as

if TYPE_CHECKING:
    from datetime import datetime

    from iris.contracts.availability import AvailabilitySnapshot
    from iris.contracts.delivery import DeliveryTarget


class _AvailabilityProvider:
    """DeliveryAvailabilityProvider fake for wiring identity assertions."""

    async def availability_for_target(
        self,
        target: DeliveryTarget,
        *,
        now: datetime,
    ) -> AvailabilitySnapshot | None:
        """Return no availability snapshot.

        Returns:
            None。wire identity test では呼び出されない。
        """
        _ = target, now
        return None


def test_wire_scheduler_runner_keeps_explicit_safety_dependencies() -> None:
    """wire_scheduler_runner は明示された safety dependencies を runner へ渡す。"""
    config = default_runtime_config()
    stores = wire_runtime_state(config)
    feature_catalog = wire_runtime_features()
    output_pipeline = wire_output_pipeline()
    runtime_service = build_runtime_service(
        app=IrisApp(steps=(), output_pipeline=output_pipeline),
        stores=stores,
        feature_catalog=feature_catalog,
        output_pipeline=output_pipeline,
        options=RuntimeServiceBuildOptions(
            target_stale_after_seconds=config.scheduler.target_stale_after_seconds,
        ),
    )
    availability_provider = _AvailabilityProvider()
    audit_journal = InMemorySafetyAuditJournal()

    runner = wire_scheduler_runner(
        runtime_service=runtime_service,
        scheduler=wire_runtime_scheduler(stores.scheduler_target_store, config),
        delivery_gate=wire_delivery_safety_gate(config.delivery),
        outbox=stores.delivery_outbox,
        config=config,
        safety=SchedulerSafetyDependencies(
            availability_provider=availability_provider,
            audit_journal=audit_journal,
        ),
    )

    assert runner.availability_provider is availability_provider
    assert runner.safety_audit_journal is audit_journal


def test_wire_runtime_scheduler_maps_runtime_scheduler_config_to_policy() -> None:
    """wire_runtime_scheduler は scheduler config を policy に写像する。"""
    base_config = default_runtime_config()
    config = replace(
        base_config,
        scheduler=replace(
            base_config.scheduler,
            idle_threshold_seconds=10.0,
            min_interval_per_target_seconds=20.0,
            max_due_per_run=3,
        ),
    )
    stores = wire_runtime_state(config)

    source = wire_runtime_scheduler(stores.scheduler_target_store, config)

    assert isinstance(source, IdleTickSource)
    policy = get_private_attr_as(source, "_policy", IdleTickSchedulePolicy)
    assert isinstance(policy, IdleTickSchedulePolicy)
    assert isclose(policy.idle_threshold_seconds, 10.0)
    assert isclose(policy.min_interval_per_target_seconds, 20.0)
    assert policy.max_due_per_run == 3
