"""LocalInferenceResourceScheduler から final verifier 可用性を導出する adapter。"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, override

from iris.contracts.verifier import (
    DeliveryVerifierAvailabilityResolver,
    VerifierAvailability,
    VerifierStatus,
)
from iris.core.datetime_utils import now_utc
from iris.runtime.inference.models import InferenceResourceState

if TYPE_CHECKING:
    from collections.abc import Mapping

    from iris.runtime.inference.scheduler import LocalInferenceResourceScheduler

_VERIFIER_STATUS_BY_STATE: Mapping[InferenceResourceState, VerifierStatus] = MappingProxyType(
    {
        InferenceResourceState.IDLE: VerifierStatus.AVAILABLE,
        InferenceResourceState.BUSY: VerifierStatus.BUSY,
        InferenceResourceState.WARMING: VerifierStatus.WARMING,
        InferenceResourceState.UNAVAILABLE: VerifierStatus.UNAVAILABLE,
    }
)
_VERIFIER_STATUS_DEFAULT = VerifierStatus.UNAVAILABLE


class LocalInferenceVerifierAvailabilityResolver(DeliveryVerifierAvailabilityResolver):
    """推論資源 scheduler の snapshot を verifier 可用性へ写像する。"""

    def __init__(self, scheduler: LocalInferenceResourceScheduler) -> None:
        """Scheduler を指定して resolver を作成する。

        Args:
            scheduler: snapshot() を持つ LocalInferenceResourceScheduler。
        """
        self._scheduler = scheduler

    @override
    async def availability(self) -> VerifierAvailability:
        """現在の final verifier 可用性を返す。

        Returns:
            scheduler の resource state に対応する VerifierAvailability。
        """
        snapshot = await self._scheduler.snapshot()
        status = _VERIFIER_STATUS_BY_STATE.get(snapshot.state, _VERIFIER_STATUS_DEFAULT)
        return VerifierAvailability(
            status=status,
            reason=f"local inference resource {snapshot.state.value}",
            observed_at=now_utc(),
        )
