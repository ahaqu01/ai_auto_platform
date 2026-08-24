# M0R-04R-03 JWKS 连接地址固定验收标准

- 关闭发现：`REV01-P1-01`
- 状态上限：`IMPLEMENTED_LOCAL`

## 门禁

1. 每个 JWKS URL 解析并验证全部候选 IP 均为公网地址。
2. TCP 仅连接本次已验证集合中的固定 IP，实际 socket peer 不在集合时拒绝。
3. TLS SNI、证书 hostname verification 和 HTTP Host 保持原 hostname。
4. 每个重定向 hop 重新解析、验证并固定，不复用上一跳地址。
5. 保留“验证公网、实际 peer 私网”的预期红灯证据。
6. 专项、配置及非 PostgreSQL API 全量回归通过。
