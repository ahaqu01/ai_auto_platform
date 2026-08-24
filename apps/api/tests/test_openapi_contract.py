import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from platform_api.main import create_app
from platform_api.openapi_policy import HTTP_METHODS, forbidden_identity_inputs
from platform_api.settings import get_settings

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPOSITORY_ROOT / "packages" / "contracts" / "openapi.json"
EXPORT_SCRIPT = REPOSITORY_ROOT / "scripts" / "export_openapi.py"
REQUIRED_PATHS = {
    "/health/live",
    "/api/v1/organizations",
    "/api/v1/organizations/{organization_id}/projects",
}
PROTECTED_PATHS = REQUIRED_PATHS - {"/health/live"}


def minimal_subprocess_environment(**application_values: str) -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in {"HOME", "LANG", "LC_ALL", "PATH", "PYTHONPATH", "SYSTEMROOT"}
    }
    environment.update(application_values)
    return environment


def test_controlled_openapi_snapshot_matches_runtime() -> None:
    assert CONTRACT_PATH.exists(), "run scripts/export_openapi.py"
    controlled = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    runtime_schema = create_app().openapi()

    assert controlled == runtime_schema


def test_openapi_export_is_byte_stable_across_sanitized_environments(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    environments = [
        minimal_subprocess_environment(
            APP_ENV="production",
            DATABASE_URL="not-a-database-url",
            KEYCLOAK_ISSUER="http://127.0.0.1/realms/poisoned",
        ),
        minimal_subprocess_environment(
            APP_ENV="staging",
            DATABASE_URL="sqlite:///host-dependent.db",
            OSS_PUBLIC_ENDPOINT="http://169.254.169.254",
        ),
    ]

    for output, environment in zip((first, second), environments, strict=True):
        subprocess.run(
            [sys.executable, str(EXPORT_SCRIPT), "--output", str(output)],
            cwd=REPOSITORY_ROOT,
            env=environment,
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
        for method, operation in schema["paths"][path].items():
            if method.lower() in HTTP_METHODS:
                assert {"HTTPBearer": []} in operation["security"]


def test_caller_identity_is_not_accepted_by_any_operation_input() -> None:
    assert forbidden_identity_inputs(create_app().openapi()) == set()


def test_operation_ids_are_present_and_unique() -> None:
    schema = create_app().openapi()
    operation_ids = [
        operation["operationId"]
        for path_item in schema["paths"].values()
        for method, operation in path_item.items()
        if method.lower() in HTTP_METHODS
    ]
    assert all(operation_ids)
    assert len(operation_ids) == len(set(operation_ids))


def load_export_module():
    spec = importlib.util.spec_from_file_location(
        "controlled_export_openapi", EXPORT_SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_programmatic_export_preserves_environment_and_settings_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_export_module()
    monkeypatch.setenv("APP_FUTURE_SCHEMA_POISON", "caller-value")
    before_environment = os.environ.copy()
    get_settings.cache_clear()
    cached_settings = get_settings()
    before_cache = get_settings.cache_info()

    schema = module.sanitized_schema()

    assert schema["info"]["title"] == "AI Auto Platform API"
    assert os.environ.copy() == before_environment
    assert get_settings.cache_info() == before_cache
    assert get_settings() is cached_settings


def test_programmatic_export_restores_state_when_child_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_export_module()
    monkeypatch.setenv("APP_FUTURE_SCHEMA_POISON", "caller-value")
    before_environment = os.environ.copy()
    get_settings.cache_clear()
    cached_settings = get_settings()
    before_cache = get_settings.cache_info()

    def fail(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, "schema-worker")

    monkeypatch.setattr(module.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        module.sanitized_schema()

    assert os.environ.copy() == before_environment
    assert get_settings.cache_info() == before_cache
    assert get_settings() is cached_settings
