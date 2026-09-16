# M2-04 Multipart 验收标准

> 状态：ACTIVE  
> 日期：2026-09-11

## 功能

- 首次签名初始化 Multipart，重复签名复用同一个远端 Upload ID。
- 批量分片号必须唯一且为 1～10000；单次最多 100 个；签名 TTL 为 60～3600 秒。
- 分片登记相同 ETag/大小可重放，不同内容返回 409；查询按分片号排序。
- 取消已初始化会话调用远端 Abort；ABORTED/EXPIRED/其他终态拒绝继续登记。

## 一致性与安全

- 初始化使用数据库行锁保护并发状态；`upload_parts` 有复合主键和数据库检查约束。
- `upload_parts` 启用 FORCE RLS，并通过 A/B/跨租户 PostgreSQL 测试。
- 初始化、登记和取消具备审计/Outbox 证据；审计、Outbox、日志和公开 DTO 均不含对象 Key、Upload ID、密钥或预签名 URL。
- 未配置安全存储运行时时失败关闭，真实 OSS/MinIO 网络数据面仍受 M2-02 安全门约束。

## 工程门禁

- M2-03/M2-04 专项测试通过。
- API/Web/Go、OpenAPI、文档、依赖安全检查和 `git diff --check` 通过。
- PostgreSQL 全迁移、RLS 与回滚隔离验收通过。
- 独立实现提交及独立验收证据提交均推送，GitHub Actions 成功。
