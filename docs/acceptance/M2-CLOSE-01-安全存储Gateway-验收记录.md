# M2-CLOSE-01 安全存储 Gateway 验收记录

> 日期：2026-09-15  
> 结论：CODE / RUNTIME / MINIO ACCEPTED；OSS CREDENTIAL ROTATION EVIDENCE PENDING

## 版本证据

- 实现提交：`ea748b5`。
- 验收修复提交：`efe20f3`。
- 最终 GitHub Actions：run `34964313687`，baseline、PostgreSQL、security 全部 `success`。
- 前一运行 `34962727462` 因新增 Gateway 拉低总体覆盖率而失败；补充操作/分支测试后 Gateway 覆盖率升至 83%，非 PostgreSQL 总体覆盖率为 80.01%，最终远端门禁恢复成功。

## 已通过

- Ruff、OpenAPI、文档、Demo 部署契约通过。
- API：254 项非 PostgreSQL 测试通过；最终全仓本地 CI 通过。
- Web：7 个测试文件、17 项测试及生产构建通过。
- Gateway 专项覆盖 DNS 重解析、固定 peer、socket peer 复核、TLS hostname/SNI、重定向拒绝、私网 HTTP 白名单、metadata/link-local 拒绝、日志过滤、TTL 和 XML 错误。
- 存储相关上传、完成、下载、清理/对账回归 39 项通过。
- 使用 Demo 容器实际 `OSS_*` 配置，通过 `192.168.1.129:8080/demo/` 完成真实 MinIO Multipart→PUT→complete→Head→流式 SHA-256→list→下载签名→delete；专用测试对象已清理。
- 使用故意无效的探测凭据向杭州 OSS 发出只读 HEAD：公网 DNS、固定 peer、TLS/SNI 网络链路可达，并归一化为拒绝；未读取或写入 Bucket。
- API、Web、Keycloak、PostgreSQL、Redis、MinIO 均 healthy；Demo HTTP smoke 通过；部署未删除任何数据卷。

## 未通过的外部条件

此前公开的长期 OSS AccessKey 必须视为泄露。开发和验收未复用该 Key。当前没有阿里云控制台权限或脱敏审计证据能够证明旧 Key 已禁用/删除，因此 M2-CLOSE-01 尚不能标记为无条件 ACCEPTED。

需要账号持有人提供：旧 Key 已禁用/删除的脱敏截图或审计记录，以及新最小权限 RAM/STS 策略的脱敏说明。新凭据不得粘贴到对话、Git、文档或日志；应通过仓库外 `0600` 环境文件或工作负载身份注入。

真实 OSS 写入、CORS、ETag 和文件矩阵仍属于 M2-CLOSE-03，不以本次只读 transport 探测替代。
