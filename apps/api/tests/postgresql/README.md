# PostgreSQL integration tests

普通 PostgreSQL 集成测试使用专用 `platform_test` 数据库和非超级用户，仅在随机 `test_<uuid>` schema 中操作。

```bash
TEST_DATABASE_CONFIRM=M0R05R01_TEST_DATABASE_ONLY \
TEST_DATABASE_URL='postgresql+psycopg://platform_test:<local-only>@127.0.0.1:5432/platform_test' \
  .venv/bin/pytest apps/api/tests/postgresql -q -k 'not base_catalog'
```

migration downgrade round-trip 不会在共享 `platform_test` 上执行。它额外要求管理员连接，用于为本次测试创建随机一次性数据库、写入数据库级 disposal marker，并在结束时核对 owner/marker 后销毁精确目标：

```bash
TEST_DATABASE_ADMIN_URL='postgresql+psycopg://<admin>:<local-only>@127.0.0.1:5432/platform' \
TEST_DATABASE_ALLOW_DOWNGRADE=M0R05R01_DISPOSABLE_DATABASE_DOWNGRADE \
TEST_DATABASE_ALLOW_DESTROY=M0R05R04_DESTROY_EPHEMERAL_DATABASE
```

安全门禁包括：目标/角色后缀、非生产环境、非超级用户、随机数据库名、管理员写入的 marker、数据库 owner、无其他连接、迁移 global/schema-qualified DDL 扫描，以及销毁前独立确认。不得为了运行测试删除或弱化这些门禁。
