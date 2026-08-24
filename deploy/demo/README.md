# 本地阶段性演示部署

该部署仅用于可信局域网内展示当前阶段成果，不适用于公网或生产环境。REV-01 中尚未关闭的问题仍然有效。

## 启动

在仓库根目录执行：

```bash
docker compose -f deploy/demo/docker-compose.yml up -d --build
docker compose -f deploy/demo/docker-compose.yml ps
DEMO_BASE_URL=http://127.0.0.1:8080 bash scripts/smoke_demo.sh
```

局域网浏览器访问：

- 平台首页：`http://192.168.1.129:8080/`
- API 文档：`http://192.168.1.129:8080/docs`
- 健康检查：`http://192.168.1.129:8080/health/live`

## 日常维护

```bash
# 查看状态
docker compose -f deploy/demo/docker-compose.yml ps

# 查看最近日志
docker compose -f deploy/demo/docker-compose.yml logs --tail=200

# 重启（保留数据）
docker compose -f deploy/demo/docker-compose.yml restart

# 停止（保留数据）
docker compose -f deploy/demo/docker-compose.yml down

# 更新代码后重建
docker compose -f deploy/demo/docker-compose.yml up -d --build
```

不要使用 `down -v`，它会删除演示数据库和对象存储数据。

## 暴露面

只有 Web 网关发布宿主机 `8080` 端口。PostgreSQL、Redis、MinIO、API 仅在 Compose 内部网络通信。本任务不修改路由器、公网防火墙、安全组或 DNS。
