"""Architecture tests で使う repository path 定数。"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
IRIS_ROOT = PROJECT_ROOT / "iris"
