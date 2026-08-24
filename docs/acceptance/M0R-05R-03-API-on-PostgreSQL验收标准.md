# M0R-05R-03 API-on-PostgreSQL 验收标准

- 制定日期：2026-08-24
- 基线提交：`c0e7c2b93f6b166672d02e2b90161c2f2f99cc9b`
- 基线标签：`m0r-05r-02-implemented`
- 目标状态：`IMPLEMENTED_LOCAL`

## 范围

本任务为真实 PostgreSQL 上的 FastAPI 认证租户链路建立证据。继续复用 M0R-05R-01 的测试数据库保险丝、随机 schema 和 M0R-05R-02 的 `upgrade heads` fixture；不新增业务功能，不使用 SQLite 结果替代 PostgreSQL 验收。

## 验收条件

1. FastAPI 的 `get_session` 必须通过 dependency override 指向当前随机 `test_` schema 的 PostgreSQL `AsyncSession`。
2. 测试必须从实际连接断言 dialect 为 `postgresql`、`current_schema()` 等于 fixture schema，避免名为 PostgreSQL、实际走 SQLite 的假证据。
3. Bearer 身份首次请求同步为一条 PostgreSQL `users` 记录；同一 issuer/subject 的后续请求不得重复创建用户。
4. 认证用户可通过 HTTP 创建企业，并自动成为该企业 owner；HTTP 列表只能返回其成员企业。
5. owner 可通过 HTTP 创建并读取项目，响应与 PostgreSQL 持久化记录一致。
6. outsider 即使知道 organization UUID，也不能读取该企业项目；返回统一的 404 `ORGANIZATION_NOT_FOUND`，不得泄露企业存在性。
7. 重复项目 code 的 HTTP 请求返回 409 `PROJECT_CODE_EXISTS`；失败事务必须 rollback，后续请求仍可用，数据库中只保留第一次成功记录。
8. 测试必须区分 HTTP 行为断言和直接 PostgreSQL 持久化断言，并在验收记录中明确其覆盖范围。
9. fixture 清理仍只能删除本次生成的随机 schema，并在连接前及清理前验证数据库名、角色和非 superuser 身份。
10. PostgreSQL 专项、API 全量、Ruff、OpenAPI、Web、Agent、Compose 回归通过；独立提交并创建 `m0r-05r-03-implemented` 标签，提交后工作区干净。

## 状态边界

本任务只可达到 `IMPLEMENTED_LOCAL`。Staging、受保护 CI、Bugbot/Security Review 和签字不在本任务中宣称完成。
