# M2-CLOSE-01 开发文档

> 日期：2026-09-15  
> 范围：安全 S3 兼容 Gateway、MinIO/OSS 运行时装配  
> 状态：IMPLEMENTED / ACCEPTANCE IN PROGRESS

## 实现

- `SafeS3Gateway` 实现 Multipart 初始化、预签名分片、完成、取消、Head、流式读取、下载签名、删除和分页列举。
- botocore 只使用 S3 V4 签名器、AWSRequest 和 Credentials；不创建 SDK 网络客户端。
- 所有公网 HTTPS 请求逐次验证 DNS、固定已验证 IP并复核 socket peer，TLS 保留原 hostname 的 SNI 与证书校验。
- 存储重定向全部拒绝，比自动跟随逐跳校验更严格。
- 私网 HTTP 仅允许显式启用的 MinIO，拒绝公网、metadata、link-local、组播和未指定地址。
- OSS 使用 virtual-hosted style，MinIO 使用 path-style；预签名有效期限定为 1～900 秒。
- 流式读取每次最多 1 MiB；控制面 XML 响应上限 4 MiB；XML 错误及网络异常统一归一化。
- 签名库 debug 日志强制过滤；凭据通过 SecretStr 保存，不进入设置 repr。
- API composition 通过配置装配适配器；配置不完整时保持 fail-closed。
- Demo 通过同源 `/demo/` 路由访问 MinIO；保留所有现有数据卷。

## 配置

`OSS_PROVIDER`、`OSS_REGION`、`OSS_INTERNAL_ENDPOINT`、`OSS_PUBLIC_ENDPOINT`、`OSS_BUCKET`、`OSS_ACCESS_KEY_ID`、`OSS_ACCESS_KEY_SECRET`、可选 `OSS_SESSION_TOKEN`。

真实凭据只能由仓库外受控通道注入。此前公开的 OSS Key 已视为泄露，禁止复用；必须在阿里云侧废止后使用新最小权限 RAM/STS 身份。

## 验收边界

本任务验收安全 Gateway 和运行时装配，不替代 M2-CLOSE-02 浏览器 MinIO E2E、M2-CLOSE-03 OSS Staging E2E、三档文件矩阵、调度或 M2 总签。

阿里云真实兼容性和旧 Key 废止证据仍需单独验收，不允许用 MinIO 结果替代。
