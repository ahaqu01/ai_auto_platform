# M0R-05 PostgreSQL 集成测试夹具验收标准

> Status: READY
> Work package: M0R-05
> Baseline: `879b260`
> Scope: isolated PostgreSQL integration fixture, constraints, transactions, concurrency and migrations

## 1. 目标

建立不会污染开发数据、可重复运行的 PostgreSQL 集成测试夹具，以真实 PostgreSQL 和 Alembic 迁移证明数据库约束、事务、并发及升级/降级行为。SQLite 继续用于快速反馈，但不得作为 PostgreSQL 行为验收证据。

## 2. 验收标准

| ID | 验收标准 | 证据 |
|---|---|---|
| PG-01 | 集成测试只接受显式 `TEST_DATABASE_URL`，禁止误用 Production URL | 夹具保护测试/代码审查 |
| PG-02 | 每个测试使用随机独立 schema，开始前创建、结束后 `CASCADE` 清理 | schema 生命周期测试 |
| PG-03 | schema 通过 Alembic `upgrade head` 建立，不使用 `metadata.create_all()` 替代迁移 | alembic_version 断言 |
| PG-04 | 测试连接的 dialect 为 PostgreSQL，且 search_path 指向隔离 schema | 数据库断言 |
| PG-05 | 同企业项目 code 并发写入只成功一次，另一事务得到唯一约束错误 | 并发集成测试 |
| PG-06 | 事务回滚后不留下组织记录 | 事务集成测试 |
| PG-07 | 删除企业由 PostgreSQL 外键级联删除成员和项目 | 外键集成测试 |
| PG-08 | 当前 head 可降到 base 并重新升级到 head | 迁移往返测试 |
| PG-09 | 测试失败也执行 schema 清理，不删除数据库或 public schema | fixture teardown 设计与残留检查 |
| PG-10 | PostgreSQL 专项及 API/Web/Agent/OpenAPI 全量回归通过 | 验收记录 |

## 3. 安全约束

- `TEST_DATABASE_URL` 必须指向 PostgreSQL，且不得包含 `production` 数据库名或 `APP_ENV=production`。
- 夹具只允许创建/删除名称以 `test_` 开头的随机 schema。
- 禁止执行 `DROP DATABASE`、`DROP SCHEMA public` 或对非测试 schema 做清理。
- 测试日志和验收文档不得记录真实数据库密码。

## 4. 测试优先要求

先提交 PostgreSQL 专项测试并运行。预期因 `postgresql_database` 夹具尚不存在而失败；该失败直接对应本工作包缺失能力。实现夹具后必须使用开发服务器的显式测试 URL 运行并转绿。

## 5. 完成定义

PG-01 至 PG-10 通过后状态为 `IMPLEMENTED_LOCAL`。没有独立评审、CI PostgreSQL Service 和 Staging 证据时，不得标记为 `ACCEPTED`。
