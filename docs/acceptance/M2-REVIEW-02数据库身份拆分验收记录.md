# M2-REVIEW-02 数据库身份拆分验收记录

日期：2026-09-17。范围仅数据库身份与 Staging 切换，不代替后续 P2、规模化全量回归或四方复签。

## 已验证证据

- 实现提交 `d72da41cad4052eefadf3f8c1e2145824f35b63e`；运行态验证脚本提交 `4c81947`。
- 隔离环境：一次性 PostgreSQL 16.4，数据库 `platform_identity_split_test`，仅绑定 `127.0.0.1:55433`。迁移 0～12、角色 SQL 和配置生成成功。
- 权限负向验证：API/维护无超级用户、BYPASSRLS、建库、建角色权限；禁止切换管理员；API 禁止切换维护身份和读取维护游标；维护禁止读 users、修改 organizations。
- 生命周期：受限 API 组织/项目创建 201，上传完成 201，外部用户读取资产 404，无上下文资产数为 0；过期会话刷新 EXPIRED。受限维护处理过期与缺失对象，SYSTEM 审计及资产 Outbox 均正确。
- 配置隔离：API/维护无数据库、MinIO、Keycloak 管理员环境键；维护无 BFF secret；实际目录 0700、全部配置文件 0600。
- 回归：`281 passed, 32 deselected`；Ruff、`git diff --check` 通过。第一次回归因复用主工作区 editable 安装而加载旧维护代码，显式指定 `PYTHONPATH=apps/api/src` 后修正；新上下文恢复涉及的 FakeSession 测试桩也同步更新，不降低门禁。
- CI：[35172007557](https://github.com/ahaqu01/ai_auto_platform/actions/runs/35172007557) 对实现提交 completed/success，baseline、PostgreSQL、security 均 success；PostgreSQL 作业包含新增身份隔离生命周期测试。
- Staging 备份：数据库 dump、roles-only、原配置、Compose 和旧 API/维护镜像已归档；恢复未实际演练。
- Staging migration exit 0，升级到 `20260916_12` 并应用专用角色权限；API 与维护容器 healthy，维护首轮 `failures=0`。
- 运行态验证脚本对 `platform_api`、`platform_maintenance` 均 PASS，包含两角色相互切换拒绝、管理员提权拒绝、环境隔离及 API 无租户上下文查询。
- `bash scripts/smoke_staging.sh` PASS。

## 真实 OSS 浏览器验收

执行现有 `scripts/run_m2_close03_e2e.sh`，明确 `E2E_ENVIRONMENT=staging` 和 `http://127.0.0.1:8081`。首次失败为 Nginx 旧上游地址缓存造成登录 502；重载 Staging Nginx 后重试。不能把首次失败删除或视为通过。

重试结果：`1 passed (4.0m)`，覆盖 100 MiB 暂停恢复、取消、1 KiB 故障重试、1 GiB Multipart、VERIFIED 详情及下载 SHA-256。清理日志 `DELETE 1`、临时 E2E 用户 absent；独立只读检查 OSS `v1/o/` 前缀对象数为 0。维护第二轮 Multipart aborted=1、failures=0；运行身份和 smoke 再次 PASS。

运行态验证脚本提交 `4c81947` 的 CI [35172236228](https://github.com/ahaqu01/ai_auto_platform/actions/runs/35172236228) completed/success。结论：`M2-REVIEW-02 ACCEPTED / STAGING SWITCH ACCEPTED`。

临时隔离 PostgreSQL 容器已停止并自动删除；其一次性数据不可恢复，Staging/Demo 数据未删除。浏览器原始日志位于受控主机 `/tmp/m2-role-staging-e2e-retry.log`，截图位于发布工作树 `apps/web/test-results`；原始 trace/视频不提交仓库，防止认证信息外泄。

## 边界

隔离权限与维护生命周期测试使用存储测试替身，真实 OSS 浏览器 E2E 另行验证 API 业务。没有把测试替身称为真实 OSS 维护故障矩阵。Demo 服务未重启、未切换；历史 `m2-accepted` 不变。角色专家或真实人员四方复签不在本记录中代签。
