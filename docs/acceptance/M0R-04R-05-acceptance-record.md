# M0R-04R-05 OSS 出站范围闭环验收记录

- 关闭发现：`REV01-P2-05`
- 基线：`508cee6b5828c2fab0b0a7c8da1521105007d6fd`
- 状态：`IMPLEMENTED_LOCAL`

## 测试证据

- 实现前：1 failed，缺少机器可读范围状态。
- OSS 客户端架构门禁：1 passed。
- 非 PostgreSQL API 全量：148 passed, 10 deselected, 1 warning。
- Ruff：通过。

## 结论

当前采用计划允许的“客户端尚未实现时范围降级”路径。文档明确 OSS 运行时 SSRF 尚未关闭，架构测试阻止在缺少固定 peer/重定向/TLS hostname 证据时接入 OSS SDK 或消费公网 endpoint。
