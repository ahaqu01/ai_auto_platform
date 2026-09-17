# M2-REVIEW-02 数据库身份拆分开发文档

日期：2026-09-17；对应问题：P1-SEC-01；分支：`codex/m2-review-remediation`。

## 目标与设计核查

按“设计核查 → 实现 → 隔离 PostgreSQL 验证 → Staging 切换验收”执行。原 Staging API/维护共用超级用户 `platform`，共享 env_file 还暴露管理员凭据，因此同时拆分数据库身份和容器配置；只修改 DATABASE_URL 不满足安全目标。

保留迁移管理员 `platform`。API 使用 `platform_api`，继承现有 `platform_runtime` 租户权限，并获得身份同步所需 users 的 SELECT/INSERT/UPDATE。用户身份表的必要写权限不等于租户业务授权，业务表仍使用 FORCE RLS。维护使用 `platform_maintenance`，不继承 runtime，仅获得 upload_sessions/artifacts 的 SELECT/UPDATE、维护游标的 SELECT/INSERT/UPDATE，以及限定 SYSTEM 审计和四类资产维护 Outbox 事件的 SELECT/INSERT。

两个登录角色均无 SUPERUSER、BYPASSRLS、CREATEDB、CREATEROLE；不能切换到管理员或互相切换。API 被撤销 maintenance state 权限。维护跨租户资产访问是明确授予的必要职责，而非绕过所有 RLS。

## 实现

- `deploy/postgres/02-service-roles.sql`：由迁移管理员执行角色授权和专用 RLS 策略，拒绝已有高权限同名角色；不把角色创建混入业务 Alembic 迁移。
- `scripts/split_staging_service_env.py`：随机独立服务密码，生成六份服务配置和 Compose 路径索引；目录 0700、文件 0600，拒绝覆盖目录，避免意外轮转。
- `deploy/staging/docker-compose.yml`：PostgreSQL、MinIO、Keycloak、迁移、API、维护使用独立 env_file。API/维护无数据库或身份管理员密码；维护无 BFF 客户端密钥。迁移完成退出。
- 项目创建/更新/归档/恢复/关闭、项目成员变更、企业邀请和上传会话过期后的 refresh 显式恢复事务级租户上下文。隔离测试暴露了原超级用户掩盖的项目刷新失败，已修复。
- `scripts/verify_database_identity_split.py`：限定独立数据库名，验证实际权限、身份同步、租户拒绝、上传完成/过期、维护事件和配置隔离；加入 PostgreSQL CI。
- `scripts/verify_staging_database_identities.py`：只读核查运行容器实际数据库身份、禁止权限和环境键，不输出凭据。

实现提交：`d72da41cad4052eefadf3f8c1e2145824f35b63e`。

## 验收标准

1. 两个服务角色均为受限登录；角色提权和相互切换被 PostgreSQL 拒绝。
2. API 无上下文不能读取资产；跨租户 API 请求返回 404；维护不能读 users 或改 organizations。
3. API 身份同步、组织/项目创建、资产上传完成和会话过期刷新成功；维护过期和缺失对象处理写入 SYSTEM 审计/Outbox。
4. API/维护无 POSTGRES_*、MINIO_ROOT_*、Keycloak 管理员配置；维护无 BFF secret；拆分文件权限符合要求。
5. 隔离验证及 CI 成功后归档 Staging 切换；实际登录、真实 OSS 上传/取消/恢复/断线重试/校验/详情/授权下载成功；测试资源清理。
6. 切换前备份数据库、角色、原配置、旧镜像，Demo 不变；不移动历史验收标签，不提前关闭后续 P2/全量复验/复签门禁。

## 部署和回滚

Staging 受控配置：`/home/diffgram/.config/ai-auto-platform/staging-split-20260917/compose.env`，真实值不进入仓库或交付文档。

备份目录：`/home/diffgram/.config/ai-auto-platform/backup-m2-role-split-20260917`，含数据库自定义格式 dump、角色导出、原配置和旧 Compose。目录 0700、文件 0600。旧运行镜像分别标记 `aiap-m2-role-backup:api`、`aiap-m2-role-backup:maintenance`。备份已生成，但未进行破坏性的恢复演练。

迁移已升级到 `20260916_12` 并应用服务角色 SQL。仅重新创建 Staging migrate/API/维护容器，基础设施和 Demo 未重启。Nginx 因缓存旧上游导致首次登录 E2E 502，重载 Staging 代理后重试；此问题不掩盖、不当作权限验证成功。

回滚先在受控临时目录还原旧 Compose，并确保其中相对挂载路径正确指向旧部署目录；使用原配置、旧镜像重新创建 Staging API/维护服务。新增数据库字段可保留。恢复数据库 dump 会覆盖后续数据，必须单独批准；禁止 `down -v`。管理员源配置保留为受限回滚材料，不再注入新运行容器。

## 验收状态

隔离 PostgreSQL 身份和生命周期测试通过；非 PostgreSQL 回归 281 passed、32 deselected，Ruff 与 diff check 通过。GitHub Actions [35172007557](https://github.com/ahaqu01/ai_auto_platform/actions/runs/35172007557) 为 success，baseline/PostgreSQL/security 全通过，包含新增身份隔离集成测试。

Staging 实际身份检查、健康检查和维护首轮无失败已通过。真实 OSS 浏览器重试 `1 passed (4.0m)`，覆盖 100 MiB 暂停恢复、取消、1 KiB 断线重试、1 GiB Multipart、VERIFIED 和授权下载 SHA-256。临时组织、用户和对象已清理，OSS 平台前缀对象数为 0；维护后续一轮成功清理 1 个 Multipart，failures=0。运行态验证提交 `4c81947` 的 CI [35172236228](https://github.com/ahaqu01/ai_auto_platform/actions/runs/35172236228) 也为 success。

结论：`M2-REVIEW-02 ACCEPTED / STAGING SWITCH ACCEPTED`。此任务不代表 M2 全量复验或四方复签完成；Demo 仍待后续批准的统一发布。
