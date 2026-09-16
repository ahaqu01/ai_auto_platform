# M2-CLOSE-04 开发文档

> 工作包：故障、安全与运维闭环  
> 启动日期：2026-09-16  
> 当前状态：`IN PROGRESS`  
> 分支：`codex/m2-assets-storage`

## 1. 目标与范围

M2-CLOSE-04 用于关闭 M2 专家评审中关于故障恢复、真实权限隔离、敏感信息泄漏和 M2-07 生产调度的阻断项。该工作包不改变 M2 已冻结的对象 Key、上传会话、资产状态机和租户授权语义。

本次启动首先交付生产可运行的资产维护调度入口，包含单实例互斥、防重入、单轮超时、结构化指标、失败告警、健康心跳、参数边界和 Staging 编排。其余故障注入与真实数据库/存储矩阵按验收标准继续执行。

## 2. 已实现内容

- 新增 `platform_api.modules.artifact.maintenance_runner`，支持常驻循环和 `--once` 验证模式。
- 使用 PostgreSQL advisory lock 保证多个调度副本不会同时清理或对账。
- 每轮维护受独立超时保护；无论成功、异常或超时均释放锁。
- 输出 JSON 结构化的完成、跳过、失败和告警事件，不输出对象凭证或预签名 URL。
- 维护成功后更新心跳文件，Docker 健康检查按调度周期判断新鲜度。
- 新增调度周期、超时、批量、孤儿保护窗口、告警阈值和心跳路径配置边界。
- Staging 新增独立 `artifact-maintenance` 服务，并复用 API 的受控环境文件。

## 3. 版本记录

- `47a80c6`：按批准的范围变更关闭 M2-CLOSE-03，并开放 M2-CLOSE-04。
- `09c03bb`：实现故障安全的资产维护生产调度入口、测试和 Staging 编排。

以上提交均已推送到 `origin/codex/m2-assets-storage`。`09c03bb` 的远端 CI 结论需在工作流完成后写入最终验收记录。

## 4. 启动验证记录

- Ruff：通过。
- 调度专项及 M2-07 回归：`14 passed in 2.94s`。
- 非 PostgreSQL API 测试：`273 passed`；另有 28 项 PostgreSQL 用例因未提供破坏性测试专用确认变量而在安全门处拒绝执行，不计为业务失败，需在隔离测试库/CI 中复验。
- Staging `artifact-maintenance`：`healthy`。
- 真实 OSS 配置下单轮维护：完成，`failures=0`。
- 互斥验证：外部持有 advisory lock 时，`--once` 返回 `status=skipped, reason=lock_held`。
- 心跳：容器内心跳文件存在。
- 凭证扫描：API、Web/Nginx、Keycloak、维护服务日志及 PostgreSQL 审计/Outbox 数据均未命中新 OSS AK/Secret。

## 5. 尚未完成

- 补齐并执行完整故障注入矩阵：分片 500/超时、签名过期、重复分片、并发 complete、响应丢失、数据库提交失败、HEAD 瞬时失败、对象缺失和删除失败。
- 在真实 PostgreSQL 与真实对象存储链路复验租户 A/B/无租户、非成员、归档项目及 QUARANTINED/DELETING/DELETED。
- 重复运行 reconcile，记录幂等、退避、孤儿保护窗口和真实清理结果。
- 扫描完整预签名 URL、Authorization/Cookie 等敏感请求头，而不只 AK/Secret。
- 等待实现提交 CI 成功，并形成最终验收结论。

## 6. 当前结论

`M2-CLOSE-03 = ACCEPTED/CLOSED`；`M2-CLOSE-04 = STARTED/IN PROGRESS`。生产调度缺口已实现并在 Staging 实跑，但完整故障与真实隔离矩阵尚未全部完成，因此本工作包当前不得标记 `ACCEPTED`，M2 也不得总签。
