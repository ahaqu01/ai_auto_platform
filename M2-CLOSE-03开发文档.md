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

2026-09-16 已创建新的 RAM AccessKey（文档仅记录尾号 `8cg4`），通过受限 CSV 通道写入 Staging `0600` 环境文件并重建 API 容器。切换后重新执行完整真实 OSS Playwright 用例，结果为 `1 passed (4.0m)`；API 为 `healthy`，清理后 Bucket 对象数为 0，证明本平台已停止使用旧 Key。

随后对项目目录、受限配置目录和全部运行容器执行配置审计：项目文件中的旧 Key 引用为 0；Staging 中携带 `OSS_ACCESS_KEY_ID` 的 API、PostgreSQL、Keycloak、MinIO 容器均已刷新为新 Key。六个 Staging 服务全部健康，Web 返回 200。Demo API 保持使用隔离的本地 MinIO 凭据，不使用阿里云旧 Key。

旧 Key 因仍被其他外部服务使用，用户明确要求暂不停用或删除。项目负责人于 2026-09-16 批准范围变更：本项目全部使用新 Key 且补偿控制通过后，外部服务的旧 Key 迁移与废止作为独立遗留安全风险，不再阻塞本工作包。M2-CLOSE-03 状态更新为 `ACCEPTED`，但旧 Key 仍必须按已暴露凭据处理。
