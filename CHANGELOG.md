# Changelog

## 0.2.0 — 2026-11-18

### ✨ NEW: HTTP service mode, runs on the Observium host
- **What changed:** The server can now run as a long-lived service speaking MCP *streamable HTTP*
  (`--transport http` / `OBSERVIUM_MCP_TRANSPORT=http`) at `/mcp`, with an unauthenticated
  `/health` endpoint (`200 {"status":"ok","database":true}` / `503` when the DB is unreachable).
  stdio remains the default.
- **Technical details:**
  - New `observium_mcp/http_app.py`: Starlette app + `StreamableHTTPSessionManager` in stateless,
    JSON-response mode (a service restart never strands a client session).
  - Bearer-token ASGI middleware (`hmac.compare_digest`), token required and ≥32 chars even on
    loopback, because `tailscale serve` forwards tailnet traffic to 127.0.0.1.
  - Optional DNS-rebinding protection via `OBSERVIUM_MCP_ALLOWED_HOSTS`.
  - Server instructions moved into the `Server(...)` constructor so both transports send them.
  - `deploy/install.sh` (idempotent): system user, pinned + checksum-verified `uv`, uv-managed
    Python 3.13 under `/opt/observium-mcp`, venv, read-only MariaDB account
    `observium_mcp@localhost` (SELECT only), generated token/password in
    `/etc/observium-mcp/observium-mcp.env` (0640), sandboxed systemd unit
    (`systemd-analyze security` 3.2 "OK"), and `tailscale serve --http=8765`.
- **Impact:** No SSH tunnel to keep alive, MariaDB stays bound to 127.0.0.1, one server for every
  client, and an OS Python upgrade can no longer break the venv (the 0.1.x outage: the client venv
  pointed at a removed Python 3.12).

### Changed
- `database.py`: `OBSERVIUM_DB_SOCKET` (unix socket; host/port ignored when set),
  `OBSERVIUM_DB_CONNECT_TIMEOUT` (default 5 s), `check_connection()` for `/health`.
- Dependencies: `mcp>=1.26,<2` (2.x removed the low-level decorator API — `Server.list_tools`
  etc.), explicit `starlette`/`uvicorn`; dropped the unused `rrdtool` Python binding (the code uses
  the `rrdtool` CLI). `requires-python` raised to 3.10 (the MCP SDK's floor). Added
  `requirements-dev.txt`.

### Removed
- SSH remote RRD mode (`OBSERVIUM_RRD_SSH_*`, `build_ssh_cmd`, remote helpers). This also removes
  the remote `test -e '<path>'` shell strings.
- `start-tunnel.sh`.

### Docs
- Sanitized `TEST_PLAN.md` and a tool-description example: real hostnames, LAN IPs and a home path
  replaced with `example.com` / RFC 5737 (`192.0.2.x`) / `/path/to/` placeholders.

### Tests
- New `tests/test_unit.py` and `tests/test_e2e.py` (33 tests, no external services): auth edge cases,
  health 200/503, settings validation, RRD parsing/local invocation, a real uvicorn + MCP HTTP client
  session, and the stdio transport as a subprocess.

## 0.1.0 — 2026-02-05
- Initial release: 10 read-only tools over stdio; DB via SSH tunnel, RRD via SSH.
