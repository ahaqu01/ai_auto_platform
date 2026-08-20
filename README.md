# AI Auto Platform

多模型、多芯片 AI 工程化与交付平台。第一阶段目标：

`身份 → 企业/项目 → OSS 资产 → Job/Attempt/Lease → 本地 Agent → 日志/结果 → 审计`

## Repository

- `apps/api`: FastAPI 模块化单体
- `apps/workflow-worker`: Temporal Worker
- `apps/web`: Vue 3 Web
- `apps/agent`: Go Agent
- `packages/contracts`: OpenAPI 契约
- `packages/schemas`: Job/Event JSON Schema
- `deploy/compose`: 本地依赖
- `docs`: 设计与运行手册

## API quick start

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e 'apps/api[dev]'
uvicorn platform_api.main:app --reload --port 8000
pytest apps/api/tests
```

健康检查：`GET http://127.0.0.1:8000/health/live`。

