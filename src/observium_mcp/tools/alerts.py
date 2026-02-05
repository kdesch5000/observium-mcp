"""Alert-related MCP tools for Observium."""

from datetime import datetime
from typing import Any, Optional
from ..database import execute_query


def list_alerts(
    device_id: Optional[int] = None,
    hostname: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50
) -> list[dict[str, Any]]:
    """
    List alerts from Observium.

    Args:
        device_id: Filter by device ID
        hostname: Filter by hostname (used if device_id not provided)
        status: Filter by status ('active', 'recovered', 'all')
        limit: Maximum number of alerts to return (default: 50)

    Returns:
        List of alerts with status and details
    """
    query = """
        SELECT
            a.alert_table_id,
            a.device_id,
            a.entity_type,
            a.entity_id,
            a.alert_test_id,
            a.alert_status,
            a.last_changed,
            a.last_checked,
            a.last_ok,
            a.last_failed,
            a.ignore_until,
            d.hostname,
            d.sysName,
            t.alert_name,
            t.alert_message
        FROM alert_table a
        JOIN devices d ON a.device_id = d.device_id
        LEFT JOIN alert_tests t ON a.alert_test_id = t.alert_test_id
        WHERE d.disabled = 0
    """
    params = []

    if device_id is not None:
        query += " AND a.device_id = %s"
        params.append(device_id)
    elif hostname:
        query += " AND (d.hostname = %s OR d.sysName = %s)"
        params.append(hostname)
        params.append(hostname)

    if status:
        if status.lower() == "active":
            query += " AND a.alert_status = 1"
        elif status.lower() == "recovered":
            query += " AND a.alert_status = 0"
        # 'all' returns everything, no filter needed

    query += " ORDER BY a.last_changed DESC LIMIT %s"
    params.append(limit)

    results = execute_query(query, tuple(params))

    alerts = []
    for row in results:
        # Convert Unix timestamps to readable format
        last_changed = format_timestamp(row.get("last_changed"))
        last_ok = format_timestamp(row.get("last_ok"))
        last_failed = format_timestamp(row.get("last_failed"))

        alerts.append({
            "alert_id": row["alert_table_id"],
            "device_id": row["device_id"],
            "hostname": row["hostname"],
            "sysname": row["sysName"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "alert_name": row.get("alert_name"),
            "message": row.get("alert_message"),
            "status": "active" if row["alert_status"] == 1 else "recovered",
            "last_changed": last_changed,
            "last_ok": last_ok,
            "last_failed": last_failed,
            "last_changed_unix": row.get("last_changed"),
        })

    return alerts


def format_timestamp(unix_ts: Optional[int]) -> Optional[str]:
    """Convert Unix timestamp to ISO format string."""
    if unix_ts is None:
        return None
    try:
        return datetime.fromtimestamp(unix_ts).isoformat()
    except (ValueError, OSError):
        return None


def get_alert_summary() -> dict[str, Any]:
    """
    Get a summary of current alert status.

    Returns:
        Summary with counts by status and entity type
    """
    # Count by status
    status_query = """
        SELECT
            alert_status,
            COUNT(*) as count
        FROM alert_table a
        JOIN devices d ON a.device_id = d.device_id
        WHERE d.disabled = 0
        GROUP BY alert_status
    """
    status_results = execute_query(status_query)

    status_counts = {"active": 0, "recovered": 0}
    for row in status_results:
        if row["alert_status"] == 1:
            status_counts["active"] = row["count"]
        else:
            status_counts["recovered"] = row["count"]

    # Count active alerts by entity type
    entity_query = """
        SELECT
            entity_type,
            COUNT(*) as count
        FROM alert_table a
        JOIN devices d ON a.device_id = d.device_id
        WHERE d.disabled = 0 AND a.alert_status = 1
        GROUP BY entity_type
        ORDER BY count DESC
    """
    entity_results = execute_query(entity_query)

    by_entity_type = {row["entity_type"]: row["count"] for row in entity_results}

    # Count active alerts by device
    device_query = """
        SELECT
            d.hostname,
            COUNT(*) as count
        FROM alert_table a
        JOIN devices d ON a.device_id = d.device_id
        WHERE d.disabled = 0 AND a.alert_status = 1
        GROUP BY a.device_id, d.hostname
        ORDER BY count DESC
        LIMIT 10
    """
    device_results = execute_query(device_query)

    by_device = {row["hostname"]: row["count"] for row in device_results}

    return {
        "total_active": status_counts["active"],
        "total_recovered": status_counts["recovered"],
        "by_entity_type": by_entity_type,
        "by_device": by_device,
    }
