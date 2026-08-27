# M1-04 DTO、错误与契约基线验收记录

> Owner：QA / 平台工程
> 日期：2026-08-27
> 状态：PASSED_LOCAL

## 结论

M1-04 的严格 DTO、Problem Details、401 Bearer challenge 与 OpenAPI 固定响应均已实现。本地 CI、真实 PostgreSQL 与 Demo 验收通过，判定为 IMPLEMENTED_LOCAL / PASSED_LOCAL。外部 PR、远端 CI 和 Staging 签章仍为 BLOCKED_EXTERNAL。

## 证据

1. 红灯：M1-04 专项 4 failed、3 passed。
2. 绿灯：M1-04 专项 8 passed。
3. OpenAPI 与专项组合：17 passed。
4. CI baseline：API 166 passed、14 deselected；Web 5 passed；构建、npm audit、Go 和文档治理通过。
5. PostgreSQL：43 passed，包含迁移往返。
6. Demo：
   - 新 API 镜像运行 healthy；
   - /health/live 与 /health/ready 返回 200；
   - 401 响应包含 www-authenticate: Bearer；
   - 响应体包含固定 7 个 Problem Details 字段；
   - 运行时 OpenAPI 包含 ProblemDetails、additionalProperties=false 和 WWW-Authenticate。

## 验收项对照

- 请求 DTO extra=forbid：通过。
- 未知字段 HTTP 422 / extra_forbidden：通过。
- 401/403/404/409 响应结构统一：通过。
- 401 Bearer challenge：通过。
- 非 401 不附带认证头：通过。
- 受保护路由 OpenAPI 四类响应固定：通过。
- 受控 OpenAPI 快照稳定：通过。
- 全量门禁和 Demo：通过。
- 开发文档、独立提交、标签与干净工作区：通过。

## 外部阻塞

未取得远端仓库、受保护 PR、远端 CI 和外部 Staging 签章授权，因此不得标记 ACCEPTED。
