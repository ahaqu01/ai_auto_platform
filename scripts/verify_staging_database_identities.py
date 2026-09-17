"""Read-only verification of the running Staging identity boundary; never print secrets."""

import subprocess

CHECK = """
import os,psycopg
from sqlalchemy.engine import make_url
expected = os.environ['VERIFY_ROLE']
assert not any(k.startswith(('POSTGRES_','MINIO_ROOT_','KC_','KEYCLOAK_ADMIN')) for k in os.environ)
if expected == 'platform_maintenance':
    assert 'BFF_CLIENT_SECRET' not in os.environ
url=make_url(os.environ['DATABASE_URL'])
assert url.username == expected
with psycopg.connect(url.set(drivername='postgresql').render_as_string(hide_password=False),autocommit=True) as db:
    row=db.execute('SELECT current_user,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user').fetchone()
    assert row[0] == expected and not any(row[1:])
    forbidden=['SET ROLE platform']
    if expected=='platform_api':
        forbidden += ['SET ROLE platform_maintenance','SELECT * FROM artifact_maintenance_state']
        assert db.execute('SELECT count(*) FROM artifacts').fetchone()[0] == 0
    else:
        forbidden += ['SET ROLE platform_api','SELECT * FROM users','UPDATE organizations SET name=name WHERE false']
    for statement in forbidden:
        try:
            db.execute(statement)
        except psycopg.errors.InsufficientPrivilege:
            pass
        else:
            raise AssertionError('identity boundary failed')
print('PASS:',expected,'restricted attributes, denied escalation, environment isolation')
"""


def main() -> None:
    for service, role in (("api", "platform_api"), ("artifact-maintenance", "platform_maintenance")):
        subprocess.run(
            ["docker", "exec", "-e", f"VERIFY_ROLE={role}", f"ai-auto-platform-staging-{service}-1", "python", "-c", CHECK],
            check=True,
        )


if __name__ == "__main__":
    main()
