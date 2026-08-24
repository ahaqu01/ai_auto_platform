# M0R-04R-04 生产 TLS 与 Keycloak 前缀验收标准

- 关闭发现：`REV01-P2-01`、`REV01-P2-04`
- 基线：`501b5808216f4e6ffb3c3bb3421a515a959bfe51`
- 状态上限：`IMPLEMENTED_LOCAL`

## 门禁

1. staging/production PostgreSQL 默认要求唯一 `sslmode=verify-full`。
2. staging/production Redis 默认要求 `rediss://`。
3. 明文例外必须显式开启，且目标只能是 `.internal` hostname 或非 loopback 私网 IP。
4. Keycloak issuer 允许安全 context prefix，但最后两段必须为 `realms/<realm>`。
5. issuer 继续禁止 userinfo、query、fragment、不安全 scheme 和伪造尾部结构。
6. 配置专项、Ruff 和非 PostgreSQL API 全量回归通过。
