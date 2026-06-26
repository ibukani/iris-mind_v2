"""Runtime doctor command tests."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from iris.runtime.doctor import main, run_runtime_doctor

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.anyio
async def test_runtime_doctor_default_config_reports_ok() -> None:
    """Default fake-provider config passes runtime doctor."""
    report = await run_runtime_doctor()

    assert report.ok
    names = {check.name for check in report.checks}
    assert "config-discovery" in names
    assert "config-parse" in names
    assert "state-backend" in names
    assert "provider-readiness" in names
    assert "delivery" in names
    assert "scheduler" in names


@pytest.mark.anyio
async def test_runtime_doctor_missing_explicit_config_reports_failure(tmp_path: Path) -> None:
    """Missing explicit config path is reported as a config discovery failure."""
    missing = tmp_path / "missing.toml"

    report = await run_runtime_doctor(str(missing))

    assert not report.ok
    failure = next(check for check in report.checks if check.status == "fail")
    assert failure.name in {"config-discovery", "config-parse"}
    assert failure.next_action in {
        "check --config path or IRIS_MIND_CONFIG",
        "fix runtime TOML or environment override",
    }


def test_runtime_doctor_json_cli_outputs_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--json CLI emits a JSON report."""
    monkeypatch.setattr("sys.argv", ["iris.runtime.doctor", "--json"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["checks"][0]["name"] == "config-discovery"
