"""Device-related MCP tools for Observium."""

from typing import Any, Optional
from ..database import execute_query, execute_single


def format_uptime(seconds: Optional[int]) -> str:
    """Format uptime in seconds to human-readable string."""
    if seconds is None:
        return "Unknown"

    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60

    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"


def format_status(status: int) -> str:
    """Format device status code to human-readable string."""
    status_map = {
        0: "down",
        1: "up",
        2: "disabled",
    }
    return status_map.get(status, f"unknown ({status})")


def list_devices(
    status_filter: Optional[str] = None,
    os_filter: Optional[str] = None
) -> list[dict[str, Any]]:
    """
    List all devices monitored by Observium.

    Args:
        status_filter: Filter by status ('up', 'down', 'disabled')
        os_filter: Filter by OS type (e.g., 'linux', 'ios', 'junos')

    Returns:
        List of devices with basic status information
    """
    query = """
        SELECT
            device_id,
            hostname,
            sysName,
            os,
            version,
            hardware,
            status,
            uptime,
            last_polled,
            location
        FROM devices
        WHERE disabled = 0
    """
    params = []

    if status_filter:
        status_code = {"up": 1, "down": 0, "disabled": 2}.get(status_filter.lower())
        if status_code is not None:
            query += " AND status = %s"
            params.append(status_code)

    if os_filter:
        query += " AND os LIKE %s"
        params.append(f"%{os_filter}%")

    query += " ORDER BY hostname"

    results = execute_query(query, tuple(params) if params else None)

    devices = []
    for row in results:
        devices.append({
            "device_id": row["device_id"],
            "hostname": row["hostname"],
            "sysname": row["sysName"],
            "os": row["os"],
            "version": row["version"],
            "hardware": row["hardware"],
            "status": format_status(row["status"]),
            "uptime": format_uptime(row["uptime"]),
            "uptime_seconds": row["uptime"],
            "last_polled": str(row["last_polled"]) if row["last_polled"] else None,
            "location": row["location"],
        })

    return devices


def get_device(device_id: Optional[int] = None, hostname: Optional[str] = None) -> dict[str, Any]:
    """
    Get detailed information about a specific device.

    Args:
        device_id: The device ID to look up
        hostname: The hostname to look up (used if device_id not provided)

    Returns:
        Detailed device information including hardware, software, and status
    """
    if device_id is None and hostname is None:
        return {"error": "Either device_id or hostname must be provided"}

    query = """
        SELECT
            device_id,
            hostname,
            sysName,
            sysDescr,
            sysContact,
            os,
            version,
            hardware,
            vendor,
            serial,
            features,
            status,
            status_type,
            uptime,
            last_polled,
            last_discovered,
            last_polled_timetaken,
            location,
            purpose,
            type,
            ip,
            snmp_version
        FROM devices
        WHERE 1=1
    """

    if device_id is not None:
        query += " AND device_id = %s"
        params = (device_id,)
    else:
        query += " AND (hostname = %s OR sysName = %s)"
        params = (hostname, hostname)

    row = execute_single(query, params)

    if not row:
        return {"error": "Device not found"}

    # Get port count
    port_query = "SELECT COUNT(*) as count FROM ports WHERE device_id = %s"
    port_result = execute_single(port_query, (row["device_id"],))
    port_count = port_result["count"] if port_result else 0

    # Get sensor count
    sensor_query = "SELECT COUNT(*) as count FROM sensors WHERE device_id = %s"
    sensor_result = execute_single(sensor_query, (row["device_id"],))
    sensor_count = sensor_result["count"] if sensor_result else 0

    # Get active alert count
    alert_query = """
        SELECT COUNT(*) as count FROM alert_table
        WHERE device_id = %s AND alert_status = 1
    """
    alert_result = execute_single(alert_query, (row["device_id"],))
    alert_count = alert_result["count"] if alert_result else 0

    return {
        "device_id": row["device_id"],
        "hostname": row["hostname"],
        "sysname": row["sysName"],
        "description": row["sysDescr"],
        "contact": row["sysContact"],
        "os": row["os"],
        "version": row["version"],
        "hardware": row["hardware"],
        "vendor": row["vendor"],
        "serial": row["serial"],
        "features": row["features"],
        "status": format_status(row["status"]),
        "status_type": row["status_type"],
        "uptime": format_uptime(row["uptime"]),
        "uptime_seconds": row["uptime"],
        "last_polled": str(row["last_polled"]) if row["last_polled"] else None,
        "last_discovered": str(row["last_discovered"]) if row["last_discovered"] else None,
        "poll_duration_seconds": row["last_polled_timetaken"],
        "location": row["location"],
        "purpose": row["purpose"],
        "type": row["type"],
        "ip": row["ip"],
        "snmp_version": row["snmp_version"],
        "port_count": port_count,
        "sensor_count": sensor_count,
        "active_alert_count": alert_count,
    }
