# Observium MCP Server

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that exposes [Observium CE](https://www.observium.org/) network monitoring data to LLMs like Claude, enabling natural language queries about device status, network traffic, sensor readings, alerts, and historical trends.

## Features

- **Device Management**: List and query monitored devices with status, uptime, and hardware info
- **Network Ports**: View interface status, traffic rates, and utilization
- **Sensors**: Access temperature, voltage, frequency, and other sensor data
- **Alerts**: Query active and historical alerts with summaries
- **Trends**: Retrieve historical metrics from RRD data (load, CPU, memory)
- ✨ **NEW (0.2.0) — HTTP service mode**: run the server *on the Observium host* as a systemd
  service speaking MCP streamable HTTP, so clients connect by URL. No SSH tunnel, no exposed
  database port, RRD files read from local disk. Bearer-token auth plus an open `/health` endpoint.

## How it fits together

```
MCP client (Claude Code, any machine on your tailnet/LAN)
   │  MCP streamable HTTP  +  Authorization: Bearer <token>
   ▼
Observium host
   ├─ tailscale serve :8765  ──►  observium-mcp on 127.0.0.1:18765  (systemd)
   ├─ MariaDB via unix socket, read-only account (SELECT on observium.*)
   └─ /opt/observium/rrd read locally with the rrdtool CLI
```

The server also still speaks **stdio** for local use (a client on the Observium host itself, or
development).

## Requirements

- Observium CE with MySQL/MariaDB
- `rrdtool` CLI on the Observium host (`apt install rrdtool`)
- For the service install: Linux with systemd, `tailscale`, `curl`, `openssl`, `rsync`
- Python 3.10+ (the installer fetches its own pinned, uv-managed Python 3.13 — the OS Python is not used)
- `mcp` SDK **1.x** (`>=1.26,<2`). 2.x removed the low-level decorator API this server uses.

## Install as a service (recommended)

On the Observium host:

```bash
git clone https://github.com/kdesch5000/observium-mcp.git
cd observium-mcp
sudo ./deploy/install.sh
```

`deploy/install.sh` is idempotent (re-run it to upgrade). It:

1. creates a `observium-mcp` system user (no shell, no home);
2. installs a pinned, checksum-verified `uv` and a uv-managed Python under `/opt/observium-mcp`
   — so an OS release upgrade that replaces `/usr/bin/python3` can't break the venv;
3. copies the app to `/opt/observium-mcp/app` and builds `/opt/observium-mcp/venv`;
4. on first run, writes `/etc/observium-mcp/observium-mcp.env` (mode 0640) with a random bearer
   token and DB password, and creates the read-only MariaDB account `observium_mcp@localhost`;
5. installs and starts `observium-mcp.service` (sandboxed: `ProtectSystem=strict`, no capabilities,
   loopback + unix socket only) and checks `/health`;
6. runs `tailscale serve --bg --http=8765 http://127.0.0.1:18765`, publishing it to the tailnet only.

Overrides: `OBSERVIUM_MCP_PORT`, `OBSERVIUM_MCP_TS_PORT`, `OBSERVIUM_DB_SOCKET`, `OBSERVIUM_RRD_PATH`
in the environment of `install.sh`.

Traffic between tailnet nodes is WireGuard-encrypted, so plain HTTP inside the tailnet is fine. If you
enable HTTPS certificates for your tailnet you can use `tailscale serve --https=443` instead.

### Register the client (Claude Code)

```bash
TOKEN=$(ssh observium-host "sudo sed -n 's/^OBSERVIUM_MCP_TOKEN=//p' /etc/observium-mcp/observium-mcp.env")
claude mcp add --scope user --transport http observium \
  http://observium-host.your-tailnet.ts.net:8765/mcp \
  --header "Authorization: Bearer $TOKEN"
unset TOKEN
claude mcp list   # observium: ... (HTTP) - ✔ Connected
```

### Operating it

```bash
systemctl status observium-mcp
journalctl -u observium-mcp -f
curl http://127.0.0.1:18765/health        # {"status":"ok","database":true}; 503 if DB unreachable
sudo tailscale serve status
```

Rotate the token: edit `OBSERVIUM_MCP_TOKEN` in the env file, `systemctl restart observium-mcp`,
re-run `claude mcp add` on each client.

## Configuration reference

| Variable | Default | Purpose |
|---|---|---|
| `OBSERVIUM_MCP_TRANSPORT` | `stdio` | `stdio` or `http` (also `--transport`) |
| `OBSERVIUM_MCP_HOST` | `127.0.0.1` | HTTP bind address (also `--host`) |
| `OBSERVIUM_MCP_PORT` | `18765` | HTTP port (also `--port`) |
| `OBSERVIUM_MCP_TOKEN` | — | **Required for http**, ≥32 chars (`openssl rand -hex 32`) |
| `OBSERVIUM_MCP_ALLOWED_HOSTS` | *(off)* | Comma list of accepted `Host` headers on `/mcp` (DNS-rebinding protection); `host:*` wildcards ports |
| `OBSERVIUM_DB_SOCKET` | — | MariaDB unix socket; when set, host/port are ignored |
| `OBSERVIUM_DB_HOST` / `_PORT` | `localhost` / `3306` | TCP connection (if no socket) |
| `OBSERVIUM_DB_NAME` / `_USER` / `_PASS` | `observium` / `observium` / — | Credentials |
| `OBSERVIUM_DB_CONNECT_TIMEOUT` | `5` | Seconds |
| `OBSERVIUM_RRD_PATH` | `/opt/observium/rrd` | RRD tree (local disk) |

For stdio/dev use, values can also come from a `.env` in the project root (see `config.example.env`).
Real environment variables win over `.env`.

## Local / development use (stdio)

```bash
uv venv --python 3.13 .venv
uv pip install --python .venv -e '.[dev]'
cp config.example.env .env      # edit
.venv/bin/observium-mcp          # stdio
.venv/bin/observium-mcp --transport http --port 18765   # needs OBSERVIUM_MCP_TOKEN
```

## Testing

```bash
uv pip install --python .venv -e '.[dev]'    # or: pip install -r requirements-dev.txt
.venv/bin/pytest tests/
```

No database, network, or rrdtool needed: the DB layer and `subprocess` are mocked.

- `tests/test_unit.py` — DB config (socket vs TCP), health check, RRD parsing, local-only rrdtool
  invocation, token validation, bearer auth (missing / wrong / wrong scheme / prefix-match), `/health`
  200/503, CLI/env transport selection.
- `tests/test_e2e.py` — a real uvicorn server on a random loopback port driven by the real MCP
  streamable-HTTP client (initialize → list_tools → call_tool with mocked rows), 401 without a token,
  `/health` over a socket, and the stdio transport as a subprocess (tool errors cleanly when the DB is
  unreachable).

## Available Tools

| Tool | Description |
|------|-------------|
| `get_observium_capabilities` | Summary of what's monitored |
| `list_devices` | List all monitored devices with status |
| `get_device` | Get detailed info for a specific device |
| `list_ports` | List network interfaces for a device |
| `get_port_traffic` | Get traffic stats for a specific port |
| `list_sensors` | List sensor readings (temp, voltage, etc.) |
| `list_alerts` | List active or historical alerts |
| `get_alert_summary` | Get alert count summary |
| `get_trends` | Get historical metric data |
| `list_available_metrics` | List available RRD metrics for a device |

See [docs/TOOLS.md](docs/TOOLS.md) for parameters.

## Example Queries

- "What devices are currently down?"
- "Show me the temperature sensors on the main switch"
- "What's the CPU load trend for the firewall over the past week?"
- "Are there any active alerts?"
- "Which ports on the core switch have errors?"

## Security Considerations

- The database is never exposed on the network; the service uses the local unix socket.
- Dedicated read-only DB account (`SELECT` on `observium.*` only), password generated at install.
- `/mcp` requires a bearer token (constant-time comparison); only `/health` is open, and it reveals
  only whether the DB is reachable.
- The service binds to loopback; `tailscale serve` is the only path in, limited to tailnet devices.
- RRD access is read-only `rrdtool fetch`/`info` with argument lists (no shell).
- Secrets live in `/etc/observium-mcp/observium-mcp.env` (root:observium-mcp 0640) and the client's
  MCP config; `.env` is gitignored.

## Troubleshooting

- **`claude mcp list` shows "Failed to connect"**: `curl http://<host>:8765/health` from the client.
  No answer → check `tailscale serve status` and that the client is on the tailnet. `401` on `/mcp` →
  token mismatch. `503` from `/health` → MariaDB down or the DB account/password is out of sync
  (re-run `install.sh`, which re-syncs the password from the env file).
- **`421 Misdirected Request` / invalid Host**: the client's hostname isn't in
  `OBSERVIUM_MCP_ALLOWED_HOSTS`.
- **Trend tools fail**: check `OBSERVIUM_RRD_PATH` and that `rrdtool` is installed on the host.
- **`AttributeError: 'Server' object has no attribute 'list_tools'`**: `mcp` 2.x got installed; pin `mcp<2`.

## Upgrading from 0.1.x

0.1.x ran on the client and reached Observium through an SSH tunnel (`start-tunnel.sh`) plus per-query
SSH for RRD files. Both are gone: `OBSERVIUM_RRD_SSH_*` settings are ignored, and `start-tunnel.sh` is
deleted. Install the service on the Observium host and re-register clients with `--transport http`.

## License

MIT License - see [LICENSE](LICENSE) for details.
