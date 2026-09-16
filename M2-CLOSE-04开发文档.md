# M2-CLOSE-04 开发文档

> 工作包：故障、安全与运维闭环  
> 启动日期：2026-09-16  
> 当前状态：`ACCEPTED / CLOSED`
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
- `3024674`：补齐分片签名故障、完成响应丢失、HEAD 瞬时失败、清理退避/幂等和真实 PostgreSQL RLS 矩阵；CI run `35085772619` success。
- `de4992d`：修复并发完成序列化、提交后租户上下文恢复，加入数据库最终提交失败和真实 OSS+PostgreSQL 联合矩阵；CI run `35101720073` success。

以上提交均已推送到 `origin/codex/m2-assets-storage`，对应 CI 均成功。

## 4. 启动验证记录

- Ruff：通过。
- 调度专项及 M2-07 回归：`14 passed in 2.94s`。
- 非 PostgreSQL API 测试：`273 passed`；另有 28 项 PostgreSQL 用例因未提供破坏性测试专用确认变量而在安全门处拒绝执行，不计为业务失败，需在隔离测试库/CI 中复验。
- Staging `artifact-maintenance`：`healthy`。
- 真实 OSS 配置下单轮维护：完成，`failures=0`。
- 互斥验证：外部持有 advisory lock 时，`--once` 返回 `status=skipped, reason=lock_held`。
- 心跳：容器内心跳文件存在。
- 凭证扫描：API、Web/Nginx、Keycloak、维护服务日志及 PostgreSQL 审计/Outbox 数据均未命中新 OSS AK/Secret。

## 5. 最终复验证据

- 全量 API/隔离 PostgreSQL 回归：`309 passed, 1 skipped`；skip 为必须显式授权的真实 OSS 用例，已单独执行并 `1 passed`。
- 真实 PostgreSQL + 真实阿里云 OSS：AVAILABLE/下载逐字节一致、非成员、无认证、归档、QUARANTINED、DELETING、DELETED、删除失败退避及重复 reconcile 全部通过。
- PostgreSQL 并发 complete 只发布一个 Artifact；响应分别为 201/200，真实远端 complete 仅调用一次。
- 最终数据库提交失败后保持 COMPLETING、无伪 Artifact，重试恢复为 AVAILABLE。
- 真实 OSS 签名：新签名 PUT `200`，65 秒后同一 URL `403`；Multipart 已清理。
- 敏感扫描覆盖 AK/Secret、完整签名查询参数、Authorization、Cookie、Set-Cookie 和内部 upload ID；API、Web/Nginx、Keycloak、维护服务、审计与 Outbox 均未命中。
- 最新 Staging API 与维护服务均 `healthy`；维护单轮 `failures=0`；Bucket `v1/o/` 对象数为 0。
- 临时 `platform_test` 数据库和角色均已删除，复核计数为 0/0。

## 6. 当前结论

`M2-CLOSE-04 = ACCEPTED/CLOSED`。故障、安全、真实租户隔离、生产调度和清理证据均已满足验收标准，允许启动 `M2-CLOSE-05`；M2 总签仍须等待 M2-CLOSE-05。
