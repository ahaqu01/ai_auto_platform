# M0R-04R-03 JWKS 连接地址固定验收记录

- 关闭发现：`REV01-P1-01`
- 基线：`4bac1ddcd7cc043ebad74011f1f68f6bfa08caba`
- 状态：`IMPLEMENTED_LOCAL`

## 测试证据

- 实现前：专项测试因缺少 `PinnedHTTPSConnection` 收集失败（1 error），符合预期红灯。
- 专项与公网配置：37 passed；新增逐跳测试后 JWKS 专项 5 passed。
- 非 PostgreSQL API 全量：126 passed, 9 deselected, 1 warning。
- Ruff：待提交前最终确认为通过。

## 实现结论

TCP 连接目标固定为本次 DNS 验证集合中的 IP，连接后复核 socket peer；TLS 包装继续使用原 hostname。JWKS 重定向在客户端中逐跳处理，每一跳重新解析并创建新的固定连接。
