#!/usr/bin/env bash
echo "Deprecated: use scripts/restart-osiris.sh"
exec "$(dirname "$0")/restart-osiris.sh" "$@"
