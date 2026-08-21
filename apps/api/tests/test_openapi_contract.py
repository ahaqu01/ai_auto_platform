import json
import subprocess
import sys
from pathlib import Path

from platform_api.main import create_app

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPOSITORY_ROOT / "packages" / "contracts" / "openapi.json"
EXPORT_SCRIPT = REPOSITORY_ROOT / "scripts" / "export_openapi.py"
REQUIRED_PATHS = {
    "/health/live",
    "/api/v1/organizations",
    "/api/v1/organizations/{organization_id}/projects",
}
PROTECTED_PATHS = REQUIRED_PATHS - {"/health/live"}


def test_controlled_openapi_snapshot_matches_runtime() -> None:
    assert CONTRACT_PATH.exists(), "run scripts/export_openapi.py"
    controlled = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    runtime_schema = create_app().openapi()

    assert controlled == runtime_schema


def test_openapi_export_is_byte_stable(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    for output in (first, second):
        subprocess.run(
            [sys.executable, str(EXPORT_SCRIPT), "--output", str(output)],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

    assert first.read_bytes() == second.read_bytes()
    assert CONTRACT_PATH.read_bytes() == first.read_bytes()


def test_required_paths_and_bearer_security_are_declared() -> None:
    schema = create_app().openapi()
    assert REQUIRED_PATHS <= schema["paths"].keys()
    assert schema["components"]["securitySchemes"]["HTTPBearer"] == {
        "type": "http",
        "scheme": "bearer",
    }

    for path in PROTECTED_PATHS:
        for operation in schema["paths"][path].values():
            assert {"HTTPBearer": []} in operation["security"]


def test_identity_is_not_accepted_as_user_id_and_operation_ids_are_unique() -> None:
    schema = create_app().openapi()
    serialized = json.dumps(schema)
    operation_ids: list[str] = []

    assert "user_id" not in serialized
    for path_item in schema["paths"].values():
        for method, operation in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            operation_id = operation.get("operationId")
            assert operation_id
            operation_ids.append(operation_id)

    assert len(operation_ids) == len(set(operation_ids))
