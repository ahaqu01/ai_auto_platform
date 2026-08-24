# M0R-05R-03 API-on-PostgreSQL 验收记录

- 验收日期：2026-08-24
- 基线提交：`c0e7c2b93f6b166672d02e2b90161c2f2f99cc9b`
- 基线标签：`m0r-05r-02-implemented`
- 状态：通过（`IMPLEMENTED_LOCAL`）

## 测试先行证据

实现前运行新增 API-on-PostgreSQL 测试：

```text
fixture 'postgresql_api' not found
3 errors in 0.04s
```

该红灯准确表明仓库已有 SQLite API 测试和直接 PostgreSQL 集成测试，但尚无 FastAPI dependency override 到受保护 PostgreSQL 随机 schema 的 fixture。

## 实现结果

- 在 PostgreSQL 测试 fixture 中增加 `postgresql_api`，复用已经通过身份保险丝、随机 schema 和 `upgrade heads` 的 `postgresql_database`。
- FastAPI `get_session` override 每个请求创建当前 PostgreSQL schema 的 `AsyncSession`；未使用 SQLite 或 `metadata.create_all()`。
- token verifier 使用确定性 owner/outsider 身份，HTTP 请求仍完整经过 Bearer dependency、身份同步、租户成员校验、路由和 ORM 持久化。
- fixture 退出时清空 dependency overrides；数据库 fixture 随后在复核连接身份后删除本次随机 schema。
- 未修改生产路由、业务模型或迁移。

## HTTP 行为证据

- owner 首次认证后成功创建企业，并能在企业列表中读取。
- owner 成功创建项目，并从项目列表读取相同项目 ID。
- outsider 使用已知 organization UUID 读取项目时得到 404 `ORGANIZATION_NOT_FOUND`。
- 重复项目 code 得到 409 `PROJECT_CODE_EXISTS`；随后项目列表仍可正常读取且只有第一次成功记录。

## PostgreSQL 持久化证据

- 实际连接 dialect 为 `postgresql`，`current_schema()` 等于当前随机 `test_` schema。
- 同一 owner 多次 HTTP 请求后 `users` 仅一条，证明 issuer/subject 身份同步未重复创建。
- `organization_members` 仅一条，证明企业创建链路持久化 owner 成员关系。
- 项目记录的 code 与 HTTP 创建值一致。
- 重复 code 事务回滚后 `projects` 计数仍为一。

## 验收结果

```text
API-on-PostgreSQL 专项：3 passed in 1.06s
PostgreSQL 全套：27 passed in 2.92s
API 全量：129 passed, 1 warning in 9.00s
API 覆盖率：83%
Ruff（apps/api/src + apps/api/tests）：通过
git diff --check：通过
Alembic heads：20260821_02 (head)
Docker Compose config：通过
npm audit --audit-level=high：0 vulnerabilities
Web 测试：1 passed
Web 生产构建：通过
Go vet：通过
Go race test：通过
```

API 测试仍有一条既有 Starlette/httpx 弃用警告，与本任务无关。

## 边界复核

- 这些用例证明测试服务器上的专用 PostgreSQL 数据库链路，不代表共享 Staging 或生产数据库验证。
- 测试 token verifier 只替代外部 Keycloak 验签；Bearer 解析、用户同步、成员授权、API handler 和 PostgreSQL 事务均运行真实平台代码。
- 本任务没有覆盖真实 Keycloak 网络调用或 OSS/Temporal 链路。

## 验收结论

M0R-05R-03 的本地验收标准满足，可以独立版本封存。该结论不等于 `REVIEWED`、`VERIFIED_STAGING` 或 `ACCEPTED`。下一整改包按计划为 M0R-03R-01。
