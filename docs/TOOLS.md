# Observium MCP Tools Reference

Detailed documentation for all available MCP tools.

## Device Tools

### list_devices

List all devices monitored by Observium with their current status.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `status_filter` | string | No | Filter by status: `up`, `down`, or `disabled` |
| `os_filter` | string | No | Filter by OS type (e.g., `linux`, `ios`, `junos`) |

**Returns:** Array of device objects with:
- `device_id`: Unique device identifier
- `hostname`: Device hostname
- `sysname`: SNMP system name
- `os`: Operating system type
- `version`: Software version
- `hardware`: Hardware model
- `status`: Current status (up/down/disabled)
- `uptime`: Human-readable uptime
- `uptime_seconds`: Uptime in seconds
- `last_polled`: Last poll timestamp
- `location`: Device location

**Example:**
```
"List all devices that are currently down"
"Show me all Linux servers"
```

---

### get_device

Get detailed information about a specific device.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `device_id` | integer | No* | The device ID to look up |
| `hostname` | string | No* | The hostname to look up |

*One of `device_id` or `hostname` is required.

**Returns:** Device object with:
- All fields from `list_devices`
- `description`: System description
- `contact`: System contact
- `vendor`: Hardware vendor
- `serial`: Serial number
- `features`: Device features
- `ip`: IP address
- `snmp_version`: SNMP version in use
- `port_count`: Number of network ports
- `sensor_count`: Number of sensors
- `active_alert_count`: Number of active alerts

**Example:**
```
"Get details for the firewall device"
"Show me information about device ID 5"
```

---

## Port Tools

### list_ports

List network ports/interfaces for a device.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `device_id` | integer | No* | The device ID |
| `hostname` | string | No* | The hostname |
| `admin_status` | string | No | Filter by admin status: `up` or `down` |
| `oper_status` | string | No | Filter by oper status: `up` or `down` |

*One of `device_id` or `hostname` is required.

**Returns:** Array of port objects with:
- `port_id`: Unique port identifier
- `name`: Interface name
- `description`: Interface description
- `alias`: Interface alias (if configured)
- `speed`: Human-readable speed
- `speed_bps`: Speed in bits per second
- `admin_status`: Administrative status
- `oper_status`: Operational status
- `in_octets`: Total bytes received
- `out_octets`: Total bytes transmitted
- `in_errors`: Input errors
- `out_errors`: Output errors

**Example:**
```
"Show all ports on the core switch"
"Which ports are operationally down on router1?"
```

---

### get_port_traffic

Get detailed traffic statistics for a specific port.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `port_id` | integer | No* | The port ID |
| `device_hostname` | string | No* | Device hostname |
| `port_name` | string | No* | Port name or description |
| `period` | string | No | Time period: `1h`, `6h`, `1d`, `1w`, `1m` (default: `1d`) |

*Either `port_id` OR both `device_hostname` and `port_name` are required.

**Returns:** Traffic statistics including:
- Port identification details
- `current`: Current traffic rates
  - `in_rate_bps`: Inbound rate in bps
  - `out_rate_bps`: Outbound rate in bps
  - `in_utilization_pct`: Inbound utilization percentage
  - `out_utilization_pct`: Outbound utilization percentage
- `historical`: RRD data summary (if available)

**Example:**
```
"What's the traffic on GigabitEthernet0/1 on the switch?"
"Show me the weekly traffic for port 42"
```

---

## Sensor Tools

### list_sensors

List sensors for a device or all devices.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `device_id` | integer | No | Filter by device ID |
| `hostname` | string | No | Filter by hostname |
| `sensor_class` | string | No | Filter by class: `temperature`, `voltage`, `frequency`, etc. |

**Returns:** Array of sensor objects with:
- `sensor_id`: Unique sensor identifier
- `hostname`: Device hostname
- `class`: Sensor class (temperature, voltage, etc.)
- `type`: Sensor type/source
- `description`: Sensor description
- `value`: Current value (raw)
- `value_formatted`: Human-readable value with units
- `status`: Alert status (normal, warning_high, critical_high, etc.)
- `limits`: Threshold values

**Example:**
```
"What are the current temperatures on all devices?"
"Show me voltage sensors on the UPS"
```

---

## Alert Tools

### list_alerts

List alerts from Observium.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `device_id` | integer | No | Filter by device ID |
| `hostname` | string | No | Filter by hostname |
| `status` | string | No | Filter: `active`, `recovered`, or `all` (default: `active`) |
| `limit` | integer | No | Maximum alerts to return (default: 50) |

**Returns:** Array of alert objects with:
- `alert_id`: Alert identifier
- `hostname`: Device hostname
- `entity_type`: Type of entity (device, port, sensor, etc.)
- `alert_name`: Alert rule name
- `message`: Alert message
- `status`: Current status (active/recovered)
- `last_changed`: When the alert last changed state

**Example:**
```
"Are there any active alerts?"
"Show me all alerts for the firewall"
```

---

### get_alert_summary

Get a summary of current alert status.

**Parameters:** None

**Returns:** Summary object with:
- `total_active`: Count of active alerts
- `total_recovered`: Count of recovered alerts
- `by_entity_type`: Counts grouped by entity type
- `by_device`: Counts grouped by device (top 10)

**Example:**
```
"Give me an alert summary"
"How many alerts are there by device?"
```

---

## Trend Tools

### get_trends

Get historical trend data for a device metric.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `device_id` | integer | No* | The device ID |
| `hostname` | string | Yes* | The hostname |
| `metric` | string | No | Metric type: `load`, `cpu`, `memory`, `uptime` (default: `load`) |
| `period` | string | No | Time period: `1h`, `6h`, `1d`, `1w`, `1m` (default: `1d`) |

*One of `device_id` or `hostname` is required.

**Returns:** Trend data with:
- `hostname`: Device hostname
- `metric`: Metric type queried
- `period`: Time period
- `datasources`: Available data series names
- `statistics`: Min, max, avg, current for each datasource
- `data`: Array of data points (limited to last 100)

**Example:**
```
"What's the CPU load trend for the web server over the past week?"
"Show me memory usage for firewall.local today"
```

---

### list_available_metrics

List available metrics (RRD files) for a device.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `device_id` | integer | No* | The device ID |
| `hostname` | string | No* | The hostname |

*One of `device_id` or `hostname` is required.

**Returns:** Available metrics categorized by type:
- `system`: Load, CPU, memory, processes
- `network`: Port traffic, IP stats
- `sensors`: Temperature, voltage, etc.
- `performance`: Poller performance metrics
- `other`: Uncategorized RRD files

**Example:**
```
"What metrics are available for the firewall?"
"List RRD files for device 12"
```
