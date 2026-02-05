"""Observium MCP Server - Model Context Protocol server for Observium CE.

This server exposes Observium monitoring data to LLMs via the MCP protocol,
enabling natural language queries about device status, network traffic,
sensor readings, alerts, and historical trends.
"""

import os
import json
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    Resource,
    Prompt,
    PromptArgument,
    PromptMessage,
    GetPromptResult,
)

from .tools.devices import list_devices, get_device
from .tools.ports import list_ports, get_port_traffic
from .tools.sensors import list_sensors, get_sensor_classes
from .tools.alerts import list_alerts, get_alert_summary
from .tools.trends import get_trends, list_available_metrics

# Load environment variables from .env file
# Use explicit path since working directory may vary when run via MCP
_env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(_env_path)

# Server instructions that help LLMs understand the service
SERVER_INSTRUCTIONS = """
Observium MCP provides access to network monitoring data from Observium CE (Community Edition).

WHAT IS OBSERVIUM:
Observium is a network monitoring platform that autodiscovers and tracks network devices,
interfaces, sensors, and generates alerts via SNMP polling. It stores historical metrics
in RRD (Round Robin Database) files for trend analysis.

DATA AVAILABLE:
- Devices: Servers, switches, routers, firewalls, APs, IoT devices
- Ports: Network interfaces with traffic rates, errors, utilization
- Sensors: Temperature, voltage, frequency, fan speed, power readings
- Alerts: Device down, port down, sensor threshold violations
- Trends: Historical CPU, memory, load, bandwidth data

COMMON WORKFLOWS:
1. Device Health Check: list_devices → get_device → list_sensors
2. Traffic Analysis: list_ports → get_port_traffic (use period for history)
3. Troubleshooting: list_alerts → get_device → list_sensors → get_trends
4. Capacity Planning: get_port_traffic or get_trends with period="1w" or "1m"
5. Discovery: get_observium_capabilities to see what's monitored

EXAMPLE QUESTIONS THIS SERVICE CAN ANSWER:
- "What devices are currently down?"
- "What's the hottest temperature sensor?"
- "Show peak bandwidth on the Internet port this week"
- "Which device has the highest CPU load?"
- "Are there any active alerts?"
- "What's the memory usage trend on the firewall?"
- "List all ports with errors on the switch"
- "What sensors are in warning or critical state?"

TIPS FOR BEST RESULTS:
- Use list_devices first to discover hostnames and device_ids
- Use list_ports to find port_ids before querying traffic
- Use list_available_metrics to see what trend data exists for a device
- Historical queries support periods: 1h, 6h, 1d, 1w, 1m
- Sensor classes include: temperature, voltage, frequency, fanspeed, power, humidity
"""

