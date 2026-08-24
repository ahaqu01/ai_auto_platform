# M0R-04R-05 OSS 出站范围闭环验收标准

- 关闭发现：`REV01-P2-05`
- 基线：`508cee6b5828c2fab0b0a7c8da1521105007d6fd`
- 状态上限：`IMPLEMENTED_LOCAL`

## 门禁

1. 明确记录 OSS 客户端尚未实现，禁止声称运行时 SSRF 已关闭。
2. 修订 M0R-04R-02 的运行时证据范围，不得从策略单测/JWKS 外推到 OSS。
3. 架构测试阻止 OSS SDK 依赖和生产代码消费 `oss_public_endpoint`。
4. 状态解除必须与真实客户端固定 peer、TLS hostname、逐跳重定向测试原子提交。
5. 专项、Ruff 和非 PostgreSQL API 全量回归通过。
