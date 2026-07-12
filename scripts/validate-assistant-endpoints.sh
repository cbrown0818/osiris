#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== OSIRIS ASSISTANT ENDPOINT SMOKE TESTS =="

python3 <<'PY'
import json
import urllib.request
import urllib.error
import sys

URL = "http://localhost:8000/assistant/command"

tests = [
    ("project summary", "dev_summary"),
    ("gpu status", "gpu_status"),
    ("security status", "security_status"),
    ("pending patches", "patch_pending"),
    ("show patch backups", "patch_backups"),
    ("self heal dry run", "self_heal"),
]

def call_assistant(message: str) -> dict:
    payload = json.dumps({"message": message}).encode("utf-8")

    request = urllib.request.Request(
        URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP error for {message!r}: {exc.code}\n{body}") from exc
    except Exception as exc:
        raise SystemExit(f"Request failed for {message!r}: {exc}") from exc

for message, expected_command in tests:
    result = call_assistant(message)
    actual_command = result.get("command")

    print(f"endpoint: {message!r} -> {actual_command!r}")

    if actual_command != expected_command:
        print(json.dumps(result, indent=2))
        raise SystemExit(
            f"Expected command {expected_command!r}, got {actual_command!r}"
        )

    if message == "self heal dry run":
        data = result.get("data") or {}

        if data.get("status") != "dry_run":
            print(json.dumps(result, indent=2))
            raise SystemExit("Self-heal dry-run did not return dry_run status")

        if data.get("patch_created") is not False:
            print(json.dumps(result, indent=2))
            raise SystemExit("Self-heal dry-run reported patch creation")

pending_result = call_assistant("pending patches")
pending_data = pending_result.get("data") or {}

if pending_data.get("count") != 0:
    print(json.dumps(pending_result, indent=2))
    raise SystemExit("Pending patches were created during smoke tests")

print("OK no pending patches after smoke tests")
print("OSIRIS ASSISTANT ENDPOINT SMOKE TESTS COMPLETE")
PY
