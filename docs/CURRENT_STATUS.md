# Current Status

> Owner：平台工程
> Updated：2026-08-27
> Git baseline：M1-07 提交（标签 m1-07-project-lifecycle-implemented）
> Database migration：20260827_05 (head)
> Status：M1-07 IMPLEMENTED_LOCAL / PASSED_LOCAL / BLOCKED_EXTERNAL

## 当前结论

- M1-07 已完成项目 CRUD、归档/恢复、项目成员和软删除。
- 项目列表支持默认 20、最大 100 的 opaque cursor 分页，并保持既有数组响应兼容。
- 项目写操作使用 ETag/If-Match 与数据库 version 谓词；同版本并发更新严格只成功一个。
- CI baseline、真实 PostgreSQL 和 Demo 验收通过；数据库迁移为 `20260827_05`。

## 状态边界

本地与 Demo 证据完整；私有远端、PR、远端 CI 和外部 Staging 签章缺授权，因此不标记 ACCEPTED。

## 权威执行顺序

1. 执行 M1-08 审计、幂等与 Outbox。
2. 执行 M1-09 租户纵深防御。
3. 执行 M1-10 Web 企业/项目闭环。
4. M1-08、M1-09 均完成前禁止进入资产/任务域。

文档索引见 [文档治理入口](README.md)，验收证据见 [acceptance](acceptance/README.md)。
