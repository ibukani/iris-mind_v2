"""SQLiteAccountStore のイベントループ非ブロック化テスト。"""

from __future__ import annotations

import asyncio
import dataclasses
from typing import TYPE_CHECKING

import pytest

from iris.adapters.sqlite.account_store import SQLiteAccountStore
from iris.contracts.accounts import AccountProfile
from iris.core.ids import AccountId, ActorId, ExternalRef

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def profile() -> AccountProfile:
    """テスト用の標準アカウントプロファイルを返す。

    Returns:
        AccountProfile: テスト用アカウントプロファイル。
    """
    return AccountProfile(
        account_id=AccountId("acct-async-1"),
        provider="discord",
        provider_subject=ExternalRef("async-123"),
        display_name="Async Mina",
    )


@pytest.mark.anyio
async def test_sqlite_account_store_does_not_block_event_loop(
    tmp_path: Path,
    profile: AccountProfile,
) -> None:
    """SQLiteAccountStore が asyncio のティッカーをブロックしないことを確認する。"""
    store = SQLiteAccountStore(tmp_path / "state.sqlite3")

    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        for _ in range(10):
            await asyncio.sleep(0.01)
            ticks += 1

    await asyncio.gather(
        ticker(),
        store.put(profile),
        store.get_by_external_ref(provider="discord", provider_subject=ExternalRef("async-123")),
        store.get_by_account_id(AccountId("acct-async-1")),
    )

    assert ticks > 0
    await store.close()


@pytest.mark.anyio
async def test_concurrent_account_operations_complete_correctly(
    tmp_path: Path,
) -> None:
    """並行アカウント操作が正しく完了することを確認する。"""
    store = SQLiteAccountStore(tmp_path / "concurrent.sqlite3")

    profiles = [
        AccountProfile(
            account_id=AccountId(f"acct-concurrent-{i}"),
            provider=f"provider-{i}",
            provider_subject=ExternalRef(f"subject-{i}"),
            display_name=f"Concurrent User {i}",
        )
        for i in range(5)
    ]

    await asyncio.gather(*(store.put(p) for p in profiles))

    fetched = await asyncio.gather(*(store.get_by_account_id(p.account_id) for p in profiles))
    for original, result in zip(profiles, fetched, strict=True):
        assert result == original
    await store.close()


@pytest.mark.anyio
async def test_update_linked_actor_id_async(
    tmp_path: Path,
    profile: AccountProfile,
) -> None:
    """Updating linked_actor_id via put should work correctly asynchronously."""
    store = SQLiteAccountStore(tmp_path / "link.sqlite3")

    await store.put(profile)
    updated = dataclasses.replace(profile, linked_actor_id=ActorId("actor-link-1"))
    linked = await store.put(updated)
    assert linked.linked_actor_id == ActorId("actor-link-1")

    unlinked_profile = dataclasses.replace(linked, linked_actor_id=None)
    unlinked = await store.put(unlinked_profile)
    assert unlinked.linked_actor_id is None
    await store.close()
