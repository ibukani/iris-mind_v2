"""Runtime Config schemaを生成または検査する。"""

from __future__ import annotations

import argparse
from pathlib import Path

from iris.runtime.config.schema import render_runtime_config_schema


def main() -> int:
    """Schemaを生成し、check時はdriftを終了codeで返す。

    Returns:
        driftがなければ0、それ以外は1。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = Path(".iris/control-plane/runtime-config.schema.json")
    rendered = render_runtime_config_schema()
    if args.check:
        return 0 if path.is_file() and path.read_text(encoding="utf-8") == rendered else 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