# Create the MCP server with instructions
server = Server("observium-mcp")


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """Return the list of available tools."""
    return [
        Tool(
            name="get_observium_capabilities",
            description="""Discover what data is available in this Observium instance.

CALL THIS FIRST to understand what devices, sensors, and metrics exist before
making specific queries. Returns summary counts and available data types.

RETURNS:
- device_count: Total monitored devices
- devices_by_os: Breakdown by operating system
- devices_by_status: Count of up/down/disabled devices
- sensor_classes: Available sensor types (temperature, voltage, etc.)
- alert_summary: Active and recovered alert counts
- available_trend_metrics: What historical data can be queried

EXAMPLE QUESTIONS:
- "What does Observium monitor?"
- "How many devices are being tracked?"
- "What types of sensors are available?"
""",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="list_devices",
            description="""List all devices monitored by Observium with their current status.

Returns hostname, IP, OS, hardware model, uptime, and polling status for each device.
Use this to discover what devices exist before drilling down with other tools.

RETURNS: Array of devices with:
- device_id: Unique identifier (use with other tools)
- hostname: Device hostname or IP
- os: Operating system (linux, ios, junos, etc.)
- hardware: Hardware model
- uptime: How long since last reboot
- status: Current state (up, down, disabled)
- last_polled: When Observium last collected data

EXAMPLE QUESTIONS:
- "What devices are monitored?"
- "Show me all Linux servers"
- "What devices are currently down?"
- "List all network switches"

NEXT STEPS: Use device_id or hostname with get_device, list_ports, list_sensors, get_trends
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "status_filter": {
                        "type": "string",
                        "description": "Filter by device status",
                        "enum": ["up", "down", "disabled"]
                    },
                    "os_filter": {
                        "type": "string",
                        "description": "Filter by OS type (examples: 'linux', 'ios', 'junos', 'dlink', 'unifi')"
                    }
                }
            }
        ),
        Tool(
            name="get_device",
            description="""Get detailed information about a specific device.

Returns comprehensive device details including hardware specs, software version,
location, uptime, and counts of associated ports, sensors, and alerts.

RETURNS:
- device_id, hostname, sysName, IP address
- os, os_version, hardware model, serial number
- uptime (formatted), last_polled, last_rebooted
- location, contact information
- port_count: Number of network interfaces
- sensor_count: Number of sensors (temp, voltage, etc.)
- active_alert_count: Current alerts on this device

EXAMPLE QUESTIONS:
- "Tell me about the firewall"
- "What's the uptime of unifi.mf?"
- "Show details for device 16"
- "How many ports does the switch have?"

NEXT STEPS: Use list_ports, list_sensors, or list_alerts with this device
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "The device ID (get from list_devices)"
                    },
                    "hostname": {
                        "type": "string",
                        "description": "The hostname or IP (e.g., 'firewall.local', '192.168.1.1')"
                    }
                }
            }
        ),
        Tool(
            name="list_ports",
            description="""List network ports/interfaces for a device.

Returns all network interfaces with their operational state, speed, and basic
traffic counters. Essential for finding port_ids before querying traffic details.

RETURNS: Array of ports with:
- port_id: Unique identifier (use with get_port_traffic)
- name: Interface name (e.g., 'GigabitEthernet0/1', 'eth0')
- description: Interface description from device
- alias: Configured port description/label
- speed: Port speed (e.g., '1 Gbps', '10 Gbps')
- admin_status: Administrative state (up/down)
- oper_status: Operational state (up/down)
- in_octets, out_octets: Total bytes transferred
- in_errors, out_errors: Error counters

EXAMPLE QUESTIONS:
- "What ports are on the switch?"
- "Show me all active interfaces on the router"
- "Which ports have errors?"
- "List ports that are admin up but operationally down"

NEXT STEPS: Use port_id with get_port_traffic for detailed bandwidth analysis
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "The device ID (get from list_devices)"
                    },
                    "hostname": {
                        "type": "string",
                        "description": "The hostname or IP address"
                    },
                    "admin_status": {
                        "type": "string",
                        "description": "Filter by administrative status",
                        "enum": ["up", "down"]
                    },
                    "oper_status": {
                        "type": "string",
                        "description": "Filter by operational status",
                        "enum": ["up", "down"]
                    }
                }
            }
        ),
        Tool(
            name="get_port_traffic",
            description="""Get detailed traffic statistics for a specific network port.

Returns current bandwidth rates and historical statistics including peak and
average utilization. Essential for capacity planning and troubleshooting.

RETURNS:
- port_id, hostname, name, alias, speed
- admin_status, oper_status
- current:
  - in_rate_bps, out_rate_bps: Current traffic rate in bits/sec
  - in_utilization_pct, out_utilization_pct: Current % of port capacity
  - total_in_octets, total_out_octets: Lifetime byte counters
- historical (when RRD data available):
  - period: Time range analyzed
  - statistics.in: peak_bps, peak_mbps, avg_bps, avg_mbps, peak_utilization_pct
  - statistics.out: peak_bps, peak_mbps, avg_bps, avg_mbps, peak_utilization_pct

PERIODS: 1h (hour), 6h (6 hours), 1d (day), 1w (week), 1m (month)

EXAMPLE QUESTIONS:
- "What's the current bandwidth on port 211?"
- "What was peak utilization on the Internet port this week?"
- "Show traffic trends for the uplink over the past month"
- "Is the WAN link congested?"

TIP: Use list_ports first to find the port_id, or specify device_hostname + port_name
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "port_id": {
                        "type": "integer",
                        "description": "The port ID (get from list_ports)"
                    },
                    "device_hostname": {
                        "type": "string",
                        "description": "Device hostname (use with port_name if port_id unknown)"
                    },
                    "port_name": {
                        "type": "string",
                        "description": "Port name like 'GE0/0/1', 'eth0', or description like 'Internet'"
                    },
                    "period": {
                        "type": "string",
                        "description": "Time period for historical statistics",
                        "enum": ["1h", "6h", "1d", "1w", "1m"],
                        "default": "1d"
                    }
                }
            }
        ),
        Tool(
            name="list_sensors",
            description="""List sensors (temperature, voltage, frequency, etc.) across devices.

Returns current sensor readings with status relative to configured thresholds.
Sensors are auto-discovered via SNMP from devices that support environmental monitoring.

RETURNS: Array of sensors with:
- sensor_id: Unique identifier
- hostname: Device the sensor belongs to
- sensor_class: Type (temperature, voltage, frequency, fanspeed, power, humidity)
- sensor_descr: Sensor name/description
- value: Current reading with unit
- status: normal, warning, or critical (based on thresholds)
- limits: Configured thresholds (critical_high, warning_high, warning_low, critical_low)

SENSOR CLASSES:
- temperature: CPU, chassis, ambient temps (°C)
- voltage: Power supply, rail voltages (V)
- frequency: CPU, clock frequencies (Hz/MHz)
- fanspeed: Cooling fan RPM
- power: Power consumption (W)
- humidity: Environmental humidity (%)

EXAMPLE QUESTIONS:
- "What's the hottest sensor?"
- "Show all temperature readings"
- "Are any sensors in warning or critical state?"
- "What's the CPU temperature on the server?"

TIP: Filter by sensor_class to focus on specific sensor types
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "Filter by device ID"
                    },
                    "hostname": {
                        "type": "string",
                        "description": "Filter by device hostname"
                    },
                    "sensor_class": {
                        "type": "string",
                        "description": "Filter by sensor type",
                        "enum": ["temperature", "voltage", "frequency", "fanspeed", "power", "humidity", "current", "dbm", "load", "state"]
                    }
                }
            }
        ),
        Tool(
            name="list_alerts",
            description="""List alerts from Observium with status and details.

Returns active or historical alerts including device down, port down, and
sensor threshold violations. Use for troubleshooting and monitoring.

RETURNS: Array of alerts with:
- alert_id: Unique identifier
- hostname: Affected device
- alert_name: Type of alert
- entity_type: What triggered it (device, port, sensor)
- entity_name: Specific entity affected
- status: active or recovered
- timestamp: When alert was raised
- duration: How long alert has been active

ALERT TYPES:
- Device alerts: Device down, device rebooted
- Port alerts: Port down, port errors, port utilization
- Sensor alerts: Temperature high, voltage out of range

EXAMPLE QUESTIONS:
- "Are there any active alerts?"
- "What alerts fired this week?"
- "Show me all recovered alerts"
- "What's alerting on the switch?"

NEXT STEPS: Use get_alert_summary for overview, or investigate with get_device/list_sensors
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "Filter by device ID"
                    },
                    "hostname": {
                        "type": "string",
                        "description": "Filter by device hostname"
                    },
                    "status": {
                        "type": "string",
                        "description": "Filter by alert status",
                        "enum": ["active", "recovered", "all"],
                        "default": "active"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum alerts to return (default: 50, max: 500)",
                        "default": 50
                    }
                }
            }
        ),
        Tool(
            name="get_alert_summary",
            description="""Get a summary of current alert status.

Returns aggregated alert counts by type, entity, and device. Use for quick
health overview before drilling into specific alerts.

RETURNS:
- total_active: Count of currently active alerts
- total_recovered: Count of recovered alerts (last 7 days)
- by_entity_type: Breakdown by device/port/sensor
- by_device: Top devices with most alerts
- recent_alerts: Last few alerts raised

EXAMPLE QUESTIONS:
- "How many active alerts are there?"
- "Which device has the most alerts?"
- "Give me an alert overview"
- "What's the current alert situation?"

NEXT STEPS: Use list_alerts for details on specific alerts
""",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_trends",
            description="""Get historical trend data for device metrics.

Returns time-series data for CPU, memory, load, or uptime with statistics.
Data comes from RRD files updated every 5 minutes by Observium polling.

RETURNS:
- hostname, metric, period
- datasources: What values are in the data (e.g., load1, load5, load15)
- data_points: Number of samples
- statistics: For each datasource - min, max, avg, current
- data: Array of timestamped values (last 100 points)

METRICS:
- load: System load average (load1, load5, load15)
- cpu: CPU utilization percentage
- memory: Memory usage percentage or bytes
- uptime: System uptime in seconds

PERIODS: 1h, 6h, 1d (default), 1w, 1m

EXAMPLE QUESTIONS:
- "What's the CPU trend on the server this week?"
- "Show load average history for the firewall"
- "What was peak memory usage this month?"
- "How has uptime looked over the past week?"

TIP: Use list_available_metrics first to see what data exists for a device
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "The device ID"
                    },
                    "hostname": {
                        "type": "string",
                        "description": "The device hostname"
                    },
                    "metric": {
                        "type": "string",
                        "description": "Type of metric to retrieve",
                        "enum": ["load", "cpu", "memory", "uptime"],
                        "default": "load"
                    },
                    "period": {
                        "type": "string",
                        "description": "Time period for historical data",
                        "enum": ["1h", "6h", "1d", "1w", "1m"],
                        "default": "1d"
                    }
                },
                "required": ["hostname"]
            }
        ),
        Tool(
            name="list_available_metrics",
            description="""List available metrics (RRD files) for a device.

Shows what historical trend data can be queried for a specific device.
RRD files are created automatically based on what Observium discovers via SNMP.

RETURNS:
- hostname: Device queried
- total_rrd_files: Count of available metrics
- categories: Metrics grouped by type
  - system: la.rrd (load), processor (cpu), mempool (memory), uptime
  - network: port-*.rrd (interface traffic)
  - sensors: sensor-*.rrd (environmental data)
  - performance: poller stats

EXAMPLE QUESTIONS:
- "What metrics are available for the server?"
- "Can I get CPU data for this device?"
- "What historical data exists for the switch?"

NEXT STEPS: Use get_trends with discovered metrics, or get_port_traffic for network data
""",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "The device ID"
                    },
                    "hostname": {
                        "type": "string",
                        "description": "The device hostname"
                    }
                }
            }
        ),
    ]


@server.list_resources()
async def handle_list_resources() -> list[Resource]:
    """Return browsable resources."""
    return [
        Resource(
            uri="observium://devices",
            name="All Monitored Devices",
            description="Complete list of devices monitored by Observium with current status, OS, and uptime",
            mimeType="application/json"
        ),
        Resource(
            uri="observium://devices/down",
            name="Down Devices",
            description="Devices currently in 'down' status requiring attention",
            mimeType="application/json"
        ),
        Resource(
            uri="observium://alerts/active",
            name="Active Alerts",
            description="Currently active alerts that have not been recovered",
            mimeType="application/json"
        ),
        Resource(
            uri="observium://alerts/summary",
            name="Alert Summary",
            description="Overview of alert counts by type and device",
            mimeType="application/json"
        ),
        Resource(
            uri="observium://sensors/temperature",
            name="Temperature Sensors",
            description="All temperature sensor readings across all devices",
            mimeType="application/json"
        ),
        Resource(
            uri="observium://sensors/critical",
            name="Critical Sensors",
            description="Sensors currently in warning or critical state",
            mimeType="application/json"
        ),
    ]


@server.read_resource()
async def handle_read_resource(uri: str) -> str:
    """Handle resource reads."""
    result = None

    if uri == "observium://devices":
        result = list_devices()
    elif uri == "observium://devices/down":
        result = list_devices(status_filter="down")
    elif uri == "observium://alerts/active":
        result = list_alerts(status="active", limit=100)
    elif uri == "observium://alerts/summary":
        result = get_alert_summary()
    elif uri == "observium://sensors/temperature":
        result = list_sensors(sensor_class="temperature")
    elif uri == "observium://sensors/critical":
        # Get all sensors and filter for warning/critical
        all_sensors = list_sensors()
        result = [s for s in all_sensors if s.get("status") in ("warning", "critical")]
    else:
        result = {"error": f"Unknown resource: {uri}"}

    return json.dumps(result, indent=2, default=str)


@server.list_prompts()
async def handle_list_prompts() -> list[Prompt]:
    """Return available prompt templates."""
    return [
        Prompt(
            name="network_health_check",
            description="Comprehensive network health check: device status, active alerts, and critical sensors",
            arguments=[]
        ),
        Prompt(
            name="device_troubleshooting",
            description="Diagnose issues with a specific device: status, alerts, sensors, and recent trends",
            arguments=[
                PromptArgument(
                    name="hostname",
                    description="Device hostname or IP to troubleshoot",
                    required=True
                )
            ]
        ),
        Prompt(
            name="capacity_report",
            description="Analyze bandwidth utilization across ports to identify busy or congested links",
            arguments=[
                PromptArgument(
                    name="hostname",
                    description="Device hostname (optional - all devices if not specified)",
                    required=False
                ),
                PromptArgument(
                    name="period",
                    description="Analysis period: 1d, 1w, or 1m (default: 1w)",
                    required=False
                )
            ]
        ),
        Prompt(
            name="temperature_audit",
            description="Review all temperature sensors and identify any running hot or in warning state",
            arguments=[]
        ),
        Prompt(
            name="alert_investigation",
            description="Investigate current alerts and provide recommended actions",
            arguments=[]
        ),
    ]


@server.get_prompt()
async def handle_get_prompt(name: str, arguments: dict | None) -> GetPromptResult:
    """Handle prompt requests."""
    args = arguments or {}

    if name == "network_health_check":
        return GetPromptResult(
            description="Comprehensive network health check",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text="""Please perform a comprehensive network health check using the Observium data:

1. First, use get_observium_capabilities to understand what's being monitored
2. Check for any devices that are down using list_devices with status_filter="down"
3. Review active alerts using get_alert_summary and list_alerts
4. Check for any sensors in warning or critical state using list_sensors
5. Summarize the overall health status and any issues requiring attention

Provide a clear summary with:
- Overall status (healthy/warning/critical)
- Count of devices up vs down
- Active alerts requiring attention
- Any sensors outside normal range
- Recommended actions if any issues found"""
                    )
                )
            ]
        )

    elif name == "device_troubleshooting":
        hostname = args.get("hostname", "")
        return GetPromptResult(
            description=f"Troubleshoot device: {hostname}",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=f"""Please troubleshoot the device "{hostname}" using Observium data:

1. Get device details using get_device with hostname="{hostname}"
2. Check for any active alerts on this device using list_alerts
3. Review sensor readings using list_sensors for this device
4. Check what metrics are available using list_available_metrics
5. If load/cpu metrics exist, get recent trends using get_trends
6. List the ports and their status using list_ports

Provide a diagnostic summary:
- Device status and uptime
- Any active alerts or recent issues
- Sensor readings (especially any warnings)
- Resource utilization trends (CPU, memory, load)
- Port status summary
- Potential issues identified
- Recommended actions"""
                    )
                )
            ]
        )

    elif name == "capacity_report":
        hostname = args.get("hostname", "")
        period = args.get("period", "1w")

        device_filter = f'for device "{hostname}"' if hostname else "across all devices"
        return GetPromptResult(
            description=f"Capacity analysis {device_filter}",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=f"""Please analyze network capacity {device_filter} over the past {period}:

1. {"Use get_device to get details for " + hostname if hostname else "Use list_devices to identify network devices (switches, routers)"}
2. For each relevant device, use list_ports to find active interfaces
3. For key ports (uplinks, WAN links), use get_port_traffic with period="{period}"
4. Focus on ports with high utilization or significant traffic

Provide a capacity report including:
- Summary of analyzed ports
- Peak utilization for each significant link
- Average utilization
- Any ports approaching capacity (>70% peak)
- Ports with concerning trends
- Recommendations for capacity planning"""
                    )
                )
            ]
        )

    elif name == "temperature_audit":
        return GetPromptResult(
            description="Temperature sensor audit",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text="""Please audit all temperature sensors in Observium:

1. Use list_sensors with sensor_class="temperature" to get all temperature readings
2. Identify the hottest sensors
3. Check for any in warning or critical state
4. Group by device to identify any devices running hot

Provide a temperature report:
- Total temperature sensors monitored
- Sensors grouped by device with current readings
- Hottest sensors (top 5)
- Any sensors in warning or critical state
- Devices that may have cooling issues
- Recommendations if any temperatures are concerning"""
                    )
                )
            ]
        )

    elif name == "alert_investigation":
        return GetPromptResult(
            description="Alert investigation and recommendations",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text="""Please investigate current Observium alerts:

1. Use get_alert_summary to get an overview
2. Use list_alerts with status="active" to get details on active alerts
3. For each active alert, gather context:
   - Device alerts: check device status with get_device
   - Port alerts: check port status with list_ports
   - Sensor alerts: check sensor readings with list_sensors
4. Also check recently recovered alerts to understand patterns

Provide an alert investigation report:
- Summary of active alerts
- Details on each active alert with context
- Impact assessment (which services/devices affected)
- Recommended actions for each alert
- Any patterns observed (e.g., multiple alerts on same device)
- Priority order for addressing issues"""
                    )
                )
            ]
        )

    else:
        return GetPromptResult(
            description="Unknown prompt",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=f"Unknown prompt: {name}"
                    )
                )
            ]
        )


def get_observium_capabilities() -> dict:
    """Get a summary of what's available in this Observium instance."""
    # Get device summary
    all_devices = list_devices()
    devices_by_os = {}
    devices_by_status = {"up": 0, "down": 0, "disabled": 0}

    for device in all_devices:
        os_name = device.get("os", "unknown")
        devices_by_os[os_name] = devices_by_os.get(os_name, 0) + 1

        status = device.get("status", "unknown")
        if status in devices_by_status:
            devices_by_status[status] += 1

    # Get sensor classes
    sensor_classes = get_sensor_classes()

    # Get alert summary
    alert_summary = get_alert_summary()

    return {
        "description": "Observium CE Network Monitoring System",
        "device_count": len(all_devices),
        "devices_by_os": devices_by_os,
        "devices_by_status": devices_by_status,
        "sensor_classes": sensor_classes,
        "alert_summary": {
            "active": alert_summary.get("total_active", 0),
            "recovered": alert_summary.get("total_recovered", 0),
        },
        "available_trend_metrics": ["load", "cpu", "memory", "uptime"],
        "supported_periods": ["1h", "6h", "1d", "1w", "1m"],
        "example_queries": [
            "What devices are down?",
            "Show temperature sensors",
            "What's the CPU load on [hostname]?",
            "List active alerts",
            "Peak bandwidth on [port] this week",
            "Which device is hottest?",
        ]
    }


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    result = None

    try:
        if name == "get_observium_capabilities":
            result = get_observium_capabilities()
        elif name == "list_devices":
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
        init_options = server.create_initialization_options()
        # Add server instructions to initialization
        init_options.instructions = SERVER_INSTRUCTIONS
        await server.run(
            read_stream,
            write_stream,
            init_options
        )


def run():
    """Entry point for the server."""
    import asyncio
    asyncio.run(main())


if __name__ == "__main__":
    run()
