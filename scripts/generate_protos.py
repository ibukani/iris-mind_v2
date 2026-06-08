"""Generate Iris protobuf and gRPC code from proto definitions.

Runs grpc_tools.protoc and fixes generated import paths to match the
iris.generated package layout.
"""

from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts._subprocess_runner import run as _run_command

PROTO_DIR = REPO_ROOT / "proto"
OUTPUT_DIR = REPO_ROOT / "iris" / "generated"

MESSAGE_PROTOS: tuple[str, ...] = (
    "iris/api/v1/identity.proto",
    "iris/api/v1/observations.proto",
    "iris/api/v1/outputs.proto",
    "iris/api/v1/spaces.proto",
)

SERVICE_PROTOS: tuple[str, ...] = ("iris/runtime/v1/runtime.proto",)

_IMPORT_FIXES: tuple[tuple[str, str], ...] = (
    ("from iris.api.v1 import", "from iris.generated.iris.api.v1 import"),
    ("from iris.runtime.v1 import", "from iris.generated.iris.runtime.v1 import"),
)


def main() -> int:
    """Generate protobuf code and fix import paths.

    Returns:
        int: Process exit code (0 on success).
    """
    if MESSAGE_PROTOS:
        msg_args = [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            f"--proto_path={PROTO_DIR}",
            f"--python_out={OUTPUT_DIR}",
            f"--mypy_out={OUTPUT_DIR}",
            *[str(PROTO_DIR / p) for p in MESSAGE_PROTOS],
        ]
        result = _run_command(msg_args, check=False)
        if result.returncode != 0:
            return result.returncode

    if SERVICE_PROTOS:
        svc_args = [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            f"--proto_path={PROTO_DIR}",
            f"--python_out={OUTPUT_DIR}",
            f"--grpc_python_out={OUTPUT_DIR}",
            f"--mypy_out={OUTPUT_DIR}",
            f"--mypy_grpc_out={OUTPUT_DIR}",
            *[str(PROTO_DIR / p) for p in SERVICE_PROTOS],
        ]
        result = _run_command(svc_args, check=False)
        if result.returncode != 0:
            return result.returncode

    _fix_imports()
    return 0


def _fix_imports() -> None:
    """Fix generated import paths to match iris.generated package layout."""
    for pattern in ("*.py", "*.pyi"):
        for generated_file in OUTPUT_DIR.rglob(pattern):
            if "__pycache__" in generated_file.parts:
                continue
            content = generated_file.read_text()
            fixed = content
            for old, new in _IMPORT_FIXES:
                fixed = fixed.replace(old, new)
            if fixed != content:
                generated_file.write_text(fixed)


if __name__ == "__main__":
    sys.exit(main())
