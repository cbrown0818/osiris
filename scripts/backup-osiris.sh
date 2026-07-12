#!/usr/bin/env bash
set -euo pipefail

OSIRIS_DIR="/srv/osiris"
BACKUP_ROOT="/srv/osiris/backups"
DATE="$(date +%Y-%m-%d_%H-%M-%S)"
BACKUP_DIR="$BACKUP_ROOT/$DATE"

POSTGRES_CONTAINER="osiris-postgres"
POSTGRES_USER="osiris_user"
POSTGRES_DB="osiris"

mkdir -p "$BACKUP_DIR"

echo "========================================"
echo " Osiris Backup Started: $DATE"
echo " Backup directory: $BACKUP_DIR"
echo "========================================"

echo "[1/8] Saving Docker container list..."
docker ps > "$BACKUP_DIR/docker-ps.txt"

echo "[2/8] Backing up compose and environment files..."
cp "$OSIRIS_DIR/docker-compose.yml" "$BACKUP_DIR/docker-compose.yml"

if [ -f "$OSIRIS_DIR/.env" ]; then
  cp "$OSIRIS_DIR/.env" "$BACKUP_DIR/env.backup"
  chmod 600 "$BACKUP_DIR/env.backup"
fi

echo "[3/8] Backing up website files..."
tar -czf "$BACKUP_DIR/website.tar.gz" -C "$OSIRIS_DIR" website

echo "[4/8] Backing up Osiris API files..."
tar -czf "$BACKUP_DIR/osiris-api.tar.gz" -C "$OSIRIS_DIR" osiris-api

echo "[5/8] Backing up Nginx Proxy Manager data..."
tar -czf "$BACKUP_DIR/proxy.tar.gz" -C "$OSIRIS_DIR" proxy

echo "[6/8] Backing up Uptime Kuma data..."
tar -czf "$BACKUP_DIR/uptime-kuma.tar.gz" -C "$OSIRIS_DIR" monitoring

echo "[7/8] Backing up PostgreSQL database..."
docker exec "$POSTGRES_CONTAINER" pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > "$BACKUP_DIR/postgres-osiris.sql"

echo "[8/8] Backing up Qdrant vector storage..."
tar -czf "$BACKUP_DIR/qdrant.tar.gz" -C "$OSIRIS_DIR" qdrant

echo "Creating final archive..."
tar -czf "$BACKUP_ROOT/osiris-backup-$DATE.tar.gz" -C "$BACKUP_ROOT" "$DATE"

echo "Calculating checksum..."
sha256sum "$BACKUP_ROOT/osiris-backup-$DATE.tar.gz" > "$BACKUP_ROOT/osiris-backup-$DATE.tar.gz.sha256"

echo "Cleaning temporary backup directory..."
rm -rf "$BACKUP_DIR"

echo "========================================"
echo " Osiris Backup Complete"
echo " Archive:"
echo " $BACKUP_ROOT/osiris-backup-$DATE.tar.gz"
echo " Checksum:"
echo " $BACKUP_ROOT/osiris-backup-$DATE.tar.gz.sha256"
echo "========================================"

