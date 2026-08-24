# M0R-05R-02 PostgreSQL 断言收紧验收标准

- 制定日期：2026-08-24
- 基线提交：`6fc3888aea62f7bd58f357dd64151784765d0b11`
- 基线标签：`m0r-04r-02-implemented`
- 目标状态：`IMPLEMENTED_LOCAL`

## 范围

本任务只增强 PostgreSQL 约束与迁移证据，不新增业务模型或迁移。所有破坏性迁移测试继续受 M0R-05R-01 的专用数据库、最小权限角色及独立 downgrade 确认保护。

## 验收条件

1. 并发插入相同项目编码时必须恰有一个提交成功、一个唯一约束冲突。
2. 冲突必须断言 PostgreSQL SQLSTATE 为 `23505`，约束名为 `uq_projects_organization_id`；仅捕获通用 `IntegrityError` 不足以通过。
3. Alembic fixture 必须读取并保存全部 head revision，不得依赖只允许单 head 的 `get_current_head()`。
4. `upgrade heads` 后 `alembic_version` 中的 revision 集合必须与脚本目录全部 head 完全相等，不得只检查任意一个 revision。
5. `downgrade base` 后必须从 PostgreSQL catalog 枚举当前隔离 schema 的 tables、indexes、constraints、types、sequences、triggers。
6. base 状态必须与显式 allowlist 完全相等；多余和缺失对象都导致失败。allowlist 仅允许 Alembic 自身版本表及其 PostgreSQL 自动派生对象。
7. base 清单通过后必须 `upgrade heads`，并再次断言数据库 revision 集合等于全部脚本 heads。
8. catalog 查询必须限定本次随机 `test_` schema，不扫描或比较其他 schema。
9. downgrade 仍必须要求 `TEST_DATABASE_ALLOW_DOWNGRADE=M0R05R01_DISPOSABLE_DATABASE_DOWNGRADE`，且数据库身份保险丝测试不得退化。
10. PostgreSQL 专项、API 全量、Ruff、OpenAPI、Web、Agent、Compose 回归通过；形成独立提交和 `m0r-05r-02-implemented` 标签，提交后工作区干净。

## 状态边界

本地测试通过只可标记 `IMPLEMENTED_LOCAL`。Bugbot、Security Review、非作者人工评审、Staging 证据与 CI 连续成功仍属于后续状态，不在本任务中宣称完成。
