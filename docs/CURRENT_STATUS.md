# Current Status

> Owner：平台后端
> Updated：2026-08-27
> Git baseline：M1-09 提交，标签 `m1-09-tenant-rls-implemented`
> Database migration：`20260827_07` (head)
> Status：M1-09 IMPLEMENTED_LOCAL / PASSED_LOCAL / BLOCKED_EXTERNAL

## 当前事实

- M1-09 已落地应用 RBAC + PostgreSQL RLS 双层租户隔离。
- API 认证事务切换到无登录、非超级用户、无 BYPASSRLS 的 `platform_runtime`；actor/organization context 均为 transaction-local。
- organizations、成员、邀请、projects、项目成员、audit、outbox 共 7 张表启用 RLS。
- 同连接 A/B/无租户矩阵、跨租户读写、commit/rollback 清理、全迁移升降级均通过。
- PostgreSQL 全量 `56 passed`；本地 CI 与 Demo 通过；Demo migration 为 `20260827_07`。

## 状态边界

当前是本地与 Demo 证据。远程 CI、PR 和外部 Staging 签收缺少外部权限，因此不能标记 ACCEPTED。

## 权威执行顺序

1. 执行 M1-10 Web 组织/项目闭环。
2. 完成 M1 总体验收。
3. M1-08/M1-09 的资产/任务域前置阻断已解除；总体验收后再进入资产/任务域。

文档入口见 [文档治理索引](README.md)，验证证据见 [acceptance](acceptance/README.md)。
