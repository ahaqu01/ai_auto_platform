# M1-01 Keycloak Compose 与 Realm IaC 验收标准

> Owner：身份平台负责人 / QA
> 状态：CURRENT
> 版本：1.0

1. Keycloak 镜像版本固定，服务有健康检查、重启策略和有界日志。
2. Realm JSON 可在空数据卷重复导入，Realm 固定为 `ai-platform`。
3. 存在 `platform-api` audience 与 confidential `platform-bff`；BFF 使用 Authorization Code、PKCE S256，禁用 Direct Access Grant。
4. Realm roles 包含 platform-admin、org-owner、org-admin、org-member。
5. 同源 `/auth` 可访问 discovery；client credentials 产生有效签名 Token，issuer 和 audience 正确。
6. 本地演示凭证明确带 `local-demo-only`，不得用于 Staging/Production；无真实凭证入库。
7. 删除 Keycloak 数据卷后重建，Realm/Client/Role 和 Token 验收仍通过。
8. API/Web/Keycloak 冒烟、CI 基线、文档、差异和敏感信息扫描通过。
