# M2-REVIEW-03 P2 合同与产品修复开发文档

日期：2026-09-17；分支：`codex/m2-review-remediation`。

## 范围和取舍

关闭 P2-BUG-03/04/05，顺带修复 P3-BUG-06 的范围锁定和 P3-SEC-03 的扫描边界提示。P2-SEC-02 长期 RAM Key 不能由功能测试关闭，单列 STS 迁移条件，不伪造云配置或风险批准。不进入下一道全量回归、四方复签、main 合并和新验收标签门禁；Demo 不变。

## 实现

### 签名合同

API 上传与下载签名允许 60～900 秒，默认分别为 900/600，与现有 Gateway 上限相容。旧 3600 秒不是被实际 Gateway 支持的能力，因此收紧请求/OpenAPI，而不扩大签名寿命。59、901、3600 秒在 Pydantic 层返回 422，不触发远程 Multipart 或下载签名，不再误映射成 503。

受控 OpenAPI 已重新导出，M2-04/06 开发文档与标准更新；旧验收记录作为历史快照加注修订，不删除旧证据。

### 完成幂等

复用通用幂等表，actor + `upload_session.complete:<全局唯一 upload UUID>` + key 绑定规范请求 hash，route_key 不超过数据库 160 字符约束。同 key 不同清单返回 409 IDEMPOTENCY_CONFLICT。PROCESSING 与 COMPLETING checkpoint 同时持久化；只在已取得上传会话行锁时允许恢复 PROCESSING，其他命令仍默认拒绝重入。

发布资产、审计/Outbox、完整幂等响应同事务提交。首次成功 201、同 key 成功重放 200；不同 key 的已完成资源请求必须仍符合登记清单，并记录结果。SIZE/CHECKSUM 隔离错误 409 持久化并重放，不在重试时变成成功。外部失败或最终 DB 提交失败可用同 key 恢复，不重复发布。Web 同一任务在内存中保留 completion key，重试不生成新 key。

保持原有重新持锁串行验证机制；文档不再错误声称 completion 全程不持锁访问网络，不新增异步架构。

### 产品界面

资产列表保存 next_cursor，提供中文“加载更多”；失败保留已加载行和游标、可重试，重复行按 id 去重。切换项目后丢弃旧列表/详情响应，不能把另一项目旧页写入当前列表。已完成和恢复完成都会刷新资产。

HASHING/UPLOADING/PAUSED/COMPLETING 期间锁定组织、项目和文件；可恢复的 FAILED 会话也锁定范围，先取消再开始新任务。同步 Web 扫描状态枚举为后端实际值 NOT_REQUIRED/PENDING/CLEAN/BLOCKED；显示“未执行恶意文件扫描”和“完整性校验不等于恶意文件扫描”。ADR 明确 AVAILABLE 不是训练、解压、设备执行的充分条件，M3 消费者须执行独立内容安全门禁；尚未宣称部署了病毒扫描器。

终态恢复补丁：取消先读取服务端状态；COMPLETED/ABORTED/EXPIRED/FAILED 只结束本地任务，活动会话仍正常取消远端。已生成的资产不因此被删除，避免隔离错误后无法解除 FAILED 范围锁。

## 验收标准

1. 上传/下载 59/60/900/901/3600 秒边界、OpenAPI 漂移检查通过。
2. 同 key 重放、payload 冲突、checkpoint 故障恢复、最终 DB 提交失败、相同/不同 key 并发完成只发布一个资产；隔离错误重放保持 409。
3. 第 101 条资产能加载、查看详情、授权下载；下一页失败可重试、去重、项目切换旧响应不污染；任务全阶段范围锁定。
4. Staging 以受限数据库角色和真实 OSS 验证三个 P2 功能项，测试资源清理；Demo 和历史验收标签不变。
5. 长期 Key 安全项需要真实 STS/RAM Role 切换，或负责人明确批准限期风险处置；没有批准不得将本门禁全部 ACCEPTED。

## 版本及证据

- `fa74c93`：合同、幂等、分页、范围和扫描提示实现；专项 API 31 passed，API 非 PostgreSQL 295 passed/32 deselected，Web 27 passed、构建通过。
- CI [35179387752](https://github.com/ahaqu01/ai_auto_platform/actions/runs/35179387752)：baseline、PostgreSQL、security success，包含新增同 key 并发/提交失败恢复测试和受限身份生命周期。
- `52a552d`：真实 OSS 101 资产产品/合同验收脚本；CI [35179580912](https://github.com/ahaqu01/ai_auto_platform/actions/runs/35179580912) success。
- `8979ecb`：FAILED 终态任务结束修复；Web 28 passed/build 成功，CI [35180232766](https://github.com/ahaqu01/ai_auto_platform/actions/runs/35180232766) success。真实 OSS 浏览器“隔离失败 → 结束任务 → 再上传” `1 passed (6.2s)`；临时资源清理，平台前缀对象、资产和会话数再核查为 0。
- Staging 专项 Chromium `1 passed (1.3m)`：101 个真实 OSS 小对象，不是模拟列表；最旧资产在第 101 行加载后可查看 VERIFIED、下载字节一致；60/900 秒真实下载成功、901/3600 秒 422；同 key 重放和不同清单冲突成功。
- 切换前数据库快照：`/home/diffgram/.config/ai-auto-platform/backup-m2-p2-20260917/staging.dump`，目录 0700、文件 0600。旧受限运行镜像 `aiap-m2-p2-backup:api/maintenance/web` 保留；原数据库身份和外部配置没有变化。

## 当前结论

`FUNCTIONAL FIXES VERIFIED / SECURITY ITEM OPEN`。三个 P2 功能项及关联 P3 产品项可按专项证据关闭；长期 Key 的真实 STS 迁移仍待 ARN/签发方式与刷新验收。后续全量复验、复签未完成，不能称为 M2 复评全部关闭。

详见同名验收记录和《M2-REVIEW-03-OSS-STS迁移与风险处置清单》。
