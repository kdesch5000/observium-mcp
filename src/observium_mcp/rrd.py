"""RRD data access for historical metrics from Observium."""

import os
import subprocess
from datetime import datetime, timedelta
from typing import Any, Optional


def get_rrd_path() -> str:
    """Get the base RRD path from environment."""
    return os.getenv("OBSERVIUM_RRD_PATH", "/opt/observium/rrd")


def get_device_rrd_path(hostname: str) -> str:
    """Get the RRD directory path for a specific device."""
    return os.path.join(get_rrd_path(), hostname)


def list_device_rrd_files(hostname: str) -> list[str]:
    """List all RRD files for a device."""
    device_path = get_device_rrd_path(hostname)
    if not os.path.isdir(device_path):
        return []
    return [f for f in os.listdir(device_path) if f.endswith(".rrd")]


def fetch_rrd_data(
    rrd_file: str,
    cf: str = "AVERAGE",
    start: Optional[str] = None,
    end: Optional[str] = None,
    resolution: Optional[int] = None
) -> dict[str, Any]:
    """
    Fetch data from an RRD file using rrdtool.

    Args:
        rrd_file: Full path to the RRD file
        cf: Consolidation function (AVERAGE, MIN, MAX, LAST)
        start: Start time (rrdtool format, e.g., "-1d", "-1w", Unix timestamp)
        end: End time (rrdtool format, default: now)
        resolution: Desired resolution in seconds

    Returns:
        Dictionary with 'timestamps', 'datasources', and 'data' keys
    """
    if not os.path.exists(rrd_file):
        return {"error": f"RRD file not found: {rrd_file}"}

    # Build rrdtool fetch command
    cmd = ["rrdtool", "fetch", rrd_file, cf]

    if start:
        cmd.extend(["--start", str(start)])
    else:
        cmd.extend(["--start", "-1d"])  # Default to last day

    if end:
        cmd.extend(["--end", str(end)])

    if resolution:
        cmd.extend(["--resolution", str(resolution)])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return parse_rrd_output(result.stdout)
    except subprocess.CalledProcessError as e:
        return {"error": f"rrdtool error: {e.stderr}"}
    except Exception as e:
        return {"error": str(e)}


def parse_rrd_output(output: str) -> dict[str, Any]:
    """Parse rrdtool fetch output into structured data."""
    lines = output.strip().split("\n")
    if not lines:
        return {"error": "Empty rrdtool output"}

    # First line contains datasource names
    header = lines[0].strip()
    datasources = header.split()

    # Remaining lines contain timestamp: values
    data = []
    timestamps = []

    for line in lines[1:]:
        line = line.strip()
        if not line or ":" not in line:
            continue

        parts = line.split(":")
        if len(parts) != 2:
            continue

        timestamp = int(parts[0].strip())
        values_str = parts[1].strip().split()

        # Convert values, handling NaN
        values = []
        for v in values_str:
            try:
                if v.lower() in ("nan", "-nan"):
                    values.append(None)
                else:
                    values.append(float(v))
            except ValueError:
                values.append(None)

        timestamps.append(timestamp)
        data.append(values)

    return {
        "datasources": datasources,
        "timestamps": timestamps,
        "data": data
    }


def get_rrd_info(rrd_file: str) -> dict[str, Any]:
    """Get information about an RRD file."""
    if not os.path.exists(rrd_file):
        return {"error": f"RRD file not found: {rrd_file}"}

    try:
        result = subprocess.run(
            ["rrdtool", "info", rrd_file],
            capture_output=True,
            text=True,
            check=True
        )
        return parse_rrd_info(result.stdout)
    except subprocess.CalledProcessError as e:
        return {"error": f"rrdtool error: {e.stderr}"}


def parse_rrd_info(output: str) -> dict[str, Any]:
    """Parse rrdtool info output."""
    info = {"datasources": [], "rras": []}
    ds_names = set()

    for line in output.split("\n"):
        line = line.strip()
        if not line or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        # Extract datasource names
        if key.startswith("ds[") and "].type" in key:
            ds_name = key.split("[")[1].split("]")[0]
            if ds_name not in ds_names:
                ds_names.add(ds_name)
                info["datasources"].append(ds_name)

        # Basic info
        elif key == "step":
            info["step"] = int(value)
        elif key == "last_update":
            info["last_update"] = int(value)

    return info


def get_last_value(rrd_file: str, datasource: Optional[str] = None) -> dict[str, Any]:
    """Get the last recorded value from an RRD file."""
    data = fetch_rrd_data(rrd_file, cf="LAST", start="-5m")

    if "error" in data:
        return data

    # Find the last non-null value
    for i in range(len(data["timestamps"]) - 1, -1, -1):
        values = data["data"][i]
        if datasource:
            try:
                ds_idx = data["datasources"].index(datasource)
                if values[ds_idx] is not None:
                    return {
                        "timestamp": data["timestamps"][i],
                        "datasource": datasource,
                        "value": values[ds_idx]
                    }
            except (ValueError, IndexError):
                pass
        else:
            # Return all datasources with values
            result = {"timestamp": data["timestamps"][i], "values": {}}
            for j, ds in enumerate(data["datasources"]):
                if j < len(values) and values[j] is not None:
                    result["values"][ds] = values[j]
            if result["values"]:
                return result

    return {"error": "No recent data available"}
