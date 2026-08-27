# M1-05 企业成员邀请与 RBAC 验收记录

> Owner：QA / 平台工程
> 日期：2026-08-27
> 状态：PASSED_LOCAL

## 结论

邀请生命周期、Owner/Admin/Member 权限矩阵、成员即时失权和项目创建授权已通过真实 PostgreSQL 与本地 CI 验收，判定 IMPLEMENTED_LOCAL / PASSED_LOCAL。

## 证据

- 红灯：OrganizationInviteModel 不存在，测试收集失败。
- 专项：2 passed，覆盖完整矩阵、token 摘要、重放、邮箱不匹配、撤销、重发和过期。
- PostgreSQL 全量：45 passed，包含 upgrade/downgrade/upgrade。
- CI baseline：API 166 passed、Web 5 passed、构建、审计、Go、文档与 OpenAPI 均通过。
- Demo：迁移 head 20260827_04，API healthy，live/ready 200，新端点出现在运行时 OpenAPI。

## 验收裁决

验收标准第 1—11 项全部通过。Owner 目标操作返回 403，符合 M1-05/M1-06 边界。远端 PR、远端 CI 和外部 Staging 签章缺少授权，维持 BLOCKED_EXTERNAL。
