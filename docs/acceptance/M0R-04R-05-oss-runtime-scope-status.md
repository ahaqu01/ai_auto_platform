# M0R-04R-05 OSS 运行时范围状态

OSS_RUNTIME_SSRF_STATUS: RUNTIME_GATEWAY_IMPLEMENTED_OSS_E2E_PENDING

## 当前事实

M2-CLOSE-01 已实现并装配 `SafeS3Gateway`：S3 Signature V4 仅负责签名，真实网络 I/O 统一经过平台 transport。公网 HTTPS 请求在每次操作时重新解析并验证地址，TCP 固定到已验证 IP，复核实际 socket peer，并保持原 hostname 的 TLS SNI 与证书校验；存储重定向全部拒绝。可信私网 HTTP 只能由显式部署开关启用，且同样固定和复核 peer。

MinIO 运行时已在 Demo 装配并完成真实 Multipart、读取、列举、预签名下载和删除验收。阿里云 OSS 支持的 S3 兼容操作已按 virtual-hosted style 实现，但旧长期 AccessKey 已视为泄露且禁止复用；在轮换为最小权限 RAM/STS 凭据并完成真实 OSS Staging E2E 前，状态保持 `OSS_E2E_PENDING`。

## 已关闭的原阻断

1. 公网地址逐请求解析与验证；
2. TCP 固定到本次验证 IP并复核 socket peer；
3. TLS 保持原 hostname 的 SNI 与证书校验；
4. 不允许存储重定向，避免逐跳策略被绕过；
5. API 只通过运行时 composition 注入 Gateway，不在路由中实例化 SDK；
6. 凭据使用 `SecretStr`，异常和日志不输出原始签名、Key、Upload ID 或 SDK 响应体。

## 尚未关闭

阿里云侧旧 Key 废止证明、新最小权限凭据注入、Bucket/CORS 以及真实 OSS E2E 属于 M2-CLOSE-03，不得用 MinIO 结果替代。
