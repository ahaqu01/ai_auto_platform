#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

.venv/bin/ruff check apps/api/src apps/api/tests scripts
.venv/bin/python scripts/export_openapi.py --check
.venv/bin/pytest apps/api/tests -m 'not postgresql' -q
.venv/bin/python scripts/check_docs.py .
bash scripts/test_demo_deployment.sh

npm --prefix apps/web test
npm --prefix apps/web run build
npm --prefix apps/web audit --audit-level=high

(cd apps/agent && go vet ./... && go test -race ./...)

echo "PASS: local CI baseline"
