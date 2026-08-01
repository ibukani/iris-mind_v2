"""LocalInferenceVerifierAvailabilityResolver のテスト。"""

from __future__ import annotations

import pytest

from iris.contracts.verifier import VerifierStatus
from iris.runtime.inference.models import InferenceResourceState
from iris.runtime.inference.policy import LocalInferenceResourcePolicy
from iris.runtime.inference.scheduler import LocalInferenceResourceScheduler
from iris.runtime.inference.verifier_availability import (
    LocalInferenceVerifierAvailabilityResolver,
)

pytestmark = pytest.mark.anyio


def _scheduler() -> LocalInferenceResourceScheduler:
    return LocalInferenceResourceScheduler(
        policy=LocalInferenceResourcePolicy(enabled=True),
    )


@pytest.mark.parametrize(
    ("resource_state", "expected_status"),
    [
        (InferenceResourceState.IDLE, VerifierStatus.AVAILABLE),
        (InferenceResourceState.BUSY, VerifierStatus.BUSY),
        (InferenceResourceState.WARMING, VerifierStatus.WARMING),
        (InferenceResourceState.UNAVAILABLE, VerifierStatus.UNAVAILABLE),
    ],
)
async def test_resolver_maps_resource_state_to_verifier_status(
    resource_state: InferenceResourceState,
    expected_status: VerifierStatus,
) -> None:
    """Scheduler の resource state が verifier 可用性へ写像される。"""
    scheduler = _scheduler()
    await scheduler.set_state(resource_state)
    resolver = LocalInferenceVerifierAvailabilityResolver(scheduler)

    availability = await resolver.availability()

    assert availability.status is expected_status
    assert availability.reason


async def test_resolver_reports_available_without_state_override() -> None:
    """状態 override が無い scheduler は available とみなす。"""
    scheduler = _scheduler()
    resolver = LocalInferenceVerifierAvailabilityResolver(scheduler)

    availability = await resolver.availability()

    assert availability.status is VerifierStatus.AVAILABLE
