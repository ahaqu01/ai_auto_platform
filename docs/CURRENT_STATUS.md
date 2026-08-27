# Current Status

> Owner：平台后端 / Web
> Updated：2026-08-27
> Git baseline：M1-10 提交，标签 `m1-10-web-tenant-workspace-implemented`
> Database migration：`20260827_07` (head)
> Status：M1-10 IMPLEMENTED_LOCAL / PASSED_LOCAL / BLOCKED_EXTERNAL

## 当前事实

- M1-01 至 M1-10 的本地实现链路完成。
- 管理台支持 BFF 登录/退出、组织创建与切换、成员邀请/改角色/移除、项目创建/修改/归档/恢复。
- Web 写请求复用 CSRF；创建请求使用 Idempotency-Key；项目并发更新使用 If-Match。
- Web 单测、类型检查、生产构建、全仓 CI 与 Demo SPA 路由通过。
- 数据库 head 仍为 `20260827_07`，M1-09 RLS 前置保持有效。

## 状态边界

当前是本地自动化与 Demo 证据。远程 CI、PR、外部 Staging 和真实用户浏览器签收缺少外部权限，因此不能标记 ACCEPTED。

## 权威执行顺序

1. 执行 M1 总体验收：真实 Keycloak 浏览器 E2E、身份/授权矩阵、连续远程 CI 和 Staging 签收。
2. 清零 M1 总体验收阻断项。
3. 总体验收通过后进入资产/任务域。

文档入口见 [文档治理索引](README.md)，验证证据见 [acceptance](acceptance/README.md)。
