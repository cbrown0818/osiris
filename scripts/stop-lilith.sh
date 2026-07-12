#!/usr/bin/env bash
echo "Deprecated: use scripts/stop-osiris.sh"
exec "$(dirname "$0")/stop-osiris.sh" "$@"
