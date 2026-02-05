"""Sensor-related MCP tools for Observium."""

from typing import Any, Optional
from ..database import execute_query


def list_sensors(
    device_id: Optional[int] = None,
    hostname: Optional[str] = None,
    sensor_class: Optional[str] = None
) -> list[dict[str, Any]]:
    """
    List sensors for a device or all devices.

    Args:
        device_id: Filter by device ID
        hostname: Filter by hostname (used if device_id not provided)
        sensor_class: Filter by sensor class (e.g., 'temperature', 'voltage', 'frequency')

    Returns:
        List of sensors with current values
    """
    query = """
        SELECT
            s.sensor_id,
            s.device_id,
            s.sensor_class,
            s.sensor_type,
            s.sensor_descr,
            s.sensor_value,
            s.sensor_unit,
            s.sensor_limit,
            s.sensor_limit_low,
            s.sensor_limit_warn,
            s.sensor_limit_low_warn,
            d.hostname,
            d.sysName
        FROM sensors s
        JOIN devices d ON s.device_id = d.device_id
        WHERE d.disabled = 0 AND s.sensor_deleted = 0
    """
    params = []

    if device_id is not None:
        query += " AND s.device_id = %s"
        params.append(device_id)
    elif hostname:
        query += " AND (d.hostname = %s OR d.sysName = %s)"
        params.append(hostname)
        params.append(hostname)

    if sensor_class:
        query += " AND s.sensor_class = %s"
        params.append(sensor_class.lower())

    query += " ORDER BY d.hostname, s.sensor_class, s.sensor_descr"

    results = execute_query(query, tuple(params) if params else None)

    sensors = []
    for row in results:
        # Determine status based on limits
        status = "normal"
        value = row.get("sensor_value")

        if value is not None:
            # Check critical limits
            if row.get("sensor_limit") and value > row["sensor_limit"]:
                status = "critical_high"
            elif row.get("sensor_limit_low") and value < row["sensor_limit_low"]:
                status = "critical_low"
            # Check warning limits
            elif row.get("sensor_limit_warn") and value > row["sensor_limit_warn"]:
                status = "warning_high"
            elif row.get("sensor_limit_low_warn") and value < row["sensor_limit_low_warn"]:
                status = "warning_low"

        # Format value with unit
        formatted_value = format_sensor_value(
            value,
            row["sensor_class"],
            row.get("sensor_unit")
        )

        sensors.append({
            "sensor_id": row["sensor_id"],
            "device_id": row["device_id"],
            "hostname": row["hostname"],
            "sysname": row["sysName"],
            "class": row["sensor_class"],
            "type": row["sensor_type"],
            "description": row["sensor_descr"],
            "value": value,
            "value_formatted": formatted_value,
            "unit": row.get("sensor_unit"),
            "status": status,
            "limits": {
                "critical_high": row.get("sensor_limit"),
                "critical_low": row.get("sensor_limit_low"),
                "warning_high": row.get("sensor_limit_warn"),
                "warning_low": row.get("sensor_limit_low_warn"),
            }
        })

    return sensors


def format_sensor_value(value: Optional[float], sensor_class: str, unit: Optional[str] = None) -> str:
    """Format sensor value based on its class."""
    if value is None:
        return "N/A"

    # Class-specific formatting
    if sensor_class == "temperature":
        return f"{value:.1f}°C"
    elif sensor_class == "humidity":
        return f"{value:.1f}%"
    elif sensor_class == "voltage":
        return f"{value:.2f}V"
    elif sensor_class == "current":
        return f"{value:.2f}A"
    elif sensor_class == "power":
        return f"{value:.1f}W"
    elif sensor_class == "frequency":
        if value >= 1_000_000_000:
            return f"{value / 1_000_000_000:.2f} GHz"
        elif value >= 1_000_000:
            return f"{value / 1_000_000:.2f} MHz"
        elif value >= 1_000:
            return f"{value / 1_000:.2f} KHz"
        else:
            return f"{value:.2f} Hz"
    elif sensor_class == "fanspeed":
        return f"{value:.0f} RPM"
    elif sensor_class == "load":
        return f"{value:.1f}%"
    elif unit:
        return f"{value} {unit}"
    else:
        return str(value)


def get_sensor_classes() -> list[str]:
    """Get list of all sensor classes in the system."""
    query = "SELECT DISTINCT sensor_class FROM sensors WHERE sensor_deleted = 0 ORDER BY sensor_class"
    results = execute_query(query)
    return [row["sensor_class"] for row in results]
