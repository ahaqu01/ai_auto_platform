#!/usr/bin/env bash
set -euo pipefail

base_url="${DEMO_BASE_URL:-http://127.0.0.1:8080}"
temporary_dir="$(mktemp -d)"
trap 'rm -rf "$temporary_dir"' EXIT

curl --fail --silent --show-error "${base_url}/" >"${temporary_dir}/index.html"
grep -q '<title>AI 工程化与交付平台</title>' "${temporary_dir}/index.html"
grep -q 'name="application-version" content="m0d-02"' "${temporary_dir}/index.html"

curl --fail --silent --show-error "${base_url}/health/live" >"${temporary_dir}/health.json"
python3 - "${temporary_dir}/health.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["status"] == "ok", payload
assert payload["service"] == "ai-auto-platform", payload
PY

curl --fail --silent --show-error "${base_url}/docs" >"${temporary_dir}/docs.html"
grep -q 'Swagger UI' "${temporary_dir}/docs.html"

echo "PASS: M0D-01 HTTP smoke test at ${base_url}"
