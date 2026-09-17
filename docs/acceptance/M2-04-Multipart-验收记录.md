# M2-04 Multipart 验收记录

> 历史证据快照。2026-09-17 P2 复评确认旧 3600 秒声明与 Gateway 不一致，当前合同已修订为 60～900 秒；最新边界证据见 M2-REVIEW-03 验收记录，不以本快照证明超过 900 秒有效。

> 日期：2026-09-11  
> 状态：ACCEPTED

## 版本证据

- 实现提交：`eb78d1a`（`feat: implement M2-04 multipart uploads`）。
- PostgreSQL RLS 计数修复：`b4b89d0`（新增第 9 张 RLS 表后的验收断言同步）。
- 数据库迁移头：`20260911_09`。
- 分支：`codex/m2-assets-storage`，均已推送远端。
- GitHub Actions：run `34555956515`，Baseline、PostgreSQL、Security 全部 success。

## 验收结果

- M2-03 + M2-04 专项：15 passed。
- 全量非 PostgreSQL API：226 passed，28 deselected。
- Web：5 个测试文件、9 项测试通过；TypeScript/Vite 构建通过。
- OpenAPI 快照、文档检查、部署可靠性契约、Go 测试、Ruff、`git diff --check` 通过。
- GitHub PostgreSQL 作业通过，覆盖全迁移、随机隔离 schema、FORCE RLS 与回滚契约。
- GitHub Security 作业通过；差异凭据扫描未发现 AccessKey ID/Secret。

## 功能矩阵

- 首次签名初始化 Multipart，行锁保证同一会话并发串行化，后续签名复用远端 Upload ID。
- 批量签名限制 1～100 个唯一分片、分片号 1～10000、TTL 60～3600 秒。
- 分片登记同值幂等、异值 409；断点续传清单按分片号排序。
- 取消已初始化会话调用远端 Abort；终态继续登记被拒绝。
- `upload_parts` 复合主键、检查约束及 FORCE RLS 生效。
- 未配置安全存储网关时返回 `503 STORAGE_UNAVAILABLE`，不降级为不受控网络访问。
- 公开 DTO、审计、Outbox 和日志不包含对象 Key、远端 Upload ID、长期凭据或预签名 URL。

## 已知边界

- 本验收使用依赖注入的存储替身验证协议；真实 OSS/MinIO 网络数据面仍受 M2-02 SSRF 安全门约束，未冒充 Staging E2E。
- npm audit 报告 Vitest 依赖链 2 个 moderate 公告；当前安全门成功，自动修复要求跨 Vitest 大版本，留待独立依赖升级工作处理。
- 直接在开发机重跑 PostgreSQL 套件时因缺少显式专用数据库确认变量而被安全保险丝拒绝；最终 PostgreSQL 验收以隔离的 GitHub Actions PostgreSQL 作业 success 为准。
