# M1-08 审计、幂等与 Outbox 验收标准

> Owner：平台工程 / QA
> 日期：2026-08-27
> 状态：PROPOSED

## 验收标准

1. 企业创建与项目创建强制 `Idempotency-Key`，长度 16–128；缺失返回 428。
2. 同主体、路由、键和请求摘要重放返回首次状态码及响应快照，不重复创建业务资源。
3. 同键不同请求返回 409 `IDEMPOTENCY_CONFLICT`；并发同键同请求最多创建一份资源。
4. 企业创建、项目创建、项目归档、企业成员移除在业务事务内写入 SUCCESS 审计。
5. 企业创建、项目创建、项目归档、企业成员移除在同一事务写入版本化 Outbox 事件。
6. 业务事务回滚时，业务数据、审计、幂等记录和 Outbox 均不留下半状态。
7. 审计 detail 与 Outbox payload 不包含 Token、密码、Cookie 或 Idempotency-Key 原文。
8. Outbox 保存 event id、聚合、事件类型、版本化 payload、attempts 与 published_at，支持后续至少一次发布。
9. Alembic 升降级、OpenAPI、本地 CI、真实 PostgreSQL 与 Demo 验收通过。
10. 形成独立提交和标签，工作树干净；M1-09 完成前仍不得进入资产/任务域。
