# M1-08 审计、幂等与 Outbox 验收记录

> 日期：2026-08-27
> 环境：本地服务器 / PostgreSQL / Docker Compose Demo
> 裁决：IMPLEMENTED_LOCAL / PASSED_LOCAL / BLOCKED_EXTERNAL

## 验收结论

关键创建命令的强制幂等、关键业务写入的 SUCCESS 审计和版本化 Outbox 已落地。业务、幂等完成快照、审计和 Outbox 具备同事务原子性。

## 自动化证据

- M1-08 专项：`4 passed in 2.48s`。
- PostgreSQL 全量：`54 passed in 15.58s`，包含迁移升降级与历史回归。
- 本地 CI：API `166 passed, 25 deselected`；Web `5 passed`；构建、Go、文档和部署契约通过。
- 并发同键项目创建：两个请求均返回 201 和相同资源 ID，仅一个业务行、审计行和 Outbox 行。
- 同键异请求：409 `IDEMPOTENCY_CONFLICT`。
- 唯一约束失败：业务行、失败键幂等记录、审计和 Outbox 均未留下半状态。
- 审计 detail 与 Outbox payload 的敏感词检查通过。

## Demo 证据

API/迁移镜像重建后容器 healthy，Demo 数据库 `alembic_version` 为 `20260827_06`。

## 状态边界

当前 Outbox 建立数据库可靠投递基线，尚未宣称外部 broker 发布成功。外部远端 CI、PR 和 Staging 签章缺授权，不能升级为 ACCEPTED。M1-09 完成前不得进入资产/任务域。
