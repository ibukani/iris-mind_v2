"""ランタイム設定ファイルの明示的な初期化。"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from iris.runtime.config.errors import ConfigError

DEFAULT_RUNTIME_CONFIG_PATH = Path(".iris/config/runtime.toml")
_TEMPLATE_PACKAGE = "iris.runtime.config.templates"
_TEMPLATE_NAME = "runtime.example.toml"


@dataclass(frozen=True)
class InitConfigResult:
    """ランタイム設定初期化の結果。"""

    path: Path
    created: bool
    overwritten: bool
    printed: bool = False


def init_runtime_config(
    *,
    path: Path | None = None,
    force: bool = False,
    print_only: bool = False,
) -> InitConfigResult:
    """サンプル TOML からローカルランタイム設定を初期化する。

    Args:
        path: 作成先の TOML パス。省略時は `.iris/config/runtime.toml`。
        force: 既存ファイルを上書きするかどうか。
        print_only: テンプレート内容のみ返すため、ファイルを書かない。

    Returns:
        初期化結果。

    """
    target_path = path or DEFAULT_RUNTIME_CONFIG_PATH

    if print_only:
        _read_template()
        return InitConfigResult(
            path=target_path,
            created=False,
            overwritten=False,
            printed=True,
        )

    if target_path.exists() and not force:
        return InitConfigResult(
            path=target_path,
            created=False,
            overwritten=False,
        )

    template = _read_template()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    overwritten = target_path.exists()
    target_path.write_text(template, encoding="utf-8")
    return InitConfigResult(
        path=target_path,
        created=not overwritten,
        overwritten=overwritten,
    )


def runtime_config_template() -> str:
    """初期化で使う TOML テンプレート内容を返す。

    Returns:
        TOML テンプレート本文。
    """
    return _read_template()


def _read_template() -> str:
    try:
        return _read_template_resource()
    except FileNotFoundError as exc:
        message = f"Runtime config template does not exist: {_TEMPLATE_PACKAGE}/{_TEMPLATE_NAME}"
        raise ConfigError(message) from exc


def _read_template_resource() -> str:
    return resources.files(_TEMPLATE_PACKAGE).joinpath(_TEMPLATE_NAME).read_text(encoding="utf-8")
