#!/bin/bash
# Clean start script for agent-catalogue with current code

cd /home/dicolomb/amplifier-app-agent-catalogue

# Kill any existing servers
pkill -9 -f "agent-catalogue"
sleep 2

# Start fresh
echo "Starting agent-catalogue server..."
uv run agent-catalogue serve --host 127.0.0.1 --port 8000
