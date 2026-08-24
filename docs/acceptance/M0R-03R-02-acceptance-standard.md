# M0R-03R-02 无副作用 OpenAPI 导出验收标准

- 关闭发现：`REV01-P2-02`
- 基线：`ca4f80b2d8f4c0dce08b9cdd8595411fe1e5ad53`
- 状态上限：`IMPLEMENTED_LOCAL`

## 门禁

1. schema 在仅含系统运行变量与固定 schema 变量的 allowlist 子进程生成。
2. 未知 `APP_*`、宿主部署变量不能影响导出字节。
3. 程序化正常调用前后 `os.environ` 与 Settings cache 等价。
4. 子进程异常路径同样不修改调用进程环境或 cache。
5. 身份输入策略仍在 worker 和父进程结果上执行。
6. 契约快照字节一致，专项、Ruff 和非 PostgreSQL 全量通过。
