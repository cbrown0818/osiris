#!/usr/bin/env bash
set -euo pipefail

cd /srv/osiris

echo "Restarting Osiris Docker stack..."
docker compose up -d --force-recreate

echo "Restarting Osiris Host Agent service..."
sudo systemctl restart osiris-host-agent

sleep 5

echo
echo "Osiris restarted. Running status check..."
./scripts/status-osiris.sh
