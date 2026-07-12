import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LOG_DIR = Path("/app/logs")
ACTION_LOG = LOG_DIR / "actions.log"


def log_action(entry: dict[str, Any]) -> dict[str, Any]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **entry,
    }

    with ACTION_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    return entry


def read_recent_actions(limit: int = 50) -> list[dict[str, Any]]:
    if not ACTION_LOG.exists():
        return []

    lines = ACTION_LOG.read_text(encoding="utf-8").splitlines()
    recent = lines[-limit:]

    actions = []
    for line in recent:
        try:
            actions.append(json.loads(line))
        except Exception:
            actions.append({"raw": line})

    return actions
