"""Runtime auth token CLI tests."""

from __future__ import annotations

import json

import pytest

from iris.runtime.auth.errors import RuntimeUnauthenticatedError
from iris.runtime.server import main


def test_auth_create_token_prints_raw_token_once_and_hash_entry(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """create-token は raw token を一度だけ表示し、JSON には hash だけを含める。"""
    monkeypatch.setattr(
        "sys.argv",
        [
            "iris.runtime.server",
            "auth",
            "create-token",
            "--client-id",
            "cli-1",
            "--client-kind",
            "external_client",
            "--provider",
            "cli",
            "--allowed-provider",
            "cli",
            "--scope",
            "observation.submit",
        ],
    )

    main()

    lines = capsys.readouterr().out.splitlines()
    raw_token = lines[0]
    token_hash = lines[1]
    entry = json.loads(lines[2])
    assert raw_token.startswith("iris_rt_")
    assert len(raw_token) >= 40
    assert token_hash == entry["token_sha256"]
    assert raw_token not in lines[2]
    assert not capsys.readouterr().err


def test_auth_create_token_prints_trusted_adapter_profile(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """trusted_adapter token は dotted trusted scope と provider 制限を出力する。"""
    monkeypatch.setattr(
        "sys.argv",
        [
            "iris.runtime.server",
            "auth",
            "create-token",
            "--client-id",
            "discord-adapter",
            "--client-kind",
            "trusted_adapter",
            "--provider",
            "discord",
            "--allowed-provider",
            "discord",
            "--scope",
            "runtime.info.read",
            "--scope",
            "observation.submit.trusted",
            "--scope",
            "delivery.poll",
            "--scope",
            "delivery.report",
            "--observation-capability",
            "integrate_activity",
        ],
    )

    main()

    lines = capsys.readouterr().out.splitlines()
    entry = json.loads(lines[2])
    assert entry["client_kind"] == "trusted_adapter"
    assert entry["provider"] == "discord"
    assert entry["allowed_providers"] == ["discord"]
    assert entry["scopes"] == [
        "delivery.poll",
        "delivery.report",
        "observation.submit.trusted",
        "runtime.info.read",
    ]
    assert entry["observation_capabilities"] == ["integrate_activity"]


def test_auth_create_token_rejects_trusted_adapter_wildcard_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """trusted_adapter token は wildcard provider を発行できない。"""
    monkeypatch.setattr(
        "sys.argv",
        [
            "iris.runtime.server",
            "auth",
            "create-token",
            "--client-id",
            "discord-adapter",
            "--client-kind",
            "trusted_adapter",
            "--provider",
            "discord",
            "--allowed-provider",
            "*",
            "--scope",
            "observation.submit.trusted",
        ],
    )

    with pytest.raises(RuntimeUnauthenticatedError):
        main()


def test_auth_create_token_rejects_trusted_adapter_internal_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """trusted_adapter token は internal-only capability を発行できない。"""
    monkeypatch.setattr(
        "sys.argv",
        [
            "iris.runtime.server",
            "auth",
            "create-token",
            "--client-id",
            "discord-adapter",
            "--client-kind",
            "trusted_adapter",
            "--provider",
            "discord",
            "--allowed-provider",
            "discord",
            "--scope",
            "observation.submit.trusted",
            "--observation-capability",
            "internal_event",
        ],
    )

    with pytest.raises(RuntimeUnauthenticatedError):
        main()
