"""Port-related MCP tools for Observium."""

import os
from typing import Any, Optional
from ..database import execute_query, execute_single
from ..rrd import get_rrd_path, fetch_rrd_data, rrd_file_exists, list_device_rrd_files


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

    # Find the correct RRD file - Observium may use different naming conventions
    # Try: port-{ifIndex}.rrd, port-{port_id}.rrd
    rrd_base = os.path.join(get_rrd_path(), port["hostname"])
    rrd_file = None

    # Get ifIndex from database
    ifindex_query = "SELECT ifIndex FROM ports WHERE port_id = %s"
    ifindex_result = execute_single(ifindex_query, (port_id,))
    ifindex = ifindex_result.get("ifIndex") if ifindex_result else None

    # Try different RRD file naming patterns
    candidates = []
    if ifindex:
        candidates.append(f"port-{ifindex}.rrd")
    candidates.append(f"port-{port['port_id']}.rrd")

    # Also check available RRD files to find a match
    device_rrds = list_device_rrd_files(port["hostname"])
    port_rrds = [f for f in device_rrds if f.startswith("port-") and not f.startswith("port-ipv6")]

    for candidate in candidates:
        candidate_path = os.path.join(rrd_base, candidate)
        if rrd_file_exists(candidate_path):
            rrd_file = candidate_path
            break

    if rrd_file:
        rrd_data = fetch_rrd_data(rrd_file, start=rrd_start)
        if "error" not in rrd_data:
            # Calculate statistics including peak values
            historical = {
                "period": period,
                "rrd_file": os.path.basename(rrd_file),
                "datasources": rrd_data.get("datasources", []),
                "data_points": len(rrd_data.get("timestamps", [])),
            }

            # Calculate peak and average for in/out traffic
            stats = calculate_port_stats(rrd_data, speed)
            if stats:
                historical["statistics"] = stats

            result["historical"] = historical

    return result


def calculate_port_stats(rrd_data: dict, port_speed_bps: Optional[int]) -> dict:
    """Calculate peak and average statistics from RRD data."""
    stats = {}
    datasources = rrd_data.get("datasources", [])
    data = rrd_data.get("data", [])
    timestamps = rrd_data.get("timestamps", [])

    if not data or not datasources:
        return stats

    # Find indices for INOCTETS and OUTOCTETS datasources
    in_idx = None
    out_idx = None
    for i, ds in enumerate(datasources):
        ds_lower = ds.lower()
        if "in" in ds_lower and "octet" in ds_lower:
            in_idx = i
        elif "out" in ds_lower and "octet" in ds_lower:
            out_idx = i

    # If standard names not found, assume first two columns are in/out
    if in_idx is None and len(datasources) >= 1:
        in_idx = 0
    if out_idx is None and len(datasources) >= 2:
        out_idx = 1

    # Calculate stats for inbound traffic
    if in_idx is not None:
        in_values = []
        for row in data:
            if in_idx < len(row) and row[in_idx] is not None:
                # Convert bytes/sec to bits/sec
                in_values.append(row[in_idx] * 8)

        if in_values:
            peak_in = max(in_values)
            avg_in = sum(in_values) / len(in_values)
            stats["in"] = {
                "peak_bps": peak_in,
                "peak_mbps": peak_in / 1_000_000,
                "avg_bps": avg_in,
                "avg_mbps": avg_in / 1_000_000,
            }
            if port_speed_bps and port_speed_bps > 0:
                stats["in"]["peak_utilization_pct"] = (peak_in / port_speed_bps) * 100
                stats["in"]["avg_utilization_pct"] = (avg_in / port_speed_bps) * 100

    # Calculate stats for outbound traffic
    if out_idx is not None:
        out_values = []
        for row in data:
            if out_idx < len(row) and row[out_idx] is not None:
                out_values.append(row[out_idx] * 8)

        if out_values:
            peak_out = max(out_values)
            avg_out = sum(out_values) / len(out_values)
            stats["out"] = {
                "peak_bps": peak_out,
                "peak_mbps": peak_out / 1_000_000,
                "avg_bps": avg_out,
                "avg_mbps": avg_out / 1_000_000,
            }
            if port_speed_bps and port_speed_bps > 0:
                stats["out"]["peak_utilization_pct"] = (peak_out / port_speed_bps) * 100
                stats["out"]["avg_utilization_pct"] = (avg_out / port_speed_bps) * 100

    return stats
