"""Delivery surface の安全 policy 契約。

public / DM / voice / avatar / notification を typed surface として区別し、
production mode の fail-closed 判定に使う provider/surface allowlist と
denylist を定義する。provider 名や channel 種別は safety core に埋め込まず、
adapter metadata から runtime-owned surface へ正規化済みの値だけを扱う。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from iris.contracts.delivery import DeliverySurface


class DeliverySurfacePolicy(BaseModel):
    """Surface 単位の配送許可 / 拒否 policy。

    すべて fail-closed に評価される。

    - allowed_surfaces が空の場合は surface 制限なし。
    - allowed_providers が空の場合は provider 制限なし。
    - denied_* は allowed_* に優先する。
    """

    model_config = ConfigDict(frozen=True)

    allowed_surfaces: frozenset[DeliverySurface] = frozenset()
    allowed_providers: frozenset[str] = frozenset()
    denied_surfaces: frozenset[DeliverySurface] = frozenset()
    denied_providers: frozenset[str] = frozenset()

    def surface_reason(
        self,
        *,
        surface: DeliverySurface,
        provider: str,
    ) -> str | None:
        """Surface と provider を policy と突き合わせる。

        Returns:
            block 理由。許可なら ``None``。
        """
        checks: tuple[tuple[bool, str], ...] = (
            (surface in self.denied_surfaces, "surface_denied"),
            (provider in self.denied_providers, "provider_denied"),
            (
                bool(self.allowed_surfaces) and surface not in self.allowed_surfaces,
                "surface_not_allowed",
            ),
            (
                bool(self.allowed_providers) and provider not in self.allowed_providers,
                "provider_not_allowed",
            ),
        )
        for violated, reason in checks:
            if violated:
                return reason
        return None
