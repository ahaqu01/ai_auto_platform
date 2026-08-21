# M0R-03 OpenAPI 单一事实源验收结果

- 执行日期：2026-08-21
- 基线提交：`2121145`
- 验收状态：`IMPLEMENTED_LOCAL`
- 结论：本地开发服务器验证通过；尚未经过独立评审、CI 和 Staging，因此不标记为 `ACCEPTED`。

## 1. 测试优先证据

实现前仅加入验收测试并执行：

```text
FAILED apps/api/tests/test_openapi_contract.py::test_controlled_openapi_snapshot_matches_runtime
AssertionError: run scripts/export_openapi.py
1 failed, 2 passed in 0.75s
```

该失败准确证明受控的 `packages/contracts/openapi.json` 尚不存在。实现后的契约测试结果：

```text
4 passed in 2.50s
OpenAPI snapshot is current
```

过程中还发现测试曾直接导入仓库根目录 `scripts`，在 API 的 pytest 导入根下不可移植。测试已改为黑盒调用导出命令，并同时验证两次导出的字节完全一致。

## 2. 验收标准核对

| 编号 | 结果 | 证据 |
|---|---|---|
| OAS-01 | 通过 | `scripts/export_openapi.py` 从 `create_app().openapi()` 生成 JSON 快照 |
| OAS-02 | 通过 | 两个临时目标连续导出，字节完全一致 |
| OAS-03 | 通过 | JSON 快照与运行时模式深度相等 |
| OAS-04 | 通过 | 健康、组织、项目路径均由测试断言 |
| OAS-05 | 通过 | `HTTPBearer` 及受保护操作的安全声明均由测试断言 |
| OAS-06 | 通过 | 契约中不存在由调用方传入的 `user_id` |
| OAS-07 | 通过 | 所有 HTTP 操作均有非空且唯一的 `operationId` |
| OAS-08 | 通过 | 已删除旧的手工维护 `openapi.yaml`，只保留生成的 `openapi.json` |
| OAS-09 | 通过 | `packages/contracts/README.md` 记录导出和检查命令 |
| OAS-10 | 通过 | API、迁移、Web、Agent 回归全部通过 |

## 3. 全量验证

- Ruff（API 源码、测试、脚本）：通过。
- API：`20 passed`，覆盖率 `81%`；有 1 条来自 FastAPI/Starlette TestClient 的上游弃用警告。
- Alembic：`No new upgrade operations detected.`
- npm audit：`0 vulnerabilities`。
- Web：`1 passed`；生产构建成功。
- Agent：`go vet ./...` 与 `go test -race ./...` 通过。
- `git diff --check`：通过。

全仓库 `ruff format --check apps/api scripts` 仍会报告两份历史迁移文件未按当前格式化规则排版；本切片没有改写已执行过的历史迁移，只对新增文件执行并通过格式及静态检查。这是基线遗留的工程规范问题，应在后续质量治理任务中明确迁移目录的格式化策略。

## 4. 变更与回滚

- 新增确定性 OpenAPI 导出和 `--check` 模式。
- 新增运行时契约快照、契约测试和维护说明。
- 删除旧的手工维护 YAML；该删除已纳入 Git，可通过版本历史恢复。
- 未变更数据库结构、运行时业务逻辑或部署配置。

## 5. 后续门禁

进入 `ACCEPTED` 前仍需：

1. 在具备远端仓库后由独立评审者审查变更；
2. 在 CI 中执行 `scripts/export_openapi.py --check` 与契约测试；
3. 在 Staging 完成一次真实部署和契约可访问性验证。
