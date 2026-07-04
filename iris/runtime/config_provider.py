"""Control Plane向けRuntime Config provider。"""

from __future__ import annotations

import sys

from iris.runtime.config.init import runtime_config_template
from iris.runtime.config.schema import render_runtime_config_schema


def main(argv: list[str] | None = None) -> int:
    """要求されたconfig template / schemaを標準出力へ返す。

    Returns:
        process exit code。
    """
    args = sys.argv[1:] if argv is None else argv
    if args == ["template", "--config-id", "runtime"]:
        sys.stdout.write(runtime_config_template())
        return 0
    if args == ["schema", "--config-id", "runtime"]:
        sys.stdout.write(render_runtime_config_schema())
        return 0
    sys.stderr.write("Usage: {template|schema} --config-id runtime\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
