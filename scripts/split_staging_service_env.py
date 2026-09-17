"""Provision restricted service logins and isolate their external env files."""

from __future__ import annotations

import argparse
import json
import os
import secrets
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from platform_api.settings import Settings
from psycopg import sql
from sqlalchemy.engine import make_url


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-env", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source = {key: value for key, value in dotenv_values(args.source_env).items() if value is not None}
    if args.output_dir.exists():
        raise ValueError("output directory already exists; refuse implicit credential rotation")
    owner_url = make_url(source["DATABASE_URL"])
    if owner_url.get_backend_name() != "postgresql":
        raise ValueError("PostgreSQL is required")
    urls = {}
    with psycopg.connect(owner_url.set(drivername="postgresql").render_as_string(hide_password=False)) as db:
        for role in ("platform_api", "platform_maintenance"):
            row = db.execute("SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
            if row is not None and any(row):
                raise ValueError("existing service role has unsafe attributes")
            if row is None:
                db.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE").format(sql.Identifier(role)))
            password = secrets.token_urlsafe(48)
            db.execute(sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(role), sql.Literal(password)))
            urls[role] = owner_url.set(username=role, password=password).render_as_string(hide_password=False)
    args.output_dir.mkdir(mode=0o700, parents=True)
    os.chmod(args.output_dir, 0o700)

    def write(name: str, values: dict[str, str]) -> None:
        path = args.output_dir / f"{name}.env"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write("".join(f"{key}={json.dumps(value, ensure_ascii=False)}\n" for key, value in values.items()))

    runtime_keys = {key.upper() for key in Settings.model_fields}
    api = {key: value for key, value in source.items() if key in runtime_keys}
    api["DATABASE_URL"] = urls["platform_api"]
    maintenance = {key: value for key, value in api.items() if key.startswith(("OSS_", "ARTIFACT_")) or key in {"APP_ENV", "APP_NAME", "APP_VERSION", "ALLOW_INSECURE_PRIVATE_SERVICE_TRANSPORT"}}
    maintenance["DATABASE_URL"] = urls["platform_maintenance"]
    write("api", api)
    write("maintenance", maintenance)
    write("migration", {"APP_ENV": "local", "DATABASE_URL": source["DATABASE_URL"]})
    write("postgres", {key: value for key, value in source.items() if key.startswith("POSTGRES_")})
    write("minio", {key: value for key, value in source.items() if key.startswith("MINIO_ROOT_")})
    write("keycloak", {key: value for key, value in source.items() if key.startswith(("KC_", "KEYCLOAK_ADMIN")) or key == "BFF_CLIENT_SECRET"})
    write("compose", {
        "STAGING_HTTP_PORT": source.get("STAGING_HTTP_PORT", "8081"),
        **{f"STAGING_{key}_ENV_FILE": str(args.output_dir / f"{name}.env") for key, name in (("API", "api"), ("MAINTENANCE", "maintenance"), ("MIGRATION", "migration"), ("DATABASE", "postgres"), ("STORAGE", "minio"), ("IDENTITY", "keycloak"))},
    })
    print("Restricted service credentials provisioned; split files created with mode 0600")


if __name__ == "__main__":
    main()
