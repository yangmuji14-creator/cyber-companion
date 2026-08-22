#!/bin/sh
set -eu

mkdir -p /app/config /app/data /app/logs

if [ ! -f /app/config/settings.json ] && [ -f /opt/mu/default-config/settings.example.json ]; then
  cp /opt/mu/default-config/settings.example.json /app/config/settings.json
fi
if [ ! -f /app/config/personas.json ] && [ -f /opt/mu/default-config/personas.example.json ]; then
  cp /opt/mu/default-config/personas.example.json /app/config/personas.json
fi
if [ ! -f /app/config/mcp_servers.json ] && [ -f /opt/mu/default-config/mcp_servers.example.json ]; then
  cp /opt/mu/default-config/mcp_servers.example.json /app/config/mcp_servers.json
fi

exec "$@"
