"""Observium MCP Server - Model Context Protocol server for Observium CE.

This server exposes Observium monitoring data to LLMs via the MCP protocol,
enabling natural language queries about device status, network traffic,
sensor readings, alerts, and historical trends.
"""

import os
from typing import Optional

from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .tools.devices import list_devices, get_device
from .tools.ports import list_ports, get_port_traffic
from .tools.sensors import list_sensors, get_sensor_classes
from .tools.alerts import list_alerts, get_alert_summary
from .tools.trends import get_trends, list_available_metrics

# Load environment variables from .env file
load_dotenv()

# Create the MCP server
server = Server("observium-mcp")


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """Return the list of available tools."""
    return [
        Tool(
            name="list_devices",
            description="List all devices monitored by Observium with their current status. "
                       "Returns hostname, OS, hardware, uptime, and status for each device.",
            inputSchema={
                "type": "object",
                "properties": {
                    "status_filter": {
                        "type": "string",
                        "description": "Filter by device status: 'up', 'down', or 'disabled'",
                        "enum": ["up", "down", "disabled"]
                    },
                    "os_filter": {
                        "type": "string",
                        "description": "Filter by OS type (e.g., 'linux', 'ios', 'junos')"
                    }
                }
            }
        ),
        Tool(
            name="get_device",
            description="Get detailed information about a specific device including hardware, "
                       "software version, uptime, location, and counts of ports/sensors/alerts.",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "The device ID to look up"
                    },
                    "hostname": {
                        "type": "string",
                        "description": "The hostname to look up (used if device_id not provided)"
                    }
                }
            }
        ),
        Tool(
            name="list_ports",
            description="List network ports/interfaces for a device with their status and basic traffic info.",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "The device ID to get ports for"
                    },
                    "hostname": {
                        "type": "string",
                        "description": "The hostname (used if device_id not provided)"
                    },
                    "admin_status": {
                        "type": "string",
                        "description": "Filter by admin status: 'up' or 'down'",
                        "enum": ["up", "down"]
                    },
                    "oper_status": {
                        "type": "string",
                        "description": "Filter by operational status: 'up' or 'down'",
                        "enum": ["up", "down"]
                    }
                }
            }
        ),
        Tool(
            name="get_port_traffic",
            description="Get detailed traffic statistics for a specific network port, "
                       "including current rates and historical data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "port_id": {
                        "type": "integer",
                        "description": "The port ID to get traffic for"
                    },
                    "device_hostname": {
                        "type": "string",
                        "description": "Device hostname (used with port_name if port_id not provided)"
                    },
                    "port_name": {
                        "type": "string",
                        "description": "Port name or interface description"
                    },
                    "period": {
                        "type": "string",
                        "description": "Time period for historical data",
                        "enum": ["1h", "6h", "1d", "1w", "1m"],
                        "default": "1d"
                    }
                }
            }
        ),
        Tool(
            name="list_sensors",
            description="List sensors (temperature, voltage, frequency, etc.) for a device or all devices. "
                       "Returns current values and status relative to thresholds.",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "Filter by device ID"
                    },
                    "hostname": {
                        "type": "string",
                        "description": "Filter by hostname"
                    },
                    "sensor_class": {
                        "type": "string",
                        "description": "Filter by sensor class (e.g., 'temperature', 'voltage', 'frequency')"
                    }
                }
            }
        ),
        Tool(
            name="list_alerts",
            description="List alerts from Observium with their status and details.",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "Filter by device ID"
                    },
                    "hostname": {
                        "type": "string",
                        "description": "Filter by hostname"
                    },
                    "status": {
                        "type": "string",
                        "description": "Filter by alert status",
                        "enum": ["active", "recovered", "all"],
                        "default": "active"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of alerts to return",
                        "default": 50
                    }
                }
            }
        ),
        Tool(
            name="get_alert_summary",
            description="Get a summary of current alert status including counts by type and device.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_trends",
            description="Get historical trend data for a device metric like CPU load, memory, or system load. "
                       "Returns statistics (min, max, avg) and recent data points.",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "The device ID"
                    },
                    "hostname": {
                        "type": "string",
                        "description": "The hostname (used if device_id not provided)"
                    },
                    "metric": {
                        "type": "string",
                        "description": "Type of metric to retrieve",
                        "enum": ["load", "cpu", "memory", "uptime"],
                        "default": "load"
                    },
                    "period": {
                        "type": "string",
                        "description": "Time period for data",
                        "enum": ["1h", "6h", "1d", "1w", "1m"],
                        "default": "1d"
                    }
                },
                "required": ["hostname"]
            }
        ),
        Tool(
            name="list_available_metrics",
            description="List available metrics (RRD files) for a device to see what trend data can be queried.",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "The device ID"
                    },
                    "hostname": {
                        "type": "string",
                        "description": "The hostname (used if device_id not provided)"
                    }
                }
            }
        ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    import json

    result = None

    try:
        if name == "list_devices":
            result = list_devices(
                status_filter=arguments.get("status_filter"),
                os_filter=arguments.get("os_filter")
            )
        elif name == "get_device":
            result = get_device(
                device_id=arguments.get("device_id"),
                hostname=arguments.get("hostname")
            )
        elif name == "list_ports":
            result = list_ports(
                device_id=arguments.get("device_id"),
                hostname=arguments.get("hostname"),
                admin_status=arguments.get("admin_status"),
                oper_status=arguments.get("oper_status")
            )
        elif name == "get_port_traffic":
            result = get_port_traffic(
                port_id=arguments.get("port_id"),
                device_hostname=arguments.get("device_hostname"),
                port_name=arguments.get("port_name"),
                period=arguments.get("period", "1d")
            )
        elif name == "list_sensors":
            result = list_sensors(
                device_id=arguments.get("device_id"),
                hostname=arguments.get("hostname"),
                sensor_class=arguments.get("sensor_class")
            )
        elif name == "list_alerts":
            result = list_alerts(
                device_id=arguments.get("device_id"),
                hostname=arguments.get("hostname"),
                status=arguments.get("status", "active"),
                limit=arguments.get("limit", 50)
            )
        elif name == "get_alert_summary":
            result = get_alert_summary()
        elif name == "get_trends":
            result = get_trends(
                device_id=arguments.get("device_id"),
                hostname=arguments.get("hostname"),
                metric=arguments.get("metric", "load"),
                period=arguments.get("period", "1d")
            )
        elif name == "list_available_metrics":
            result = list_available_metrics(
                device_id=arguments.get("device_id"),
                hostname=arguments.get("hostname")
            )
        else:
            result = {"error": f"Unknown tool: {name}"}

    except Exception as e:
        result = {"error": str(e)}

    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


def run():
    """Entry point for the server."""
    import asyncio
    asyncio.run(main())


if __name__ == "__main__":
    run()
