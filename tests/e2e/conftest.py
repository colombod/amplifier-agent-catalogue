"""E2E test configuration - starts a real server."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time

import pytest


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def server_url():
    """Start the Agent Catalogue server for E2E tests."""
    port = _find_free_port()
    url = f"http://127.0.0.1:{port}"

    # Start server as subprocess
    env = {**os.environ, "AS_PORT": str(port)}
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "agent_catalogue.api:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    # Wait for server to be ready
    for _ in range(30):
        try:
            import httpx

            resp = httpx.get(f"{url}/api/agents", timeout=2)
            if resp.status_code == 200:
                break
        except Exception:
            time.sleep(1)
    else:
        proc.kill()
        stdout = proc.stdout.read().decode() if proc.stdout else ""
        pytest.fail(f"Server failed to start. Output:\n{stdout}")

    yield url

    proc.terminate()
    proc.wait(timeout=10)
