#!/usr/bin/env bash
set -u

API_URL="http://localhost:8000"
WEB_URL="http://localhost:8088"

line() {
  echo "------------------------------------------------------------"
}

section() {
  echo
  line
  echo "$1"
  line
}

ok() {
  echo "✅ $1"
}

warn() {
  echo "⚠️  $1"
}

fail() {
  echo "❌ $1"
}

section "Osiris Status Check"

echo "Time: $(date)"
echo "Project: $(readlink -f /srv/osiris 2>/dev/null || echo /srv/osiris)"

section "Docker Containers"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" || fail "Docker command failed"

section "Osiris API Health"
health="$(curl -fsS "$API_URL/health" 2>/dev/null || true)"
if [ -n "$health" ]; then
  echo "$health"
  echo "$health" | grep -q '"api":"ok"' && ok "API is responding" || warn "API response did not show api ok"
  echo "$health" | grep -q '"postgres":"ok"' && ok "Postgres is ok" || warn "Postgres is not ok"
  echo "$health" | grep -q '"qdrant":"ok"' && ok "Qdrant is ok" || warn "Qdrant is not ok"
  echo "$health" | grep -q '"ollama":"ok"' && ok "Ollama is ok" || warn "Ollama is not ok"
else
  fail "API health endpoint failed"
fi

section "Security Status"
security="$(curl -fsS "$API_URL/security/status" 2>/dev/null || true)"
if [ -n "$security" ]; then
  grade="$(SECURITY_JSON="$security" python3 -c 'import json,os; print(json.loads(os.environ["SECURITY_JSON"]).get("grade","unknown"))' 2>/dev/null || echo unknown)"
  echo "Security Grade: $grade"

  if [ "$grade" = "Strong" ]; then
    ok "Security grade is Strong"
  else
    warn "Security grade is not Strong"
  fi

  SECURITY_JSON="$security" python3 - << 'PY'
import json
import os

data = json.loads(os.environ.get("SECURITY_JSON", "{}"))

print("Issues:")
for item in data.get("issues", []):
    print(f"  - {item}")
if not data.get("issues"):
    print("  none")

print("Warnings:")
for item in data.get("warnings", []):
    print(f"  - {item}")
if not data.get("warnings"):
    print("  none")

print("Passed:")
for item in data.get("passed", [])[:12]:
    print(f"  - {item}")
PY
else
  fail "Security status endpoint failed"
fi

section "Host Agent Service"
if systemctl is-active --quiet osiris-host-agent; then
  ok "osiris-host-agent service is active"
else
  fail "osiris-host-agent service is not active"
fi

systemctl status osiris-host-agent --no-pager | sed -n '1,12p' || true

section "Host Agent Listener"
if sudo ss -tulpn | grep -q '172.17.0.1:5055'; then
  ok "Host Agent is bound to Docker gateway 172.17.0.1:5055"
else
  warn "Host Agent is not detected on 172.17.0.1:5055"
fi

sudo ss -tulpn | grep 5055 || true

section "Host Agent Health"
if docker exec osiris-api curl -fsS http://host.docker.internal:5055/health 2>/dev/null; then
  echo
  ok "API container can reach Host Agent"
else
  fail "API container cannot reach Host Agent"
fi

section "Website Dashboard"
if curl -fsSI "$WEB_URL/chat.html" >/dev/null 2>&1; then
  ok "Chat dashboard reachable at $WEB_URL/chat.html"
else
  fail "Chat dashboard not reachable"
fi

if curl -fsSI "$WEB_URL/security.html" >/dev/null 2>&1; then
  ok "Security dashboard reachable at $WEB_URL/security.html"
else
  warn "Security dashboard not reachable"
fi

section "Pending Patches"
patches="$(curl -fsS "$API_URL/patches/pending" 2>/dev/null || true)"
if [ -n "$patches" ]; then
  echo "$patches" | python3 -m json.tool 2>/dev/null || echo "$patches"
else
  warn "Could not check pending patches"
fi

section "Pending Approvals"
approvals="$(curl -fsS "$API_URL/approvals/pending" 2>/dev/null || true)"
if [ -n "$approvals" ]; then
  echo "$approvals" | python3 -m json.tool 2>/dev/null || echo "$approvals"
else
  warn "Could not check pending approvals"
fi

section "System Summary"
summary="$(curl -fsS "$API_URL/host/summary" 2>/dev/null || true)"
if [ -n "$summary" ]; then
  SUMMARY_JSON="$summary" python3 - << 'PY'
import json
import os

data = json.loads(os.environ.get("SUMMARY_JSON", "{}"))
system = data.get("system", {})
host = system.get("host", {})
cpu = system.get("cpu", {})
memory = system.get("memory", {})
disk = system.get("disk", {})
gpu = data.get("gpu", {})

print(f"Host: {host.get('hostname')}")
print(f"CPU: {cpu.get('physical_cores')} cores / {cpu.get('logical_cores')} threads | {cpu.get('percent')}% used")
print(f"RAM: {memory.get('used_gb')} GB used / {memory.get('total_gb')} GB total | {memory.get('available_gb')} GB available")
print(f"Disk: {disk.get('used_gb')} GB used / {disk.get('total_gb')} GB total | {disk.get('free_gb')} GB free")

if gpu.get("available") and gpu.get("gpus"):
    g = gpu["gpus"][0]
    print(f"GPU: {g.get('name')} | {g.get('temperature_c')}°C | VRAM {g.get('memory_used_mib')}/{g.get('memory_total_mib')} MiB")
else:
    print("GPU: not available")
PY
else
  warn "Could not load host summary"
fi

section "Status Check Complete"
