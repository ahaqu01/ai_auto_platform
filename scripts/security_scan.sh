#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir"

.venv/bin/pip-audit --local --skip-editable
.venv/bin/bandit -q -r apps/api/src -lll -i
npm --prefix apps/web audit --audit-level=high

govulncheck_bin="${GOVULNCHECK_BIN:-$root_dir/.security-bin/govulncheck}"
if [[ ! -x "$govulncheck_bin" ]]; then
  echo "govulncheck is required at $govulncheck_bin" >&2
  exit 2
fi
(
  cd apps/agent
  "$govulncheck_bin" ./...
)

echo "M1 SECURITY SCAN PASSED"
