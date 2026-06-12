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
from iris.runtime.config import (
    IrisRuntimeConfig,
    RuntimeConfigOverrides,
    load_runtime_config,
    resolve_runtime_config_path,
)
from iris.runtime.config.init import init_runtime_config, runtime_config_template
from iris.runtime.config.root import all_model_slots_are_fake
from iris.runtime.observability.logging import configure_runtime_logging
from iris.runtime.service import IrisRuntimeService
from iris.runtime.wiring.app import build_app_from_config
from iris.runtime.wiring.grpc import create_grpc_server
from iris.runtime.wiring.state import RuntimeStateStores, wire_runtime_state

if TYPE_CHECKING:
    from iris.runtime.app import IrisApp


@dataclass(frozen=True)
class RuntimeComponents:
    """ランタイムサーバー起動前に組み立てるコンポーネント群。"""

    stores: RuntimeStateStores
    runtime_service: IrisRuntimeService
    identity_resolver: AccountBackedIdentityResolver
    space_resolver: EphemeralSpaceResolver


def build_runtime_components(config: IrisRuntimeConfig) -> RuntimeComponents:
    """ランタイム設定から永続ストアとサービス境界を組み立てる。

    ``wire_runtime_state`` で組み立てたメモリストアを
    ``build_app_from_config`` に明示注入する。``FakeMemoryStore`` への
    フォールバックは持たない。
    埋め込み関数が構成されていない場合、SQLite は FTS5 専用検索を使う。

    Args:
        config: ランタイム設定。

    Returns:
        ランタイムコンポーネント。
    """
    stores = wire_runtime_state(config)
    app: IrisApp = build_app_from_config(
        config,
        memory_store=stores.memory_store,
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
    selected_config_path = resolve_runtime_config_path(config_path)
    config = load_runtime_config(selected_config_path, overrides=overrides)

    configure_runtime_logging(config.logging)

    if all_model_slots_are_fake(config):
        msg = (
            "all model slots are using the fake provider; "
            "runtime responses are not backed by a real LLM"
        )
        logger.warning(msg)

    if config.safety.mode == "development":
        logger.warning("safety mode is 'development'; all safety gates are pass-through")

    logger.info("runtime server starting")
    if selected_config_path is None:
        logger.info("config source: built-in defaults; no TOML file found")
    else:
        logger.info("config source: {}", selected_config_path)
        if selected_config_path.name == "llm.toml":
            logger.warning(
                "legacy config filename llm.toml is deprecated; rename it to runtime.toml"
            )
    logger.info("config source policy: single TOML < environment < CLI")
    logger.info("host: {}", config.server.host)
    logger.info("port: {}", config.server.port)
    logger.info("state backend: {}", config.state.backend)
    logger.info("default_chat provider: {}", config.models.default_chat.provider)
    logger.info("fast_judge provider: {}", config.models.fast_judge.provider)
    logger.info("reasoning provider: {}", config.models.reasoning.provider)
    logger.info("log level: {}", config.logging.level)
    logger.info("log format: {}", config.logging.format)
    logger.info("safety mode: {}", config.safety.mode)
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
        help="Use this TOML configuration file instead of default discovery",
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
    sys.stdout.write(
        "".join(
            (
                f"{message}\n",
                "Iris-Mind will load this file automatically on normal startup.\n",
                "Use --config PATH to run with a different config file.\n",
            ),
        ),
    )


if __name__ == "__main__":
    main()
