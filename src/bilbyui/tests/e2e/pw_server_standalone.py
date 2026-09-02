"""Standalone shared Playwright browser server for CI.

Starts one headless Chromium ``launchServer``, prints its WebSocket endpoint to
stdout, and stays alive until SIGTERM/SIGINT. CI exports the printed endpoint
as ``PW_WS_ENDPOINT`` so every parallel Django test worker shares the single
browser server instead of each worker spawning its own Node process + Chromium
(which exhausts container memory and can kill workers mid-run).

Usage (CI, after the Node deps + browser are installed):

    python -m bilbyui.tests.e2e.pw_server_standalone > /tmp/pw_endpoint.txt &
    export PW_WS_ENDPOINT=$(cat /tmp/pw_endpoint.txt)
    bash run_coverage.sh --parallel
"""

import signal
import sys

from bilbyui.tests.e2e.pw_server import start_pw_server, stop_pw_server


def main() -> int:
    server = start_pw_server()
    print(server.ws_endpoint, flush=True)

    def shutdown(_signum, _frame):
        stop_pw_server(server)
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    # Stay alive until terminated by the CI job shell.
    signal.pause()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
