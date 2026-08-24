# M0R-05R-02 PostgreSQL 断言收紧验收记录

- 验收日期：2026-08-24
- 基线提交：`6fc3888aea62f7bd58f357dd64151784765d0b11`
- 基线标签：`m0r-04r-02-implemented`
- 状态：通过（`IMPLEMENTED_LOCAL`）

## 测试先行证据

实现前运行新增迁移契约测试：

```text
ModuleNotFoundError: No module named 'postgresql.catalog'
1 error during collection
```

该红灯准确识别出当前没有 PostgreSQL catalog 枚举与 base allowlist 能力。代码盘点同时确认旧实现仅使用 `get_current_head()` 保存单 head，且并发冲突只捕获通用 `IntegrityError`。

## 实现结果

- 并发相同项目编码插入继续验证单一赢家，并从 psycopg 原始异常断言 SQLSTATE `23505` 与约束名 `uq_projects_organization_id`。
- Alembic fixture 改为读取 `ScriptDirectory.get_heads()` 的完整集合，并使用 `upgrade heads`。
- 数据库 `alembic_version` 按集合与全部脚本 heads 做完全相等比较。
- 新增限定随机 `test_` schema 的 catalog 枚举，覆盖 tables、indexes、constraints、types、sequences、triggers。
- `downgrade base` 后清单与显式 allowlist 完全相等；允许对象仅为：
  - table：`alembic_version`
  - index/constraint：`alembic_version_pkc`
  - PostgreSQL 自动类型：`alembic_version`、`_alembic_version`
  - sequence/trigger：空集合
- base 清单通过后重新 `upgrade heads` 并再次验证全部 revision。
- M0R-05R-01 的测试数据库身份校验、非 superuser 限制和 downgrade 二次确认保持启用。

## 验收结果

```text
PostgreSQL 专项：24 passed in 1.97s
API 全量：126 passed, 1 warning in 8.11s
API 覆盖率：82%
Ruff（apps/api/src + apps/api/tests）：通过
git diff --check：通过
Alembic heads：20260821_02 (head)
Docker Compose config：通过
npm audit --audit-level=high：0 vulnerabilities
Web 测试：1 passed
Web 生产构建：通过
Go vet：通过
Go race test：通过
```

API 测试仍有一条既有 Starlette/httpx 弃用警告，与本任务无关。

## 人工复核

- 本任务未修改任何业务迁移或生产模型，只收紧测试 fixture 和数据库证据。
- catalog SQL 全部使用绑定参数限定当前随机测试 schema；CREATE/DROP 目标仍由 fixture 内部 UUID 生成并受 `test_` 前缀和数据库身份保险丝保护。
- allowlist 使用完全相等而非子集判断，可同时发现残留对象和预期对象缺失。
- 多 head 支持验证“脚本 head 集合 = 数据库 revision 集合”，当前仓库仍只有一个 head，但 fixture 不再假设永远单 head。

## 验收结论

M0R-05R-02 的本地验收标准满足，可以独立版本封存。该结果不代表 `REVIEWED`、`VERIFIED_STAGING` 或 `ACCEPTED`。下一工作包按计划为 M0R-05R-03（API-on-PostgreSQL）。
