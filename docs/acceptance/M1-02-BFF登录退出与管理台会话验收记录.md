# M1-02 BFF 登录、退出与管理台会话验收记录

> Owner：平台工程 / QA
> 日期：2026-08-27
> 状态：IMPLEMENTED_LOCAL

## 版本与范围

- 前置：`dd95fb4`（`m1-pre-01-hardening-implemented`）
- 结果：本记录所在提交，标签 `m1-02-bff-session-implemented`

## 红灯

- 初始测试因 `platform_api.auth.bff` 不存在而收集失败，证明旧代码仅支持 Bearer。
- 首次真实镜像构建暴露 `redis` 离线 wheel 缺失；第二次暴露 `httpx` 错放 dev 依赖。均已修正并由健康容器验证。

## 自动化验收

- Ruff、OpenAPI 确定性快照、文档检查与部署契约：通过。
- API：158 passed，10 deselected；仅保留已登记的 TestClient 上游弃用警告。
- PostgreSQL 一次性数据库：39 passed，临时角色与数据库按安全门禁创建和清理。
- Web：5 passed，生产构建通过；npm audit 0 vulnerabilities。
- Go：测试通过。
- 外部 return target 回退、state 重放、Cookie 标志、Origin/CSRF、Bearer 兼容与无 Token 前端状态均有测试。

## Demo 验收

- Postgres、Redis、MinIO、Keycloak、API、Web 全部 healthy，重建后持续运行。
- `/auth/login` 返回 303，Location 包含 `code_challenge_method=S256`、state、nonce 和 callback。
- 真实 Keycloak discovery 返回 200，授权重定向最终呈现用户名登录表单。
- Redis 出现 `bff:login:*`，300 秒后 TTL 为 `-2`；无效 state callback 返回 400 `INVALID_LOGIN_STATE`。
- `/auth/session` 未登录返回 `{"authenticated":false}`。

## 证据边界与结论

未把固定测试账户密码写入 Realm IaC。真实凭据登录可使用受控临时账户补充人工证据；回调令牌交换、Cookie 创建、会话和退出由自动化隔离桩覆盖。

M1-02 达到 `IMPLEMENTED_LOCAL`。远端 PR、受保护分支、正式 Staging 签署仍为 `BLOCKED_EXTERNAL`，不得标记 `ACCEPTED`。
