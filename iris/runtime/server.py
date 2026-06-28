"""ランタイムサーバーのエントリポイント。"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    import grpc

    from iris.adapters.app_gateway.ports import AppActionBroker
    from iris.runtime.app import IrisApp
    from iris.runtime.output_pipeline import RuntimeOutputPipeline
    from iris.runtime.scheduler.runner import SchedulerRunner

from iris.adapters.app_gateway.identity_resolver import AccountBackedIdentityResolver
from iris.adapters.app_gateway.space_resolver import EphemeralSpaceResolver
from iris.core.datetime_utils import now_utc
from iris.runtime.auth.principals import ClientKind
from iris.runtime.auth.scopes import AuthScope
from iris.runtime.auth.static_tokens import create_static_token
from iris.runtime.config import (
    IrisRuntimeConfig,
    RuntimeConfigOverrides,
    load_runtime_config,
    resolve_runtime_config_path,
)
from iris.runtime.config.auth import load_token_verifier_from_runtime_env
from iris.runtime.config.init import init_runtime_config, runtime_config_template
from iris.runtime.config.root import all_model_slots_are_fake
from iris.runtime.ingress.activity_event_reaction import ActivityEventReactionHandler
from iris.runtime.ingress.observation_ingress import ObservationCapability
from iris.runtime.ingress.observation_trust import ObservationTrustPolicy
from iris.runtime.lifecycle.scheduler_loop import run_scheduler_loop
from iris.runtime.observability.diagnostics import run_startup_diagnostics
from iris.runtime.observability.events import LoggingRuntimeObservationObserver
from iris.runtime.observability.logging import configure_runtime_logging
from iris.runtime.scheduler.availability import DeliveryAvailabilityResolverAdapter
from iris.runtime.service import IntegratingObservationPipeline, IrisRuntimeService
from iris.runtime.state.activity_integrator import ActivityIntegrator
from iris.runtime.state.presence_integrator import PresenceIntegrator
from iris.runtime.state.scheduler_target_integrator import SchedulerTargetIntegrator
from iris.runtime.state.space_occupancy_integrator import SpaceOccupancyIntegrator
from iris.runtime.wiring.app import AppStateDependencies, build_app_from_config
from iris.runtime.wiring.availability import wire_availability_resolver
from iris.runtime.wiring.context import wire_workspace_context_assembler
from iris.runtime.wiring.delivery import wire_app_action_broker, wire_delivery_safety_gate
from iris.runtime.wiring.event_reaction import wire_event_reaction_decision_pipeline
from iris.runtime.wiring.features import RuntimeFeatureCatalog, wire_runtime_features
from iris.runtime.wiring.grpc import create_grpc_server
from iris.runtime.wiring.presentation import wire_output_pipeline
from iris.runtime.wiring.scheduler import wire_runtime_scheduler, wire_scheduler_runner
from iris.runtime.wiring.state import RuntimeStateStores, wire_runtime_state


@dataclass(frozen=True)
class RuntimeComponents:
    """ランタイムサーバー起動前に組み立てるコンポーネント群。"""

    stores: RuntimeStateStores
    runtime_service: IrisRuntimeService
    identity_resolver: AccountBackedIdentityResolver
    space_resolver: EphemeralSpaceResolver
    app_action_broker: AppActionBroker | None
    scheduler_runner: SchedulerRunner


def build_runtime_service(
    app: IrisApp,
    stores: RuntimeStateStores,
    *,
    feature_catalog: RuntimeFeatureCatalog,
    output_pipeline: RuntimeOutputPipeline,
    target_stale_after_seconds: float,
    now: Callable[[], datetime] | None = None,
) -> IrisRuntimeService:
    """IrisApp とランタイムstateストアからサービス境界を組み立てる。

    Activity / presence / occupancy 統合、availability 解決、
    workspace context assembly を同一ストアインスタンスで配線する。

    Args:
        app: アプリケーション定義。
        stores: ランタイムstateストア。
        feature_catalog: 有効なフィーチャー定義の集合。
        output_pipeline: presentation と safety を適用する共有出力境界。
        target_stale_after_seconds: target が stale になるまでの idle 秒数。
        now: 現在時刻を返す関数。省略時は `datetime.now(UTC)`。

    Returns:
        構成済みの IrisRuntimeService。
    """
    trust_policy = ObservationTrustPolicy()
    current_now = now or now_utc
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
    scheduler_target_integrator = SchedulerTargetIntegrator(
        target_store=stores.scheduler_target_store,
        target_stale_after_seconds=target_stale_after_seconds,
    )
    availability_resolver = wire_availability_resolver()
    workspace_context_assembler = wire_workspace_context_assembler(
        activity_projection_store=stores.activity_projection_store,
        presence_store=stores.presence_store,
        occupancy_store=stores.space_occupancy_store,
        availability_resolver=availability_resolver,
        now=current_now,
    )
    decision_pipeline = wire_event_reaction_decision_pipeline(feature_catalog.features)
    activity_event_reaction_handler = ActivityEventReactionHandler(
        trust_policy=trust_policy,
        decision_pipeline=decision_pipeline,
        output_pipeline=output_pipeline,
    )
    return IrisRuntimeService(
        app,
        observation_pipeline=IntegratingObservationPipeline(
            (
                activity_integrator,
                presence_integrator,
                occupancy_integrator,
                scheduler_target_integrator,
            )
        ),
        workspace_context_assembler=workspace_context_assembler,
        activity_event_reaction_handler=activity_event_reaction_handler,
        observation_observer=LoggingRuntimeObservationObserver(),
    )


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
    feature_catalog = wire_runtime_features()
    output_pipeline = wire_output_pipeline(safety_config=config.safety)
    runtime_service = build_runtime_service(
        build_app_from_config(
            config,
            state=AppStateDependencies(
                memory_store=stores.memory_store,
                relationship_store=stores.relationship_store,
                affect_store=stores.affect_store,
            ),
            output_pipeline=output_pipeline,
            features=feature_catalog.features,
        ),
        stores,
        feature_catalog=feature_catalog,
        output_pipeline=output_pipeline,
        target_stale_after_seconds=config.scheduler.target_stale_after_seconds,
    )
    identity_resolver = AccountBackedIdentityResolver(account_store=stores.account_store)
    space_resolver = EphemeralSpaceResolver()
    app_action_broker = (
        wire_app_action_broker(stores.delivery_outbox, config.delivery)
        if config.delivery.enabled
        else None
    )
    delivery_gate = wire_delivery_safety_gate(config.delivery)
    scheduler = wire_runtime_scheduler(stores.scheduler_target_store, config)
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
        auth_config=config.auth,
        token_verifier=load_token_verifier_from_runtime_env(config.auth),
        tls_config=config.server.tls,
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
    parser = _runtime_arg_parser()
    args = parser.parse_args()

    init_config: bool = args.init_config
    if init_config:
        _run_init_config_command(args)
        return
    auth_command: str | None = args.auth_command
    if auth_command == "create-token":
        _run_auth_create_token_command(args)
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


def _runtime_arg_parser() -> argparse.ArgumentParser:
    """Runtime server CLI parser を構築する。

    Returns:
        構築済み parser。
    """
    parser = argparse.ArgumentParser(description="Iris gRPC Runtime Server")
    parser.add_argument(
        "--config",
        type=str,
        help="Use TOML configuration file instead of default discovery",
    )
    parser.add_argument("--host", type=str, help="Server host address")
    parser.add_argument("--port", type=int, help="Server port")
    parser.set_defaults(init_config=False, auth_command=None)

    subparsers = parser.add_subparsers()

    # init-config
    init_parser: argparse.ArgumentParser = subparsers.add_parser(
        "init-config",
        help="Create local runtime config example template",
    )
    init_parser.add_argument("--path", type=Path, help="Target TOML configuration path")
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite target configuration file if it already exists",
    )
    init_parser.add_argument(
        "--print",
        action="store_true",
        dest="print_only",
        help="Print configuration template without writing file",
    )
    init_parser.set_defaults(init_config=True)

    # auth
    auth_parser: argparse.ArgumentParser = subparsers.add_parser(
        "auth",
        help="Runtime auth utilities",
    )
    auth_subparsers = auth_parser.add_subparsers(dest="auth_command")
    create_token_parser: argparse.ArgumentParser = auth_subparsers.add_parser(
        "create-token",
        help="Create static bearer token env entry",
    )
    create_token_parser.add_argument("--client-id", required=True)
    client_kind_choices: list[str] = [kind.value for kind in ClientKind]
    create_token_parser.add_argument(
        "--client-kind",
        choices=client_kind_choices,
        default=ClientKind.EXTERNAL_CLIENT.value,
    )
    create_token_parser.add_argument("--provider")
    empty_str_list: list[str] = []
    create_token_parser.add_argument(
        "--allowed-provider",
        action="append",
        dest="allowed_providers",
        default=empty_str_list,
    )
    create_token_parser.add_argument(
        "--scope",
        action="append",
        dest="scopes",
        default=empty_str_list,
    )
    create_token_parser.add_argument(
        "--observation-capability",
        action="append",
        dest="observation_capabilities",
        default=empty_str_list,
    )

    return parser


def _run_auth_create_token_command(args: argparse.Namespace) -> None:
    client_id: str = args.client_id
    client_kind: str = args.client_kind
    provider: str | None = args.provider
    generated = create_static_token(
        client_id=client_id,
        client_kind=ClientKind(client_kind),
        provider=provider,
        allowed_providers=_auth_allowed_providers(args),
        scopes=_auth_scopes(args),
        observation_capabilities=_auth_capabilities(args),
    )
    sys.stdout.write(f"{generated.raw_token}\n")
    sys.stdout.write(f"{generated.token_sha256}\n")
    sys.stdout.write(f"{generated.entry_json}\n")
    json.loads(generated.entry_json)


def _auth_allowed_providers(args: argparse.Namespace) -> frozenset[str]:
    values: list[str] = args.allowed_providers
    provider: str | None = args.provider
    if values:
        return frozenset(values)
    if provider is not None:
        return frozenset({provider})
    return frozenset()


def _auth_scopes(args: argparse.Namespace) -> frozenset[AuthScope]:
    values: list[str] = args.scopes
    return frozenset(AuthScope(value) for value in values)


def _auth_capabilities(args: argparse.Namespace) -> frozenset[ObservationCapability]:
    values: list[str] = args.observation_capabilities
    return frozenset(ObservationCapability(value) for value in values)


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
