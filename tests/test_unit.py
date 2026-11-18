"""Unit tests for observium-mcp. No database, network, or rrdtool required."""

import subprocess
from unittest import mock

import pytest
from starlette.testclient import TestClient

from observium_mcp import database, http_app, rrd
from observium_mcp import server as srv
from observium_mcp.tools.devices import format_status, format_uptime

TOKEN = "t" * 40


# ---------------------------------------------------------------- database


def test_db_config_tcp_default(monkeypatch):
    for var in ("OBSERVIUM_DB_SOCKET", "OBSERVIUM_DB_HOST", "OBSERVIUM_DB_PORT"):
        monkeypatch.delenv(var, raising=False)
    cfg = database.get_db_config()
    assert cfg["host"] == "localhost" and cfg["port"] == 3306
    assert "unix_socket" not in cfg
    assert cfg["connect_timeout"] == 5


def test_db_config_socket_overrides_host(monkeypatch):
    monkeypatch.setenv("OBSERVIUM_DB_SOCKET", "/run/mysqld/mysqld.sock")
    monkeypatch.setenv("OBSERVIUM_DB_HOST", "ignored.example")
    cfg = database.get_db_config()
    assert cfg["unix_socket"] == "/run/mysqld/mysqld.sock"
    assert "host" not in cfg and "port" not in cfg


def test_check_connection_ok():
    with mock.patch.object(database, "execute_single", return_value={"ok": 1}):
        assert database.check_connection() is True


def test_check_connection_failure_is_false_not_raise():
    with mock.patch.object(database, "execute_single", side_effect=OSError("refused")):
        assert database.check_connection() is False


# ---------------------------------------------------------------- rrd

RRD_FETCH = """                          INOCTETS          OUTOCTETS

1700000000: 1.5000000000e+02 nan
1700000300: -nan 2.0000000000e+01
"""


def test_parse_rrd_output_handles_nan():
    out = rrd.parse_rrd_output(RRD_FETCH)
    assert out["datasources"] == ["INOCTETS", "OUTOCTETS"]
    assert out["timestamps"] == [1700000000, 1700000300]
    assert out["data"] == [[150.0, None], [None, 20.0]]


def test_parse_rrd_info():
    text = 'step = 300\nlast_update = 1700000300\nds[INOCTETS].type = "DERIVE"\n' \
           'ds[INOCTETS].min = 0\nds[OUTOCTETS].type = "DERIVE"\n'
    info = rrd.parse_rrd_info(text)
    assert info == {"datasources": ["INOCTETS", "OUTOCTETS"], "rras": [],
                    "step": 300, "last_update": 1700000300}


def test_list_device_rrd_files_local(tmp_path, monkeypatch):
    monkeypatch.setenv("OBSERVIUM_RRD_PATH", str(tmp_path))
    dev = tmp_path / "sw1.example"
    dev.mkdir()
    (dev / "la.rrd").write_text("")
    (dev / "notes.txt").write_text("")
    assert rrd.list_device_rrd_files("sw1.example") == ["la.rrd"]
    assert rrd.list_device_rrd_files("missing.example") == []


def test_fetch_runs_rrdtool_locally_never_ssh(tmp_path):
    f = tmp_path / "la.rrd"
    f.write_text("")
    done = subprocess.CompletedProcess([], 0, stdout=RRD_FETCH, stderr="")
    with mock.patch.object(rrd.subprocess, "run", return_value=done) as run:
        out = rrd.fetch_rrd_data(str(f), start="-1w")
    cmd = run.call_args.args[0]
    assert cmd[:4] == ["rrdtool", "fetch", str(f), "AVERAGE"]
    assert "ssh" not in cmd and "-1w" in cmd
    assert out["timestamps"] == [1700000000, 1700000300]


def test_fetch_missing_file_reports_error(tmp_path):
    assert "error" in rrd.fetch_rrd_data(str(tmp_path / "nope.rrd"))


def test_no_ssh_helpers_remain():
    for name in ("build_ssh_cmd", "is_remote_mode", "get_ssh_config"):
        assert not hasattr(rrd, name)


# ---------------------------------------------------------------- formatting


@pytest.mark.parametrize("secs,expected", [(None, "Unknown"), (59, "0m"),
                                           (3700, "1h 1m"), (90061, "1d 1h 1m")])
def test_format_uptime(secs, expected):
    assert format_uptime(secs) == expected


def test_format_status():
    assert format_status(1) == "up" and format_status(7) == "unknown (7)"


# ---------------------------------------------------------------- http settings


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("OBSERVIUM_MCP_HOST", "127.0.0.2")
    monkeypatch.setenv("OBSERVIUM_MCP_PORT", "9999")
    monkeypatch.setenv("OBSERVIUM_MCP_TOKEN", TOKEN)
    monkeypatch.setenv("OBSERVIUM_MCP_ALLOWED_HOSTS", "a.example, b.example:*, ")
    s = http_app.HttpSettings.from_env()
    assert (s.host, s.port, s.token) == ("127.0.0.2", 9999, TOKEN)
    assert s.allowed_hosts == ["a.example", "b.example:*"]


@pytest.mark.parametrize("token", ["", "short"])
def test_settings_reject_missing_or_short_token(token):
    with pytest.raises(http_app.ConfigError):
        http_app.HttpSettings(token=token).validate()


def test_run_http_without_token_exits_cleanly(monkeypatch):
    monkeypatch.delenv("OBSERVIUM_MCP_TOKEN", raising=False)
    with pytest.raises(SystemExit, match="OBSERVIUM_MCP_TOKEN"):
        srv.run(["--transport", "http"])


def test_parse_args_env_default_and_flag_override(monkeypatch):
    monkeypatch.setenv("OBSERVIUM_MCP_TRANSPORT", "http")
    assert srv.parse_args([]).transport == "http"
    assert srv.parse_args(["--transport", "stdio"]).transport == "stdio"


def test_instructions_attached_to_server():
    opts = srv.server.create_initialization_options()
    assert opts.instructions and "Observium" in opts.instructions


# ---------------------------------------------------------------- http app / auth


@pytest.fixture
def client():
    app = http_app.create_app(srv.server, http_app.HttpSettings(token=TOKEN))
    with TestClient(app) as c:
        yield c


def test_health_is_open_and_reports_db(client):
    with mock.patch.object(database, "check_connection", return_value=True):
        r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "database": True}


def test_health_503_when_db_down(client):
    with mock.patch.object(database, "check_connection", return_value=False):
        r = client.get("/health")
    assert r.status_code == 503 and r.json()["database"] is False


@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": "Bearer wrong-token"},
    {"Authorization": f"Basic {TOKEN}"},
    {"Authorization": f"Bearer {TOKEN}x"},
])
def test_mcp_rejects_bad_auth(client, headers):
    r = client.post("/mcp", json={}, headers=headers)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_unknown_path_requires_auth_too(client):
    assert client.get("/anything").status_code == 401


def test_mcp_accepts_good_token(client):
    r = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        headers={"Authorization": f"Bearer {TOKEN}",
                 "Accept": "application/json, text/event-stream"},
    )
    assert r.status_code == 200
