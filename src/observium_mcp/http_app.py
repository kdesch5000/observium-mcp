"""Streamable-HTTP transport for the Observium MCP server.

Serves MCP at ``/mcp`` (bearer-token protected) and an unauthenticated
``/health`` endpoint that reports whether the database is reachable.

Intended deployment: bind to 127.0.0.1 on the Observium host and publish it
to the tailnet with ``tailscale serve``. The token is a second layer on top of
Tailscale's device-level access control.
"""

from __future__ import annotations

import contextlib
import hmac
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from . import database

MCP_PATH = "/mcp"
HEALTH_PATH = "/health"
MIN_TOKEN_LENGTH = 32


class ConfigError(ValueError):
    """Raised when the HTTP transport is misconfigured."""


@dataclass
class HttpSettings:
    host: str = "127.0.0.1"
    port: int = 18765
    token: str = ""
    allowed_hosts: list[str] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> "HttpSettings":
        allowed = [h.strip() for h in os.getenv("OBSERVIUM_MCP_ALLOWED_HOSTS", "").split(",")]
        return cls(
            host=os.getenv("OBSERVIUM_MCP_HOST", "127.0.0.1"),
            port=int(os.getenv("OBSERVIUM_MCP_PORT", "18765")),
            token=os.getenv("OBSERVIUM_MCP_TOKEN", ""),
            allowed_hosts=[h for h in allowed if h],
        )

    def validate(self) -> None:
        # Always require a token: even on 127.0.0.1, `tailscale serve` forwards
        # tailnet traffic to us, so "loopback" does not mean "local users only".
        if len(self.token) < MIN_TOKEN_LENGTH:
            raise ConfigError(
                f"OBSERVIUM_MCP_TOKEN must be set to at least {MIN_TOKEN_LENGTH} characters "
                "for the HTTP transport (generate one with: openssl rand -hex 32)"
            )


class BearerAuth:
    """ASGI middleware: require ``Authorization: Bearer <token>`` except on /health."""

    def __init__(self, app, token: str, open_paths: tuple[str, ...] = (HEALTH_PATH,)):
        self.app = app
        self._token = token.encode()
        self._open_paths = open_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") in self._open_paths:
            await self.app(scope, receive, send)
            return
        supplied = b""
        for name, value in scope.get("headers", []):
            if name == b"authorization":
                scheme, _, cred = value.partition(b" ")
                if scheme.lower() == b"bearer":
                    supplied = cred.strip()
                break
        if not supplied or not hmac.compare_digest(supplied, self._token):
            response = JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


class _ManagerEndpoint:
    def __init__(self, manager: StreamableHTTPSessionManager):
        self._manager = manager

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self._manager.handle_request(scope, receive, send)


async def health(_: Request) -> JSONResponse:
    db_ok = database.check_connection()
    return JSONResponse(
        {"status": "ok" if db_ok else "degraded", "database": db_ok},
        status_code=200 if db_ok else 503,
    )


def create_app(server: Server, settings: HttpSettings) -> BearerAuth:
    """Build the ASGI app. Raises ConfigError if settings are unusable."""
    settings.validate()

    security = None
    if settings.allowed_hosts:
        security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=settings.allowed_hosts,
        )

    # Stateless + JSON responses: every POST is self-contained, so a service
    # restart never strands a client with a dead session id.
    manager = StreamableHTTPSessionManager(
        app=server,
        json_response=True,
        stateless=True,
        security_settings=security,
    )

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        async with manager.run():
            yield

    app = Starlette(
        routes=[
            Route(HEALTH_PATH, health, methods=["GET"]),
            # A class instance (not a function) so Starlette passes raw ASGI through.
            Route(MCP_PATH, _ManagerEndpoint(manager), methods=["GET", "POST", "DELETE"]),
        ],
        lifespan=lifespan,
    )
    return BearerAuth(app, settings.token)


def serve(server: Server, settings: HttpSettings | None = None) -> None:
    """Run the HTTP transport with uvicorn (blocking)."""
    import uvicorn

    settings = settings or HttpSettings.from_env()
    app = create_app(server, settings)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info",
                proxy_headers=False, server_header=False)
