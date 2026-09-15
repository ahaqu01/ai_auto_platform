#!/usr/bin/env bash
set -euo pipefail

action="${1:-}"
environment="${E2E_ENVIRONMENT:-demo}"
username="${E2E_USERNAME:-m1-e2e}"
email="${E2E_EMAIL:-m1-e2e@example.test}"
kcadm="/opt/keycloak/bin/kcadm.sh"

case "$environment" in
  demo)
    container="ai-auto-platform-demo-keycloak-1"
    realm="ai-platform"
    ;;
  staging)
    container="ai-auto-platform-staging-keycloak-1"
    realm="ai-platform-staging"
    ;;
  *)
    echo "E2E_ENVIRONMENT must be demo or staging" >&2
    exit 2
    ;;
esac

if [[ "$action" != "create" && "$action" != "delete" ]]; then
  echo "usage: E2E_PASSWORD=... E2E_ENVIRONMENT=demo|staging $0 create|delete" >&2
  exit 2
fi
if [[ "$username" != m1-e2e* ]]; then
  echo "refusing non-E2E username: $username" >&2
  exit 2
fi

admin_username="$(docker exec "$container" printenv KC_BOOTSTRAP_ADMIN_USERNAME)"
admin_password="$(docker exec "$container" printenv KC_BOOTSTRAP_ADMIN_PASSWORD)"
docker exec "$container" "$kcadm" config credentials \
  --server http://127.0.0.1:8080/auth \
  --realm master \
  --user "$admin_username" \
  --password "$admin_password" >/dev/null

user_id="$({
  docker exec "$container" "$kcadm" get users -r "$realm" \
    -q "username=$username" --fields id,username
} | python3 -c 'import json,sys; rows=json.load(sys.stdin); print(rows[0]["id"] if rows else "")')"
if [[ -z "$user_id" ]]; then
  user_id="$({
    docker exec "$container" "$kcadm" get users -r "$realm" \
      -q "email=$email" --fields id,username
  } | python3 -c 'import json,sys; rows=json.load(sys.stdin); print(rows[0]["id"] if rows else "")')"
fi

if [[ "$action" == "delete" ]]; then
  if [[ -n "$user_id" ]]; then
    docker exec "$container" "$kcadm" delete "users/$user_id" -r "$realm"
  fi
  echo "$environment E2E user absent: $username"
  exit 0
fi

if [[ -z "${E2E_PASSWORD:-}" ]]; then
  echo "E2E_PASSWORD is required for create" >&2
  exit 2
fi
if [[ -z "$user_id" ]]; then
  docker exec "$container" "$kcadm" create users -r "$realm" \
    -s "username=$username" -s "email=$email" \
    -s firstName=M1 -s lastName=E2E -s enabled=true >/dev/null
  user_id="$({
    docker exec "$container" "$kcadm" get users -r "$realm" \
      -q "email=$email" --fields id
  } | python3 -c 'import json,sys; rows=json.load(sys.stdin); print(rows[0]["id"] if rows else "")')"
fi
if [[ -z "$user_id" ]]; then
  echo "E2E user lookup failed after create: $email" >&2
  exit 1
fi
docker exec "$container" "$kcadm" set-password -r "$realm" \
  --userid "$user_id" --new-password "$E2E_PASSWORD" --temporary=false
echo "$environment E2E user ready: $username"
