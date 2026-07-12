#!/usr/bin/env bash
echo "Deprecated: use scripts/start-osiris.sh"
exec "$(dirname "$0")/start-osiris.sh" "$@"
