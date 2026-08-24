# M0R-05R-05 完整 PostgreSQL base inventory 验收标准

- 关闭发现：`REV01-P2-03`
- 基线：`391322219078f43944691e6fd5226e66d79bf366`
- 状态上限：`IMPLEMENTED_LOCAL`

## 门禁

1. base inventory 在原有 table/index/constraint/type/sequence/trigger 基础上覆盖 view、materialized view、routine、policy、domain、collation 和显式 relation grant。
2. 每类新增对象都有独立可识别名称，不能只比较对象总数。
3. base allowlist 对所有新增类别显式定义，默认不得隐式忽略。
4. 真实一次性数据库 downgrade 后注入各类残留并证明 inventory 可见。
5. 完整 PostgreSQL 专项、Ruff 和无临时数据库残留检查通过。
