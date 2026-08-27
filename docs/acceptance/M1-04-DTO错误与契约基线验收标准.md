# M1-04 DTO、错误与契约基线验收标准

> Owner：平台工程
> 日期：2026-08-27
> 状态：ACCEPTANCE_DEFINED

## 目标

固定 API 输入、错误响应和 OpenAPI 契约，为 M1-05 之后的成员、RBAC 和项目生命周期提供稳定边界。本阶段不扩展业务功能。

## 验收项

1. API 请求 DTO 使用 extra=forbid；组织和项目创建携带未知字段时返回 422，错误类型为 extra_forbidden。
2. 错误响应统一为 Problem Details：type、title、status、code、detail、instance、traceId。
3. DomainError 的 401/403/404/409 均保持统一响应结构。
4. 所有 401 响应附带 WWW-Authenticate: Bearer；非 401 不错误附带该头。
5. 组织和项目受保护操作在 OpenAPI 中固定声明 401/403/404/409，均引用 ProblemDetails；401 声明 WWW-Authenticate 响应头。
6. DTO 与 ProblemDetails 的 OpenAPI schema 固定 additionalProperties=false。
7. 受控 OpenAPI 快照更新且字节稳定，调用者身份字段仍不得作为输入。
8. API、PostgreSQL、Web、Go、文档治理和 Demo 回归通过。
9. 输出开发文档、验收记录、独立 Git 提交和 implemented 标签，提交后工作区干净。

## 判定

第 1—7 项任一失败即不通过。远端 CI、PR 或外部 Staging 缺少授权时记录 BLOCKED_EXTERNAL，不伪造 ACCEPTED。
