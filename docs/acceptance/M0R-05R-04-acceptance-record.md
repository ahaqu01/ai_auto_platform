# M0R-05R-04 一次性 downgrade 数据库验收记录

- 关闭发现：`REV01-P1-02`
- 基线：`6e9b29bab5752da94a283808531823bb40141de7`
- 状态：`IMPLEMENTED_LOCAL`

## 测试证据

- 实现前安全门禁：6 failed, 18 passed（缺少销毁确认和 DDL 门禁）。
- 实现后安全门禁：24 passed；追加 owner/marker/共享连接及 DDL 补强反例后 29 passed。
- 首次真实 round-trip：1 passed, 1 failed；失败原因为既有 catalog 要求 `test_` schema，一次性数据库已按 finally 安全销毁。
- 兼容随机 schema 后真实 round-trip：2 passed。
- PostgreSQL 专项最终：38 passed。
- M0R-05R-04 最终非 PostgreSQL API 全量：137 passed, 9 deselected, 1 warning。

## 结论

普通集成测试不再暴露 downgrade 方法。唯一 destructive round-trip 使用本次创建的一次性数据库，downgrade 前验证生命周期与迁移 DDL，结束时经独立确认和 owner/marker 二次核对后销毁精确目标。
