"""Port-related MCP tools for Observium."""

import os
from typing import Any, Optional
from ..database import execute_query, execute_single
from ..rrd import get_rrd_path, fetch_rrd_data


def format_speed(speed: Optional[int]) -> str:
    """Format port speed in bps to human-readable string."""
    if speed is None or speed == 0:
        return "Unknown"

    if speed >= 1_000_000_000_000:
        return f"{speed / 1_000_000_000_000:.0f} Tbps"
    elif speed >= 1_000_000_000:
        return f"{speed / 1_000_000_000:.0f} Gbps"
    elif speed >= 1_000_000:
        return f"{speed / 1_000_000:.0f} Mbps"
    elif speed >= 1_000:
        return f"{speed / 1_000:.0f} Kbps"
    else:
        return f"{speed} bps"


def format_bytes(bytes_val: Optional[float]) -> str:
    """Format bytes to human-readable string."""
    if bytes_val is None:
        return "N/A"

    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(bytes_val) < 1024:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.2f} PB"


def list_ports(
    device_id: Optional[int] = None,
    hostname: Optional[str] = None,
    admin_status: Optional[str] = None,
    oper_status: Optional[str] = None
) -> list[dict[str, Any]]:
    """
    List network ports for a device.

    Args:
        device_id: The device ID to get ports for
        hostname: The hostname to get ports for (used if device_id not provided)
        admin_status: Filter by admin status ('up', 'down')
        oper_status: Filter by operational status ('up', 'down')

    Returns:
        List of ports with status and basic traffic info
    """
    # First, resolve hostname to device_id if needed
    if device_id is None and hostname:
        device_query = "SELECT device_id FROM devices WHERE hostname = %s OR sysName = %s"
        result = execute_single(device_query, (hostname, hostname))
        if result:
            device_id = result["device_id"]
        else:
            return [{"error": f"Device not found: {hostname}"}]

    if device_id is None:
        return [{"error": "Either device_id or hostname must be provided"}]

    query = """
        SELECT
            p.port_id,
            p.device_id,
            p.ifDescr,
            p.ifName,
            p.ifAlias,
            p.ifSpeed,
            p.ifHighSpeed,
            p.ifAdminStatus,
            p.ifOperStatus,
            p.ifInOctets,
            p.ifOutOctets,
            p.ifInErrors,
            p.ifOutErrors,
            p.ifType,
            p.ifMtu,
            d.hostname
        FROM ports p
        JOIN devices d ON p.device_id = d.device_id
        WHERE p.device_id = %s
    """
    params = [device_id]

    if admin_status:
        query += " AND p.ifAdminStatus = %s"
        params.append(admin_status.lower())

    if oper_status:
        query += " AND p.ifOperStatus = %s"
        params.append(oper_status.lower())

    query += " ORDER BY p.ifIndex"

    results = execute_query(query, tuple(params))

    ports = []
    for row in results:
        # Use ifHighSpeed (in Mbps) if available, otherwise ifSpeed (in bps)
        speed = None
        if row.get("ifHighSpeed") and row["ifHighSpeed"] > 0:
            speed = row["ifHighSpeed"] * 1_000_000  # Convert Mbps to bps
        elif row.get("ifSpeed"):
            speed = row["ifSpeed"]

        ports.append({
            "port_id": row["port_id"],
            "device_id": row["device_id"],
            "hostname": row["hostname"],
            "name": row["ifName"] or row["ifDescr"],
            "description": row["ifDescr"],
            "alias": row.get("ifAlias"),
            "speed": format_speed(speed),
            "speed_bps": speed,
            "admin_status": row["ifAdminStatus"],
            "oper_status": row["ifOperStatus"],
            "in_octets": row["ifInOctets"],
            "out_octets": row["ifOutOctets"],
            "in_errors": row["ifInErrors"],
            "out_errors": row["ifOutErrors"],
            "type": row["ifType"],
            "mtu": row["ifMtu"],
        })

    return ports


