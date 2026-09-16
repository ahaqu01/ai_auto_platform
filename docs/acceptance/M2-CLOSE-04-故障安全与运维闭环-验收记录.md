# M2-CLOSE-04 故障、安全与运维闭环验收记录

> 日期：2026-09-16  
> 当前结论：`ACCEPTED / CLOSED`
> 验收依据：自动化门禁、真实 PostgreSQL、真实阿里云 OSS、Staging 运行证据

## 已取得证据

- 实现提交 `09c03bb` 已推送。
- Ruff 通过；调度专项及 M2-07 回归 `14 passed`。
- Staging 维护服务已部署并达到 `healthy`。
- 真实 OSS 配置下一次常规运行输出 `status=completed`、`failures=0`。
- advisory lock 被另一连接占用时，一次性任务输出 `status=skipped`、`reason=lock_held`。
- 心跳文件存在，健康检查通过。
- AK/Secret 扫描覆盖 API、Web/Nginx、Keycloak、维护任务以及数据库审计/Outbox，结果均为未命中。
- 故障与恢复专项：`27 passed`；覆盖分片签名 500/超时、重复分片、complete 响应丢失、HEAD 瞬时失败、对象缺失、删除失败、孤儿保护、退避和重复 reconcile。
- PostgreSQL 并发完成与 DB 最终提交失败：`2 passed`；只生成一个 Artifact，失败不产生伪成功并可重试恢复。
- 真实 PostgreSQL RLS：`3 passed`；租户 A/B/无租户及非成员隔离通过。
- 全量回归：`309 passed, 1 skipped`；显式真实存储用例单独执行 `1 passed`。
- 真实 OSS + PostgreSQL 联合矩阵覆盖 AVAILABLE/授权下载、非成员、无认证、归档项目、QUARANTINED/DELETING/DELETED、删除退避和 reconcile 幂等。
- OSS 过期签名：新签名 PUT `200`，65 秒后返回 `403`。
- 完整敏感扫描包含签名参数、Authorization/Cookie/Set-Cookie 和内部 upload ID，全部未命中。
- 提交 `3024674` CI run `35085772619` success；提交 `de4992d` CI run `35101720073` success。
- 最新 Staging API/维护服务均 healthy；维护 `failures=0`；Bucket 对象数 0；临时测试数据库与角色已删除。

## 验收标准逐项判定

- A 故障恢复矩阵：通过。
- B 授权与状态矩阵：通过。
- C 调度与可观测性：通过。
- D 敏感信息与日志：通过。
- E 质量、版本与清理门禁：通过。

## 判定

M2-CLOSE-04 验收通过并关闭，允许进入 M2-CLOSE-05。该结论不等于 M2 阶段总签；M2-CLOSE-05 产品范围与阶段治理仍须独立完成。
