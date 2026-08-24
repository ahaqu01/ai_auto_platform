"""Export the FastAPI runtime schema as the controlled OpenAPI contract."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from platform_api.openapi_policy import assert_no_forbidden_identity_inputs

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPOSITORY_ROOT / "packages" / "contracts" / "openapi.json"
SYSTEM_ENVIRONMENT_ALLOWLIST = {
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "PYTHONHOME",
    "PYTHONPATH",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "USERPROFILE",
}
SCHEMA_ENVIRONMENT = {
    "APP_ENV": "local",
    "APP_NAME": "ai-auto-platform",
    "APP_VERSION": "0.1.0",
    "DATABASE_URL": ("postgresql+psycopg://platform:platform@127.0.0.1:5432/platform"),
    "REDIS_URL": "redis://127.0.0.1:6379/0",
    "TEMPORAL_ADDRESS": "",
    "TEMPORAL_NAMESPACE": "default",
    "KEYCLOAK_ISSUER": "",
    "OIDC_AUDIENCE": "",
    "OSS_PUBLIC_ENDPOINT": "",
    "OSS_INTERNAL_ENDPOINT": "",
    "OSS_BUCKET": "",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "",
    "ALLOW_INSECURE_PRIVATE_SERVICE_TRANSPORT": "false",
}


def _schema_subprocess_environment() -> dict[str, str]:
    environment = {
        name: value
        for name, value in os.environ.items()
        if name.upper() in SYSTEM_ENVIRONMENT_ALLOWLIST
    }
    environment.update(SCHEMA_ENVIRONMENT)
    return environment


def _schema_in_current_process() -> dict[str, Any]:
    from platform_api.main import create_app

    schema = create_app().openapi()
    assert_no_forbidden_identity_inputs(schema)
    return schema


def sanitized_schema() -> dict[str, Any]:
    """Generate the schema in an allowlisted child process without caller side effects."""
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--schema-worker"],
        cwd=REPOSITORY_ROOT,
        env=_schema_subprocess_environment(),
        check=True,
        capture_output=True,
        text=True,
    )
    schema = json.loads(completed.stdout)
    assert_no_forbidden_identity_inputs(schema)
    return schema


def render_openapi() -> str:
    """Return a stable, human-readable representation of the runtime schema."""
    return (
        json.dumps(
            sanitized_schema(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def export_openapi(output: Path = DEFAULT_OUTPUT) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_openapi(), encoding="utf-8")


def check_openapi(output: Path = DEFAULT_OUTPUT) -> bool:
    return output.exists() and output.read_text(encoding="utf-8") == render_openapi()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if snapshot is stale")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--schema-worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.schema_worker:
        json.dump(
            _schema_in_current_process(),
            sys.stdout,
            ensure_ascii=False,
            sort_keys=True,
        )
        return 0

    output = args.output.resolve()
    if args.check:
        if check_openapi(output):
            print(f"OpenAPI snapshot is current: {output}")
            return 0
        print(f"OpenAPI snapshot is missing or stale: {output}")
        return 1

    export_openapi(output)
    print(f"Exported OpenAPI snapshot: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
