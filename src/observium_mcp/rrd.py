"""RRD data access for historical metrics from Observium.

Supports both local and remote (SSH) access to RRD files.
For remote access, set OBSERVIUM_RRD_SSH_HOST in your .env file.
"""

import os
import subprocess
from datetime import datetime, timedelta
from typing import Any, Optional


def get_ssh_config() -> dict[str, Optional[str]]:
    """Get SSH configuration for remote RRD access."""
    return {
        "host": os.getenv("OBSERVIUM_RRD_SSH_HOST"),
        "user": os.getenv("OBSERVIUM_RRD_SSH_USER", "pi"),
        "port": os.getenv("OBSERVIUM_RRD_SSH_PORT", "22"),
        "key": os.getenv("OBSERVIUM_RRD_SSH_KEY"),  # Optional: path to SSH key
    }


def is_remote_mode() -> bool:
    """Check if we should use SSH for remote RRD access."""
    return bool(os.getenv("OBSERVIUM_RRD_SSH_HOST"))


def build_ssh_cmd(cmd: list[str]) -> list[str]:
    """Build an SSH command to run remotely."""
    ssh_config = get_ssh_config()
    ssh_cmd = ["ssh"]

    if ssh_config["port"] and ssh_config["port"] != "22":
        ssh_cmd.extend(["-p", ssh_config["port"]])

    if ssh_config["key"]:
        ssh_cmd.extend(["-i", ssh_config["key"]])

    # Add options for non-interactive use
    ssh_cmd.extend(["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"])

    # Add user@host
    target = f"{ssh_config['user']}@{ssh_config['host']}"
    ssh_cmd.append(target)

    # Add the actual command
    ssh_cmd.extend(cmd)

    return ssh_cmd


def get_rrd_path() -> str:
    """Get the base RRD path from environment."""
    return os.getenv("OBSERVIUM_RRD_PATH", "/opt/observium/rrd")


def get_device_rrd_path(hostname: str) -> str:
    """Get the RRD directory path for a specific device."""
    return os.path.join(get_rrd_path(), hostname)


def remote_path_exists(path: str) -> bool:
    """Check if a path exists on the remote server."""
    # Use shell=True equivalent by passing command as a single string to remote shell
    cmd = build_ssh_cmd([f"test -e '{path}'"])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except Exception:
        return False


def remote_is_dir(path: str) -> bool:
    """Check if a path is a directory on the remote server."""
    cmd = build_ssh_cmd([f"test -d '{path}'"])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except Exception:
        return False


def remote_list_dir(path: str) -> list[str]:
    """List files in a directory on the remote server."""
    cmd = build_ssh_cmd(["ls", "-1", path])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        return []
    except Exception:
        return []


def list_device_rrd_files(hostname: str) -> list[str]:
    """List all RRD files for a device."""
    device_path = get_device_rrd_path(hostname)

    if is_remote_mode():
        # Remote mode: use SSH
        if not remote_is_dir(device_path):
            return []
        files = remote_list_dir(device_path)
        return [f for f in files if f.endswith(".rrd")]
    else:
        # Local mode
        if not os.path.isdir(device_path):
            return []
        return [f for f in os.listdir(device_path) if f.endswith(".rrd")]


def rrd_file_exists(rrd_file: str) -> bool:
    """Check if an RRD file exists (local or remote)."""
    if is_remote_mode():
        return remote_path_exists(rrd_file)
    else:
        return os.path.exists(rrd_file)


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
    if not rrd_file_exists(rrd_file):
        return {"error": f"RRD file not found: {rrd_file}"}

    # Build rrdtool fetch command
    rrdtool_cmd = ["rrdtool", "fetch", rrd_file, cf]

    if start:
        rrdtool_cmd.extend(["--start", str(start)])
    else:
        rrdtool_cmd.extend(["--start", "-1d"])  # Default to last day

    if end:
        rrdtool_cmd.extend(["--end", str(end)])

    if resolution:
        rrdtool_cmd.extend(["--resolution", str(resolution)])

    # Execute locally or via SSH
    if is_remote_mode():
        cmd = build_ssh_cmd(rrdtool_cmd)
    else:
        cmd = rrdtool_cmd

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)
        return parse_rrd_output(result.stdout)
    except subprocess.CalledProcessError as e:
        return {"error": f"rrdtool error: {e.stderr}"}
    except subprocess.TimeoutExpired:
        return {"error": "RRD fetch timed out"}
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
    if not rrd_file_exists(rrd_file):
        return {"error": f"RRD file not found: {rrd_file}"}

    # Build rrdtool info command
    rrdtool_cmd = ["rrdtool", "info", rrd_file]

    # Execute locally or via SSH
    if is_remote_mode():
        cmd = build_ssh_cmd(rrdtool_cmd)
    else:
        cmd = rrdtool_cmd

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
        return parse_rrd_info(result.stdout)
    except subprocess.CalledProcessError as e:
        return {"error": f"rrdtool error: {e.stderr}"}
    except subprocess.TimeoutExpired:
        return {"error": "RRD info timed out"}
    except Exception as e:
        return {"error": str(e)}


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
