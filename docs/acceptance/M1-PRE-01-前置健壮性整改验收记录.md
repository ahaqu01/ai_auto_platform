# M1-PRE-01 前置健壮性整改验收记录

> Owner：平台工程 / QA
> 日期：2026-08-26
> 状态：IMPLEMENTED_LOCAL

## 版本与范围

- 前置：`53217d3566770de9a74b0e25c5631f2f8cb9d43e`
- 结果：本记录所在提交，标签 `m1-pre-01-hardening-implemented`

## 红灯与绿灯

- 红灯：返回类型提示为 `str`；destroy confirmation 位于 `CREATE DATABASE` 后，2 failed。
- 绿灯：类型改为 `tuple[str, ...]`；destroy confirmation 在管理员连接/建库前 fail-fast，teardown 保留二次确认。
- 针对性安全测试：31 passed。

## 完整验收

- Ruff：通过。
- 非 PostgreSQL API：152 passed，10 deselected；仅保留已登记 TestClient 上游警告。
- PostgreSQL：39 passed，包含 disposable downgrade，临时容器已清理。
- Web：3 passed，构建通过；npm audit 0 vulnerabilities。
- Go vet/race、OpenAPI、部署契约、文档结构检查：通过。
- CI：配置 concurrency/cancel-in-progress、pip/npm/Go 缓存和明确依赖路径。
- `check_docs.py`：不再硬编码历史里程碑，只校验链接、元数据、状态定义和权威执行顺序。

## 结论

M1-PRE-01 达到 `IMPLEMENTED_LOCAL`，两个 P3 已关闭，可进入 M1-02。
