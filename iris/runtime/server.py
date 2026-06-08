"""ランタイムサーバーのエントリポイント。"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    import grpc

from iris.adapters.app_gateway.identity_resolver import AccountBackedIdentityResolver
from iris.adapters.app_gateway.space_resolver import EphemeralSpaceResolver
from iris.adapters.memory.sqlite import SQLiteMemoryStore
from iris.runtime.config import RuntimeConfigOverrides, load_runtime_config
from iris.runtime.config.init import init_runtime_config, runtime_config_template
from iris.runtime.observability.logging import configure_runtime_logging
from iris.runtime.service import IrisRuntimeService
from iris.runtime.wiring.app import build_app_from_config
from iris.runtime.wiring.grpc import create_grpc_server
from iris.runtime.wiring.state import RuntimeStateStores, wire_runtime_state

if TYPE_CHECKING:
    from collections.abc import Sequence

    from iris.runtime.app import IrisApp
    from iris.runtime.config import IrisRuntimeConfig


@dataclass(frozen=True)
class RuntimeComponents:
    """ランタイムサーバー起動前に組み立てるコンポーネント群。"""

    stores: RuntimeStateStores
    runtime_service: IrisRuntimeService
    identity_resolver: AccountBackedIdentityResolver
    space_resolver: EphemeralSpaceResolver


def _fake_embed_text(_text: str) -> Sequence[float]:
    """プレースホルダー埋め込み関数（ハイブリッド検索有効化用）。

    Returns:
        Sequence[float]: 固定ゼロベクトル。
    """
    return [0.0] * 384


def build_runtime_components(config: IrisRuntimeConfig) -> RuntimeComponents:
    """ランタイム設定から永続ストアとサービス境界を組み立てる。

    メモリ検索は ``wire_runtime_state`` で組み立てたメモリストアを
    ``build_app_from_config`` に明示注入する。``FakeMemoryStore`` への
    フォールバックは持たない。
    SQLite バックエンドの場合はハイブリッド検索を有効化する。

    Args:
        config: ランタイム設定。

    Returns:
        ランタイムコンポーネント。
    """
    stores = wire_runtime_state(config)
    embed_text = None
    if isinstance(stores.memory_store, SQLiteMemoryStore):
        embed_text = _fake_embed_text
    app: IrisApp = build_app_from_config(
        config,
        memory_store=stores.memory_store,
        embed_text=embed_text,
    )
    runtime_service = IrisRuntimeService(app)
    identity_resolver = AccountBackedIdentityResolver(account_store=stores.account_store)
    space_resolver = EphemeralSpaceResolver()
    return RuntimeComponents(
        stores=stores,
        runtime_service=runtime_service,
        identity_resolver=identity_resolver,
        space_resolver=space_resolver,
    )


async def serve(
    config_path: str | None = None,
    overrides: RuntimeConfigOverrides | None = None,
) -> None:
    """GRPC ランタイムサーバーを起動する。

    Args:
        config_path: 任意の TOML 設定ファイルパス。
        overrides: 任意のランタイム設定オーバーライド。
    """
    config = load_runtime_config(config_path, overrides=overrides)

    configure_runtime_logging(config.logging)

    logger.info("runtime server starting")
    logger.info("host: {}", config.server.host)
    logger.info("port: {}", config.server.port)
    logger.info("state backend: {}", config.state.backend)
    logger.info("log level: {}", config.logging.level)
    logger.info("log format: {}", config.logging.format)
    if config.logging.file_path:
        logger.info("log file path: {}", config.logging.file_path)

    components = build_runtime_components(config)

    server: grpc.aio.Server = create_grpc_server(
        components.runtime_service,
        host=config.server.host,
        port=config.server.port,
        identity_resolver=components.identity_resolver,
        space_resolver=components.space_resolver,
    )

    await server.start()

    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        logger.info("shutdown requested")
    finally:
        await server.stop(grace=config.server.shutdown_grace_seconds)
        logger.info("shutdown complete")


def main() -> None:
    """ランタイムサーバーの CLI エントリポイント。"""
    parser = argparse.ArgumentParser(description="Iris gRPC Runtime Server")
    parser.add_argument(
        "--config",
        type=str,
        help="Path to TOML configuration file",
    )
    parser.add_argument(
        "--host",
        type=str,
        help="Server host address",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Server port",
    )

    parser.set_defaults(init_config=False)
    subparsers = parser.add_subparsers()
    init_parser = subparsers.add_parser(
        "init-config",
        help="Create a local runtime config from the example template",
    )
    init_parser.add_argument(
        "--path",
        type=Path,
        help="Target TOML configuration path",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the target configuration file if it already exists",
    )
    init_parser.add_argument(
        "--print",
        action="store_true",
        dest="print_only",
        help="Print the configuration template without writing a file",
    )
    init_parser.set_defaults(init_config=True)

    args = parser.parse_args()

    init_config: bool = args.init_config
    if init_config:
        _run_init_config_command(args)
        return

    host: str | None = args.host
    port_val: int | str | None = args.port
    config_path: str | None = args.config

    overrides = RuntimeConfigOverrides(
        server_host=host,
        server_port=int(port_val) if port_val is not None else None,
    )

    try:
        asyncio.run(
            serve(
                config_path=config_path,
                overrides=overrides,
            )
        )
    except KeyboardInterrupt:
        return


def _run_init_config_command(args: argparse.Namespace) -> None:
    target_path: Path | None = args.path
    force: bool = args.force
    print_only: bool = args.print_only

    if print_only:
        sys.stdout.write(runtime_config_template())
        return

    result = init_runtime_config(path=target_path, force=force)
    if result.overwritten:
        message = f"Runtime config overwritten: {result.path}"
    elif result.created:
        message = f"Runtime config created: {result.path}"
    else:
        message = f"Runtime config already exists: {result.path}"
    sys.stdout.write(f"{message}\n")


if __name__ == "__main__":
    main()
