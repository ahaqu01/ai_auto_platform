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

## 待关闭项

- 新建并验证轮换 Key 后，停用并删除旧 Key。
- 当前旧 Key 只作为受限 Staging 临时凭据，不能作为 M2 最终生产凭据。

