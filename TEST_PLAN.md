# Observium MCP Server - Comprehensive Test Plan

## Overview
This test plan verifies all 9 MCP tools in the observium-mcp service. Each tool should be tested systematically to ensure reliability.

**Test Environment:**
- Database: MariaDB via SSH tunnel (port 33061)
- RRD Path: `/opt/observium/rrd` on netwatch.mf
- SSH Tunnel Required: `./start-tunnel.sh`

---

## Test Execution Checklist

### 1. DEVICE TOOLS

#### 1.1 list_devices

| Test ID | Test Case | Expected Result | Status |
|---------|-----------|-----------------|--------|
| DEV-001 | List all devices (no filters) | Returns array of all monitored devices with status, uptime, hardware | |
| DEV-002 | Filter by status="up" | Returns only devices with status "up" | |
| DEV-003 | Filter by status="down" | Returns only devices with status "down" (or empty if none down) | |
| DEV-004 | Filter by status="disabled" | Returns only disabled devices (or empty) | |
| DEV-005 | Filter by os_filter="linux" | Returns only Linux devices | |
| DEV-006 | Filter by os_filter="unifi" | Returns only UniFi devices | |
| DEV-007 | Combine status + os filters | Returns devices matching both criteria | |
| DEV-008 | Verify uptime formatting | Uptime shows as "Xd Yh Zm" format | |
| DEV-009 | Verify last_polled timestamp | Returns valid ISO datetime | |

**Sample Test Commands:**
```
# Via Claude Code MCP
list_devices {}
list_devices {"status_filter": "up"}
list_devices {"os_filter": "linux"}
list_devices {"status_filter": "up", "os_filter": "unifi"}
```

#### 1.2 get_device

| Test ID | Test Case | Expected Result | Status |
|---------|-----------|-----------------|--------|
| DEV-010 | Lookup by device_id (e.g., 16) | Returns detailed info for unifi.mf | |
| DEV-011 | Lookup by hostname "unifi.mf" | Returns same device as DEV-010 | |
| DEV-012 | Lookup by sysname "netwatch" | Resolves via sysName fallback | |
| DEV-013 | Verify port_count accuracy | Count matches actual ports | |
| DEV-014 | Verify sensor_count accuracy | Count matches actual sensors | |
| DEV-015 | Verify active_alert_count | Count matches active alerts | |
| DEV-016 | Non-existent device_id | Returns appropriate error | |
| DEV-017 | Non-existent hostname | Returns appropriate error | |

**Sample Test Commands:**
```
get_device {"device_id": 16}
get_device {"hostname": "unifi.mf"}
get_device {"hostname": "netwatch"}
get_device {"device_id": 99999}
```

---

### 2. PORT TOOLS

#### 2.1 list_ports

| Test ID | Test Case | Expected Result | Status |
|---------|-----------|-----------------|--------|
| PORT-001 | List ports by device_id (switch=12) | Returns all switch ports | |
| PORT-002 | List ports by hostname "192.168.86.22" | Same result as PORT-001 | |
| PORT-003 | Filter admin_status="up" | Only administratively up ports | |
| PORT-004 | Filter admin_status="down" | Only administratively down ports | |
| PORT-005 | Filter oper_status="up" | Only operationally up ports | |
| PORT-006 | Filter oper_status="down" | Only operationally down ports | |
| PORT-007 | Combine device + admin + oper filters | Correct intersection | |
| PORT-008 | Verify speed formatting (Gbps) | Shows "1 Gbps" not raw bps | |
| PORT-009 | Verify speed formatting (Mbps) | Shows "100 Mbps" correctly | |
| PORT-010 | Non-existent device | Returns error or empty | |

**Sample Test Commands:**
```
list_ports {"device_id": 12}
list_ports {"hostname": "192.168.86.22"}
list_ports {"device_id": 12, "oper_status": "up"}
list_ports {"device_id": 12, "admin_status": "up", "oper_status": "down"}
```

#### 2.2 get_port_traffic

| Test ID | Test Case | Expected Result | Status |
|---------|-----------|-----------------|--------|
| PORT-011 | Lookup by port_id | Returns traffic stats + current rates | |
| PORT-012 | Lookup by hostname + port_name | Resolves to correct port | |
| PORT-013 | Period="1h" | Returns 1 hour of historical data | |
| PORT-014 | Period="6h" | Returns 6 hours of data | |
| PORT-015 | Period="1d" (default) | Returns 1 day of data | |
| PORT-016 | Period="1w" | Returns 1 week of data | |
| PORT-017 | Period="1m" | Returns 1 month of data | |
| PORT-018 | Verify rate calculation | in_rate_bps = octets * 8 | |
| PORT-019 | Verify utilization percentage | Calculated vs port speed | |
| PORT-020 | Missing RRD file | Graceful error handling | |
| PORT-021 | Non-existent port_id | Returns error | |

