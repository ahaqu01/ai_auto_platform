# Acceptance Status Index

> Owner：QA 负责人
> Updated：2026-09-02
> Status：EVIDENCE INDEX
> Authoritative current status：[../CURRENT_STATUS.md](../CURRENT_STATUS.md)

## 当前里程碑裁决

| Slice | 当前状态 | 说明 |
|---|---|---|
| M0R-03/04/05 及整改包 | `IMPLEMENTED_LOCAL / REVIEWED` | REV-01R P1=0、P2=0；缺少 CI/Staging，不能标记 ACCEPTED |
| REV-01R | `PASSED` | 双专项评审已完成；两个 P3 不阻塞 |
| M0R-06 | IMPLEMENTED_LOCAL | 文档治理验收通过 |
| M0R-07 | IMPLEMENTED_LOCAL | 运行可靠性验收通过 |
| CI/Staging baseline | VERIFIED_STAGING / BLOCKED_EXTERNAL | 服务器验证通过；远端协作门禁待仓库 |
| M1-01 Keycloak IaC | IMPLEMENTED_LOCAL | Realm/Client/Role 与空卷重建验收通过 |
| M1-PRE-01 前置健壮性整改 | IMPLEMENTED_LOCAL | 两个 P3 与 CI/doc checker 健壮性验收通过 |
| M1-02 BFF 会话 | IMPLEMENTED_LOCAL | PKCE、Redis 会话、Cookie/CSRF、退出与管理台验收通过 |

历史验收结果中的“通过”只表示所列测试在当时通过，不自动升级当前里程碑状态。

## 记录规则

1. 记录 Git 提交、迁移版本、环境和精确命令。
2. 本地测试通过最高只能达到 `IMPLEMENTED_LOCAL`。
3. 安全与租户切片需要 PostgreSQL 及真实身份提供方验证。
4. `ACCEPTED` 需要 CI、Staging 和签署证据。
5. 历史记录不回写；状态纠偏写入新记录和 `CURRENT_STATUS.md`。

## M1-03 补充状态

M1-03 身份同步：IMPLEMENTED_LOCAL / PASSED_LOCAL。邮箱非唯一、OIDC 身份键原子 upsert、20 路 PostgreSQL 并发及 Demo 迁移已通过；外部签章仍阻塞。

## M1-04 补充状态

M1-04 DTO、错误与契约基线：IMPLEMENTED_LOCAL / PASSED_LOCAL。extra forbid、Problem Details、401 Bearer challenge、OpenAPI 固定响应及 Demo 已通过；外部签章仍阻塞。

## M1-05 补充状态

M1-05 企业成员邀请与 RBAC：IMPLEMENTED_LOCAL / PASSED_LOCAL。邀请生命周期、权限矩阵、成员即时失权、项目创建授权和 PostgreSQL 迁移已通过；外部签章仍阻塞。

## M1-06 补充状态

M1-06 最后 Owner 并发保护：IMPLEMENTED_LOCAL / PASSED_LOCAL。组织行锁、锁后复核、Owner 授予权限和并发降级/移除不变量已通过真实 PostgreSQL 与 Demo 验收；外部签章仍阻塞。

## M1-07 补充状态

M1-07 项目完整生命周期：IMPLEMENTED_LOCAL / PASSED_LOCAL。CRUD、归档恢复、项目成员、opaque cursor、软删除与 If-Match 并发保护已通过真实 PostgreSQL 和 Demo 验收；外部签章仍阻塞。


## M1-08 补充状态

M1-08 审计、幂等与 Outbox：IMPLEMENTED_LOCAL / PASSED_LOCAL。强制幂等、并发重放、同键冲突、关键写审计/Outbox 同事务和回滚无半状态已通过真实 PostgreSQL 与 Demo 验收；外部签章仍阻塞。

## M1-09 当前状态

M1-09 租户纵深防御：IMPLEMENTED_LOCAL / PASSED_LOCAL。受限运行角色、7 张表 RLS、同连接 A/B/无租户矩阵、提交/回滚清理、全迁移升降级、真实 PostgreSQL 与 Demo 验收通过；外部签收仍受阻。

## M1-10 当前状态

M1-10 Web 组织/项目闭环：IMPLEMENTED_LOCAL / PASSED_LOCAL。BFF 登录入口、组织切换、成员管理、项目管理、幂等和 If-Match 客户端协议、Web 测试与 Demo SPA 路由通过；外部签收仍受阻。

## M1 总体验收状态

M1 总体验收：ACCEPTED。最终复验、main CI、真实 Chromium Staging E2E、安全扫描和四方确认均已完成；不可变标签 `m1-accepted` 指向 `c81a005`。

## M2 当前状态

| Slice | 当前状态 | 说明 |
|---|---|---|
| M2-00 | ACCEPTED | M1 验收基线、独立分支和实施计划门禁通过 |
| M2-01 | ACCEPTED | 双状态机、opaque Key、完整性、威胁模型和恢复矩阵设计门禁通过 |
| M2-02 | ACCEPTED | 对象存储端口、MinIO/OSS 适配契约及 CI 通过；网络 gateway 继续受安全门禁约束 |
| M2-03 | ACCEPTED | 上传会话、opaque Key、配额、幂等、取消、过期、RLS 与 CI 通过 |
| M2-04～08 | NOT STARTED | 必须按计划顺序实施和逐项验收 |

| M2-05 | ACCEPTED | Multipart 完成、完整流式 SHA-256、大小/摘要强校验、资产隔离及 RLS/CI 通过 |

| M2-06 | ACCEPTED | 资产列表/详情、短期下载授权、软删除、跨租户与归档语义及 CI 通过 |

| M2-07 | ACCEPTED | 过期会话、遗留 Multipart、失败删除、缺失/孤儿对象对账、退避、审计与 CI 通过 |
