# PostgreSQL integration tests

These tests must use the dedicated local/CI database and non-superuser role. They never fall back to application settings.

For a fresh local Compose volume, `deploy/compose/initdb/01-test-database.sql` creates `platform_test`. Existing volumes must be provisioned once by an administrator using the same role/database definition.

Run non-downgrade tests from the repository root:

```bash
TEST_DATABASE_CONFIRM=M0R05R01_TEST_DATABASE_ONLY \
TEST_DATABASE_URL='postgresql+psycopg://platform_test:platform-test-local-only@127.0.0.1:5432/platform_test' \
  .venv/bin/pytest apps/api/tests/postgresql -q -k 'not migrations_can_downgrade'
```

The migration round-trip additionally requires:

```bash
TEST_DATABASE_ALLOW_DOWNGRADE=M0R05R01_DISPOSABLE_DATABASE_DOWNGRADE
```

The fixture validates the URL before connecting, then verifies `current_database()`, `current_user`, and that the role is not a superuser before any DDL. It creates only a random `test_<uuid>` schema and rechecks identity before cleanup.
