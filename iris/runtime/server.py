"""ランタイムサーバーのエントリポイント。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from pathlib import Path

    import grpc
from iris.runtime.cli import run_runtime_cli
from iris.runtime.config import (
    IrisRuntimeConfig,
    RuntimeConfigOverrides,
    load_runtime_config,
    resolve_runtime_config_path,
)
from iris.runtime.config.auth import load_token_verifier_from_runtime_env
from iris.runtime.config.root import all_model_slots_are_fake
from iris.runtime.lifecycle.background_job_loop import run_background_job_loop
from iris.runtime.lifecycle.scheduler_loop import run_scheduler_loop
from iris.runtime.observability.diagnostics import run_startup_diagnostics
from iris.runtime.observability.logging import configure_runtime_logging
from iris.runtime.wiring.grpc import create_grpc_server
from iris.runtime.wiring.runtime import (
    RuntimeComponents,
    build_runtime_components,
    build_runtime_service,
)

__all__ = ["build_runtime_components", "build_runtime_service", "main", "serve"]


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


def _start_background_job_task(
    components: RuntimeComponents,
    config: IrisRuntimeConfig,
) -> asyncio.Task[None] | None:
    """設定で有効な場合だけ background job loop を起動する。

    Returns:
        起動した task。無効時は None。
    """
    if not config.learning.enabled or not config.learning.background_jobs_enabled:
        return None
    return asyncio.create_task(
        run_background_job_loop(
            components.background_job_runner,
            interval_seconds=config.learning.background_job_interval_seconds,
        )
    )


async def _shutdown(
    server: grpc.aio.Server,
    scheduler_task: asyncio.Task[None] | None,
    background_job_task: asyncio.Task[None] | None,
    grace: float,
) -> None:
    """Scheduler task と gRPC server を安全に停止する。

    Args:
        server: 起動中の gRPC server。
        scheduler_task: 起動中の scheduler task。無ければ None。
        background_job_task: 起動中の background job task。無ければ None。
        grace: server stop の grace 秒。
    """
    if scheduler_task is not None:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            logger.info("scheduler loop cancelled")
    if background_job_task is not None:
        background_job_task.cancel()
        try:
            await background_job_task
        except asyncio.CancelledError:
            logger.info("background job loop cancelled")
    await server.stop(grace=grace)
    logger.info("shutdown complete")


def _create_runtime_server(
    components: RuntimeComponents,
    config: IrisRuntimeConfig,
) -> grpc.aio.Server:
    """Runtime components から gRPC server を組み立てる。

    Returns:
        構成済みの gRPC server。
    """
    return create_grpc_server(
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


async def _run_runtime_server(
    server: grpc.aio.Server,
    components: RuntimeComponents,
    config: IrisRuntimeConfig,
) -> None:
    """Scheduler task と gRPC server の待受けを管理する。"""
    await server.start()
    scheduler_task = _start_scheduler_task(components, config)
    background_job_task = _start_background_job_task(components, config)

    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        logger.info("shutdown requested")
    finally:
        await _shutdown(
            server,
            scheduler_task,
            background_job_task,
            config.server.shutdown_grace_seconds,
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
    _log_development_warnings(config)
    _log_startup(config, selected_config_path)

    await run_startup_diagnostics(config)

    components = build_runtime_components(config)

    server = _create_runtime_server(components, config)
    await _run_runtime_server(server, components, config)


def main() -> None:
    """ランタイムサーバーの CLI エントリポイント。"""
    run_runtime_cli(serve)


if __name__ == "__main__":
    main()
