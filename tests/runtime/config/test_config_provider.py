"""Runtime config provider契約のテスト。"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING

from iris.runtime.config_provider import main

if TYPE_CHECKING:
    import pytest


def test_template_provider_outputs_compact_v2(capsys: pytest.CaptureFixture[str]) -> None:
    """Providerはruntime向けv2 templateだけをstdoutへ返す。"""
    assert main(["template", "--config-id", "runtime"]) == 0
    document = tomllib.loads(capsys.readouterr().out)
    assert document["config"]["version"] == 2
    assert "advanced" not in document


def test_template_provider_rejects_unknown_config_id() -> None:
    """未知config idを拒否する。"""
    assert main(["template", "--config-id", "unknown"]) == 2
