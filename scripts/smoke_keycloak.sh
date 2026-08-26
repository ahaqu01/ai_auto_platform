#!/usr/bin/env bash
set -euo pipefail

base_url="${KEYCLOAK_BASE_URL:-http://127.0.0.1:8080/auth}"
realm_url="${base_url}/realms/ai-platform"
temporary_dir="$(mktemp -d)"
trap 'rm -rf "$temporary_dir"' EXIT

curl --fail --silent --show-error "${realm_url}/.well-known/openid-configuration" >"${temporary_dir}/discovery.json"
curl --fail --silent --show-error -X POST "${realm_url}/protocol/openid-connect/token" \
  -d grant_type=client_credentials -d client_id=platform-bff -d client_secret=bff-local-demo-only \
  >"${temporary_dir}/token.json"

python3 - "$temporary_dir" <<'PY'
import base64
import json
import sys
from pathlib import Path

directory = Path(sys.argv[1])
discovery = json.loads((directory / "discovery.json").read_text())
assert discovery["issuer"].endswith("/auth/realms/ai-platform")
assert discovery["authorization_endpoint"].endswith("/protocol/openid-connect/auth")
token = json.loads((directory / "token.json").read_text())["access_token"]
payload = token.split(".")[1]
payload += "=" * (-len(payload) % 4)
claims = json.loads(base64.urlsafe_b64decode(payload))
assert claims["iss"].endswith("/auth/realms/ai-platform")
audience = claims["aud"] if isinstance(claims["aud"], list) else [claims["aud"]]
assert "platform-api" in audience
PY

echo "PASS: Keycloak Realm, discovery and signed token"
