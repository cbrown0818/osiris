#!/usr/bin/env bash
set -euo pipefail

cd /srv/osiris

echo "Stopping Osiris Docker stack..."
docker compose down

echo "Stopping Osiris Host Agent service..."
sudo systemctl stop osiris-host-agent

echo
echo "Osiris stopped."
