# M2-CLOSE-01 安全存储 Gateway 验收标准

1. 真实网络仅通过平台固定 peer transport；不得在 API 路由或领域服务创建 SDK 客户端。
2. 公网 HTTPS 每次请求重新验证 DNS；metadata、私网、混合 DNS 回答在连接前拒绝。
3. TCP 固定本次验证 IP并复核实际 peer；TLS SNI、Host、证书 hostname 验证保留。
4. 所有 3xx 存储重定向拒绝，不传递凭据到新目标。
5. 私网 HTTP 仅允许显式开启的 MinIO，并拒绝 metadata/link-local/公网/未指定/组播地址。
6. MinIO path-style、OSS virtual-hosted style；预签名 PUT 使用 UNSIGNED-PAYLOAD，TTL 1～900 秒。
7. Multipart、Head、流式读取、下载签名、删除和分页列举均经统一错误边界。
8. 真实 MinIO 验证 Multipart→PUT→complete→Head→流式 SHA-256→list→下载→delete；清理专用测试对象。
9. 日志、异常、设置 repr 不泄露长期凭据、原始签名 URL、Key 或 Upload ID。
10. Ruff、全仓 CI、PostgreSQL 和安全 CI 通过；工作区干净、独立版本提交和验收记录齐全。
11. 旧 OSS Key 不复用；OSS 实网 E2E和轮换证明明确保留至 CLOSE-03，不得提前宣称 M2 总体验收完成。
