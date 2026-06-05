"""Runtime server entrypoint."""

from __future__ import annotations

import argparse
import asyncio
import logging
from typing import TYPE_CHECKING

from iris.adapters.app_gateway.resolvers import AccountIdentityResolver, EphemeralSpaceResolver
from iris.runtime.config import RuntimeConfigOverrides, load_runtime_config
from iris.runtime.service import IrisRuntimeService
from iris.runtime.wiring.app import build_app_from_config
from iris.runtime.wiring.grpc import create_grpc_server
from iris.runtime.wiring.state import wire_runtime_state

if TYPE_CHECKING:
    import grpc

logger = logging.getLogger(__name__)


async def serve(
    config_path: str | None = None,
    overrides: RuntimeConfigOverrides | None = None,
) -> None:
    """Start the gRPC runtime server.

    Args:
        config_path: Optional path to TOML config file.
        overrides: Optional runtime configuration overrides.
    """
    logging.basicConfig(level=logging.INFO)

    config = load_runtime_config(config_path, overrides=overrides)
    app = build_app_from_config(config)
    runtime_service = IrisRuntimeService(app)

    stores = wire_runtime_state(config)

    identity_resolver = AccountIdentityResolver(
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
    logger.info("Server started on %s:%d", config.server.host, config.server.port)

    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        logger.info("Server shutdown requested")
    finally:
        await server.stop(grace=config.server.shutdown_grace_seconds)
        logger.info("Server shut down")


def main() -> None:
    """CLI entrypoint for the runtime server."""
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
