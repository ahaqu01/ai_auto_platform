"""Verify service identity boundaries in a named disposable PostgreSQL database."""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

import psycopg
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from httpx import ASGITransport, AsyncClient
from platform_api.api.upload_sessions import get_object_storage
from platform_api.auth.dependencies import get_token_verifier
from platform_api.auth.identity import IdentityClaims
from platform_api.db.session import get_session
from platform_api.main import create_app
from platform_api.modules.artifact.maintenance import ArtifactMaintenanceService
from platform_api.modules.artifact.storage import (
    ObjectMetadata,
    ObjectStorageError,
    PresignedRequest,
    StorageErrorCode,
)
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parents[1]


def connect(url: str):
    return psycopg.connect(
        make_url(url).set(drivername="postgresql").render_as_string(hide_password=False),
        autocommit=True,
    )


def must_deny(url: str, statement: str) -> None:
    with connect(url) as db:
        try:
            db.execute(statement)
        except psycopg.errors.InsufficientPrivilege:
            return
    raise AssertionError("operation unexpectedly allowed")


class Verifier:
    async def verify(self, token: str) -> IdentityClaims:
        return IdentityClaims("https://auth.example.test", token, f"{token}@example.test", token)


class Storage:
    missing = False

    async def start_multipart(self, *_args):
        return "test-upload-id"

    async def sign_upload_part(self, *_args):
        return PresignedRequest("https://storage.example.test/part", 900)

    async def complete_multipart(self, *_args):
        return None

    async def head(self, *_args):
        if self.missing:
            raise ObjectStorageError(StorageErrorCode.NOT_FOUND, "test missing", retryable=False)
        return ObjectMetadata(3, "etag", "application/octet-stream")

    async def read_chunks(self, *_args):
        yield b"abc"

    async def list_objects(self, *_args):
        if False:
            yield


async def verify_runtime(owner: str, api: str, maintenance: str) -> None:
    api_engine = create_async_engine(api)
    maintenance_engine = create_async_engine(maintenance)
    api_sessions = async_sessionmaker(api_engine, expire_on_commit=False)
    maintenance_sessions = async_sessionmaker(maintenance_engine, expire_on_commit=False)

    async def session_override():
        async with api_sessions() as db:
            try:
                yield db
                await db.commit()
            except BaseException:
                await db.rollback()
                raise

    storage = Storage()
    app = create_app()
    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_token_verifier] = lambda: Verifier()
    app.dependency_overrides[get_object_storage] = lambda: storage
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver", headers={"Authorization": "Bearer owner"}) as client:
            response = await client.post("/api/v1/organizations", json={"name": "Identity split test"}, headers={"Idempotency-Key": str(uuid4())})
            assert response.status_code == 201, response.text
            org = response.json()["id"]
            response = await client.post(f"/api/v1/organizations/{org}/projects", json={"code": "split", "name": "Split"}, headers={"Idempotency-Key": str(uuid4())})
            assert response.status_code == 201, response.text
            project = response.json()["id"]
            base = f"/api/v1/organizations/{org}/projects/{project}"
            payload = {"display_name": "test.bin", "size_bytes": 3, "sha256": hashlib.sha256(b"abc").hexdigest(), "content_type": "application/octet-stream"}
            response = await client.post(f"{base}/upload-sessions", json=payload, headers={"Idempotency-Key": str(uuid4())})
            assert response.status_code == 201, response.text
            upload = response.json()["id"]
            response = await client.post(f"{base}/upload-sessions/{upload}/parts:sign", json={"part_numbers": [1]})
            assert response.status_code == 200, response.text
            response = await client.put(f"{base}/upload-sessions/{upload}/parts/1", json={"etag": "etag", "size_bytes": 3})
            assert response.status_code == 200, response.text
            response = await client.post(f"{base}/upload-sessions/{upload}:complete", json={"parts": [{"part_number": 1, "etag": "etag"}]}, headers={"Idempotency-Key": str(uuid4())})
            assert response.status_code == 201, response.text
            asset = response.json()["id"]
            response = await client.get(f"{base}/artifacts/{asset}", headers={"Authorization": "Bearer outsider"})
            assert response.status_code == 404, response.text
            response = await client.post(f"{base}/upload-sessions", json=payload, headers={"Idempotency-Key": str(uuid4())})
            assert response.status_code == 201, response.text
            expired = response.json()["id"]
            with connect(owner) as db:
                db.execute("UPDATE upload_sessions SET expires_at = now() - interval '1 second' WHERE id = %s", (expired,))
            response = await client.get(f"{base}/upload-sessions/{expired}")
            assert response.status_code == 200 and response.json()["status"] == "EXPIRED", response.text
            response = await client.post(f"{base}/upload-sessions", json=payload, headers={"Idempotency-Key": str(uuid4())})
            assert response.status_code == 201, response.text
            pending = response.json()["id"]
            with connect(owner) as db:
                db.execute("UPDATE upload_sessions SET expires_at = now() - interval '1 second' WHERE id = %s", (pending,))
            storage.missing = True
            metrics = await ArtifactMaintenanceService(maintenance_sessions, storage).run_once()
            assert metrics.expired_sessions == 1 and metrics.missing_objects == 1
            with connect(owner) as db:
                assert db.execute("SELECT status FROM artifacts WHERE id = %s", (asset,)).fetchone()[0] == "FAILED"
                assert db.execute("SELECT count(*) FROM audit_events WHERE actor_type = 'SYSTEM'").fetchone()[0] == 2
                assert db.execute("SELECT count(*) FROM outbox_events WHERE aggregate_type = 'artifact'").fetchone()[0] >= 3
        with connect(api) as db:
            assert db.execute("SELECT count(*) FROM artifacts").fetchone()[0] == 0
    finally:
        await api_engine.dispose()
        await maintenance_engine.dispose()


