"""ランタイムstate永続化ポリシー定義。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

type PersistenceKind = Literal["durable", "ephemeral", "deferred"]
type RuntimeStateBackend = Literal["memory", "sqlite"]


def _literal_values(alias: object) -> tuple[str, ...]:
    """`type` 構文で定義したLiteralから、実行時に値のtupleを取り出す。

    Args:
        alias: `type` で宣言したエイリアス。

    Returns:
        tuple[str, ...]: Literalの値のtuple。
    """
    raw: object = getattr(alias, "__value__", None)
    if raw is None:
        return ()
    args: tuple[object, ...] = get_args(raw)
    return tuple(str(arg) for arg in args)


PERSISTENCE_KIND_VALUES: tuple[str, ...] = _literal_values(PersistenceKind)
RUNTIME_STATE_BACKEND_VALUES: tuple[str, ...] = _literal_values(RuntimeStateBackend)


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
    if backend == "sqlite":
        return RuntimeStatePersistencePolicy(
            account_store="durable",
            memory_store="durable",
            activity_journal="durable",
            activity_projection_store="ephemeral",
            presence_store="ephemeral",
            space_occupancy_store="ephemeral",
            space_binding_store="ephemeral",
            relationship_store="durable",
            affect_store="durable",
        )

    return RuntimeStatePersistencePolicy(
        account_store="ephemeral",
        memory_store="ephemeral",
        activity_journal="ephemeral",
        activity_projection_store="ephemeral",
        presence_store="ephemeral",
        space_occupancy_store="ephemeral",
        space_binding_store="ephemeral",
        relationship_store="ephemeral",
        affect_store="ephemeral",
    )
