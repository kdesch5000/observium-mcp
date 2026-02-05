# Observium MCP Server

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that exposes [Observium CE](https://www.observium.org/) network monitoring data to LLMs like Claude, enabling natural language queries about device status, network traffic, sensor readings, alerts, and historical trends.

## Features

- **Device Management**: List and query monitored devices with status, uptime, and hardware info
- **Network Ports**: View interface status, traffic rates, and utilization
- **Sensors**: Access temperature, voltage, frequency, and other sensor data
- **Alerts**: Query active and historical alerts with summaries
- **Trends**: Retrieve historical metrics from RRD data (load, CPU, memory)

## Requirements

- Python 3.9+
- Observium CE installation with MySQL database access
- Access to Observium's RRD data directory

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/observium-mcp.git
cd observium-mcp
```

### 2. Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

Copy the example configuration and edit with your Observium database credentials:

```bash
cp config.example.env .env
```

Edit `.env` with your settings:

```bash
OBSERVIUM_DB_HOST=localhost
OBSERVIUM_DB_NAME=observium
OBSERVIUM_DB_USER=observium
OBSERVIUM_DB_PASS=your_database_password
OBSERVIUM_RRD_PATH=/opt/observium/rrd
```

## Usage

### With Claude Code

Add to your Claude Code MCP configuration (`~/.claude/claude_code_config.json`):

```json
{
  "mcpServers": {
    "observium": {
      "command": "python",
      "args": ["-m", "observium_mcp.server"],
      "cwd": "/path/to/observium-mcp/src",
      "env": {
        "OBSERVIUM_DB_HOST": "localhost",
        "OBSERVIUM_DB_NAME": "observium",
        "OBSERVIUM_DB_USER": "observium",
        "OBSERVIUM_DB_PASS": "your_password",
        "OBSERVIUM_RRD_PATH": "/opt/observium/rrd"
      }
    }
  }
}
```

### With Claude Desktop

Add to your Claude Desktop configuration:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "observium": {
      "command": "python",
      "args": ["-m", "observium_mcp.server"],
      "cwd": "/path/to/observium-mcp/src",
      "env": {
        "OBSERVIUM_DB_HOST": "your_observium_host",
        "OBSERVIUM_DB_NAME": "observium",
        "OBSERVIUM_DB_USER": "observium",
        "OBSERVIUM_DB_PASS": "your_password",
        "OBSERVIUM_RRD_PATH": "/opt/observium/rrd"
      }
    }
  }
}
```

### Standalone

```bash
cd src
python -m observium_mcp.server
```

## Available Tools

| Tool | Description |
|------|-------------|
| `list_devices` | List all monitored devices with status |
| `get_device` | Get detailed info for a specific device |
| `list_ports` | List network interfaces for a device |
| `get_port_traffic` | Get traffic stats for a specific port |
| `list_sensors` | List sensor readings (temp, voltage, etc.) |
| `list_alerts` | List active or historical alerts |
| `get_alert_summary` | Get alert count summary |
| `get_trends` | Get historical metric data |
| `list_available_metrics` | List available RRD metrics for a device |

## Example Queries

Once connected, you can ask Claude questions like:

- "What devices are currently down?"
- "Show me the temperature sensors on the main switch"
- "What's the CPU load trend for the firewall over the past week?"
- "Are there any active alerts?"
- "Which ports on the core switch have errors?"
- "What's the uptime of all my Linux servers?"

## Remote Access

If your Observium instance is on a remote server, you have several options:

### Option 1: SSH Tunnel

```bash
# Create SSH tunnel to forward MySQL port
ssh -L 3306:localhost:3306 user@observium-server

# Then configure .env with localhost
OBSERVIUM_DB_HOST=localhost
```

### Option 2: Install on Observium Server

Install the MCP server directly on the Observium host and configure Claude to connect via SSH.

### Option 3: Network Access

If MySQL is accessible on the network (not recommended for security):

```bash
OBSERVIUM_DB_HOST=observium.example.com
```

## Security Considerations

- Database credentials are stored in `.env` which is gitignored
- The server only performs SELECT queries (read-only)
- Consider using a read-only MySQL user for additional safety
- RRD access is read-only via `rrdtool fetch`

## Creating a Read-Only Database User

For additional security, create a dedicated read-only MySQL user:

```sql
CREATE USER 'observium_mcp'@'localhost' IDENTIFIED BY 'secure_password';
GRANT SELECT ON observium.* TO 'observium_mcp'@'localhost';
FLUSH PRIVILEGES;
```

## Troubleshooting

### Connection refused

- Verify MySQL is running and accessible
- Check database credentials in `.env`
- Ensure the MySQL user has SELECT permissions

### No RRD data

- Verify `OBSERVIUM_RRD_PATH` points to the correct directory
- Check file permissions on the RRD directory
- Ensure `rrdtool` is installed and in PATH

### Module not found

Make sure you're running from the `src` directory or have installed the package:

```bash
cd /path/to/observium-mcp/src
python -m observium_mcp.server
```

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

- [Observium](https://www.observium.org/) - Network monitoring platform
- [Model Context Protocol](https://modelcontextprotocol.io/) - The MCP specification
- [Anthropic](https://www.anthropic.com/) - Claude and MCP development
