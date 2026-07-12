#!/usr/bin/env bash
set -euo pipefail

cd /srv/osiris

echo "Starting Osiris Docker stack..."
docker compose up -d

echo "Starting Osiris Host Agent service..."
sudo systemctl start osiris-host-agent

echo
echo "Osiris started. Running status check..."
./scripts/status-osiris.sh
