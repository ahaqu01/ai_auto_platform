# M0R-05R-04 一次性 downgrade 数据库验收标准

- 关闭发现：`REV01-P1-02`
- 基线：`6e9b29bab5752da94a283808531823bb40141de7`
- 状态上限：`IMPLEMENTED_LOCAL`

## 门禁

1. destructive migration round-trip 每次创建随机命名的独立数据库，不在共享测试库执行 downgrade。
2. 管理员创建数据库并写入本次随机 disposal marker；测试连接验证数据库名、角色、非超级用户、owner、marker 和无其他连接。
3. downgrade 前静态扫描全部迁移，拒绝未经批准的 global DDL、`schema=` 和 schema-qualified DDL。
4. downgrade 与销毁分别要求独立精确确认值。
5. 销毁前管理员再次核对数据库 owner 和 marker，只终止并删除精确随机目标。
6. 安全门禁、真实 round-trip、PostgreSQL 专项和非 PostgreSQL API 回归通过。
