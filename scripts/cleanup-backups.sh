#!/usr/bin/env bash
set -euo pipefail

BACKUP_ROOT="/srv/osiris/backups"
DAYS_TO_KEEP=14

echo "Cleaning Osiris backups older than $DAYS_TO_KEEP days..."

find "$BACKUP_ROOT" -type f -name "osiris-backup-*.tar.gz" -mtime +"$DAYS_TO_KEEP" -print -delete
find "$BACKUP_ROOT" -type f -name "osiris-backup-*.tar.gz.sha256" -mtime +"$DAYS_TO_KEEP" -print -delete

echo "Cleanup complete."

