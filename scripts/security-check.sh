#!/usr/bin/env bash
set -euo pipefail

API_URL="http://localhost:8000"

echo "Osiris Security Check"
echo "---------------------"

security="$(curl -fsS "$API_URL/security/status")"

grade="$(SECURITY_JSON="$security" python3 -c 'import json,os; print(json.loads(os.environ["SECURITY_JSON"]).get("grade","unknown"))')"

echo "Security Grade: $grade"
echo

SECURITY_JSON="$security" python3 - << 'PY'
import json
import os

data = json.loads(os.environ["SECURITY_JSON"])

print("Issues:")
if data.get("issues"):
    for item in data["issues"]:
        print(f"  ❌ {item}")
else:
    print("  ✅ none")

print()
print("Warnings:")
if data.get("warnings"):
    for item in data["warnings"]:
        print(f"  ⚠️ {item}")
else:
    print("  ✅ none")

print()
print("Passed:")
for item in data.get("passed", []):
    print(f"  ✅ {item}")
PY
