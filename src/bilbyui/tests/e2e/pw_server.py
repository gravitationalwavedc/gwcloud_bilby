"""
Lifecycle for the shared Playwright Node.js browser server.

One headless Chromium is started via ``chromium.launchServer()`` and shared by
every e2e test in the process over a WebSocket endpoint. The Node side of
Playwright is installed into ``<repo-root>/.playwright/`` on first use.

Dependencies are pinned exactly: ``playwright`` is pinned to the Python
package version and ``axe-core`` to :data:`AXE_CORE_VERSION`. The npm install
runs with ``--ignore-scripts`` (no lifecycle scripts execute in the privileged
CI environment), ``--no-audit`` and ``--no-fund``. Parallel workers serialize
the install with an advisory file lock and re-check before installing, so the
shared tree is mutated by at most one npm process at a time.

Node.js 20 or later is required: Playwright 1.62 drops support for older
runtimes, so :func:`_check_node_available` rejects any Node major version
below 20 before the browser server is started.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

AXE_CORE_VERSION = "4.10.3"
"""Exact axe-core version installed alongside Playwright for e2e scans."""

_INSTALL_LOCK_TIMEOUT_SECONDS = 300
"""How long a worker waits for another worker's npm install before proceeding."""


@dataclass
class PWServerProc:
    """Handle for a running Playwright Node.js server process."""

    proc: subprocess.Popen[str]
    ws_endpoint: str


def get_repo_root() -> Path:
    """Return the repository root (the directory containing TESTING.md)."""
    return Path(__file__).resolve().parents[4]


def get_playwright_dir() -> Path:
    """Return the directory where Node-side test dependencies are installed."""
    return get_repo_root() / ".playwright"


def _get_python_playwright_version() -> str:
    try:
        return version("playwright")
    except Exception as e:
        raise RuntimeError("The Python 'playwright' package is required for e2e tests.") from e


def _check_node_available() -> None:
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            check=True,
            text=True,
        )
        node_version = result.stdout.strip().removeprefix("v")
        node_major = int(node_version.split(".", maxsplit=1)[0])
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as e:
        raise RuntimeError("Node.js 20 or later is required to run e2e tests.") from e

    if node_major < 20:
        raise RuntimeError(f"Node.js 20 or later is required to run e2e tests; found {node_version}.")


def _read_installed_version(playwright_dir: Path, package: str) -> str | None:
    package_json = playwright_dir / "node_modules" / package / "package.json"
    if not package_json.exists():
        return None
    with contextlib.suppress(OSError, json.JSONDecodeError):
        return json.loads(package_json.read_text(encoding="utf-8")).get("version")
    return None


def _deps_satisfied(playwright_dir: Path, python_version: str) -> bool:
    """Return True when installed Node deps match the exact pinned versions."""
    if _read_installed_version(playwright_dir, "playwright") != python_version:
        return False
    return _read_installed_version(playwright_dir, "axe-core") == AXE_CORE_VERSION


def _run_npm_install(playwright_dir: Path, python_version: str) -> None:
    """Run the pinned, lifecycle-script-free npm install into ``playwright_dir``."""
    package_json = playwright_dir / "package.json"
    if not package_json.exists():
        package_json.write_text('{"name": "e2e-test-deps", "private": true}\n')

    print(
        f"Installing Node playwright v{python_version} and axe-core v{AXE_CORE_VERSION}...",
        file=sys.stderr,
    )
    result = subprocess.run(
        [
            "npm",
            "install",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
            "--save-exact",
            f"playwright@{python_version}",
            f"axe-core@{AXE_CORE_VERSION}",
        ],
        cwd=playwright_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to install e2e Node dependencies:\n{result.stderr}")


def _ensure_playwright_installed() -> Path:
    """
    Ensure Node playwright (matching the Python package) and axe-core are installed.

    Returns the dependency directory. Re-runs ``npm install`` only when the
    installed playwright version differs from the Python package or the
    installed axe-core version differs from :data:`AXE_CORE_VERSION`. Parallel
    workers serialize the install with an advisory file lock
    (``.playwright/.install.lock``) and double-check before installing, so the
    shared tree is mutated by at most one npm process at a time.
    """
    python_version = _get_python_playwright_version()
    _check_node_available()

    playwright_dir = get_playwright_dir()
    playwright_dir.mkdir(exist_ok=True)

    if _deps_satisfied(playwright_dir, python_version):
        return playwright_dir

    lock_path = playwright_dir / ".install.lock"
    with open(lock_path, "w") as lock_file:
        _acquire_install_lock(lock_file)
        try:
            # Double-checked locking: another worker may have finished the
            # install while we waited for the lock.
            if _deps_satisfied(playwright_dir, python_version):
                return playwright_dir
            _run_npm_install(playwright_dir, python_version)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    return playwright_dir


def _acquire_install_lock(lock_file) -> None:
    """Block on the install lock (with a timeout), then proceed regardless."""
    deadline = time.monotonic() + _INSTALL_LOCK_TIMEOUT_SECONDS
    while True:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError:
            if time.monotonic() >= deadline:
                # Give up waiting; npm install is idempotent so proceeding is safe.
                return
            time.sleep(0.2)


LAUNCH_SERVER_MJS = """
import { chromium } from 'playwright';

const server = await chromium.launchServer({ headless: true });

console.log(server.wsEndpoint());

async function shutdown() {
  try { await server.close(); } catch {}
  process.exit(0);
}

process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);

await new Promise(() => {});
"""


def start_pw_server() -> PWServerProc:
    """Start one shared headless Chromium launchServer and return its handle."""
    playwright_dir = _ensure_playwright_installed()

    wrapper_script = playwright_dir / "launch_server.mjs"
    wrapper_script.write_text(LAUNCH_SERVER_MJS)

    proc = subprocess.Popen(
        ["node", "launch_server.mjs"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        cwd=playwright_dir,
    )

    assert proc.stdout is not None
    ws = proc.stdout.readline().strip()

    if not ws:
        err = ""
        if proc.stderr is not None:
            err = proc.stderr.read(4000)
        raise RuntimeError(f"Failed to start the Playwright browser server.\n{err}")

    return PWServerProc(proc=proc, ws_endpoint=ws)


def stop_pw_server(server: PWServerProc | None) -> None:
    """Terminate a server previously returned by :func:`start_pw_server`."""
    if not server:
        return
    try:
        server.proc.terminate()
        server.proc.wait(timeout=10)
    except (subprocess.TimeoutExpired, ProcessLookupError, OSError):
        with contextlib.suppress(subprocess.TimeoutExpired, ProcessLookupError, OSError):
            server.proc.kill()
