"""Trend/historical data MCP tools for Observium."""

import os
from typing import Any, Optional
from ..database import execute_single
from ..rrd import (
    get_rrd_path,
    get_device_rrd_path,
    list_device_rrd_files,
    fetch_rrd_data,
    get_rrd_info,
    rrd_file_exists,
)


def get_trends(
    device_id: Optional[int] = None,
    hostname: Optional[str] = None,
    metric: str = "load",
    period: str = "1d"
) -> dict[str, Any]:
    """
    Get historical trend data for a device metric.

    Args:
        device_id: The device ID
        hostname: The hostname (used if device_id not provided)
        metric: Type of metric to retrieve. Options:
                - 'load': System load average
                - 'cpu': CPU utilization
                - 'memory': Memory usage
                - 'uptime': Device uptime history
        period: Time period ('1h', '6h', '1d', '1w', '1m')

    Returns:
        Historical data with timestamps and values
    """
    # Resolve hostname if device_id provided
    if hostname is None and device_id is not None:
        query = "SELECT hostname FROM devices WHERE device_id = %s"
        result = execute_single(query, (device_id,))
        if result:
            hostname = result["hostname"]
        else:
            return {"error": f"Device not found: {device_id}"}

    if hostname is None:
        return {"error": "Either device_id or hostname must be provided"}

    # Map period to rrdtool format
    period_map = {
        "1h": "-1h",
        "6h": "-6h",
        "1d": "-1d",
        "1w": "-1w",
        "1m": "-1m",
    }
    rrd_start = period_map.get(period, "-1d")

    # Map metric to RRD file
    metric_files = {
        "load": "la.rrd",
        "cpu": "processor-hr-1.rrd",
        "memory": "mempool-ucd-snmp-mib--0.rrd",
        "uptime": "uptime.rrd",
    }

    rrd_filename = metric_files.get(metric.lower())
    if not rrd_filename:
        return {
            "error": f"Unknown metric: {metric}",
            "available_metrics": list(metric_files.keys())
        }

    # Build full path
    rrd_file = os.path.join(get_device_rrd_path(hostname), rrd_filename)

    # Check if file exists, try alternative paths
    if not rrd_file_exists(rrd_file):
        # Try to find alternative RRD files for this metric
        device_rrds = list_device_rrd_files(hostname)
        alternatives = []

        if metric.lower() == "cpu":
            alternatives = [f for f in device_rrds if "processor" in f.lower()]
        elif metric.lower() == "memory":
            alternatives = [f for f in device_rrds if "mempool" in f.lower()]

        if alternatives:
            rrd_file = os.path.join(get_device_rrd_path(hostname), alternatives[0])
        else:
            return {
                "error": f"RRD file not found for metric '{metric}' on device '{hostname}'",
                "available_rrd_files": device_rrds[:20]  # Show first 20
            }

    # Fetch the data
    data = fetch_rrd_data(rrd_file, start=rrd_start)

    if "error" in data:
        return data

    # Process and summarize the data
    values = []
    for i, ts in enumerate(data.get("timestamps", [])):
        row_values = data["data"][i] if i < len(data["data"]) else []
        # Filter out None values and create data points
        point = {"timestamp": ts}
        for j, ds in enumerate(data.get("datasources", [])):
            if j < len(row_values) and row_values[j] is not None:
                point[ds] = row_values[j]
        if len(point) > 1:  # Has at least one value besides timestamp
            values.append(point)

    # Calculate statistics
    stats = calculate_stats(values, data.get("datasources", []))

    return {
        "hostname": hostname,
        "metric": metric,
        "period": period,
        "rrd_file": os.path.basename(rrd_file),
        "datasources": data.get("datasources", []),
        "data_points": len(values),
        "statistics": stats,
        "data": values[-100:] if len(values) > 100 else values  # Limit to last 100 points
    }


def calculate_stats(values: list[dict], datasources: list[str]) -> dict[str, Any]:
    """Calculate min, max, avg for each datasource."""
    stats = {}

    for ds in datasources:
        ds_values = [v[ds] for v in values if ds in v and v[ds] is not None]
        if ds_values:
            stats[ds] = {
                "min": min(ds_values),
                "max": max(ds_values),
                "avg": sum(ds_values) / len(ds_values),
                "current": ds_values[-1] if ds_values else None,
            }

    return stats


def list_available_metrics(
    device_id: Optional[int] = None,
    hostname: Optional[str] = None
) -> dict[str, Any]:
    """
    List available metrics (RRD files) for a device.

    Args:
        device_id: The device ID
        hostname: The hostname (used if device_id not provided)

    Returns:
        List of available RRD files and their datasources
    """
    # Resolve hostname if device_id provided
    if hostname is None and device_id is not None:
        query = "SELECT hostname FROM devices WHERE device_id = %s"
        result = execute_single(query, (device_id,))
        if result:
            hostname = result["hostname"]
        else:
            return {"error": f"Device not found: {device_id}"}

    if hostname is None:
        return {"error": "Either device_id or hostname must be provided"}

    rrd_files = list_device_rrd_files(hostname)

    if not rrd_files:
        return {
            "hostname": hostname,
            "error": "No RRD files found for device",
            "rrd_path": get_device_rrd_path(hostname)
        }

    # Categorize RRD files
    categories = {
        "system": [],
        "network": [],
        "sensors": [],
        "performance": [],
        "other": []
    }

    for rrd in rrd_files:
        rrd_lower = rrd.lower()
        if any(x in rrd_lower for x in ["la.rrd", "processor", "mempool", "hr_", "uptime"]):
            categories["system"].append(rrd)
        elif any(x in rrd_lower for x in ["port-", "netstats", "ip"]):
            categories["network"].append(rrd)
        elif "sensor" in rrd_lower or "alert-7" in rrd_lower:
            categories["sensors"].append(rrd)
        elif "perf" in rrd_lower or "poller" in rrd_lower:
            categories["performance"].append(rrd)
        else:
            categories["other"].append(rrd)

    return {
        "hostname": hostname,
        "total_rrd_files": len(rrd_files),
        "categories": {k: v for k, v in categories.items() if v},
    }
