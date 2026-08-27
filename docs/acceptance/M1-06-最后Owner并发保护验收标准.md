# M1-06 最后 Owner 并发保护验收标准

> Owner：平台工程
> 日期：2026-08-27
> 状态：ACCEPTANCE_DEFINED

## 验收项

1. Owner 可提升成员为 OWNER；Admin 不可授予或变更 OWNER。
2. 降级或移除最后一个 OWNER 返回 409 LAST_OWNER_REQUIRED，事务不改变数据。
3. 同企业两个 Owner 并发降级，恰好一个成功，最终 Owner 数为 1。
4. 同企业 Owner 降级与移除并发竞争，恰好一个成功，最终 Owner 数为 1。
5. 使用 PostgreSQL 企业行 FOR UPDATE 锁串行化同企业 Owner 变更；不同企业不共享锁。
6. API 生产端点调用并发安全服务，不再使用 M1-05 的 OWNER_MANAGEMENT_DEFERRED。
7. 全量 API/PostgreSQL/OpenAPI/Web/Go/文档/Demo 通过，形成独立提交、标签和开发文档。
