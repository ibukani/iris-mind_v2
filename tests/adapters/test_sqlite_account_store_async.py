"""SQLiteAccountStore のイベントループ非ブロック化テスト。"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import pytest

from iris.adapters.accounts.sqlite import SQLiteAccountStore
from iris.contracts.accounts import AccountProfile
from iris.core.ids import AccountId, ActorId, ExternalRef
from tests.helpers.private_access import _is_callable, get_private_attr_matching

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


@pytest.mark.anyio
async def test_slow_backend_does_not_block_event_loop(
    tmp_path: Path,
    profile: AccountProfile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """人工的な遅延バックエンドがイベントループをブロックしないことを確認する。"""
    store = SQLiteAccountStore(tmp_path / "slow.sqlite3")

    original_sync = get_private_attr_matching(store, "_put_sync", _is_callable)

    def slow_put(account: AccountProfile) -> AccountProfile:
        time.sleep(0.1)
        return original_sync(account)

    monkeypatch.setattr(store, "_put_sync", slow_put)

    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        for _ in range(20):
            await asyncio.sleep(0.01)
            ticks += 1

    await asyncio.gather(
        ticker(),
        store.put(profile),
        store.put(
            AccountProfile(
                account_id=AccountId("acct-slow-2"),
                provider="github",
                provider_subject=ExternalRef("slow-456"),
                display_name="Slow User",
            )
        ),
    )

    assert ticks > 0, "ティッカーがイベントループ上で進行しているべき"


@pytest.mark.anyio
async def test_link_and_unlink_account_async(
    tmp_path: Path,
    profile: AccountProfile,
) -> None:
    """link_account_to_actor と unlink_account が非同期で正しく動作することを確認する。"""
    store = SQLiteAccountStore(tmp_path / "link.sqlite3")

    await store.put(profile)
    linked = await store.link_account_to_actor(
        account_id=profile.account_id,
        actor_id=ActorId("actor-link-1"),
    )
    assert linked.linked_actor_id == ActorId("actor-link-1")

    unlinked = await store.unlink_account(profile.account_id)
    assert unlinked.linked_actor_id is None
