#!/usr/bin/env bash
set -euo pipefail

base_url="${STAGING_BASE_URL:-http://127.0.0.1:8081}"
temporary_dir="$(mktemp -d)"
trap 'rm -rf "$temporary_dir"' EXIT

curl --fail --silent --show-error "${base_url}/" >"${temporary_dir}/index.html"
grep -q '<title>AI 工程化与交付平台</title>' "${temporary_dir}/index.html"
curl --fail --silent --show-error "${base_url}/health/ready" >"${temporary_dir}/ready.json"
python3 - "${temporary_dir}/ready.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["status"] == "ok"
assert payload["checks"] == {"database": "ok"}
PY
echo "PASS: staging smoke at ${base_url}"
