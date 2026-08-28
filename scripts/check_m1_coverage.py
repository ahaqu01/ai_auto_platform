#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

SECURITY_MODULES = (
    "apps/api/src/platform_api/api/auth.py",
    "apps/api/src/platform_api/api/organization_access.py",
    "apps/api/src/platform_api/auth/bff.py",
    "apps/api/src/platform_api/auth/dependencies.py",
    "apps/api/src/platform_api/auth/verifier.py",
    "apps/api/src/platform_api/common/tenancy.py",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("coverage_json", type=Path)
    parser.add_argument("--overall-min", type=float, default=80.0)
    parser.add_argument("--security-branch-min", type=float, default=90.0)
    args = parser.parse_args()

    report = json.loads(args.coverage_json.read_text(encoding="utf-8"))
    overall = float(report["totals"]["percent_covered"])
    files = report["files"]
    missing = [name for name in SECURITY_MODULES if name not in files]
    if missing:
        print(f"M1 COVERAGE FAIL: missing modules: {', '.join(missing)}")
        return 2

    branch_total = sum(files[name]["summary"]["num_branches"] for name in SECURITY_MODULES)
    branch_covered = sum(files[name]["summary"]["covered_branches"] for name in SECURITY_MODULES)
    security_branches = 100.0 * branch_covered / branch_total
    print(
        "M1 COVERAGE: "
        f"overall={overall:.2f}% "
        f"security_branches={security_branches:.2f}% "
        f"({branch_covered}/{branch_total})"
    )
    if overall < args.overall_min or security_branches < args.security_branch_min:
        print(
            "M1 COVERAGE FAIL: "
            f"requires overall>={args.overall_min:.2f}% and "
            f"security branches>={args.security_branch_min:.2f}%"
        )
        return 1
    print("M1 COVERAGE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
