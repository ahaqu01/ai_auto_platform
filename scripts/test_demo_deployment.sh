#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose_file="${repo_root}/deploy/demo/docker-compose.yml"
nginx_file="${repo_root}/deploy/demo/nginx.conf"
api_dockerfile="${repo_root}/deploy/demo/api.Dockerfile"
web_dockerfile="${repo_root}/deploy/demo/web.Dockerfile"
smoke_script="${repo_root}/scripts/smoke_demo.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

for required in "$compose_file" "$nginx_file" "$api_dockerfile" "$web_dockerfile" "$smoke_script"; do
  [[ -f "$required" ]] || fail "missing ${required#"${repo_root}/"}"
done

docker compose -f "$compose_file" config --quiet
rendered="$(docker compose -f "$compose_file" config)"
for service in postgres redis minio migrate api web; do
  grep -q "^  ${service}:" <<<"$rendered" || fail "missing service: $service"
done

published="$(docker compose -f "$compose_file" config --format json)"
python3 - "$published" <<'PY'
import json
import sys

services = json.loads(sys.argv[1])["services"]
for name in ("postgres", "redis", "minio", "api", "migrate"):
    if services[name].get("ports"):
        raise SystemExit(f"FAIL: {name} must not publish host ports")

web_ports = services["web"].get("ports", [])
if len(web_ports) != 1:
    raise SystemExit("FAIL: web must publish exactly one port")
port = web_ports[0]
if int(port["published"]) != 8080 or int(port["target"]) != 80:
    raise SystemExit("FAIL: web must publish host 8080 to container 80")
PY

grep -q 'alembic.*upgrade head' "$compose_file" || fail "migration command missing"
grep -q 'location /health/' "$nginx_file" || fail "health proxy missing"
grep -q 'location /api/' "$nginx_file" || fail "API proxy missing"
grep -q 'location /docs' "$nginx_file" || fail "docs proxy missing"
grep -q 'try_files.*index.html' "$nginx_file" || fail "SPA fallback missing"
grep -q 'HEALTHCHECK' "$api_dockerfile" || fail "API image healthcheck missing"
grep -q '.demo-cache/wheels' "$api_dockerfile" || fail "offline wheel cache missing"
grep -q 'COPY apps/web/dist' "$web_dockerfile" || fail "tested Web dist copy missing"

echo "PASS: M0D-01 static deployment contract"