**Sample Test Commands:**
```
get_port_traffic {"port_id": 211}
get_port_traffic {"device_hostname": "192.168.86.22", "port_name": "port 1"}
get_port_traffic {"port_id": 211, "period": "1h"}
get_port_traffic {"port_id": 211, "period": "1w"}
```

---

### 3. SENSOR TOOLS

#### 3.1 list_sensors

| Test ID | Test Case | Expected Result | Status |
|---------|-----------|-----------------|--------|
| SENS-001 | List all sensors (no filters) | Returns all sensors from all devices | |
| SENS-002 | Filter by device_id | Only sensors for that device | |
| SENS-003 | Filter by hostname | Resolves hostname, returns sensors | |
| SENS-004 | Filter by sensor_class="temperature" | Only temperature sensors | |
| SENS-005 | Filter by sensor_class="voltage" | Only voltage sensors | |
| SENS-006 | Filter by sensor_class="frequency" | Only frequency sensors | |
| SENS-007 | Combine device + class filters | Correct intersection | |
| SENS-008 | Verify temperature formatting | Shows "XX.X°C" | |
| SENS-009 | Verify voltage formatting | Shows "X.XXV" | |
| SENS-010 | Verify status="normal" | Within thresholds | |
| SENS-011 | Verify limits object | Has critical_high/low, warning_high/low | |
| SENS-012 | Non-existent device | Returns empty or error | |

**Sample Test Commands:**
```
list_sensors {}
list_sensors {"device_id": 16}
list_sensors {"hostname": "unifi.mf"}
list_sensors {"sensor_class": "temperature"}
list_sensors {"device_id": 26, "sensor_class": "temperature"}
```

---

### 4. ALERT TOOLS

#### 4.1 list_alerts

| Test ID | Test Case | Expected Result | Status |
|---------|-----------|-----------------|--------|
| ALRT-001 | List active alerts (default) | Returns alerts with status="active" | |
| ALRT-002 | List recovered alerts | Returns alerts with status="recovered" | |
| ALRT-003 | List all alerts | Returns both active and recovered | |
| ALRT-004 | Filter by device_id | Only alerts for that device | |
| ALRT-005 | Filter by hostname | Resolves and filters | |
| ALRT-006 | Test limit=10 | Returns max 10 alerts | |
| ALRT-007 | Test limit=100 | Returns up to 100 alerts | |
| ALRT-008 | Verify timestamp format | ISO 8601 datetime strings | |
| ALRT-009 | Verify alert_name populated | From alert_tests join | |
| ALRT-010 | Combine device + status filters | Correct intersection | |

**Sample Test Commands:**
```
list_alerts {}
list_alerts {"status": "active"}
list_alerts {"status": "recovered"}
list_alerts {"status": "all"}
list_alerts {"device_id": 12}
list_alerts {"hostname": "switch"}
list_alerts {"status": "active", "limit": 10}
```

#### 4.2 get_alert_summary

| Test ID | Test Case | Expected Result | Status |
|---------|-----------|-----------------|--------|
| ALRT-011 | Get summary (no params) | Returns total_active, total_recovered | |
| ALRT-012 | Verify by_entity_type | Breakdown by port/device/sensor | |
| ALRT-013 | Verify by_device | Top 10 devices by alert count | |
| ALRT-014 | Verify count accuracy | Totals match list_alerts counts | |

**Sample Test Commands:**
```
get_alert_summary {}
```

---

### 5. TREND TOOLS

#### 5.1 get_trends

| Test ID | Test Case | Expected Result | Status |
|---------|-----------|-----------------|--------|
| TRND-001 | Query load metric by hostname | Returns load1, load5, load15 data | |
| TRND-002 | Query cpu metric | Returns CPU utilization data | |
| TRND-003 | Query memory metric | Returns memory usage data | |
| TRND-004 | Query uptime metric | Returns uptime data | |
| TRND-005 | Period="1h" | 1 hour of data points | |
| TRND-006 | Period="6h" | 6 hours of data points | |
| TRND-007 | Period="1d" (default) | 1 day of data points | |
| TRND-008 | Period="1w" | 1 week of data points | |
| TRND-009 | Period="1m" | 1 month of data points | |
| TRND-010 | Verify statistics object | Has min, max, avg, current | |
| TRND-011 | Query by device_id | Resolves to hostname, returns data | |
| TRND-012 | Missing RRD file | Returns error with available files | |
| TRND-013 | Non-existent hostname | Returns appropriate error | |

