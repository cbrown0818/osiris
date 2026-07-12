#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== OSIRIS COMMAND REGRESSION TESTS =="

docker compose exec -T osiris-api python - <<'PY'
from command_detector import detect_command
from routers.command_registry import can_dispatch_command, COMMAND_REGISTRY

detector_tests = {
    "project summary": "dev_summary",
    "dev summary": "dev_summary",
    "summarize osiris project": "dev_summary",
    "gpu status": "gpu_status",
    "security status": "security_status",
    "system snapshot": "system_snapshot",
    "pending patches": "patch_pending",
    "show patch backups": "patch_backups",
    "summarize the document": "doc_query",
    "what is the document about": "doc_query",
    "cognition optimize my codebase": "cognition",
    "agent loop inspect current osiris project health": "agent_loop",
    "self heal dry run": "self_heal",
    "self heal file osiris-api/app/assistant_router.py issue cleanup routing": "self_heal",
    "review file osiris-api/app/assistant_router.py": "dev_review_file",
    "explain file osiris-api/app/assistant_router.py": "dev_explain_file",
    "hello osiris": "chat",
}

required_dispatch_commands = [
    "dev_summary",
    "gpu_status",
    "security_status",
    "system_snapshot",
    "patch_pending",
    "patch_backups",
    "doc_query",
    "cognition",
    "agent_loop",
    "self_heal",
    "dev_review_file",
    "dev_explain_file",
]

print("Detector tests:")
for message, expected in detector_tests.items():
    actual = detect_command(message)
    print(f"  {message!r} -> {actual!r}")

    if actual != expected:
        raise SystemExit(
            f"Detector regression failed for {message!r}: "
            f"expected {expected!r}, got {actual!r}"
        )

print()
print("Registry dispatch tests:")
for command in required_dispatch_commands:
    dispatchable = can_dispatch_command(command)
    print(f"  {command!r} dispatchable -> {dispatchable}")

    if not dispatchable:
        raise SystemExit(f"Registry cannot dispatch required command: {command}")

print()
print("Registry contents:")
for command in sorted(COMMAND_REGISTRY):
    print(f"  {command}")

print()
print("OSIRIS COMMAND REGRESSION TESTS COMPLETE")
PY
