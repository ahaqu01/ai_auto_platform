# M2-CLOSE-03 阿里云 OSS Staging E2E 验收记录

- 日期：2026-09-16
- 环境：`aiautoplatform`，华东 1（杭州），Staging `:8081`
- 结论：**条件通过**

## 已通过

- Bucket ACL 私有；阻止公共访问已开启。
- CORS 两个精确 Staging 来源生效；OPTIONS 返回 200；GET/PUT/HEAD、ETag、600 秒缓存符合标准。
- Playwright 真实 OSS 用例通过，耗时 4.0 分钟。
- 100 MiB 暂停/恢复完成；取消任务 ABORTED。
- 1 KiB 首次 PUT 断线后重试完成。
- 1 GiB Multipart 上传完成。
- 资产状态 AVAILABLE/VERIFIED；授权下载 SHA-256 与源内容一致。
- 测试结束 Bucket 对象数为 0。
- RAM 管理越权探测返回 403 NoPermission。
- 新 RAM AccessKey（尾号 `8cg4`）已注入 Staging，配置文件权限为 `0600`，API 重建后健康状态为 `healthy`。
- 使用新 Key 重新执行完整 Playwright 用例：`1 passed (4.0m)`；清理后 Bucket 对象数再次确认为 0。
- 本平台已不再使用旧 Key。

## 待关闭项

- 旧 Key 仍被其他外部服务使用，用户要求暂不删除；需先迁移这些依赖，再停用并删除旧 Key。
- 上述保留决定不影响本平台新 Key 的运行验证，但不满足验收标准第 9 条，因此本工作包仍为条件通过，M2 总签不得提前进行。
