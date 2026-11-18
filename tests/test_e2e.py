"""End-to-end tests: real MCP clients against the real transports.

HTTP: uvicorn on a random loopback port in a background thread, database
mocked in-process. stdio: the server as a subprocess pointed at a closed
port, proving it starts, lists tools, and turns DB failure into a tool error.
No external services are contacted.
"""

import json
import os
import socket
import sys
import threading
import time
from unittest import mock

import httpx
import pytest
import uvicorn
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client  # deprecated alias, still supported in 1.x

from observium_mcp import http_app
from observium_mcp import server as srv

TOKEN = "e2e-" + "x" * 40

FAKE_DEVICES = [{
    "device_id": 34, "hostname": "sw16.example", "sysName": "sw16", "os": "unifi-switch",
    "version": "7.5.15", "hardware": "USL16PB", "status": 1, "uptime": 402838,
    "last_polled": "2026-11-18 12:00:00", "location": "basement",
}]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def http_server():
    port = _free_port()
    app = http_app.create_app(srv.server, http_app.HttpSettings(port=port, token=TOKEN))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("uvicorn did not start")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


async def test_http_full_session(http_server):
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with mock.patch("observium_mcp.tools.devices.execute_query", return_value=FAKE_DEVICES):
        async with streamablehttp_client(f"{http_server}/mcp", headers=headers) as (r, w, _):
            async with ClientSession(r, w) as session:
                init = await session.initialize()
                assert init.serverInfo.name == "observium-mcp"
                assert "Observium" in (init.instructions or "")

                tools = {t.name for t in (await session.list_tools()).tools}
                assert {"list_devices", "get_port_traffic", "get_trends"} <= tools

                result = await session.call_tool("list_devices", {})
                payload = json.loads(result.content[0].text)
                devices = payload["devices"] if isinstance(payload, dict) else payload
                assert devices[0]["hostname"] == "sw16.example"
                assert devices[0]["status"] == "up"


async def test_http_rejects_missing_token(http_server):
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{http_server}/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert r.status_code == 401


async def test_http_health_over_socket(http_server):
    with mock.patch("observium_mcp.database.check_connection", return_value=True):
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{http_server}/health")
    assert r.status_code == 200 and r.json()["database"] is True


async def test_stdio_starts_and_reports_db_error():
    env = {
        **os.environ,
        "OBSERVIUM_DB_HOST": "127.0.0.1",
        "OBSERVIUM_DB_PORT": str(_free_port()),  # nothing listening
        "OBSERVIUM_DB_CONNECT_TIMEOUT": "2",
        "OBSERVIUM_DB_SOCKET": "",
        "OBSERVIUM_MCP_TRANSPORT": "stdio",
    }
    params = StdioServerParameters(command=sys.executable,
                                   args=["-m", "observium_mcp.server"], env=env)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            assert "list_devices" in {t.name for t in (await session.list_tools()).tools}
            result = await session.call_tool("list_devices", {})
            assert "error" in json.loads(result.content[0].text)
