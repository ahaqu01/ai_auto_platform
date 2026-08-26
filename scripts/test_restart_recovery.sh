#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose_file="${repo_root}/deploy/demo/docker-compose.yml"
base_url="${BASE_URL:-http://127.0.0.1:8080}"

curl --fail --silent "${base_url}/health/ready" >/dev/null || {
  echo "FAIL: API is not ready before restart" >&2
  exit 1
}

docker compose -f "$compose_file" restart api >/dev/null

for _ in $(seq 1 30); do
  if curl --fail --silent "${base_url}/health/ready" >/dev/null; then
    echo "PASS: API readiness recovered after restart"
    exit 0
  fi
  sleep 1
done

echo "FAIL: API readiness did not recover within 30 seconds" >&2
exit 1
