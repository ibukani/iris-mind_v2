"""Runtime auth token CLI tests."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from iris.runtime.server import main

if TYPE_CHECKING:
    import pytest


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
