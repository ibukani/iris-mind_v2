"""ランタイムサーバーのエントリポイント。"""

from __future__ import annotations

import argparse
import asyncio
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    import grpc

from iris.adapters.app_gateway.identity_resolver import AccountBackedIdentityResolver
from iris.adapters.app_gateway.space_resolver import EphemeralSpaceResolver
from iris.runtime.config import RuntimeConfigOverrides, load_runtime_config
from iris.runtime.observability.logging import configure_runtime_logging
from iris.runtime.service import IrisRuntimeService
from iris.runtime.wiring.app import build_app_from_config
from iris.runtime.wiring.grpc import create_grpc_server
from iris.runtime.wiring.state import wire_runtime_state


async def serve(
    config_path: str | None = None,
    overrides: RuntimeConfigOverrides | None = None,
) -> None:
    """gRPC ランタイムサーバーを起動する。

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
    app = build_app_from_config(config)
    runtime_service = IrisRuntimeService(app)

    stores = wire_runtime_state(config)

    identity_resolver = AccountBackedIdentityResolver(
        account_store=stores.account_store,
    )
    space_resolver = EphemeralSpaceResolver()

    server: grpc.aio.Server = create_grpc_server(
        runtime_service,
        host=config.server.host,
        port=config.server.port,
        identity_resolver=identity_resolver,
        space_resolver=space_resolver,
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

    args = parser.parse_args()

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


if __name__ == "__main__":
    main()
