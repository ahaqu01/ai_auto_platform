# Staging 隔离环境

仅用于受控内网验收，不代表生产部署。Demo 数据卷及服务不在本流程范围。

## 数据库身份

- `platform`：仅 PostgreSQL 与迁移容器持有管理员凭证。
- `platform_api`：受限登录，继承 `platform_runtime`；租户数据受 FORCE RLS 约束。
- `platform_maintenance`：受限登录，只允许资产维护所需表和 SYSTEM 事件，不继承 API 身份。

先备份数据库、角色和原配置，执行 Alembic 升级与 `deploy/postgres/02-service-roles.sql`，然后在管理员可信执行环境运行：

```bash
APP_ENV=local PYTHONPATH=apps/api/src .venv/bin/python scripts/split_staging_service_env.py \
  --source-env /home/diffgram/.config/ai-auto-platform/staging.env \
  --output-dir /home/diffgram/.config/ai-auto-platform/staging-split
docker compose --env-file /home/diffgram/.config/ai-auto-platform/staging-split/compose.env \
  -f deploy/staging/docker-compose.yml config --quiet
docker compose --env-file /home/diffgram/.config/ai-auto-platform/staging-split/compose.env \
  -f deploy/staging/docker-compose.yml up -d --build
```

生成目录权限为 0700，六份服务配置和路径索引为 0600；不得提交真实配置。脚本拒绝覆盖已有目录，避免隐式轮转。源配置仍需保留并限制权限，作为回滚材料；不要将它注入 API 或维护容器。禁止打印完整 Compose 配置或容器环境。

API/维护配置不包含 PostgreSQL、Keycloak 管理员凭证。维护服务也不持有 BFF 客户端密钥。迁移容器完成后退出；管理员配置仅授予部署操作人员。

## 验收和回滚

执行 `scripts/verify_database_identity_split.py` 时必须使用独立数据库 `platform_identity_split_test`，不得使用 Staging/Demo 数据库。再执行 `STAGING_BASE_URL=http://127.0.0.1:8081 bash scripts/smoke_staging.sh` 和 Staging 登录、资产真实存储 E2E。

验证运行身份、禁止角色切换、跨租户隔离、SYSTEM 事件及容器环境键；健康检查不能代替业务验收。回滚使用备份的旧 Compose 文件、原配置与旧镜像，仅替换 Staging API/维护服务；不要 `down -v`。新增字段可保留，数据库恢复必须另行评估数据损失。
