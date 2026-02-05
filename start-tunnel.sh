#!/bin/bash
# Start SSH tunnel to Observium MySQL database
# Run this before using the Observium MCP server

TUNNEL_PORT=33061
REMOTE_HOST="pi@netwatch.mf"

# Check if tunnel already exists
if ss -tlnp | grep -q ":${TUNNEL_PORT}"; then
    echo "SSH tunnel already running on port ${TUNNEL_PORT}"
    exit 0
fi

# Create tunnel
echo "Creating SSH tunnel to ${REMOTE_HOST} on port ${TUNNEL_PORT}..."
ssh -f -N -L ${TUNNEL_PORT}:localhost:3306 ${REMOTE_HOST}

if [ $? -eq 0 ]; then
    echo "SSH tunnel created successfully"
else
    echo "Failed to create SSH tunnel"
    exit 1
fi
