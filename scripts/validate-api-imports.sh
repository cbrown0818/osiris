#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== OSIRIS API IMPORT VALIDATION =="

docker compose exec -T osiris-api python - <<'PY'
import asyncio
import importlib

modules = [
    "assistant_router",
    "command_detector",
    "intent_classifier",
    "routers.command_registry",
    "routers.system_router",
    "routers.dev_router",
    "routers.document_router",
    "routers.patch_router",
    "routers.dev_review_router",
    "routers.agent_router",
    "routers.self_heal_router",
]

for module_name in modules:
    importlib.import_module(module_name)
    print(f"OK import: {module_name}")

from command_detector import detect_command
from routers.command_registry import can_dispatch_command
from routers.self_heal_router import handle_self_heal_command

detector_tests = {
    "project summary": "dev_summary",
    "gpu status": "gpu_status",
    "security status": "security_status",
    "pending patches": "patch_pending",
    "show patch backups": "patch_backups",
    "summarize the document": "doc_query",
    "cognition optimize my codebase": "cognition",
    "agent loop inspect current osiris project health": "agent_loop",
    "self heal dry run": "self_heal",
    "review file osiris-api/app/assistant_router.py": "dev_review_file",
    "explain file osiris-api/app/assistant_router.py": "dev_explain_file",
}

for message, expected in detector_tests.items():
    command = detect_command(message)
    print(f"detect: {message!r} -> {command!r}")

    if command != expected:
        raise SystemExit(f"Expected {expected}, got {command}")

    if command != "chat" and not can_dispatch_command(command):
        raise SystemExit(f"Registry cannot dispatch {command}")

async def main():
    result = await handle_self_heal_command("self_heal", "self heal dry run")

    if result.get("command") != "self_heal":
        raise SystemExit("Self-heal dry-run returned wrong command")

    data = result.get("data") or {}

    if data.get("status") != "dry_run":
        raise SystemExit("Self-heal dry-run did not return dry_run status")

    if data.get("patch_created") is not False:
        raise SystemExit("Self-heal dry-run created or reported a patch")

    print("OK self-heal dry-run safety")

asyncio.run(main())

print("OSIRIS API IMPORT VALIDATION COMPLETE")
PY
