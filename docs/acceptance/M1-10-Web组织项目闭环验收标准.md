# M1-10 Web 组织/项目闭环验收标准

> Owner：Web / QA / 平台后端
> 日期：2026-08-27
> 状态：IMPLEMENTED_LOCAL / PASSED_LOCAL

## 验收标准

1. 未登录用户可从管理台进入 BFF 登录，已登录用户显示身份并可退出。
2. 管理台可列出、创建和切换组织，刷新后保留有效的组织选择。
3. 切换组织必须按新 organization ID 重新加载成员和项目，不展示上一组织残留数据。
4. 可列出成员，并发起邀请、修改角色和移除成员；Owner 高风险操作由 UI 防误触且 API 最终裁决。
5. 可列出和创建项目，并可修改名称、归档和恢复。
6. 组织/项目创建携带独立 Idempotency-Key。
7. 项目修改、归档和恢复携带与当前版本匹配的 If-Match。
8. Cookie 请求使用 same-origin credentials；写请求携带 BFF CSRF token。
9. API 403/404/409/412 等 Problem Details 在页面明确显示，不静默吞错。
10. 页面支持桌面和窄屏布局，导航、表单和操作具有可访问名称。
11. Web 单测、类型检查、生产构建、全仓 CI 和 Demo 路由验收通过。
12. 形成独立提交和 implemented 标签；外部 CI/Staging 未签收时不得标记 ACCEPTED。