def get_port_traffic(
    port_id: Optional[int] = None,
    device_hostname: Optional[str] = None,
    port_name: Optional[str] = None,
    period: str = "1d"
) -> dict[str, Any]:
    """
    Get traffic statistics for a specific port.

    Args:
        port_id: The port ID to get traffic for
        device_hostname: Device hostname (used with port_name if port_id not provided)
        port_name: Port name or ifDescr (used with device_hostname)
        period: Time period for historical data ('1h', '6h', '1d', '1w', '1m')

    Returns:
        Traffic statistics including current rate and historical data
    """
    # Resolve port_id if not provided
    if port_id is None:
        if device_hostname is None or port_name is None:
            return {"error": "Either port_id or (device_hostname and port_name) must be provided"}

        query = """
            SELECT p.port_id, p.ifDescr, p.ifName, d.hostname
            FROM ports p
            JOIN devices d ON p.device_id = d.device_id
            WHERE (d.hostname = %s OR d.sysName = %s)
            AND (p.ifName = %s OR p.ifDescr = %s)
        """
        result = execute_single(query, (device_hostname, device_hostname, port_name, port_name))
        if result:
            port_id = result["port_id"]
        else:
            return {"error": f"Port not found: {port_name} on {device_hostname}"}

    # Get port details
    port_query = """
        SELECT
            p.port_id,
            p.device_id,
            p.ifDescr,
            p.ifName,
            p.ifAlias,
            p.ifSpeed,
            p.ifHighSpeed,
            p.ifAdminStatus,
            p.ifOperStatus,
            p.ifInOctets,
            p.ifOutOctets,
            p.ifInOctets_rate,
            p.ifOutOctets_rate,
            p.ifInOctets_perc,
            p.ifOutOctets_perc,
            d.hostname
        FROM ports p
        JOIN devices d ON p.device_id = d.device_id
        WHERE p.port_id = %s
    """
    port = execute_single(port_query, (port_id,))

    if not port:
        return {"error": f"Port not found: {port_id}"}

    # Calculate speed
    speed = None
    if port.get("ifHighSpeed") and port["ifHighSpeed"] > 0:
        speed = port["ifHighSpeed"] * 1_000_000
    elif port.get("ifSpeed"):
        speed = port["ifSpeed"]

    result = {
        "port_id": port["port_id"],
        "device_id": port["device_id"],
        "hostname": port["hostname"],
        "name": port["ifName"] or port["ifDescr"],
        "description": port["ifDescr"],
        "alias": port.get("ifAlias"),
        "speed": format_speed(speed),
        "admin_status": port["ifAdminStatus"],
        "oper_status": port["ifOperStatus"],
        "current": {
            "in_rate_bps": port.get("ifInOctets_rate", 0) * 8 if port.get("ifInOctets_rate") else 0,
            "out_rate_bps": port.get("ifOutOctets_rate", 0) * 8 if port.get("ifOutOctets_rate") else 0,
            "in_utilization_pct": port.get("ifInOctets_perc"),
            "out_utilization_pct": port.get("ifOutOctets_perc"),
            "total_in_octets": port["ifInOctets"],
            "total_out_octets": port["ifOutOctets"],
        }
    }

    # Try to get historical data from RRD
    period_map = {
        "1h": "-1h",
        "6h": "-6h",
        "1d": "-1d",
        "1w": "-1w",
        "1m": "-1m",
    }
    rrd_start = period_map.get(period, "-1d")

    # Build RRD file path - Observium uses port-{device_id}-{port_id}.rrd
    rrd_file = os.path.join(
        get_rrd_path(),
        port["hostname"],
        f"port-{port['port_id']}.rrd"
    )

    if os.path.exists(rrd_file):
        rrd_data = fetch_rrd_data(rrd_file, start=rrd_start)
        if "error" not in rrd_data:
            result["historical"] = {
                "period": period,
                "datasources": rrd_data.get("datasources", []),
                "data_points": len(rrd_data.get("timestamps", [])),
            }

    return result
