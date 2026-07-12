#!/usr/bin/env bash
echo "Deprecated: use scripts/status-osiris.sh"
exec "$(dirname "$0")/status-osiris.sh" "$@"
