# M1-10 Web 组织/项目闭环验收记录

> 日期：2026-08-27
> 环境：Vitest / Vue TypeScript / Vite / Docker Compose Demo
> 结论：IMPLEMENTED_LOCAL / PASSED_LOCAL / BLOCKED_EXTERNAL

## 自动验证

- Web：`5 test files / 9 tests passed`。
- 管理页验证组织初始加载、成员与项目展示、组织切换清理和重新加载、选择持久化、项目创建。
- API 客户端验证项目创建 Idempotency-Key、更新 If-Match、Problem Details code/detail 保留。
- `vue-tsc -b` 和 Vite production build 通过，生成独立 WorkspaceView chunk。
- 全仓 CI 中 API、OpenAPI、文档治理、Demo 部署契约、Web、npm audit、Go vet/race 全部通过。

## Demo 证据

- Demo Web 与 API 容器 healthy。
- `/workspace` 返回 SPA 页面，刷新不会产生 Nginx 404。
- 登录、Cookie 和 CSRF 继续沿用已验收的 M1-02 BFF；真实外部用户的交互式 Keycloak 浏览器签收留在 M1 总体验收。

## 状态边界

本地自动化与 Demo 路由验证不等于外部 Staging 签收。远程 CI、PR、外部 Staging 和人工浏览器签收仍为 `BLOCKED_EXTERNAL`，因此不标记 ACCEPTED。
