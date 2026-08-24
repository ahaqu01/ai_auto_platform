# M0R-03R-02 无副作用 OpenAPI 导出验收记录

- 关闭发现：`REV01-P2-02`
- 基线：`ca4f80b2d8f4c0dce08b9cdd8595411fe1e5ad53`
- 状态：`IMPLEMENTED_LOCAL`

## 测试证据

- 实现前：2 failed, 5 passed。
- OpenAPI 专项：7 passed。
- `scripts/export_openapi.py --check`：快照 current。
- 非 PostgreSQL API 全量：147 passed, 9 deselected, 1 warning。
- Ruff：通过。

## 结论

导出由 allowlist 子进程完成，调用进程不再覆盖环境或清空 Settings cache。未知应用变量被排除，正常与异常路径均有状态等价测试，身份输入策略保持执行。
