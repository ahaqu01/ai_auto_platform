# M1-01 Keycloak Compose 与 Realm IaC 验收记录

> Owner：身份平台负责人 / QA
> 日期：2026-08-26
> 状态：IMPLEMENTED_LOCAL

## 版本与范围

- 前置：`9a0805ec188c1f82206d001ec6663a2fd0767f5f`
- 结果：本记录所在提交，标签 `m1-01-keycloak-iac-implemented`
- Keycloak：`quay.io/keycloak/keycloak:26.3.3`

## 验收证据

1. Compose config、健康检查、重启策略和有界日志：通过。
2. Realm `ai-platform`、API audience、confidential BFF、PKCE S256、四个 realm role：导入通过。
3. 同源 `/auth` discovery、client credentials 签名 Token、issuer/audience：通过。
4. 精确删除本地 Keycloak 数据卷后从 Realm JSON 重建：healthy，OIDC 验收再次通过。
5. 平台 HTTP 冒烟和部署可靠性契约：通过。
6. 完整本地 CI、文档、diff 和敏感信息扫描：待最终命令确认后随提交证据归档。

## 边界

本地 Keycloak 使用 development mode 和明确的 `local-demo-only` 凭证，仅用于 M1-01 演示。真实 HTTPS、BFF 会话和 Token→API 浏览器链路属于 M1-02，不降低现有公网 JWKS/TLS 安全门禁。

## 结论

M1-01 达到 `IMPLEMENTED_LOCAL`；不得标记产品 ACCEPTED。
