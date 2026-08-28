# Staging 工程基线

> Owner：交付负责人
> 状态：M1 身份化可信局域网集成环境

该 Compose 工程与 Demo 使用独立的 PostgreSQL、Redis、MinIO 和 Keycloak 数据卷，支持 M1 的 Keycloak Authorization Code、BFF 会话、Web、API 与租户授权验收。

环境密钥必须写入仓库外文件 `/home/diffgram/.config/ai-auto-platform/staging.env`，权限为 `0600`；禁止提交真实值。首次从旧 Staging 数据卷升级时，应确认受限角色 `platform_runtime` 已按 `deploy/postgres/01-runtime-role.sql` 创建并授权给数据库 owner。

## 启动

```bash
STAGING_ENV_FILE=/home/diffgram/.config/ai-auto-platform/staging.env \
docker compose --env-file /home/diffgram/.config/ai-auto-platform/staging.env \
  -f deploy/staging/docker-compose.yml up -d --build
```

入口默认为 `http://127.0.0.1:8081/`。当前入口仅用于服务器本机或 SSH 隧道内的可信局域网验收，因尚未配置外部 TLS/DNS，环境使用 `APP_ENV=local` 的 HTTP 校验语义。不得将该入口作为公网生产部署。

## 验收

```bash
STAGING_BASE_URL=http://127.0.0.1:8081 bash scripts/smoke_staging.sh

E2E_ENVIRONMENT=staging E2E_USERNAME=m1-e2e-staging \
E2E_EMAIL=m1-e2e@example.test E2E_PASSWORD='<ephemeral>' \
bash scripts/manage_demo_e2e_user.sh create

E2E_USERNAME=m1-e2e-staging E2E_PASSWORD='<ephemeral>' \
E2E_BASE_URL=http://127.0.0.1:8081 npm --prefix apps/web run test:e2e

E2E_ENVIRONMENT=staging E2E_USERNAME=m1-e2e-staging \
bash scripts/manage_demo_e2e_user.sh delete
```

E2E 用户必须以 `m1-e2e` 为前缀，并在验收后删除。不要使用 `docker compose down -v`，否则会删除 Staging 数据卷。
