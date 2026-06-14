"""監査済み E2E runtime subprocess ポート。

E2E テストスイートで ``subprocess`` モジュールを import するのは
このファイルだけにする。 利用者は ``RuntimeProcess`` 公開 API
(``is_alive()`` / ``returncode`` / ``stop()`` など) だけを扱い、
``subprocess.Popen`` の生 API には触らない。 これにより
Suppression Debt Group 3 / Group 4 の散在する suppression を
このポートに集約する。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os
import shutil
import socket
import subprocess  # noqa: S404 -- audited subprocess port for E2E. ``subprocess`` is intentionally confined to this module.
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

RUNTIME_HOST = "127.0.0.1"
_STOP_TIMEOUT_SECONDS = 5.0
_UV_NOT_FOUND_MESSAGE = "uv executable not found"


@dataclass
class RuntimeProcess:
    """ランタイムサブプロセスの監査済みハンドル。

    ``subprocess.Popen`` のラッパー。 利用者は ``port`` と
    ``returncode`` などの公開フィールド、および ``is_alive()`` /
    ``stop()`` だけを扱う。 ``_process`` は内部実装詳細。
    """

    port: int
    _process: subprocess.Popen[str]
    stdout: str | None = None
    stderr: str | None = None

    @property
    def returncode(self) -> int | None:
        """サブプロセスの終了コードを返す。 生存中は ``None``。"""
        return self._process.returncode

    def is_alive(self) -> bool:
        """サブプロセスが生存している間 ``True`` を返す。

        Returns:
            プロセスが終了していなければ ``True``。
        """
        return self._process.poll() is None

    async def stop(self, *, timeout_seconds: float = _STOP_TIMEOUT_SECONDS) -> tuple[str, str]:
        """サブプロセスを終了し ``(stdout, stderr)`` を返す。

        ``timeout_seconds`` 以内に終了しない場合は ``kill`` で
        強制終了する。 既に終了している場合は ``communicate`` で
        残出力を回収するだけ。

        Returns:
            キャプチャ済み ``stdout`` と ``stderr``。
        """
        if self._process.poll() is None:
            self._process.terminate()
            try:
                stdout, stderr = await asyncio.wait_for(
                    asyncio.to_thread(self._process.communicate),
                    timeout=timeout_seconds,
                )
            except TimeoutError:
                self._process.kill()
                stdout, stderr = await asyncio.to_thread(self._process.communicate)
        else:
            stdout, stderr = await asyncio.to_thread(self._process.communicate)

        self.stdout = stdout
        self.stderr = stderr
        return stdout, stderr


async def stop_runtime_process(
    runtime: RuntimeProcess,
    *,
    timeout_seconds: float = _STOP_TIMEOUT_SECONDS,
) -> tuple[str, str]:
    """``RuntimeProcess.stop()`` の薄いラッパー。

    Returns:
        キャプチャ済み ``stdout`` と ``stderr``。
    """
    return await runtime.stop(timeout_seconds=timeout_seconds)


def find_free_port() -> int:
    """未使用の loopback TCP ポートを返す。

    Returns:
        空き TCP ポート番号。
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((RUNTIME_HOST, 0))
        return int(sock.getsockname()[1])


def start_runtime_process(
    *,
    port: int,
    repo_root: Path,
    runtime_home: Path,
    config_path: Path | None = None,
    extra_env: Mapping[str, str] | None = None,
) -> RuntimeProcess:
    """ランタイムサーバーを実 subprocess として起動する。

    Returns:
        起動したランタイムサブプロセスのハンドル。

    Raises:
        RuntimeError: ``PATH`` 上に ``uv`` が見つからない。
    """
    uv_path = shutil.which("uv")
    if uv_path is None:
        raise RuntimeError(_UV_NOT_FOUND_MESSAGE)

    command = [
        uv_path,
        "run",
        "--project",
        str(repo_root),
        "python",
        "-m",
        "iris.runtime.server",
        "--host",
        RUNTIME_HOST,
        "--port",
        str(port),
    ]
    if config_path is not None:
        command.extend(("--config", str(config_path)))

    process = subprocess.Popen(  # noqa: S603 -- E2E runs a fixed uv command tuple.
        command,
        cwd=runtime_home,
        env=_runtime_env(runtime_home=runtime_home, extra_env=extra_env),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return RuntimeProcess(port=port, _process=process)


def _runtime_env(*, runtime_home: Path, extra_env: Mapping[str, str] | None) -> dict[str, str]:
    """Subprocess 起動用の環境変数を構築する。

    Returns:
        ``IRIS_MIND_CONFIG`` を除去し ``XDG_CONFIG_HOME`` /
        ``HOME`` / ``UV_CACHE_DIR`` を ``runtime_home`` 配下に
        切り替えた環境変数辞書。 ``extra_env`` が指定された場合は
        追加適用する。
    """
    env = os.environ.copy()
    env.pop("IRIS_MIND_CONFIG", None)
    env["XDG_CONFIG_HOME"] = str(runtime_home / "xdg-config")
    env["HOME"] = str(runtime_home / "home")
    env["UV_CACHE_DIR"] = str(runtime_home / "uv-cache")
    if extra_env is not None:
        env.update(extra_env)
    return env
