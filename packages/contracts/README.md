# OpenAPI 契约维护

`openapi.json` 是从 FastAPI 运行时路由确定性生成的受控快照，不得手工编辑。

在仓库根目录执行：

```bash
.venv/bin/python scripts/export_openapi.py
```

修改接口、请求模型或响应模型后必须重新导出，并将快照与代码一同提交。提交前可执行：

```bash
.venv/bin/python scripts/export_openapi.py --check
.venv/bin/pytest apps/api/tests/test_openapi_contract.py -q
```

`--check` 不修改文件；快照缺失或与运行时模式不一致时返回非零状态。
