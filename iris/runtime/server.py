"""ランタイムサーバーのエントリポイント。"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Callable

    import grpc

    from iris.adapters.app_gateway.ports import AppActionBroker
    from iris.runtime.app import IrisApp
    from iris.runtime.scheduler.runner import SchedulerRunner

from iris.adapters.app_gateway.identity_resolver import AccountBackedIdentityResolver
from iris.adapters.app_gateway.space_resolver import EphemeralSpaceResolver
from iris.runtime.activity.integrator import ActivityIntegrator
from iris.runtime.config import (
    IrisRuntimeConfig,
    RuntimeConfigOverrides,
    load_runtime_config,
    resolve_runtime_config_path,
)
from iris.runtime.config.init import init_runtime_config, runtime_config_template
from iris.runtime.config.root import all_model_slots_are_fake
from iris.runtime.event_reaction.handler import ActivityEventReactionHandler
from iris.runtime.lifecycle.scheduler_loop import run_scheduler_loop
from iris.runtime.observability.diagnostics import run_startup_diagnostics
from iris.runtime.observability.logging import configure_runtime_logging
from iris.runtime.observations.trust import ObservationTrustPolicy
from iris.runtime.presence.integrator import PresenceIntegrator
from iris.runtime.proactive.target_integrator import ProactiveTargetIntegrator
from iris.runtime.scheduler.availability import DeliveryAvailabilityResolverAdapter
from iris.runtime.service import IntegratingObservationPipeline, IrisRuntimeService
from iris.runtime.spaces.occupancy_integrator import SpaceOccupancyIntegrator
from iris.runtime.wiring.app import build_app_from_config
from iris.runtime.wiring.availability import wire_availability_resolver
from iris.runtime.wiring.context import wire_workspace_context_assembler
from iris.runtime.wiring.delivery import wire_app_action_broker, wire_delivery_safety_gate
from iris.runtime.wiring.event_reaction import wire_event_reaction_runner
from iris.runtime.wiring.grpc import create_grpc_server
from iris.runtime.wiring.scheduler import wire_runtime_scheduler, wire_scheduler_runner
from iris.runtime.wiring.state import RuntimeStateStores, wire_runtime_state
from iris.safety.output_filter import AllowAllOutputGate


@dataclass(frozen=True)
class RuntimeComponents:
    """ランタイムサーバー起動前に組み立てるコンポーネント群。"""

    stores: RuntimeStateStores
    runtime_service: IrisRuntimeService
    identity_resolver: AccountBackedIdentityResolver
    space_resolver: EphemeralSpaceResolver
    app_action_broker: AppActionBroker
    scheduler_runner: SchedulerRunner


def build_runtime_service(
    app: IrisApp,
    stores: RuntimeStateStores,
    *,
    now: Callable[[], datetime] | None = None,
) -> IrisRuntimeService:
    """IrisApp とランタイムstateストアからサービス境界を組み立てる。

    Activity / presence / occupancy 統合、availability 解決、
    workspace context assembly を同一ストアインスタンスで配線する。

    Args:
        app: 観測処理を委譲する IrisApp。
        stores: ランタイムstateストア群。
        now: 現在時刻を返す callable。省略時は UTC now。

    Returns:
        構成済みの IrisRuntimeService。
    """
    trust_policy = ObservationTrustPolicy()
    current_now = now or _utc_now
    activity_integrator = ActivityIntegrator(
        journal=stores.activity_journal,
        projections=stores.activity_projection_store,
        trust_policy=trust_policy,
        now=current_now,
    )
    presence_integrator = PresenceIntegrator(
        store=stores.presence_store,
        trust_policy=trust_policy,
        now=current_now,
    )
    occupancy_integrator = SpaceOccupancyIntegrator(
        store=stores.space_occupancy_store,
        trust_policy=trust_policy,
        now=current_now,
    )
    proactive_target_integrator = ProactiveTargetIntegrator(
        target_store=stores.proactive_target_store,
    )
    availability_resolver = wire_availability_resolver()
    workspace_context_assembler = wire_workspace_context_assembler(
        activity_projection_store=stores.activity_projection_store,
        presence_store=stores.presence_store,
        occupancy_store=stores.space_occupancy_store,
        availability_resolver=availability_resolver,
        now=current_now,
    )
    event_reaction_runner = wire_event_reaction_runner()
    activity_event_reaction_handler = ActivityEventReactionHandler(
        trust_policy=trust_policy,
        runner=event_reaction_runner,
        output_gate=AllowAllOutputGate(),
    )
    return IrisRuntimeService(
        app,
        observation_pipeline=IntegratingObservationPipeline(
            (
                activity_integrator,
                presence_integrator,
                occupancy_integrator,
                proactive_target_integrator,
            )
        ),
        workspace_context_assembler=workspace_context_assembler,
        activity_event_reaction_handler=activity_event_reaction_handler,
    )


def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(UTC)


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
    runtime_service = build_runtime_service(app, stores)
    identity_resolver = AccountBackedIdentityResolver(account_store=stores.account_store)
    space_resolver = EphemeralSpaceResolver()
    app_action_broker = wire_app_action_broker(stores.delivery_outbox, config.delivery)
    delivery_gate = wire_delivery_safety_gate(config.delivery)
    scheduler = wire_runtime_scheduler(stores.proactive_target_store, config)
    availability_resolver = wire_availability_resolver()
    availability_provider = DeliveryAvailabilityResolverAdapter(
        resolver=availability_resolver,
        presence_store=stores.presence_store,
        activity_projection_store=stores.activity_projection_store,
    )
    scheduler_runner = wire_scheduler_runner(
        runtime_service=runtime_service,
        scheduler=scheduler,
        delivery_gate=delivery_gate,
        outbox=stores.delivery_outbox,
        config=config,
        availability_provider=availability_provider,
    )
    return RuntimeComponents(
        stores=stores,
        runtime_service=runtime_service,
        identity_resolver=identity_resolver,
        space_resolver=space_resolver,
        app_action_broker=app_action_broker,
        scheduler_runner=scheduler_runner,
    )


def _log_development_warnings(config: IrisRuntimeConfig) -> None:
    """開発用設定の危険な warning を出力する。

    Args:
        config: ランタイム設定。
    """
    if all_model_slots_are_fake(config):
        msg = (
            "all model slots are using the fake provider; "
            "runtime responses are not backed by a real LLM"
        )
        logger.warning(msg)
    if config.safety.mode == "development":
        logger.warning("safety mode is 'development'; all safety gates are pass-through")


def _log_startup(config: IrisRuntimeConfig, config_path: Path | None) -> None:
    """起動時の設定ログを出力する。

    Args:
        config: ランタイム設定。
        config_path: 解決済み設定ファイルパス。なければ None。
    """
    logger.info("runtime server starting")
    if config_path is None:
        logger.info("config source: built-in defaults; no TOML file found")
    else:
        logger.info("config source: {}", config_path)
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


def _start_scheduler_task(
    components: RuntimeComponents,
    config: IrisRuntimeConfig,
) -> asyncio.Task[None] | None:
    """scheduler.enabled の場合のみ scheduler loop task を起動する。

    Args:
        components: 起動済みランタイムコンポーネント。
        config: ランタイム設定。

    Returns:
        起動した scheduler task。無効時は None。
    """
    if not config.scheduler.enabled:
        return None
    return asyncio.create_task(
        run_scheduler_loop(
            components.scheduler_runner,
            interval_seconds=config.scheduler.interval_seconds,
        )
    )


async def _shutdown(
    server: grpc.aio.Server,
    scheduler_task: asyncio.Task[None] | None,
    grace: float,
) -> None:
    """Scheduler task と gRPC server を安全に停止する。

    Args:
        server: 起動中の gRPC server。
        scheduler_task: 起動中の scheduler task。無ければ None。
        grace: server stop の grace 秒。
    """
    if scheduler_task is not None:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            logger.info("scheduler loop cancelled")
    await server.stop(grace=grace)
    logger.info("shutdown complete")


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
    _log_development_warnings(config)
    _log_startup(config, selected_config_path)

    await run_startup_diagnostics(config)

    components = build_runtime_components(config)

    server: grpc.aio.Server = create_grpc_server(
        components.runtime_service,
        host=config.server.host,
        port=config.server.port,
        app_action_broker=components.app_action_broker,
        identity_resolver=components.identity_resolver,
        space_resolver=components.space_resolver,
    )

    await server.start()
    scheduler_task = _start_scheduler_task(components, config)

    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        logger.info("shutdown requested")
    finally:
        await _shutdown(server, scheduler_task, config.server.shutdown_grace_seconds)


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
