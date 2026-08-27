# M1-06 最后 Owner 并发保护验收记录

> 日期：2026-08-27
> 环境：本地服务器 / PostgreSQL / Docker Compose Demo
> 裁决：IMPLEMENTED_LOCAL / PASSED_LOCAL / BLOCKED_EXTERNAL

## 验收结论

M1-06 的权限、最后 Owner 不变量和真实 PostgreSQL 并发保护已实现并通过本地验收。外部远端 CI、Staging 签章未获授权，不能标记 ACCEPTED。

## 证据

- `bash scripts/ci.sh`：API 166 passed、18 deselected；Web 5 passed；构建、Go、文档及部署契约全部通过。
- 完整 PostgreSQL：`47 passed in 7.73s`。
- M1-06 专项：两个独立数据库会话并发执行“两次降级”及“降级+移除”，两组均为一个提交、一个 `LAST_OWNER_REQUIRED`，最终 Owner 数为 1。
- OpenAPI 快照导出并通过一致性检查。
- Demo API 重建后 liveness/readiness 与容器健康状态通过。
- Alembic head 保持 `20260827_04`，无新增迁移。

## 风险边界

企业行锁要求所有 Owner 变更入口统一调用并发安全服务；本次生产 PATCH/DELETE 已完成接线。未来新增批处理或后台入口时必须复用同一服务，不得直接更新 membership。
