"""Runtime config provider契約のテスト。"""

from __future__ import annotations

import json
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


def test_schema_provider_outputs_valid_json_schema(capsys: pytest.CaptureFixture[str]) -> None:
    """Providerはruntime向けJSON schemaをstdoutへ返す。"""
    assert main(["schema", "--config-id", "runtime"]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert schema["x-iris-version"] == 2
    assert schema["type"] == "object"
    assert "properties" in schema


def test_template_provider_rejects_unknown_config_id() -> None:
    """未知config idを拒否する。"""
    assert main(["template", "--config-id", "unknown"]) == 2


def test_schema_provider_rejects_unknown_config_id() -> None:
    """未知schema config idを拒否する。"""
    assert main(["schema", "--config-id", "unknown"]) == 2
