# M1-02 BFF 登录、退出与管理台会话验收标准

> Owner：平台工程 / QA
> 状态：CURRENT
> 版本：1.0

1. 登录使用 Authorization Code + PKCE S256，state 与 nonce 具备足够熵，return target 不允许开放重定向。
2. state 保存于 Redis、TTL 300 秒并原子一次性消费；重放回调返回 400。
3. Token 仅存服务端；浏览器只接收不透明 HttpOnly、SameSite Cookie，Staging/Production 使用 Secure。
4. Access Token 经 issuer/audience/signature 验证，nonce 不匹配拒绝；临近过期自动刷新，失败删除会话。
5. `/auth/session` 不返回 Access/Refresh/ID Token，只返回必要用户资料和 CSRF Token。
6. Cookie 认证可访问既有受保护 API；所有状态变更请求校验精确 Origin 和会话绑定 CSRF。
7. 显式 Bearer 认证保持兼容，不要求浏览器 CSRF。
8. 退出尽力吊销 Keycloak Refresh Token；无论上游是否可用，本地 Redis 会话和 Cookie 都删除。
9. Nginx 精确区分 BFF 端点与 Keycloak `/auth/realms/*`，管理台能够显示登录/退出状态。
10. Ruff、API 全量、PostgreSQL、Web 测试/构建、OpenAPI、部署契约、文档、diff 和敏感信息检查通过；Demo 栈全部健康。
