#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
run_id="${E2E_RUN_ID:-$(date -u +%Y%m%d%H%M%S)}"
if [[ ! "$run_id" =~ ^[A-Za-z0-9-]+$ ]]; then
  echo "E2E_RUN_ID may contain only letters, digits and hyphens" >&2
  exit 2
fi

environment="${E2E_ENVIRONMENT:-demo}"
username="${E2E_USERNAME:-m1-e2e-close03}"
email="${E2E_EMAIL:-m2-close03@example.test}"
base_url="${E2E_BASE_URL:-http://192.168.1.129:8080}"
organization_name="M2-CLOSE-03-$run_id"
project="ai-auto-platform-$environment"
postgres_container="$project-postgres-1"
api_container="$project-api-1"

if [[ -z "${E2E_PASSWORD:-}" ]]; then
  echo "E2E_PASSWORD is required" >&2
  exit 2
fi

cleanup() {
  set +e
  mapfile -t object_keys < <(
    docker exec "$postgres_container" psql -U platform -d platform -Atc \
      "select a.object_key from artifacts a join organizations o on o.id=a.organization_id where o.name='$organization_name';"
  )
  if ((${#object_keys[@]})); then
    for object_key in "${object_keys[@]}"; do
      [[ -z "$object_key" ]] && continue
      docker exec -e E2E_OBJECT_KEY="$object_key" "$api_container" python -c \
        'import asyncio,os; from platform_api.settings import get_settings; from platform_api.modules.artifact.storage_runtime import build_object_storage; s=get_settings(); a=build_object_storage(s); asyncio.run(a.delete(os.environ["E2E_OBJECT_KEY"]))'
    done
  fi
  docker exec "$postgres_container" psql -v ON_ERROR_STOP=1 -U platform -d platform -c \
    "delete from organizations where name='$organization_name';"
  E2E_ENVIRONMENT="$environment" E2E_USERNAME="$username" E2E_EMAIL="$email" \
    bash "$root/scripts/manage_demo_e2e_user.sh" delete
}
trap cleanup EXIT

E2E_ENVIRONMENT="$environment" E2E_USERNAME="$username" E2E_EMAIL="$email" \
  E2E_PASSWORD="$E2E_PASSWORD" bash "$root/scripts/manage_demo_e2e_user.sh" create

E2E_BASE_URL="$base_url" E2E_USERNAME="$email" E2E_EMAIL="$email" \
  E2E_PASSWORD="$E2E_PASSWORD" E2E_RUN_ID="$run_id" \
  E2E_RESULTS_FILE="test-results/m2-close-03-results.json" \
  npm --prefix "$root/apps/web" run test:e2e -- "${E2E_SPEC_FILE:-e2e/m2-close-03-oss.spec.ts}"
