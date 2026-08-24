# M0R-04R-04 生产 TLS 与 Keycloak 前缀验收记录

- 关闭发现：`REV01-P2-01`、`REV01-P2-04`
- 基线：`501b5808216f4e6ffb3c3bb3421a515a959bfe51`
- 状态：`IMPLEMENTED_LOCAL`

## 测试证据

- 实现前：4 failed, 15 passed。
- 配置与公网专项：52 passed。
- 非 PostgreSQL API 全量：145 passed, 9 deselected, 1 warning。
- Ruff：通过。

## 结论

生产服务连接默认采用验证型 TLS。显式私网例外被限制到可信内部地址语义。Keycloak issuer 支持合法反向代理前缀，同时保留 userinfo/query/fragment/scheme 和尾部路径防绕过检查。
