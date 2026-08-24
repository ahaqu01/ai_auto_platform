# M0R-03R-01 OpenAPI 身份语义与稳定导出验收记录

- 验收日期：2026-08-24
- 基线提交：`287f2320f6528e5607b875c4cc5a287e70b813ba`
- 基线标签：`m0r-05r-03-implemented`
- 状态：通过（`IMPLEMENTED_LOCAL`）

## 测试先行证据

实现前专项结果：

```text
1 failed, 5 passed in 1.70s
FAILED test_openapi_export_is_byte_stable_across_sanitized_environments
```

语义扫描测试已能识别 request body 内经 `$ref`/`allOf` 引入并规范化后的 `Actor-Id`，同时不误报 response 中的 `user_id`。失败来自 hostile production/staging 环境在导入 FastAPI 时进入 Settings 校验，准确证明旧导出器依赖调用者环境。

## 实现结果

- 新增 `platform_api.openapi_policy`，逐 path 和 HTTP operation 检查 path/query/header/cookie parameters 与 request body。
- request body 递归覆盖 properties、items、allOf、anyOf、oneOf 和本地 `$ref`；响应 schema 不参与身份输入判定。
- 禁止字段为 `user_id`、`actor_id`、`subject`、`owner_id`，按大小写和连字符/下划线规范化。
- 审批例外键由 method、path、location、field 四部分组成；当前真实契约例外集合为空。
- exporter 在导入 FastAPI 前覆盖全部已知 schema-generation Settings 为显式 local 值，随后清理 Settings cache、生成 schema、执行身份策略，最后才允许写快照。
- 两个仅保留最小进程变量且分别注入 production/无效 DB 与 staging/SQLite/metadata 配置的子进程，导出字节相同并与受控快照一致。
- 受控 `openapi.json` 内容未变化，无需产生快照噪声。

## 契约声明与运行时授权证据分离

OpenAPI 专项只证明 `HTTPBearer` 声明存在，运行时证据单独执行：

- 401：`test_protected_api_rejects_missing_and_invalid_token`
- 租户隐藏 404：`test_non_member_cannot_use_known_organization_id`
- 专项执行结果：`2 passed in 0.89s`

当前 API 没有“资源可见但当前角色权限不足”的 operation，因此 403 为不适用，未使用测试专用假路由伪造证据。未来增加角色管理、成员变更等 owner/admin operation 时，403 将成为强制运行时验收项。

## 验收结果

```text
OpenAPI 专项：7 passed in 2.54s
OpenAPI snapshot --check：通过
运行时 401/404 专项：2 passed in 0.89s
API 全量：132 passed, 1 warning in 6.63s
覆盖率回归：83%
Ruff（API、测试、scripts）：通过
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

## 边界复核

- 净化环境保证当前 Settings 集合不影响 schema 生成；未来新增影响 OpenAPI 的配置字段时，必须同时加入显式 schema 环境或消除 schema 分支。
- 身份策略检查契约输入，不证明 handler 在运行时正确授权，因此保持独立 API 行为测试。
- 本任务未建立远端受保护 PR、CI 三次连续成功或 Staging 签字。

## 验收结论

M0R-03R-01 本地验收标准满足，可以独立版本封存。按整改计划，下一步为 REV-01 双专项复审，而不是直接宣称 M0-R 已验收。
