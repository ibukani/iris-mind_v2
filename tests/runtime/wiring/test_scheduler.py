"""Runtime wiring helper tests for scheduler wiring."""

from __future__ import annotations

from dataclasses import replace
from math import isclose

from iris.runtime.config import default_runtime_config
from iris.runtime.scheduler.idle_tick import IdleTickSchedulePolicy, IdleTickSource
from iris.runtime.wiring.scheduler import wire_runtime_scheduler
from iris.runtime.wiring.state import wire_runtime_state
from tests.helpers.private_access import get_private_attr_as


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
