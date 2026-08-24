from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
API_SOURCE = REPOSITORY_ROOT / "apps" / "api" / "src" / "platform_api"
PYPROJECT = REPOSITORY_ROOT / "apps" / "api" / "pyproject.toml"
SCOPE_STATUS = (
    REPOSITORY_ROOT
    / "docs"
    / "acceptance"
    / "M0R-04R-05-oss-runtime-scope-status.md"
)
OSS_CLIENT_PACKAGES = {"boto3", "botocore", "aioboto3", "minio"}


def test_oss_client_remains_blocked_until_pinned_transport_is_implemented() -> None:
    status = SCOPE_STATUS.read_text(encoding="utf-8")
    assert "OSS_RUNTIME_SSRF_STATUS: NOT_IMPLEMENTED_BLOCKING_CLIENT" in status

    dependency_text = PYPROJECT.read_text(encoding="utf-8").lower()
    assert all(package not in dependency_text for package in OSS_CLIENT_PACKAGES)

    runtime_references = []
    for path in API_SOURCE.rglob("*.py"):
        if path.name == "settings.py":
            continue
        source = path.read_text(encoding="utf-8").lower()
        if "oss_public_endpoint" in source or any(
            package in source for package in OSS_CLIENT_PACKAGES
        ):
            runtime_references.append(path.relative_to(REPOSITORY_ROOT).as_posix())

    assert runtime_references == []
