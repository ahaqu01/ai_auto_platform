#!/usr/bin/env bash
set -euo pipefail

action="${1:-}"
username="${E2E_USERNAME:-m1-e2e}"
email="${E2E_EMAIL:-m1-e2e@example.test}"
compose_file="deploy/demo/docker-compose.yml"
container="ai-auto-platform-demo-keycloak-1"
kcadm="/opt/keycloak/bin/kcadm.sh"

if [[ "$action" != "create" && "$action" != "delete" ]]; then
  echo "usage: E2E_PASSWORD=... $0 create|delete" >&2
  exit 2
fi
if [[ "$username" != m1-e2e* ]]; then
  echo "refusing non-E2E username: $username" >&2
  exit 2
fi
if [[ ! -f "$compose_file" ]]; then
  echo "run from repository root" >&2
  exit 2
fi

docker exec "$container" "$kcadm" config credentials \
  --server http://127.0.0.1:8080/auth \
  --realm master \
  --user admin \
  --password admin-local-demo-only >/dev/null

user_id="$({
  docker exec "$container" "$kcadm" get users -r ai-platform \
    -q "username=$username" --fields id,username
} | python3 -c 'import json,sys; rows=json.load(sys.stdin); print(rows[0]["id"] if rows else "")')"

if [[ "$action" == "delete" ]]; then
  if [[ -n "$user_id" ]]; then
    docker exec "$container" "$kcadm" delete "users/$user_id" -r ai-platform
  fi
  echo "demo E2E user absent: $username"
  exit 0
fi

if [[ -z "${E2E_PASSWORD:-}" ]]; then
  echo "E2E_PASSWORD is required for create" >&2
  exit 2
fi
if [[ -z "$user_id" ]]; then
  docker exec "$container" "$kcadm" create users -r ai-platform \
    -s "username=$username" -s "email=$email" \
    -s firstName=M1 -s lastName=E2E -s enabled=true >/dev/null
fi
docker exec "$container" "$kcadm" set-password -r ai-platform \
  --username "$username" --new-password "$E2E_PASSWORD" --temporary=false
echo "demo E2E user ready: $username"
