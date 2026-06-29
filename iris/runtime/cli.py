"""ランタイムサーバーのコマンドライン境界。"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
from typing import TYPE_CHECKING

from iris.runtime.auth.principals import ClientKind
from iris.runtime.auth.scopes import AuthScope
from iris.runtime.auth.static_tokens import create_static_token
from iris.runtime.config import RuntimeConfigOverrides
from iris.runtime.config.init import init_runtime_config, runtime_config_template
from iris.runtime.ingress.observation_ingress import ObservationCapability

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    ServeRuntime = Callable[
        [str | None, RuntimeConfigOverrides | None],
        Coroutine[object, object, None],
    ]


def run_runtime_cli(serve_runtime: ServeRuntime) -> None:
    """CLI commandを解釈し、対応するランタイム処理を実行する。

    Args:
        serve_runtime: 通常起動時に呼ぶ非同期ランタイム関数。
    """
    args = _runtime_arg_parser().parse_args()

    init_config: bool = args.init_config
    if init_config:
        _run_init_config_command(args)
        return
    auth_command: str | None = args.auth_command
    if auth_command == "create-token":
        _run_auth_create_token_command(args)
        return

    host: str | None = args.host
    port: int | None = args.port
    config_path: str | None = args.config
    overrides = RuntimeConfigOverrides(server_host=host, server_port=port)
    try:
        asyncio.run(serve_runtime(config_path, overrides))
    except KeyboardInterrupt:
        return


def _runtime_arg_parser() -> argparse.ArgumentParser:
    """Runtime server CLI parserを構築する。

    Returns:
        構築済みparser。
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
    create_token_parser.add_argument(
        "--allowed-provider",
        action="append",
        dest="allowed_providers",
        default=None,
    )
    create_token_parser.add_argument(
        "--scope",
        action="append",
        dest="scopes",
        default=None,
    )
    create_token_parser.add_argument(
        "--observation-capability",
        action="append",
        dest="observation_capabilities",
        default=None,
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
    values: list[str] | None = args.allowed_providers
    provider: str | None = args.provider
    if values:
        return frozenset(values)
    if provider is not None:
        return frozenset({provider})
    return frozenset()


def _auth_scopes(args: argparse.Namespace) -> frozenset[AuthScope]:
    values: list[str] | None = args.scopes
    return frozenset(AuthScope(value) for value in values or ())


def _auth_capabilities(args: argparse.Namespace) -> frozenset[ObservationCapability]:
    values: list[str] | None = args.observation_capabilities
    return frozenset(ObservationCapability(value) for value in values or ())


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
