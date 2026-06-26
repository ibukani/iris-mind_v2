"""ランタイムstate永続化ポリシー定義。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from iris.runtime.config.state import RuntimeStateBackend


class PersistenceKind(StrEnum):
    """永続化種別。"""

    DURABLE = "durable"
    EPHEMERAL = "ephemeral"
    DEFERRED = "deferred"


PERSISTENCE_KIND_VALUES: tuple[str, ...] = tuple(k.value for k in PersistenceKind)
RUNTIME_STATE_BACKEND_VALUES: tuple[str, ...] = tuple(k.value for k in RuntimeStateBackend)


@dataclass(frozen=True)
class RuntimeStatePersistencePolicy:
    """ランタイムstateの各ストアに対する永続化種別。"""

    account_store: PersistenceKind
    memory_store: PersistenceKind
    activity_journal: PersistenceKind
    activity_projection_store: PersistenceKind
    presence_store: PersistenceKind
    space_occupancy_store: PersistenceKind
    space_binding_store: PersistenceKind
    relationship_store: PersistenceKind
    affect_store: PersistenceKind


def runtime_state_persistence_policy(
    backend: RuntimeStateBackend,
) -> RuntimeStatePersistencePolicy:
    """backendに対応する永続化ポリシーを返す。

    Args:
        backend: ランタイムstateバックエンド。

    Returns:
        RuntimeStatePersistencePolicy: backendに対応する永続化ポリシー。
    """
    if backend == RuntimeStateBackend.SQLITE:
        return RuntimeStatePersistencePolicy(
            account_store=PersistenceKind.DURABLE,
            memory_store=PersistenceKind.DURABLE,
            activity_journal=PersistenceKind.DURABLE,
            activity_projection_store=PersistenceKind.EPHEMERAL,
            presence_store=PersistenceKind.EPHEMERAL,
            space_occupancy_store=PersistenceKind.EPHEMERAL,
            space_binding_store=PersistenceKind.EPHEMERAL,
            relationship_store=PersistenceKind.DURABLE,
            affect_store=PersistenceKind.DURABLE,
        )

    return RuntimeStatePersistencePolicy(
        account_store=PersistenceKind.EPHEMERAL,
        memory_store=PersistenceKind.EPHEMERAL,
        activity_journal=PersistenceKind.EPHEMERAL,
        activity_projection_store=PersistenceKind.EPHEMERAL,
        presence_store=PersistenceKind.EPHEMERAL,
        space_occupancy_store=PersistenceKind.EPHEMERAL,
        space_binding_store=PersistenceKind.EPHEMERAL,
        relationship_store=PersistenceKind.EPHEMERAL,
        affect_store=PersistenceKind.EPHEMERAL,
    )