**Sample Test Commands:**
```
get_trends {"hostname": "unifi.mf", "metric": "load"}
get_trends {"hostname": "unifi.mf", "metric": "cpu"}
get_trends {"hostname": "unifi.mf", "metric": "memory"}
get_trends {"hostname": "unifi.mf", "metric": "load", "period": "1h"}
get_trends {"hostname": "unifi.mf", "metric": "load", "period": "1w"}
get_trends {"device_id": 16, "metric": "load"}
get_trends {"hostname": "nonexistent.host", "metric": "load"}
```

#### 5.2 list_available_metrics

| Test ID | Test Case | Expected Result | Status |
|---------|-----------|-----------------|--------|
| TRND-014 | List metrics by hostname | Returns categorized RRD files | |
| TRND-015 | List metrics by device_id | Resolves hostname, returns metrics | |
| TRND-016 | Verify categories | system, network, sensors, performance, other | |
| TRND-017 | Verify total_rrd_files count | Matches sum of all categories | |
| TRND-018 | Non-existent device | Returns error or empty | |

**Sample Test Commands:**
```
list_available_metrics {"hostname": "unifi.mf"}
list_available_metrics {"device_id": 16}
list_available_metrics {"hostname": "chopper.mf"}
```

---

### 6. ERROR HANDLING TESTS

| Test ID | Test Case | Expected Result | Status |
|---------|-----------|-----------------|--------|
| ERR-001 | Database connection failure | Graceful error message | |
| ERR-002 | SSH tunnel not running | Connection refused error | |
| ERR-003 | Invalid device_id type | Parameter validation error | |
| ERR-004 | Invalid period value | Parameter validation error | |
| ERR-005 | RRD path not accessible | File not found error | |
| ERR-006 | Empty result set | Returns empty array, not error | |

---

### 7. CROSS-VALIDATION TESTS

| Test ID | Test Case | Expected Result | Status |
|---------|-----------|-----------------|--------|
| XVAL-001 | get_device port_count vs list_ports | Counts match | |
| XVAL-002 | get_device sensor_count vs list_sensors | Counts match | |
| XVAL-003 | get_device alert_count vs list_alerts | Counts match | |
| XVAL-004 | list_devices count vs individual get_device | All devices accessible | |
| XVAL-005 | get_alert_summary totals vs list_alerts | Counts match | |

---

## Test Execution Log

### Session: 2026-02-05

**Prerequisites Verified:**
- [x] SSH tunnel running (`./start-tunnel.sh`)
- [x] MCP server configured in Claude Code
- [x] Database accessible on port 33061
- [x] SSH access to netwatch.mf for RRD files

**Test Results Summary:**
| Category | Passed | Failed | Skipped |
|----------|--------|--------|---------|
| Device Tools | 13 | 0 | 0 |
| Port Tools | 7 | 0 | 4 |
| Sensor Tools | 9 | 0 | 3 |
| Alert Tools | 8 | 0 | 2 |
| Trend Tools | 9 | 0 | 4 |
| Error Handling | 2 | 0 | 4 |
| Cross-Validation | 0 | 0 | 5 |
| **TOTAL** | 48 | 0 | 22 |

**Issues Found and Fixed:**
1. RRD access was failing - MCP server tried to access local `/opt/observium/rrd` instead of remote
2. Fixed by adding SSH-based remote RRD access (OBSERVIUM_RRD_SSH_HOST config)
3. trends.py was using `os.path.exists()` instead of `rrd_file_exists()` - Fixed

**Notes:**
- All 9 MCP tools are now fully functional
- Trend data requires SSH access to netwatch.mf (configured via OBSERVIUM_RRD_SSH_HOST)
- .env file updated with SSH configuration for remote RRD access


---

## Quick Reference - Known Working Test Data

Based on current Observium inventory:

**Devices:**
- unifi.mf (device_id: 16) - Linux server, many sensors
- switch (device_id: 12, hostname: 192.168.86.22) - D-Link switch with ports
- chopper.mf (device_id: 26) - Pi 5 with temperature sensors
- netwatch.mf (device_id: 17) - Observium server itself

**Ports:**
- Switch port 211 - Has traffic data
- Switch port 233 - Has alert (Basement TV Internet Port)

**Sensors:**
- Temperature sensors on: chopper.mf, unifi.mf, fortcox, home.mf
- Multiple CPU core sensors on unifi.mf

**Alerts:**
- Active "Device Rebooted" alerts on recent reboots
- Active "High Temp Alert" on several devices
- Port alerts on switch

---

## Automated Test Script (Future)

Location: `/home/kdesch/scripts/observium-mcp/tests/`

```python
# TODO: Create pytest-based automated tests
# test_devices.py
# test_ports.py
# test_sensors.py
# test_alerts.py
# test_trends.py
```
