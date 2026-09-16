# M2-CLOSE-03 阿里云 OSS Staging E2E 验收标准

1. Bucket 私有，并启用阻止公共访问。
2. CORS 不使用通配来源，仅允许 Staging 来源、GET/PUT/HEAD，暴露 ETag。
3. 凭据不进入 Git、日志或测试制品；使用目标 Bucket 最小权限 RAM 身份。
4. 1 KiB 上传可在首次 PUT 失败后重试，最终 AVAILABLE/VERIFIED，下载字节一致。
5. 100 MiB 上传支持暂停、恢复及取消，状态与 OSS 结果一致。
6. 1 GiB Multipart 上传可完成，并能从中断状态继续。
7. 预签名 URL 的方法、Bucket、对象键与 TTL 受约束；过期后不可使用。
8. 测试结束自动清理测试身份、租户数据和 OSS 对象。
9. 旧泄露/建议轮转的 Key 必须在新 Key 验证后停用并删除。

全部满足为通过；第 9 项未完成时最高结论为条件通过。

