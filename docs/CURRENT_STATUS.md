# Current Status

> Owner：交付负责人 / 产品 / 技术 / 安全 / QA
> Updated：2026-09-01
> Git baseline：M1 最终复验提交 `433a1ba`
> Database migration：`20260827_07` (head)
> Status：M1 ACCEPTED / M2 STARTED

## 当前事实

- M1-PRE-01、M1-01 至 M1-10、M1-CR-00 至 M1-CR-04 已完成。
- M1-A01 至 M1-A05 已关闭；M1-A06 为非阻断 P3，转入维护清单。
- M1-CR-04 已由 ADR-0005 固化归档项目写入、恢复和错误码语义。
- API/PostgreSQL 全量复验通过；总体覆盖率 89.04%，安全关键模块分支覆盖率 90.70%（78/86）。
- Staging 真实 Chromium Keycloak/BFF/Web/API/logout E2E 通过，一次性测试用户已清理。
- pip-audit、Bandit、npm audit、govulncheck 强制安全门禁通过。
- GitHub Actions run `33466902659` 对提交 `433a1ba` 为 success。
- Staging Web、API、PostgreSQL、Redis、MinIO、Keycloak 均处于 healthy。
- 产品、技术、安全、QA 四角色沿用用户账号 `ahaqu01` 的明确确认；本轮未改变签字范围或验收主体。

## 权威执行顺序

1. M1-CR-04 归档语义决策并固化契约。
2. 在同一最终提交执行 M1 完整复验与四方确认。
3. 复验文档快进进入 `main`，等待 main CI 成功并创建不可变 M1 验收标签。
4. 从已验收的 main 基线创建 `codex/m2-assets-storage`，正式启动 M2。
5. M2 严格按工作包顺序实施和逐项验收，不以“已启动”替代“已接受”。

## 决策

M1 最终复验结论为 `ACCEPTED`，M2 进入门禁开放。发布流程仍须满足：本状态与复验报告快进进入 GitHub `main`、main CI 为 success、不可变 `m1-accepted` 与 `m1-review-remediation-accepted` 标签指向同一已验收提交。完成后方可在独立 `codex/m2-assets-storage` 分支提交 M2 业务代码。

M2 严格按“对象 Key/威胁模型 → 存储适配端口 → 上传会话 → Multipart → 完成校验 → 下载授权 → 清理/对账 → 前端上传”推进。当前仅开放并启动 M2，不表示任何 M2 工作包已验收。

详细证据见 [M1 最终复验记录](acceptance/M1-final-reacceptance-2026-09-01.md)，归档语义见 [ADR-0005](adr/0005-archived-project-mutation-policy.md)。

## M2 当前状态

M2-00 启动门禁已通过，独立工作分支为 `codex/m2-assets-storage`。当前允许执行 M2-01“对象 Key 与威胁模型”；M2-02 至 M2-08 均未开始，M2 尚未 ACCEPTED。

执行计划见 [M2 资产与对象存储闭环实施计划](plans/M2-assets-storage-implementation-plan.md)，启动证据见 [M2-00 验收记录](acceptance/M2-00-kickoff-gate.md)。
