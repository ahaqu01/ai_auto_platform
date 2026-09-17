# M2-REVIEW-03 P2 合同与产品修复验收记录

日期：2026-09-17。结论：`FUNCTIONAL ACCEPTED / P2-SEC-02 OPEN`；不是 M2 复评总签。

## 功能项判定

- P2-BUG-03 签名合同：CLOSED。上传/下载允许 60～900 秒；非法有效期由请求验证返回 422。OpenAPI 导出与 CI 漂移检查通过。
- P2-BUG-04 资产分页：CLOSED。中文加载更多、下一页失败重试、去重、旧响应丢弃通过。第 101 个真实 OSS 资产可以查看详情、授权下载。
- P2-BUG-05 完成幂等：CLOSED。持久化 key/payload hash/响应，冲突 409；同 key 的 checkpoint/最终 DB 提交失败可以恢复；相同与不同 key 并发只发布一个资产；隔离错误仍重放为 409。
- P3-BUG-06：范围/文件 HASHING、UPLOADING、PAUSED、COMPLETING 锁定通过；可恢复失败会话也锁定范围。开始上传按钮不再在 PAUSED 错误可用。
- FAILED 终态恢复：取消前读取状态，已完成/过期/终止任务仅结束本地上下文，不删除资产；活动会话仍取消远端。隔离错误后能够开始新上传。
- P3-SEC-03：M2 产品提示及 ADR 消费边界已整改；未部署扫描器，后续 M3 执行门禁必须另行实现、验证，不把 NOT_REQUIRED 当作 CLEAN。
- P2-SEC-02：OPEN。现有长期 RAM Key 未真实切换到 STS，未收到限期风险批准；策略模板/迁移清单不等于已应用配置。

## 版本与自动验证

`fa74c93` 实现；专项 API `31 passed`、非 PostgreSQL API `295 passed, 32 deselected`；Web `27 passed`，vue-tsc 与 Vite build 成功；Ruff/diff check 通过。

[CI 35179387752](https://github.com/ahaqu01/ai_auto_platform/actions/runs/35179387752) baseline、PostgreSQL、security 全部 success。PostgreSQL 包含同 key/不同 key 并发完成、最终提交失败后原 key 恢复；受限 API 身份生命周期独立脚本也通过。隔离一次性 PostgreSQL `platform_identity_split_test` 只绑定回环地址，测试结束容器已停止自动删除，未操作 Staging/Demo 数据卷。

`52a552d` 新增真实 OSS 101 资产专项，[CI 35179580912](https://github.com/ahaqu01/ai_auto_platform/actions/runs/35179580912) success。

`8979ecb` 终态恢复补丁，Web `28 passed`、build 成功，[CI 35180232766](https://github.com/ahaqu01/ai_auto_platform/actions/runs/35180232766) 全部 success。真实 OSS 浏览器“摘要不符隔离 → 结束任务解锁 → 正常新上传” `1 passed (6.2s)`；新增脚本 `m2-review-03-terminal.spec.ts`。首次终态专项失败是测试 getByLabel 精确标签定位不到元素，改为已存在的 scope select 定位器后通过，未把首轮误记为成功。原始日志 `/tmp/m2-p2-terminal-e2e.log`、重试 `/tmp/m2-p2-terminal-e2e-retry.log` 保留。

## Staging 真实存储验收

环境明确为 `staging`、`http://127.0.0.1:8081`，provider 为 `aliyun_oss`。使用现有受限数据库角色和项目新 OSS Key，没有变更 RAM 授权或撤销其他服务凭据。

Chromium `1 passed (1.3m)`，真实上传并完成 101 个不同 OSS 小对象，不是模拟 API 返回页：

1. 首页 100 行；最旧资产不在首页；加载更多后 101 行、无重复行。
2. 最旧资产详情 VERIFIED，明确未执行恶意文件扫描；经产品下载按钮授权下载，内容逐字节一致。
3. 上传 900 秒签名与真实 PUT 成功，901 秒请求 422。
4. 下载 60/900 秒签名与真实读取成功；901/3600 秒请求 422。
5. 原 key/原清单重放 200、Idempotent-Replayed=true、资产 id 相同；原 key/改清单为 409 IDEMPOTENCY_CONFLICT。

脱敏机器证据：仓库 `docs/evidence/m2-review03-staging-evidence.json`。原始主机日志 `/tmp/m2-p2-staging-e2e.log`；原始认证 trace/视频不提交，避免泄露会话或签名 URL。

## 清理和运行态复核

清理脚本完成 `DELETE 1`，临时 `m1-e2e-p2-contract` 用户 absent。独立核查 Staging artifacts=0、upload_sessions=0、OSS `v1/o/` 平台前缀对象=0。清理过程中有一次前缀残留探测未通过，当时清理进程仍运行；没有重启或抢先删库，等待其完成后重新核查通过。

`verify_staging_database_identities.py` 两角色 PASS；Staging smoke PASS；维护 metrics completed/failures=0。Demo API/Web 未重启，历史验收标签未移动；临时 node_modules 链接已移除，代码工作树归档前 clean。

## 后续门禁

提供实际专用 RAM Role ARN 和可信签发方式，完成自动刷新、过期关闭及真实 STS 验收，或者由项目负责人明确批准限期风险处置；此前 M2-REVIEW-03 整体保持 OPEN。规模化维护公平性、所有合同/安全的全量回归及产品/技术/安全/QA 复签仍属后续门禁，未代签、未合并 main、未建新总验收标签。
