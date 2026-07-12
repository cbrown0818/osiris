#!/usr/bin/env bash
set -e

echo "== OSIRIS VALIDATION =="

echo
echo "[1/6] Docker containers"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo
echo "[2/6] API health"
curl -s http://localhost:8000/health && echo

echo
echo "[3/6] Host Agent health"
curl -s http://172.17.0.1:5055/health && echo

echo
echo "[4/6] GPU status"
curl -s http://localhost:8000/assistant/command \
  -H "Content-Type: application/json" \
  -d '{"message":"show gpu status"}' && echo

echo
echo "[5/6] Security status"
curl -s http://localhost:8000/security/status && echo

echo
echo "[6/6] Full system snapshot"
curl -s http://localhost:8000/assistant/command \
  -H "Content-Type: application/json" \
  -d '{"message":"full system snapshot"}' && echo

echo
echo
echo "[7/7] API import validation"
./scripts/validate-api-imports.sh

echo
echo "[8/8] Assistant endpoint smoke tests"
./scripts/validate-assistant-endpoints.sh

echo
echo "[9/9] Command regression tests"
./scripts/validate-command-regression.sh

echo "OSIRIS VALIDATION COMPLETE"
