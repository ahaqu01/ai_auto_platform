# M2-CLOSE-03 开发文档

## 目标

将 M2 资产上传链路从本地 MinIO 验收扩展到真实阿里云 OSS Staging，验证浏览器直传、Multipart 恢复、取消、完整性校验和授权下载。

## 实现

- Staging 使用 `aliyun_oss`、`cn-hangzhou` 与 S3 兼容 Endpoint。
- AccessKey 仅保存在服务器 `0600` 环境文件中，不进入 Git、测试结果或文档。
- Bucket 保持私有并启用“阻止公共访问”。
- CORS 仅允许 `http://192.168.1.129:8081` 与同一 Staging 的回环来源 `http://127.0.0.1:8081`；仅允许 GET、PUT、HEAD；暴露 ETag。
- 新增真实 OSS Playwright 用例和自动清理脚本，下载内容以 SHA-256 做字节一致性校验。
- Staging Keycloak 默认语言修正为中文。

## 验证结果

- CORS OPTIONS：200，来源精确匹配，`ETag` 暴露，缓存 600 秒。
- 100 MiB：暂停后恢复并完成。
- 9 MiB：取消后状态为 ABORTED。
- 1 KiB：模拟首次 PUT 断线后自动重试并完成。
- 1 GiB：Multipart 完成，资产进入可用状态。
- 下载：文件名正确，SHA-256 与源内容一致。
- 清理：E2E 用户、组织、数据库记录与 OSS 对象均清理，Bucket 最终对象数为 0。

## 安全结论

当前临时 Key 可访问目标 Bucket，但 RAM OpenAPI 明确拒绝 `ram:ListAccessKeys`，说明其没有 RAM 管理权限。由于该 Key 曾出现在对话中且控制台建议轮转，M2-CLOSE-03 在新 Key 完成替换并停用/删除旧 Key 前只能条件通过。