def main() -> None:
    owner = os.environ["IDENTITY_TEST_DATABASE_URL"]
    if make_url(owner).database != "platform_identity_split_test":
        raise ValueError("only the named disposable identity test database is allowed")
    config = Config(str(ROOT / "apps/api/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "apps/api/migrations"))
    config.set_main_option("sqlalchemy.url", owner.replace("%", "%%"))
    command.upgrade(config, "head")
    with connect(owner) as db:
        db.execute((ROOT / "deploy/postgres/02-service-roles.sql").read_text())
    temp = Path(tempfile.mkdtemp(prefix="aiap-role-split-"))
    try:
        source = temp / "source.env"
        source.write_text(f"APP_ENV=local\nDATABASE_URL={owner}\nPOSTGRES_PASSWORD=administrator-test-only\nKC_BOOTSTRAP_ADMIN_PASSWORD=identity-test-only\nBFF_CLIENT_SECRET=bff-test-only\n", encoding="utf-8")
        os.chmod(source, 0o600)
        output = temp / "split"
        subprocess.run([sys.executable, str(ROOT / "scripts/split_staging_service_env.py"), "--source-env", str(source), "--output-dir", str(output)], check=True)
        api = dotenv_values(output / "api.env")["DATABASE_URL"]
        maintenance = dotenv_values(output / "maintenance.env")["DATABASE_URL"]
        assert api and maintenance
        for path in output.glob("*.env"):
            assert path.stat().st_mode & 0o777 == 0o600
        for name in ("api", "maintenance"):
            values = dotenv_values(output / f"{name}.env")
            assert not any(key.startswith(("POSTGRES_", "MINIO_ROOT_", "KC_", "MIGRATION_")) for key in values)
            assert make_url(values["DATABASE_URL"]).username == f"platform_{name}"
        assert "BFF_CLIENT_SECRET" not in dotenv_values(output / "maintenance.env")
        for url in (api, maintenance):
            with connect(url) as db:
                row = db.execute("SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = current_user").fetchone()
                assert row is not None and not any(row)
            must_deny(url, "SET ROLE platform")
        must_deny(api, "SET ROLE platform_maintenance")
        must_deny(api, "SELECT * FROM artifact_maintenance_state")
        must_deny(maintenance, "SELECT * FROM users")
        must_deny(maintenance, "UPDATE organizations SET name = 'forbidden'")
        asyncio.run(verify_runtime(owner, api, maintenance))
        print("PASS: restricted logins, role denial, tenant RLS, API lifecycle, expiry refresh, maintenance SYSTEM events, env isolation")
    finally:
        shutil.rmtree(temp)


if __name__ == "__main__":
    main()
