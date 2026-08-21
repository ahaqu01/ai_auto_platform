# PostgreSQL integration tests

These tests require an explicit PostgreSQL URL and never fall back to the application database configuration.

From the repository root:

```bash
TEST_DATABASE_URL='postgresql+psycopg://test-user:test-password@127.0.0.1:5432/platform' \
  .venv/bin/pytest apps/api/tests/postgresql -q
```

The fixture creates a random `test_<uuid>` schema, runs Alembic to `head`, and drops only that schema with `CASCADE` during teardown. It never drops a database or the `public` schema. Use a dedicated test role in CI and Staging; the local Compose superuser is acceptable only on a developer host.
