# M1-PRE-01 前置健壮性整改验收标准

> Owner：平台工程 / QA
> 状态：CURRENT
> 版本：1.0

1. `validated_public_addresses()` 返回类型准确为 `tuple[str, ...]`，静态检查和测试通过。
2. disposable DB 在管理员连接和 `CREATE DATABASE` 前 fail-fast 校验销毁确认；teardown 前保留二次确认。
3. 缺失或错误销毁确认不会创建任何数据库，并有顺序门禁测试。
4. CI 对同 workflow/ref 启用 concurrency 和 cancel-in-progress。
5. Python pip、npm、Go module/build 缓存均配置明确依赖路径。
6. 文档检查器仅校验链接、元数据、状态枚举和权威顺序，不硬编码历史里程碑名称。
7. Ruff、针对性测试、完整 CI、PostgreSQL 集成、文档、diff 和敏感信息扫描通过。
