"""Control Plane向けRuntime Config provider。"""

from __future__ import annotations

import sys

from iris.runtime.config.init import runtime_config_template


def main(argv: list[str] | None = None) -> int:
    """要求されたconfig templateを標準出力へ返す。

    Returns:
        process exit code。
    """
    args = sys.argv[1:] if argv is None else argv
    if args == ["template", "--config-id", "runtime"]:
        sys.stdout.write(runtime_config_template())
        return 0
    sys.stderr.write("Usage: template --config-id runtime\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
