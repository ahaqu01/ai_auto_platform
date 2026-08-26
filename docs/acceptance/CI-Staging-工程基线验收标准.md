# CI 与 Staging 工程基线验收标准

> Owner：QA/交付负责人
> 状态：CURRENT
> 版本：1.0

## CI

1. CI 配置在 PR 和 main push 触发，默认权限为只读。
2. 基线门禁包含 Ruff、OpenAPI check、非 PostgreSQL API 回归、文档检查、部署契约、Vitest/build、npm audit、Go vet/race。
3. PostgreSQL job 使用临时 PostgreSQL 16，创建非超级测试角色，并运行完整集成和一次性 downgrade。
4. `scripts/ci.sh` 可在服务器复现基线 job 并通过。

## Staging

5. Staging 使用独立 Compose project、端口、网络和数据卷，不复用 demo 数据。
6. 密钥保存在仓库外环境文件；仓库只提交无真实值的 `.env.example`。
7. PostgreSQL、Redis、MinIO、API、Web 全部 healthy；HTTP 冒烟和 API 重启恢复通过。
8. 记录 Git commit、镜像 ID/摘要、迁移 head、服务状态和访问入口。

## 外部门禁

9. 受保护 PR 连续成功 3 次、CODEOWNERS 审批和分支保护必须以真实远端证据验收；未提供远端时标记 `BLOCKED_EXTERNAL`，不得伪造或标记 ACCEPTED。
