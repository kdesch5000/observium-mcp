"""MCP tools for Observium data access."""

from .devices import list_devices, get_device
from .ports import list_ports, get_port_traffic
from .sensors import list_sensors
from .alerts import list_alerts
from .trends import get_trends

__all__ = [
    "list_devices",
    "get_device",
    "list_ports",
    "get_port_traffic",
    "list_sensors",
    "list_alerts",
    "get_trends",
]
