# M0R-05 PostgreSQL 集成测试夹具验收结果

> 执行日期：2026-08-21
> 基线提交：`879b260`
> 验收状态：`IMPLEMENTED_LOCAL`
> 结论：开发服务器真实 PostgreSQL 验证通过；没有独立评审、CI PostgreSQL Service 和 Staging 证据，因此不标记为 `ACCEPTED`。

## 1. 测试优先证据

实现前先加入 PostgreSQL 专项测试：

```text
fixture 'postgresql_database' not found
5 errors in 0.34s
```

五个测试均因目标夹具尚不存在而失败；Python 导入和 pytest 本身正常。实现夹具后的专项结果：

```text
5 passed in 1.56s
```

## 2. 验收标准核对

| 编号 | 结果 | 证据 |
|---|---|---|
| PG-01 | 通过 | 夹具只读取显式 `TEST_DATABASE_URL`，拒绝非 PostgreSQL、Production 环境或数据库名 |
| PG-02 | 通过 | 每个测试创建 `test_<uuid>` schema 并在 finally 中清理 |
| PG-03 | 通过 | Alembic `upgrade head` 建表；`alembic_version` 等于当前 head |
| PG-04 | 通过 | dialect 为 PostgreSQL，`current_schema()` 等于随机测试 schema |
| PG-05 | 通过 | 两事务并发写同一项目 code，结果为一次 committed、一次 conflict |
| PG-06 | 通过 | flush 后 rollback，企业计数为 0 |
| PG-07 | 通过 | 数据库级删除企业后，成员和项目计数均为 0 |
| PG-08 | 通过 | 每个独立 schema 可 `downgrade base` 后重新 `upgrade head` |
| PG-09 | 通过 | 全量测试后 `test_%` schema 残留数为 0；代码不含 DROP DATABASE/public schema |
| PG-10 | 通过 | PostgreSQL 专项、API、迁移、Web、Agent 和 OpenAPI 回归全部通过 |

## 3. 全量验证

- Ruff format/check（API 源码、测试、脚本）：通过。
- PostgreSQL 专项：`5 passed`。
- API 全量（包含 PostgreSQL）：`36 passed`，总覆盖率 `82%`。
- PostgreSQL 测试 schema 残留：`0`。
- Alembic model check：`No new upgrade operations detected.`
- npm audit：`0 vulnerabilities`。
- Web：`1 passed`；生产构建成功。
- Agent：`go vet ./...` 与 `go test -race ./...` 通过。
- OpenAPI：受控快照为 current。

仍保留一条已登记的 FastAPI/Starlette TestClient 上游弃用警告；PostgreSQL 专项自身无警告。

## 4. 实现说明

- 选择随机 schema 而不是随机数据库，避免要求测试角色具备创建/删除数据库权限。
- 所有迁移通过已有 Alembic 脚本执行，不使用 `metadata.create_all()` 冒充迁移验证。
- 清理逻辑位于 `finally`，且 schema 名必须以 `test_` 开头。
- pytest marker 已登记；Alembic 增加 `path_separator = os`，消除新版配置警告。
- 测试运行说明要求 CI/Staging 使用专用测试角色；开发机才允许使用 Compose 本地角色。

## 5. 验证中发现并修正的问题

M0R-04 曾把 Compose project 固定为 `ai-auto-platform-local`，与现有容器标签 `ai-auto-platform` 不一致，导致管理命令看不到运行中的服务。本阶段依据容器标签将 project name 修正为 `ai-auto-platform`。验证结果：三个服务均 healthy，Compose 解析无 stderr，`exec postgres` 可正常执行。

## 6. 后续门禁

进入 `ACCEPTED` 前仍需：

1. CI 使用独立 PostgreSQL Service 和最小权限测试角色运行这些测试；
2. 增加失败注入，证明测试进程异常时由 CI 清理残留 schema；
3. 独立评审夹具的目标库保护和清理边界；
4. Staging 运行迁移往返时使用专用临时数据库，不在业务数据库执行 downgrade。
