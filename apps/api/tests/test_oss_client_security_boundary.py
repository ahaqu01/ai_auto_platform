import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
API_SOURCE = REPOSITORY_ROOT / "apps" / "api" / "src" / "platform_api"
PYPROJECT = REPOSITORY_ROOT / "apps" / "api" / "pyproject.toml"
SCOPE_STATUS = (
    REPOSITORY_ROOT / "docs" / "acceptance" / "M0R-04R-05-oss-runtime-scope-status.md"
)
OSS_CLIENT_PACKAGES = {"boto3", "aioboto3", "minio"}


def test_storage_contract_does_not_bypass_pinned_transport_gate() -> None:
    status = SCOPE_STATUS.read_text(encoding="utf-8")
    assert (
        "OSS_RUNTIME_SSRF_STATUS: RUNTIME_GATEWAY_IMPLEMENTED_OSS_E2E_PENDING" in status
    )

    dependency_text = PYPROJECT.read_text(encoding="utf-8").lower()
    assert all(package not in dependency_text for package in OSS_CLIENT_PACKAGES)

    import_pattern = re.compile(
        r"^\s*(?:from|import)\s+(?:boto3|botocore|aioboto3|minio)(?:\b|\.)",
        re.MULTILINE,
    )
    forbidden_references = []
    for path in API_SOURCE.rglob("*.py"):
        if path.name == "s3_gateway.py":
            source = path.read_text(encoding="utf-8")
            assert "from botocore.auth import S3SigV4Auth, S3SigV4QueryAuth" in source
            assert "create_client" not in source
            continue
        if path.name == "settings.py":
            continue
        source = path.read_text(encoding="utf-8").lower()
        if import_pattern.search(source):
            forbidden_references.append(path.relative_to(REPOSITORY_ROOT).as_posix())

    assert forbidden_references == []

    storage = (API_SOURCE / "modules" / "artifact" / "storage.py").read_text(
        encoding="utf-8"
    )
    assert "class ObjectStoragePort" in storage
    assert "class S3CompatibleGateway" in storage
    assert "StorageGatewayError" in storage
    gateway = (API_SOURCE / "modules" / "artifact" / "s3_gateway.py").read_text(
        encoding="utf-8"
    )
    assert "validated_public_addresses" in gateway
    assert "PinnedHTTPSConnection" in gateway
    assert "storage redirects are not allowed" in gateway
