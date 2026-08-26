# CI 与 Staging 工程基线验收记录

> Owner：QA/交付负责人
> 日期：2026-08-26
> 状态：VERIFIED_STAGING / BLOCKED_EXTERNAL

## 版本与环境

- 前置基线：`8c8a69b89506a39ece9ce6f4c9063eab9162d7d6` (`m0r-07-implemented`)
- 结果版本：本记录所在提交，标签 `ci-staging-baseline-implemented`
- Staging：`http://192.168.1.129:8081/`
- 迁移：`20260821_02`
- API 镜像：`sha256:fdfbb8a0209db4fd7f8561d945f65e2f559ac5f59fe412450d955324d241b7d4`
- Web 镜像：`sha256:89c79f644b0f5b8ba94195bd1effa92d90d81887307fd223c4f57a6b2ba95fcd`

## CI 证据

- Ruff、OpenAPI check、文档和部署契约：通过。
- API：150 passed，10 deselected；仅有已登记 TestClient 上游弃用警告。
- PostgreSQL job：39 passed，包含一次性数据库 downgrade；临时容器已清理。
- Web：3 passed，production build 通过，npm audit 0 vulnerabilities。
- Agent：Go vet 与 race test 通过。

## Staging 证据

- PostgreSQL、Redis、MinIO、API、Web：healthy。
- HTTP 首页和 `/health/ready` 冒烟：通过。
- API 重启后 readiness 恢复：通过。
- 独立 project、网络、命名卷和端口 8081；密钥位于仓库外 600 权限文件。

## 阻塞项

- 仓库无 Git remote，无法创建真实 PR、配置分支保护/CODEOWNERS 或取得连续 3 次远端 CI 成功证据。
- Keycloak/TLS 尚属下一业务阶段；本记录不声称身份切片 VERIFIED_STAGING 或产品 ACCEPTED。

## 结论

CI 配置和 M0-R 工程 Staging 已实现并在服务器验证。外部协作门禁标记 `BLOCKED_EXTERNAL`，待用户提供私有远端仓库和权限后补验。
