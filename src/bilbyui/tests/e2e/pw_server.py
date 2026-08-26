"""
Lifecycle for the shared Playwright Node.js browser server.

One headless Chromium is started via ``chromium.launchServer()`` and shared by
every e2e test in the process over a WebSocket endpoint. The Node side of
Playwright is installed into ``<repo-root>/.playwright/`` on first use; the
install is skipped entirely when the installed version already matches the
Python ``playwright`` package and axe-core is present.
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path


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
        subprocess.run(["node", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise RuntimeError(
            "Node.js is not installed but is required to run e2e tests.\n"
            "On Ubuntu/Debian: sudo apt install nodejs npm\n"
            "On macOS: brew install node"
        ) from e


def _read_installed_version(playwright_dir: Path) -> str | None:
    package_json = playwright_dir / "node_modules" / "playwright" / "package.json"
    if not package_json.exists():
        return None
    with contextlib.suppress(OSError, json.JSONDecodeError):
        return json.loads(package_json.read_text(encoding="utf-8")).get("version")
    return None


def _ensure_playwright_installed() -> Path:
    """
    Ensure Node playwright (matching the Python package) and axe-core are installed.

    Returns the dependency directory. Re-runs ``npm install`` only when the
    installed playwright version differs from the Python package or axe-core
    is missing, so parallel workers and repeat runs stay cheap.
    """
    python_version = _get_python_playwright_version()
    _check_node_available()

    playwright_dir = get_playwright_dir()
    playwright_dir.mkdir(exist_ok=True)

    axe_core_marker = playwright_dir / "node_modules" / "axe-core" / "package.json"
    if _read_installed_version(playwright_dir) == python_version and axe_core_marker.exists():
        return playwright_dir

    package_json = playwright_dir / "package.json"
    if not package_json.exists():
        package_json.write_text('{"name": "e2e-test-deps", "private": true}\n')

    print(f"Installing Node playwright v{python_version} and axe-core...", file=sys.stderr)
    result = subprocess.run(
        ["npm", "install", "--no-audit", "--no-fund", f"playwright@{python_version}", "axe-core"],
        cwd=playwright_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to install e2e Node dependencies:\n{result.stderr}")

    return playwright_dir


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
