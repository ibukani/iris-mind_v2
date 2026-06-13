"""Availability contract tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.contracts.availability import AvailabilitySnapshot, AvailabilityStatus
from iris.core.ids import ActorId
from tests.helpers.immutability import assert_frozen_field

MESSAGE = "confidence must be between 0.0 and 1.0"


def test_availability_status_exposes_expected_values() -> None:
    """AvailabilityStatus が想定値を持つことを確認する。"""
    assert {status.value for status in AvailabilityStatus} == {
        "unknown",
        "available",
        "interruptible",
        "passive",
        "busy",
        "unavailable",
    }


def test_availability_snapshot_accepts_valid_confidence() -> None:
    """Confidence が 0.0 から 1.0 の範囲内であれば受け入れる。"""
    snapshot = AvailabilitySnapshot(
        actor_id=ActorId("actor-1"),
        status=AvailabilityStatus.AVAILABLE,
        reason="test",
        observed_at=datetime(2026, 6, 13, tzinfo=UTC),
        computed_at=datetime(2026, 6, 13, tzinfo=UTC),
        confidence=0.5,
    )
    assert snapshot.confidence == 0.5  # noqa: RUF069 -- exact float literal comparison in tests


def test_availability_snapshot_rejects_confidence_below_zero() -> None:
    """Confidence が 0.0 未満なら ValueError を送出する。"""
    with pytest.raises(ValueError, match=MESSAGE):
        AvailabilitySnapshot(
            actor_id=ActorId("actor-1"),
            status=AvailabilityStatus.AVAILABLE,
            reason="test",
            observed_at=datetime(2026, 6, 13, tzinfo=UTC),
            computed_at=datetime(2026, 6, 13, tzinfo=UTC),
            confidence=-0.1,
        )


def test_availability_snapshot_rejects_confidence_above_one() -> None:
    """Confidence が 1.0 を超えれば ValueError を送出する。"""
    with pytest.raises(ValueError, match=MESSAGE):
        AvailabilitySnapshot(
            actor_id=ActorId("actor-1"),
            status=AvailabilityStatus.AVAILABLE,
            reason="test",
            observed_at=datetime(2026, 6, 13, tzinfo=UTC),
            computed_at=datetime(2026, 6, 13, tzinfo=UTC),
            confidence=1.1,
        )


def test_availability_snapshot_is_frozen() -> None:
    """AvailabilitySnapshot が frozen dataclass であることを確認する。"""
    snapshot = AvailabilitySnapshot(
        actor_id=ActorId("actor-1"),
        status=AvailabilityStatus.AVAILABLE,
        reason="test",
        observed_at=datetime(2026, 6, 13, tzinfo=UTC),
        computed_at=datetime(2026, 6, 13, tzinfo=UTC),
    )
    assert_frozen_field(snapshot, "status", AvailabilityStatus.BUSY)
