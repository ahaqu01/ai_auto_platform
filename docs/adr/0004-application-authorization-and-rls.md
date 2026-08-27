# ADR-0004：应用授权与 PostgreSQL RLS 职责边界

- 状态：Accepted
- 日期：2026-08-27
- 决策者：平台工程 / 安全

## 背景

应用层 RBAC 能提供动作级权限和稳定的 403/404 语义，但遗漏企业过滤时可能造成跨租户读取或写入。PostgreSQL RLS 适合作为纵深防御，但不能替代业务授权，也不能依赖客户端 Header 选择租户。

## 决策

1. 应用层继续负责身份、成员关系、角色、动作和资源状态校验。
2. PostgreSQL RLS 负责租户行的最后一道隔离；上下文来自已经认证的主体和路由资源。
3. 迁移角色拥有 schema；请求事务使用无 `BYPASSRLS` 的 `platform_runtime` 角色。
4. 使用 `SET LOCAL ROLE` 与事务级 `set_config(..., true)`；禁止 Session 级 `SET`。
5. 无 organization context 时租户表默认拒绝。例外仅包括：
   - “我的企业列表”按 actor 自身 membership 读取；
   - 企业创建过程中创建者建立首个 OWNER；
   - 邀请 token 通过窄化 SECURITY DEFINER 函数只解析 organization ID，随后立即进入租户上下文。
6. `users` 与 `idempotency_records` 是主体/基础设施表，不以 organization RLS 隔离；应用仍按主体键访问。
7. 平台后台未来使用独立角色和 Repository，并要求显式审计，不允许普通 API 参数切换后台角色。

## 后果

- 即使应用查询遗漏 organization 条件，运行角色也无法看到或修改其他企业行。
- 每个租户事务必须先设置上下文；新增租户表必须同时增加 RLS 策略和连接复用测试。
- migration owner 的直接查询不代表运行时权限，验收必须 `SET LOCAL ROLE platform_runtime`。
