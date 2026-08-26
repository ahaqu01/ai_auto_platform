# Staging 工程基线

> Owner：交付负责人
> 状态：IMPLEMENTED_LOCAL

本目录提供与 demo 数据隔离的服务器 Staging 工程基线。环境密钥必须写入仓库外文件 `/home/diffgram/.config/ai-auto-platform/staging.env`，禁止提交真实值。

```bash
docker compose --env-file /home/diffgram/.config/ai-auto-platform/staging.env \
  -f deploy/staging/docker-compose.yml up -d --build
```

入口默认为 `http://192.168.1.129:8081/`。当前身份业务尚未实施，因此该环境只验证 M0-R 工程基线；不能作为真实 Keycloak/TLS 或产品 `ACCEPTED` 证据。
