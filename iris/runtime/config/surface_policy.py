"""Delivery surface policy の設定パース。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from iris.contracts.delivery import DeliverySurface
from iris.contracts.surface_policy import DeliverySurfacePolicy
from iris.runtime.config.errors import ConfigError
from iris.runtime.config.parsing import parse_string

if TYPE_CHECKING:
    from iris.runtime.config.parsing import TomlValue


@dataclass(frozen=True)
class RuntimeDeliverySurfacePolicyConfig:
    """Delivery surface 別の policy 設定。

    空文字列は制限なしを意味する。production mode では
    `production_surface_policy()` が既定の public surface deny policy を返す。
    """

    allowed_surfaces: str = ""
    allowed_providers: str = ""
    denied_surfaces: str = ""
    denied_providers: str = ""

    def to_policy(self) -> DeliverySurfacePolicy:
        """Contracts 層の surface policy へ変換する。

        Returns:
            DeliverySurfacePolicy: 同じ allow/deny 集合を持つ policy。
        """
        return DeliverySurfacePolicy(
            allowed_surfaces=_parse_surfaces(
                self.allowed_surfaces,
                "delivery.surface_policy.allowed_surfaces",
            ),
            allowed_providers=_parse_providers(
                self.allowed_providers,
                "delivery.surface_policy.allowed_providers",
            ),
            denied_surfaces=_parse_surfaces(
                self.denied_surfaces,
                "delivery.surface_policy.denied_surfaces",
            ),
            denied_providers=_parse_providers(
                self.denied_providers,
                "delivery.surface_policy.denied_providers",
            ),
        )


def production_surface_policy() -> RuntimeDeliverySurfacePolicyConfig:
    """Production mode の既定 surface policy。

    public surface を fail-closed で拒否する。

    Returns:
        public / voice / avatar を deny する設定。
    """
    denied = (
        f"{DeliverySurface.PUBLIC_CHANNEL.value},"
        f"{DeliverySurface.VOICE.value},"
        f"{DeliverySurface.AVATAR.value}"
    )
    return RuntimeDeliverySurfacePolicyConfig(
        allowed_surfaces="",
        denied_surfaces=denied,
    )


def apply_surface_policy_toml(
    config: RuntimeDeliverySurfacePolicyConfig,
    value: TomlValue,
    path: str,
) -> RuntimeDeliverySurfacePolicyConfig:
    """TOML テーブルから delivery surface policy を更新する。

    Args:
        config: 現在の policy 設定。
        value: 対象の TOML 値。
        path: エラーメッセージに含める設定パス。

    Returns:
        検証済みの surface policy 設定。

    Raises:
        ConfigError: 値が policy として不正な場合。
    """
    if not isinstance(value, dict):
        message = f"{path} must be a table"
        raise ConfigError(message)
    allowed_surfaces = _merge_csv(
        config.allowed_surfaces,
        value,
        "allowed_surfaces",
        f"{path}.allowed_surfaces",
    )
    allowed_providers = _merge_csv(
        config.allowed_providers,
        value,
        "allowed_providers",
        f"{path}.allowed_providers",
    )
    denied_surfaces = _merge_csv(
        config.denied_surfaces,
        value,
        "denied_surfaces",
        f"{path}.denied_surfaces",
    )
    denied_providers = _merge_csv(
        config.denied_providers,
        value,
        "denied_providers",
        f"{path}.denied_providers",
    )
    return replace(
        config,
        allowed_surfaces=allowed_surfaces,
        allowed_providers=allowed_providers,
        denied_surfaces=denied_surfaces,
        denied_providers=denied_providers,
    )


def validate_surface_policy_config(
    config: RuntimeDeliverySurfacePolicyConfig,
) -> RuntimeDeliverySurfacePolicyConfig:
    """Delivery surface policy の整合性を検証する。

    Args:
        config: 検証対象の policy 設定。

    Returns:
        検証済み policy 設定。
    """
    _parse_surfaces(
        config.allowed_surfaces,
        "delivery.surface_policy.allowed_surfaces",
    )
    _parse_surfaces(
        config.denied_surfaces,
        "delivery.surface_policy.denied_surfaces",
    )
    return config


def _merge_csv(
    current: str,
    table: dict[str, TomlValue],
    key: str,
    path: str,
) -> str:
    value = table.get(key)
    if value is None:
        return current
    if isinstance(value, str):
        if not value:
            return ""
        return ",".join(item.strip() for item in value.split(",") if item.strip())
    if isinstance(value, list):
        items: list[str] = []
        for index, item in enumerate(value):
            parsed = parse_string(item, f"{path}[{index}]")
            if not parsed:
                message = f"{path}[{index}] must not be blank"
                raise ConfigError(message)
            items.append(parsed)
        return ",".join(items)
    message = f"{path} must be a string or string list"
    raise ConfigError(message)


def _parse_surfaces(value: str, path: str) -> frozenset[DeliverySurface]:
    surfaces: set[DeliverySurface] = set()
    for item in _split_csv(value):
        try:
            surfaces.add(DeliverySurface(item))
        except ValueError as exc:
            allowed = ", ".join(surface.value for surface in DeliverySurface)
            message = f"{path} contains unknown surface '{item}'. Allowed: {allowed}"
            raise ConfigError(message) from exc
    return frozenset(surfaces)


def _parse_providers(value: str, path: str) -> frozenset[str]:
    providers: set[str] = set()
    for item in _split_csv(value):
        if not item:
            message = f"{path} must not contain blank entries"
            raise ConfigError(message)
        providers.add(item)
    return frozenset(providers)


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
